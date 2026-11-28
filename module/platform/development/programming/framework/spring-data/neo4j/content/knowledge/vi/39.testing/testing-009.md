# Kiểm thử quan hệ động, thuộc tính quan hệ và nhiều relationship cùng cặp node

Trong graph Neo4j, hai node có thể được nối bởi nhiều relationship. Các relationship đó có thể khác type, hoặc cùng type nhưng mang thuộc tính khác nhau. Spring Data Neo4j (SDN) còn hỗ trợ dynamic relationships, trong đó relationship type được lấy từ key của một `Map` thay vì cố định bằng `@Relationship`.

Những cấu trúc này cần được kiểm thử ở database thật tương thích với phiên bản Neo4j đang dùng. Unit test chỉ kiểm tra object Java không thể xác nhận SDN đã ghi đúng relationship type, giữ đủ relationship properties hay hydrate đúng nhiều cạnh cùng cặp node. Một integration test tốt cần ghi graph, đọc lại bằng repository, rồi đối chiếu trực tiếp cấu trúc graph bằng Cypher.

## 1. Ba trường hợp cần phân biệt

Trước khi viết test, xác định loại relationship mà domain model cần biểu diễn:

| Trường hợp | Ví dụ graph | Cách ánh xạ SDN |
|---|---|---|
| Dynamic relationship type | Một Person `MENTORS` một Person khác; cùng node có thể có type `COLLABORATES_WITH` | `Map<String, Person>` hoặc `Map<Enum, Person>`; key là relationship type |
| Relationship có thuộc tính | `CONNECTED_TO {channel: 'EMAIL', status: 'ACTIVE'}` | `@RelationshipProperties`, `@TargetNode` và `@RelationshipId` |
| Nhiều relationship cùng type giữa cùng hai node | Hai cạnh `CONNECTED_TO` từ A đến B, một cạnh qua EMAIL và một cạnh qua CHAT | Collection các relationship-properties object, mỗi cạnh có ID nội bộ riêng |

Dynamic relationship type và relationship properties là hai cơ chế khác nhau. Dynamic relationship map chọn type bằng key và trỏ đến node đích. Khi cần các thuộc tính riêng trên từng cạnh, dùng `@RelationshipProperties` với relationship type được khai báo rõ ràng. Không nên biến một map dynamic thành nơi chứa metadata cạnh mà SDN không hỗ trợ.

## 2. Mô hình domain cho bài kiểm thử

Ví dụ dùng `Person` làm node. Một người có thể có nhiều kết nối `CONNECTED_TO`; mỗi kết nối mang `channel` và `status`. Ngoài ra, người đó có hai dynamic relationship type như `MENTORS` và `COLLABORATES_WITH`.

### Node Person

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(type = "CONNECTED_TO", direction = Direction.OUTGOING)
    private List<Connection> connections = new ArrayList<>();

    // Key của Map là relationship type động; không đặt @Relationship trên field này.
    private Map<String, Person> dynamicRelationships = new HashMap<>();

    protected Person() {
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public List<Connection> getConnections() { return connections; }
    public Map<String, Person> getDynamicRelationships() { return dynamicRelationships; }

    public void addConnection(Connection connection) {
        connections.add(connection);
    }

    public void addDynamicRelationship(String type, Person target) {
        dynamicRelationships.put(type, target);
    }
}
```

SDN hỗ trợ dynamic relationships qua `Map<String, AnnotatedDomainClass>` hoặc `Map<Enum, AnnotatedDomainClass>`. Key được dùng làm relationship type, vì vậy không cấu hình `@Relationship(type = ...)` trên thuộc tính map. Ví dụ dùng `String` để các type có thể được cung cấp từ domain model; nếu tập type cố định, enum giúp hạn chế lỗi chính tả.

Map trên biểu diễn một node đích cho mỗi key. Nếu một relationship type cần nối đến nhiều node, hãy dùng collection relationship có type tĩnh hoặc một mô hình domain khác phù hợp, thay vì giả định map này tự biểu diễn danh sách đích.

### Relationship properties Connection

```java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Connection {

    @RelationshipId
    private Long id;

    private String channel;
    private String status;

    @TargetNode
    private Person target;

    protected Connection() {
    }

    public Connection(Person target, String channel, String status) {
        this.target = target;
        this.channel = channel;
        this.status = status;
    }

    public Long getId() { return id; }
    public Person getTarget() { return target; }
    public String getChannel() { return channel; }
    public String getStatus() { return status; }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

`@RelationshipProperties` đánh dấu class mô tả dữ liệu của cạnh. Class cần đúng một field `@TargetNode` để xác định node ở đầu kia và một field `@RelationshipId` để SDN nhận diện relationship nội bộ khi ghi. ID này do SDN/Neo4j quản lý; không dùng nó làm mã nghiệp vụ hoặc tự gán giá trị.

### Repository

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {
    Optional<Person> findOneByName(String name);
}
```

## 3. Dựng Neo4j cho integration test

`@DataNeo4jTest` là test slice giúp cấu hình mapping context, repository, template, client và transaction manager của SDN. Annotation này không tự cung cấp database; test cần kết nối đến Neo4j Testcontainers hoặc Neo4j Test Harness.

Ví dụ dùng Testcontainers và `@DynamicPropertySource`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@DataNeo4jTest
@Testcontainers
class RelationshipMappingTest {

    @Container
    static final Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5")
                    .withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
    }

    @Autowired
    PersonRepository people;

    @Autowired
    Neo4jClient neo4jClient;
}
```

Với Spring Boot 4, `@DataNeo4jTest` thuộc package `org.springframework.boot.data.neo4j.test.autoconfigure` và module test Neo4j tương ứng. Với Spring Boot 3.x, package thường dùng là `org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest`, được cung cấp qua `spring-boot-starter-test`. Hãy dùng đúng package và dependency theo major version của ứng dụng.

Pin image Neo4j vào phiên bản phù hợp với SDN và môi trường production thay vì để tag trôi trong pipeline CI. Container giúp test chạy trên database thực, kiểm tra mapping và Cypher thay vì chỉ kiểm tra mock.

## 4. Kiểm thử ghi và đọc lại nhiều relationship cùng cặp node

Các method test tiếp theo được đặt bên trong class `RelationshipMappingTest` ở mục cấu hình. Test đầu tiên tạo một node nguồn và một node đích. Sau đó gắn hai relationship cùng type `CONNECTED_TO` từ nguồn đến cùng node đích, nhưng mỗi cạnh có `channel` và `status` khác nhau.

```java
@Test
void savesAndReloadsParallelRelationshipsWithDifferentProperties() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");

    source.addConnection(new Connection(target, "EMAIL", "ACTIVE"));
    source.addConnection(new Connection(target, "CHAT", "PENDING"));

    Person saved = people.save(source);
    Person reloaded = people.findById(saved.getId()).orElseThrow();

    assertThat(reloaded.getConnections())
            .hasSize(2)
            .extracting(Connection::getChannel)
            .containsExactlyInAnyOrder("EMAIL", "CHAT");

    assertThat(reloaded.getConnections())
            .extracting(Connection::getStatus)
            .containsExactlyInAnyOrder("ACTIVE", "PENDING");

    assertThat(reloaded.getConnections())
            .extracting(Connection::getId)
            .doesNotContainNull()
            .doesNotHaveDuplicates();
}
```

Điểm cần xác nhận không chỉ là collection có hai phần tử. Test còn phải xác nhận hai relationship có ID nội bộ khác nhau và giữ đúng thuộc tính của từng cạnh. Nếu mapping chỉ còn một cạnh, hoặc cả hai cạnh có cùng metadata, lỗi có thể nằm ở cách model collection hoặc identity relationship.

### Đối chiếu trực tiếp graph bằng Cypher

Repository round-trip kiểm tra cách SDN hydrate object. Để xác nhận database thật có hai cạnh, dùng `Neo4jClient` hoặc `Driver` đọc trực tiếp:

```java
@Test
void graphContainsTwoConnectedToEdges() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");
    source.addConnection(new Connection(target, "EMAIL", "ACTIVE"));
    source.addConnection(new Connection(target, "CHAT", "PENDING"));
    people.save(source);

    Long count = neo4jClient.query("""
            MATCH (source:Person {name: $source})
                  -[relationship:CONNECTED_TO]->
                  (target:Person {name: $target})
            RETURN count(relationship) AS total
            """)
            .bind("source").to("source")
            .bind("target").to("target")
            .fetchAs(Long.class)
            .one()
            .orElseThrow();

    assertThat(count).isEqualTo(2L);
}
```

Đặt hai test trong cùng class hoặc dùng fixture chung để tạo dữ liệu trước khi query. Khi dùng test slice imperative, các thao tác trong test mặc định nằm trong transaction test và được rollback khi test kết thúc.

## 5. Kiểm thử dynamic relationship type

Dynamic relationships dùng key của map làm type. Trong ví dụ, cùng một `source` có hai relationship type khác nhau cùng trỏ đến `target`:

```java
@Test
void savesAndReloadsDynamicRelationshipTypes() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");

    source.addDynamicRelationship("MENTORS", target);
    source.addDynamicRelationship("COLLABORATES_WITH", target);

    Person saved = people.save(source);
    Person reloaded = people.findById(saved.getId()).orElseThrow();

    assertThat(reloaded.getDynamicRelationships())
            .containsKeys("MENTORS", "COLLABORATES_WITH");
    assertThat(reloaded.getDynamicRelationships().get("MENTORS").getId())
            .isEqualTo(target.getId());
    assertThat(reloaded.getDynamicRelationships().get("COLLABORATES_WITH").getId())
            .isEqualTo(target.getId());
}
```

Để kiểm tra type thực tế trong database, truy vấn các relationship từ `source`:

```java
@Test
void dynamicMapKeysBecomeRelationshipTypes() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");
    source.addDynamicRelationship("MENTORS", target);
    source.addDynamicRelationship("COLLABORATES_WITH", target);
    people.save(source);

    List<String> types = neo4jClient.query("""
            MATCH (:Person {name: $source})-[relationship]->(:Person {name: $target})
            RETURN DISTINCT type(relationship) AS relationshipType
            ORDER BY relationshipType
            """)
            .bind("source").to("source")
            .bind("target").to("target")
            .fetchAs(String.class)
            .all();

    assertThat(types).containsExactly("COLLABORATES_WITH", "MENTORS");
}
```

Hai test này kiểm tra hai chiều: map được hydrate với đúng key, và key thực sự được ghi thành relationship type trong graph. Chỉ kiểm tra map sau khi save chưa đủ nếu test không đọc lại từ database.

## 6. Kiểm thử đồng thời dynamic relationships và relationship properties

Một node có thể có cả dynamic relationship map và collection relationship-properties. Cần kiểm tra chúng không ghi đè lẫn nhau và mỗi cơ chế giữ đúng dữ liệu:

```java
@Test
void keepsDynamicTypesAndParallelRelationshipPropertiesTogether() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");

    source.addConnection(new Connection(target, "EMAIL", "ACTIVE"));
    source.addConnection(new Connection(target, "CHAT", "PENDING"));
    source.addDynamicRelationship("MENTORS", target);
    source.addDynamicRelationship("COLLABORATES_WITH", target);

    Person saved = people.save(source);
    Person reloaded = people.findById(saved.getId()).orElseThrow();

    assertThat(reloaded.getConnections()).hasSize(2);
    assertThat(reloaded.getDynamicRelationships())
            .containsKeys("MENTORS", "COLLABORATES_WITH");
}
```

Sau khi hydrate, có thể kiểm tra tổng số relationship và phân loại theo type bằng một truy vấn Cypher độc lập. Điều này giúp phát hiện trường hợp một collection được ghi đúng nhưng dynamic map làm mất hoặc thay đổi một phần graph.

## 7. Kiểm tra cập nhật và xóa relationship có chọn lọc

Relationship có thuộc tính thường thay đổi theo nghiệp vụ. Ví dụ, trạng thái kết nối chuyển từ `PENDING` sang `ACTIVE`. Khi cập nhật entity, hãy xác nhận SDN giữ nguyên relationship ID và các thuộc tính không liên quan:

```java
@Test
void updatesOneRelationshipWithoutLosingTheOther() {
    Person target = people.save(new Person("target"));
    Person source = new Person("source");
    source.addConnection(new Connection(target, "EMAIL", "PENDING"));
    source.addConnection(new Connection(target, "CHAT", "ACTIVE"));

    Person saved = people.save(source);
    Long emailRelationshipId = saved.getConnections().stream()
            .filter(connection -> connection.getChannel().equals("EMAIL"))
            .findFirst()
            .orElseThrow()
            .getId();

    saved.getConnections().stream()
            .filter(connection -> connection.getChannel().equals("EMAIL"))
            .findFirst()
            .orElseThrow()
            .setStatus("ACTIVE");

    Person updated = people.save(saved);
    Person reloaded = people.findById(updated.getId()).orElseThrow();

    Connection email = reloaded.getConnections().stream()
            .filter(connection -> connection.getChannel().equals("EMAIL"))
            .findFirst()
            .orElseThrow();
    Connection chat = reloaded.getConnections().stream()
            .filter(connection -> connection.getChannel().equals("CHAT"))
            .findFirst()
            .orElseThrow();

    assertThat(email.getId()).isEqualTo(emailRelationshipId);
    assertThat(email.getStatus()).isEqualTo("ACTIVE");
    assertThat(chat.getStatus()).isEqualTo("ACTIVE");
}
```

Khi xóa một phần tử khỏi collection relationship, SDN có thể xóa relationship tương ứng khi lưu aggregate. Hãy viết test riêng để xác nhận cạnh cần xóa biến mất, cạnh còn lại vẫn tồn tại và dynamic relationships không bị ảnh hưởng. Đừng chỉ assert collection trong object trước khi gọi `save()`.

## 8. Tạo fixture bằng Cypher để kiểm tra chiều đọc

Đôi khi cần xác nhận SDN có thể hydrate graph đã được tạo bởi một ứng dụng khác hoặc bằng Cypher trực tiếp. Dùng `Neo4jClient` tạo hai cạnh cùng type, cùng cặp node nhưng khác thuộc tính:

```cypher
MERGE (source:Person {name: 'source'})
MERGE (target:Person {name: 'target'})
CREATE (source)-[:CONNECTED_TO {channel: 'EMAIL', status: 'ACTIVE'}]->(target)
CREATE (source)-[:CONNECTED_TO {channel: 'CHAT', status: 'PENDING'}]->(target);
```

Sau đó tải `source` bằng repository và kiểm tra `connections` có đủ hai relationship properties. Cách này tách riêng hai khả năng:

- Mapping ghi: object Java được lưu thành đúng graph.
- Mapping đọc: graph có sẵn được hydrate thành đúng object Java.

Ví dụ test chiều đọc:

```java
@Test
void mapsParallelRelationshipsCreatedDirectlyByCypher() {
    neo4jClient.query("""
            MERGE (source:Person {name: 'source'})
            MERGE (target:Person {name: 'target'})
            CREATE (source)-[:CONNECTED_TO {channel: 'EMAIL', status: 'ACTIVE'}]->(target)
            CREATE (source)-[:CONNECTED_TO {channel: 'CHAT', status: 'PENDING'}]->(target)
            """).run();

    Person source = people.findOneByName("source").orElseThrow();

    assertThat(source.getConnections())
            .extracting(Connection::getChannel)
            .containsExactlyInAnyOrder("EMAIL", "CHAT");
}
```

Nếu test chỉ dùng repository save rồi đọc lại, cùng một sai lầm trong mapping có thể xuất hiện ở cả hai chiều và khó nhận ra. Fixture Cypher độc lập giúp kiểm tra chiều đọc rõ hơn.

Khi tạo fixture trực tiếp, chú ý test transaction. Nếu `@DataNeo4jTest` đang mở transaction, fixture và repository query trong cùng test thường nhìn thấy dữ liệu của nhau. Không mở một session/transaction Driver độc lập rồi giả định nó chia sẻ transaction của Spring.

## 9. Kiểm tra hướng relationship

SDN mặc định ánh xạ relationship theo `OUTGOING` nếu không khai báo direction. Với `INCOMING`, field trên entity biểu diễn relationship đi từ node kia vào node hiện tại. Test nên tạo graph theo hướng cụ thể và xác nhận query mapping không đảo chiều.

Ví dụ Cypher:

```cypher
MATCH (source:Person {name: 'source'})
CREATE (target:Person {name: 'target'})
CREATE (source)-[:FOLLOWS]->(target);
```

Nếu entity `Person` khai báo `@Relationship(type = "FOLLOWS", direction = Direction.OUTGOING)`, field của `source` phải chứa `target`. Nếu khai báo `INCOMING`, field tương ứng trên `target` mới biểu diễn `source`.

Không khai báo cùng một relationship hai chiều trên cả hai entity chỉ vì muốn truy cập thuận tiện. SDN có thể mở rộng truy vấn qua toàn bộ graph được mô hình hóa và hydrate nhiều node hơn dự kiến. Dùng projection hoặc custom query khi chỉ cần một góc nhìn hẹp.

## 10. Lưu ý về transaction và test slice

`@DataNeo4jTest` mặc định tạo transaction imperative cho test và rollback khi test kết thúc. Điều này giúp test độc lập mà không cần xóa dữ liệu sau mỗi method. Tuy nhiên:

- Transaction của test là imperative. Nó không chứng minh reactive transaction behavior.
- Reactive repository/service không được bao bọc bởi test transaction imperative như mong đợi; cần dùng `TransactionalOperator` hoặc test setup riêng cho reactive flow.
- Nếu cần kiểm tra hành vi sau commit hoặc tương tác qua HTTP server chạy ở thread khác, transaction của test không tự rollback transaction trên server.
- Nếu tắt transaction test bằng `Propagation.NOT_SUPPORTED`, phải tự dọn dữ liệu hoặc dùng database/container riêng cho test.

Với test chạy song song, dùng tên hoặc ID duy nhất cho fixture để các method không cạnh tranh cùng node. Không dựa vào thứ tự thực thi test. Nếu test thay đổi schema hoặc dùng database riêng, quản lý lifecycle database rõ ràng thay vì dùng chung state không kiểm soát.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `Map<String, Person>` rồi đặt thêm `@Relationship(type = ...)` | Xung đột với cơ chế dynamic type lấy từ map key | Không cấu hình `@Relationship` trên dynamic map |
| Dùng dynamic map khi cần metadata riêng cho từng cạnh | Không biểu diễn được relationship properties theo mô hình mong muốn | Dùng `@RelationshipProperties` với type tĩnh |
| Thiếu `@TargetNode` | SDN không biết node ở đầu kia của relationship | Đánh dấu đúng một target field |
| Thiếu `@RelationshipId` trong relationship-properties class | SDN không thể nhận diện cạnh an toàn khi ghi và có thể lỗi mapping | Khai báo field ID nội bộ theo yêu cầu SDN |
| Dùng một relationship object cho nhiều cạnh | Các cạnh có thể bị đồng nhất hoặc mất metadata riêng | Tạo một object relationship-properties cho mỗi cạnh |
| Chỉ assert số phần tử collection | Có thể bỏ sót metadata hoặc relationship type sai | Assert ID, property, target và đối chiếu bằng Cypher |
| Chỉ test bằng mock repository | Không kiểm tra mapping thực tế hoặc Cypher | Dùng Neo4j Testcontainers/Test Harness |
| Tạo fixture bằng session độc lập rồi đọc trong transaction khác | Test có thể không nhìn thấy dữ liệu chưa commit | Dùng cùng transaction/client hoặc commit fixture trước khi đọc |
| Test reactive với transaction imperative của `@DataNeo4jTest` | Kết quả rollback/commit không phản ánh reactive transaction | Dùng `TransactionalOperator` và test reactive riêng |
| Khai báo relationship hai chiều không cần thiết | Truy vấn hydrate có thể mở rộng quá lớn | Chọn một aggregate direction hoặc dùng projection |
| Chỉ kiểm tra object trước `save()` | Chưa chứng minh dữ liệu đã được ghi đúng | Save, reload và assert graph trực tiếp |

## 12. Bài tập thực hành

Xây dựng graph mạng lưới cộng tác:

1. Tạo hai node `Person` là `source` và `target`.
2. Thêm hai relationship `CONNECTED_TO` cùng nối `source` đến `target`, với `channel` lần lượt là `EMAIL` và `CHAT`.
3. Thêm hai dynamic relationship type `MENTORS` và `COLLABORATES_WITH` cùng trỏ đến `target`.
4. Lưu graph qua repository, tải lại và xác nhận hai relationship properties cùng hai dynamic map key được khôi phục.
5. Dùng Cypher đếm riêng số cạnh `CONNECTED_TO` và lấy danh sách relationship type động.
6. Cập nhật `status` của một cạnh và xác nhận cạnh còn lại không đổi.
7. Xóa một cạnh khỏi collection, lưu lại và xác nhận chỉ cạnh đó bị xóa.
8. Tạo fixture bằng Cypher trước, sau đó kiểm tra SDN hydrate được hai cạnh cùng type.
9. Chạy test với Testcontainers và xác nhận database được dọn sau test theo transaction lifecycle.
10. Viết một test riêng cho reactive repository nếu ứng dụng có reactive stack.

Sau bài tập, hãy giải thích được khác biệt giữa dynamic relationship map và relationship properties, vai trò của `@RelationshipId`, cách SDN phân biệt nhiều cạnh cùng cặp node và vì sao cần kết hợp repository assertion với Cypher assertion.

## Kết luận

Kiểm thử relationship cần xác nhận cả object mapping lẫn cấu trúc graph thực tế. Dynamic relationships dùng key của `Map<String, Person>` hoặc `Map<Enum, Person>` làm relationship type; relationship có metadata dùng `@RelationshipProperties`, `@TargetNode` và `@RelationshipId`. Khi nhiều relationship cùng type nối cùng một cặp node, tạo một relationship-properties object riêng cho từng cạnh và kiểm tra ID cùng thuộc tính sau round-trip. Dùng `@DataNeo4jTest` kết hợp Neo4j Testcontainers hoặc Test Harness, đọc lại bằng repository và đối chiếu bằng Cypher để phát hiện lỗi ở cả chiều ghi lẫn chiều đọc.

## Tài liệu tham khảo

- [Spring Data Neo4j – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – RelationshipProperties API](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/schema/RelationshipProperties.html)
- [Spring Data Neo4j – Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot – Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
