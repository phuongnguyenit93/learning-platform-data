# Kiểm thử save dữ liệu được tải một phần và bảo toàn liên kết

Trong Spring Data Neo4j (SDN), `save(entity)` đồng bộ graph trong Neo4j với trạng thái object Java được truyền vào. Đây không phải thao tác cập nhật một vài field theo kiểu HTTP PATCH. Khi lưu một node đã tồn tại, SDN có thể xóa các relationship thuộc một loại được khai báo trong domain model rồi tạo lại chúng theo những relationship hiện diện trong object. Vì vậy, nếu ứng dụng chỉ tải một phần graph, sửa một thuộc tính rồi lưu lại object đó, các relationship chưa được tải có nguy cơ bị xóa hoặc thay đổi ngoài ý muốn.

Bài học này tập trung vào cách tái hiện lỗi, viết integration test kiểm tra trạng thái graph sau khi lưu và chọn đúng cách cập nhật khi chỉ có một phần dữ liệu. Mục tiêu là bảo đảm các node liên quan, relationship và property trên relationship vẫn được giữ nguyên khi một thay đổi chỉ nhắm tới một phần aggregate.

## 1. Vì sao save một entity tải một phần có thể làm mất relationship?

Giả sử graph có cấu trúc:

```text
                 (:Person {code: "P-2"})
                         ^
                         | [:KNOWS {since: 2020}]
                         |
(:Person {code: "P-1"})-+
       |                 |
       |                 +----> (:Person {code: "P-3"})
       |                         [:KNOWS {since: 2022}]
       |
       +--[:MEMBER_OF]--> (:Team {code: "T-1"})
```

Node `P-1` có hai relationship `KNOWS` và một relationship `MEMBER_OF`. Người dùng chỉ muốn đổi tên `P-1`. Nếu service tạo một object mới chỉ chứa `code` và `name`, các collection relationship trong object có thể đang rỗng hoặc không được khởi tạo. Khi gọi `repository.save(partialPerson)`, SDN không biết rằng các relationship đó chưa được tải và cần được giữ lại. Nó xử lý object như trạng thái graph mà ứng dụng muốn lưu.

Tài liệu SDN mô tả quá trình save theo hướng đồng bộ graph: cập nhật node, xóa các relationship của loại được ánh xạ, rồi tạo lại các relationship được biểu diễn trong object. Tài liệu cũng khuyến nghị tránh load, manipulate và save các subgraph vì các relationship có thể bị loại khỏi database.

Điểm cần nhớ: **một object Java không chứa relationship không có nghĩa graph không có relationship đó**. Khi object chỉ là một phần dữ liệu, đừng dùng nó làm toàn bộ mô hình ghi.

## 2. Phân biệt full aggregate, partial object và read projection

Ba loại dữ liệu sau có mục đích khác nhau:

| Loại | Nội dung | Có nên truyền vào `repository.save()`? |
|---|---|---|
| Full aggregate/entity | Các property và relationship cần được quản lý trong lần ghi đã được nạp đầy đủ | Có, sau khi thay đổi trạng thái cần lưu |
| Partial domain object | Chỉ có một số property hoặc relationship do custom query, form hoặc API request cung cấp | Không nên lưu như full aggregate |
| Read projection/DTO | Dữ liệu chỉ phục vụ hiển thị, báo cáo hoặc kết quả truy vấn riêng | Không; dùng làm read model |

SDN giả định domain model được truyền vào save là mô tả trạng thái cần đồng bộ. Nếu `@Query` trả về một domain object chỉ được hydrate một phần, sau đó service dùng object đó để ghi lại, những property hoặc relationship không được query có thể bị xóa hoặc ghi đè. FAQ của SDN cảnh báo trực tiếp tình huống này.

Hãy chọn một trong các cách sau:

1. Tải đầy đủ phần aggregate cần quản lý, sửa object đó rồi save.
2. Dùng projection làm persistence mask để chỉ cập nhật field/relationship được chỉ định.
3. Dùng Cypher có mục tiêu để cập nhật chính xác một property hoặc relationship.
4. Trả DTO cho read query và không chuyển DTO thành entity chỉ để gọi `save()`.

## 3. Domain model dùng trong kiểm thử

Ví dụ sử dụng `Person`, `Team` và relationship có property `since`.

Entity `Person`:

```java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Version;

@Node("Person")
public class Person {

    @Id
    private String code;

    @Version
    private Long version;

    private String name;

    @Relationship(type = "KNOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Friendship> friendships = new LinkedHashSet<>();

    @Relationship(type = "MEMBER_OF", direction = Relationship.Direction.OUTGOING)
    private Team team;

    protected Person() {
    }

    public Person(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public Person(String code, String name, Long version) {
        this.code = code;
        this.name = name;
        this.version = version;
    }

    public String getCode() { return code; }
    public String getName() { return name; }
    public Set<Friendship> getFriendships() { return friendships; }
    public Team getTeam() { return team; }

    public void setName(String name) {
        this.name = name;
    }

    public void setTeam(Team team) {
        this.team = team;
    }

    public void addFriendship(Friendship friendship) {
        friendships.add(friendship);
    }
}
```

Relationship entity `Friendship`:

```java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Friendship {

    @RelationshipId
    private Long id;

    private Integer since;

    @TargetNode
    private Person person;

    protected Friendship() {
    }

    public Friendship(Person person, Integer since) {
        this.person = person;
        this.since = since;
    }

    public Long getId() { return id; }
    public Integer getSince() { return since; }
    public Person getPerson() { return person; }
}
```

Entity `Team`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Version;

@Node("Team")
public class Team {

    @Id
    private String code;

    @Version
    private Long version;

    private String name;

    protected Team() {
    }

    public String getCode() { return code; }
    public String getName() { return name; }
}
```

`@RelationshipProperties` cho phép relationship `KNOWS` có dữ liệu riêng như `since`. Khi kiểm thử bảo toàn liên kết, cần kiểm tra cả endpoint lẫn property relationship; chỉ đếm số relationship có thể bỏ sót trường hợp liên kết bị thay bằng endpoint khác hoặc property bị mất.

`Person.code` và `Team.code` là business ID được gán từ ứng dụng, không dùng `@GeneratedValue`. Vì vậy hai entity khai báo `@Version`: SDN dùng version để phân biệt entity mới với entity đã tồn tại và để phát hiện cập nhật đồng thời. Khi tạo dữ liệu fixture bằng Cypher, version ban đầu được đặt là `0`; khi lưu entity mới qua SDN, để framework quản lý version.

## 4. Repository và projection đọc

Repository quản lý entity `Person`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {code: $code})
        RETURN p.code AS code, p.name AS name, p.version AS version
        """)
    Optional<PersonCard> findCardByCode(@Param("code") String code);

    record PersonCard(String code, String name, Long version) {
    }
}
```

`PersonCard` là read projection. Query chỉ trả mã, tên và version, nên không có đủ thông tin để tái tạo các relationship của `Person`. Version được giữ lại để SDN nhận diện đúng entity có business ID khi cần tạo một object partial cho thao tác ghi có projection mask. Đây là một thiết kế có chủ đích: caller chỉ cần thông tin card thì không cần tải graph liên quan.

Không đổi kiểu trả về của query trên thành `Person` chỉ để tiện gọi `save()`. Nếu method cần trả một domain entity có thể ghi lại, custom Cypher phải cung cấp đủ thông tin để hydrate đúng domain model, hoặc service phải tải lại aggregate đầy đủ trước khi ghi.

## 5. Chuẩn bị graph fixture có nhiều relationship

Integration test cần graph ban đầu có đủ dữ liệu để phát hiện việc xóa relationship:

```cypher
CREATE (p:Person {code: 'P-1', name: 'An', version: 0})
CREATE (f1:Person {code: 'P-2', name: 'Binh', version: 0})
CREATE (f2:Person {code: 'P-3', name: 'Chi', version: 0})
CREATE (t:Team {code: 'T-1', name: 'Platform', version: 0})
CREATE (p)-[:KNOWS {since: 2020}]->(f1)
CREATE (p)-[:KNOWS {since: 2022}]->(f2)
CREATE (p)-[:MEMBER_OF]->(t);
```

Fixture có hai `KNOWS` relationship với hai giá trị `since` khác nhau và một `MEMBER_OF`. Sau khi save, test phải xác nhận cả ba relationship vẫn tồn tại và vẫn trỏ tới đúng node.

## 6. Cấu hình integration test với @DataNeo4jTest và Testcontainers

`@DataNeo4jTest` là test slice của Spring Boot. Nó cấu hình repository được khai báo, `Neo4jClient`, template và transaction manager. Test slice không tự cung cấp database; có thể kết nối tới Neo4j Testcontainers hoặc Neo4j Test Harness. Testcontainers phù hợp khi cần kiểm thử với Neo4j server thực tế.

Dependency Maven tham khảo (để Spring Boot quản lý phiên bản tương thích):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-neo4j</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ test class cho Spring Boot 3 và SDN 8.1.x:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.neo4j.Neo4jContainer;

@Testcontainers
@DataNeo4jTest
class PersonSaveRelationshipTests {

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5").withAdminPassword("test-password");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
    }

    @Autowired
    PersonRepository personRepository;

    @Autowired
    Neo4jClient neo4jClient;

    @Autowired
    Neo4jTemplate neo4jTemplate;

    @BeforeEach
    void createGraph() {
        neo4jClient.query("MATCH (n) DETACH DELETE n").run();
        neo4jClient.query("""
            CREATE (p:Person {code: 'P-1', name: 'An', version: 0})
            CREATE (f1:Person {code: 'P-2', name: 'Binh', version: 0})
            CREATE (f2:Person {code: 'P-3', name: 'Chi', version: 0})
            CREATE (t:Team {code: 'T-1', name: 'Platform', version: 0})
            CREATE (p)-[:KNOWS {since: 2020}]->(f1)
            CREATE (p)-[:KNOWS {since: 2022}]->(f2)
            CREATE (p)-[:MEMBER_OF]->(t)
            """).run();
    }
}
```

Test slice `@DataNeo4jTest` mặc định mở một imperative transaction cho mỗi test và rollback khi test kết thúc. Điều này giúp fixture và thao tác test chạy trong cùng transaction. Nếu cần kiểm thử reactive transaction, không dựa vào transaction test imperative; dùng `TransactionalOperator` hoặc service reactive có transaction boundary riêng.

Với Spring Boot 4, package của `@DataNeo4jTest` đã được tổ chức lại trong module test riêng. Hãy dùng import và dependency theo phiên bản Spring Boot của dự án; phần cấu hình Testcontainers và mục tiêu kiểm thử vẫn tương tự.

## 7. Helper kiểm tra graph trực tiếp sau khi save

Không chỉ assert trên object Java vừa được save. Hãy truy vấn lại Neo4j để xác nhận trạng thái thực tế:

```java
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

private List<String> friendCodes() {
    return neo4jClient.query("""
            MATCH (:Person {code: 'P-1'})-[:KNOWS]->(friend:Person)
            RETURN friend.code AS code
            ORDER BY code
            """)
        .fetchAs(String.class)
        .mappedBy((typeSystem, record) -> record.get("code").asString())
        .all();
}

private List<Integer> friendshipYears() {
    return neo4jClient.query("""
            MATCH (:Person {code: 'P-1'})-[r:KNOWS]->(:Person)
            RETURN r.since AS since
            ORDER BY since
            """)
        .fetchAs(Integer.class)
        .mappedBy((typeSystem, record) -> record.get("since").asInt())
        .all();
}

private List<String> teamCodes() {
    return neo4jClient.query("""
            MATCH (:Person {code: 'P-1'})-[:MEMBER_OF]->(team:Team)
            RETURN team.code AS code
            ORDER BY code
            """)
        .fetchAs(String.class)
        .mappedBy((typeSystem, record) -> record.get("code").asString())
        .all();
}

private void assertOriginalRelationshipsArePresent() {
    assertThat(friendCodes()).containsExactly("P-2", "P-3");
    assertThat(friendshipYears()).containsExactly(2020, 2022);
    assertThat(teamCodes()).containsExactly("T-1");
}
```

Các helper kiểm tra:

- Đúng hai endpoint của `KNOWS`.
- Đúng property `since` của từng relationship.
- Đúng node `Team` được liên kết.

Việc kiểm tra theo endpoint và relationship property quan trọng hơn chỉ kiểm tra tổng số cạnh. Nếu một relationship bị xóa rồi tạo lại trỏ sang node khác, count vẫn có thể bằng cũ nhưng graph đã sai.

## 8. Kiểm thử save sau khi tải đầy đủ aggregate

Đường an toàn phổ biến là tải entity bằng repository query được SDN tạo, sửa object đã tải và lưu lại:

```java
import org.junit.jupiter.api.Test;

@Test
void saveFullyLoadedPersonShouldPreserveAllRelationships() {
    Person person = personRepository.findById("P-1").orElseThrow();

    assertThat(person.getFriendships()).hasSize(2);
    assertThat(person.getTeam().getCode()).isEqualTo("T-1");

    person.setName("An Nguyen");
    personRepository.save(person);

    assertThat(neo4jClient.query("""
            MATCH (p:Person {code: 'P-1'})
            RETURN p.name AS name
            """)
        .fetchAs(String.class)
        .mappedBy((typeSystem, record) -> record.get("name").asString())
        .one()).contains("An Nguyen");

    assertOriginalRelationshipsArePresent();
}
```

Repository `findById` sử dụng mapping metadata để tạo query cho entity và các relationship đã khai báo trong domain model. Khi aggregate được nạp đủ, việc thay `name` rồi save có thể đồng bộ trạng thái object mà không làm mất các liên kết hiện có.

Không giả định rằng mọi custom query đều tải đầy đủ như query do SDN tạo. Nếu entity có nhiều nhánh relationship hoặc graph sâu, hãy xác định rõ aggregate boundary và dữ liệu nào cần được nạp trước khi ghi.

## 9. Kiểm thử persistence projection để chỉ cập nhật một phần

Khi nghiệp vụ chỉ muốn cập nhật tên, có thể dùng `Neo4jTemplate.saveAs` với projection làm persistence mask.

Projection chỉ gồm thuộc tính `name`:

```java
public interface PersonNameProjection {
    String getName();
}
```

Test tạo object chỉ có mã và tên, rồi yêu cầu SDN chỉ lưu các property được khai báo trong projection:

```java
@Test
void saveAsNameProjectionShouldLeaveRelationshipsUntouched() {
    PersonCard current = personRepository.findCardByCode("P-1").orElseThrow();
    Person partialPerson = new Person(
        current.code(), "An Updated By Projection", current.version()
    );

    PersonNameProjection saved =
        neo4jTemplate.saveAs(partialPerson, PersonNameProjection.class);

    assertThat(saved.getName()).isEqualTo("An Updated By Projection");
    assertOriginalRelationshipsArePresent();
}
```

`saveAs(instance, projectionType)` chỉ cập nhật property và relationship được định nghĩa bởi projection. Ở ví dụ này projection chỉ có `name`, nên các relationship `KNOWS` và `MEMBER_OF` không thuộc phạm vi cập nhật. Đây là cách phù hợp khi cần ghi một phần có chủ đích mà không muốn SDN coi phần còn thiếu là trạng thái graph cần xóa.

Nếu projection có một association, association đó sẽ được đưa vào phạm vi ghi và có thể được đồng bộ theo dữ liệu của object. Vì vậy, không thêm relationship vào projection nếu request không có ý định cập nhật relationship đó.

Đừng tái sử dụng object trả về từ một thao tác save projection như thể nó đã được hydrate đầy đủ. SDN cảnh báo object được trả về có thể vẫn là object không đầy đủ; nếu cần ghi tiếp theo kiểu full aggregate, hãy tải lại entity đầy đủ trước.

## 10. Kiểm thử custom query chỉ trả read model

Custom query có thể trả DTO/projection khi caller chỉ cần một phần dữ liệu:

```java
@Test
void customReadProjectionShouldNotBeUsedAsWriteAggregate() {
    PersonRepository.PersonCard card =
        personRepository.findCardByCode("P-1").orElseThrow();

    assertThat(card.code()).isEqualTo("P-1");
    assertThat(card.name()).isEqualTo("An");
    assertOriginalRelationshipsArePresent();
}
```

`PersonCard` không phải `Person`, nên API repository không cho phép vô tình gọi `save(card)`. Nếu cần cập nhật sau khi đọc card, có thể:

- Gọi command service để tải lại `Person` đầy đủ, áp dụng thay đổi và save.
- Dùng `Neo4jTemplate.saveAs` với projection ghi rõ các field được phép cập nhật.
- Dùng Cypher cập nhật một property cụ thể.

Đây là cách phân tách read model và write model: query đọc có thể tối ưu và trả ít dữ liệu, còn thao tác ghi phải có đủ ngữ cảnh để giữ graph nhất quán.

## 11. Kiểm thử cập nhật một property bằng Cypher có mục tiêu

Nếu chỉ cần thay một scalar property và không muốn đồng bộ toàn bộ object graph, có thể dùng `Neo4jClient`:

```java
@Test
void targetedCypherUpdateShouldPreserveUnrelatedRelationships() {
    neo4jClient.query("""
            MATCH (p:Person {code: $code})
            SET p.name = $name
            """)
        .bind("P-1").to("code")
        .bind("An Updated By Cypher").to("name")
        .run();

    assertOriginalRelationshipsArePresent();
}
```

Query chỉ thay `p.name`; nó không xóa hoặc tái tạo relationship. `Neo4jClient` tích hợp với transaction management của Spring, nên có thể tham gia transaction hiện hành. Nếu dùng raw Driver và tự mở session/transaction riêng, cần tự quản lý transaction boundary và không giả định nó tham gia transaction Spring.

Với custom Cypher, ứng dụng tự chịu trách nhiệm cho các field audit, callback hoặc domain event mà query không thực hiện. Test nên xác minh những side effect cần thiết đó riêng biệt.

## 12. Kiểm thử chống ghi đè relationship khi dùng @Query

SDN khuyến nghị dùng `@Query` khi kết quả có hình dạng domain model hoặc khi ứng dụng chắc chắn không dùng object được map một phần cho lệnh ghi. Nếu custom query chỉ trả một phần entity, hãy xem đó là read-only result.

Ví dụ query đọc card ở repository phần trước chỉ trả `code`, `name` và `version`. Không nên viết:

```java
// Anti-pattern: không dùng object chỉ có code/name như full aggregate.
PersonCard card = personRepository.findCardByCode("P-1").orElseThrow();
Person partial = new Person(card.code(), "An Updated", card.version());
personRepository.save(partial);
```

Object trên không mang theo `friendships` và `team`. Khi save, SDN không thể suy ra những relationship cũ cần giữ. Hãy thay bằng một trong các lựa chọn đã kiểm thử:

```java
// Full aggregate update
Person full = personRepository.findById("P-1").orElseThrow();
full.setName("An Updated");
personRepository.save(full);
```

Hoặc:

```java
// Partial update with explicit persistence mask
PersonCard card = personRepository.findCardByCode("P-1").orElseThrow();
Person partial = new Person(card.code(), "An Updated", card.version());
neo4jTemplate.saveAs(partial, PersonNameProjection.class);
```

Hoặc Cypher có mục tiêu như ví dụ ở phần trước. Test regression cần xác nhận endpoint và property relationship vẫn nguyên vẹn sau mỗi đường ghi được phép.

## 13. Kiểm thử relationship properties và nhiều loại liên kết

Nếu entity có relationship entity, kiểm tra đầy đủ:

1. Số lượng relationship.
2. Mã node đích của từng relationship.
3. Property trên relationship, ví dụ `since`, `role`, `weight` hoặc `createdAt`.
4. Hướng relationship theo mapping.
5. Các relationship type khác trên cùng node không bị ảnh hưởng.

Ví dụ kiểm tra `KNOWS`:

```cypher
MATCH (p:Person {code: 'P-1'})-[r:KNOWS]->(friend:Person)
RETURN friend.code AS friendCode, r.since AS since
ORDER BY friendCode;
```

Kết quả kỳ vọng:

| friendCode | since |
|---|---:|
| `P-2` | 2020 |
| `P-3` | 2022 |

Ví dụ kiểm tra loại relationship độc lập:

```cypher
MATCH (p:Person {code: 'P-1'})-[:MEMBER_OF]->(team:Team)
RETURN team.code AS teamCode;
```

Nếu test chỉ đếm tổng relationship, một `KNOWS` bị thay bằng một `MEMBER_OF` vẫn có thể cho tổng số cạnh giống trước. Vì vậy hãy assert theo từng loại và theo endpoint cụ thể.

## 14. Kiểm thử với relationship hai chiều hoặc hai field cùng ánh xạ một loại

Khi domain model có nhiều property ánh xạ cùng một relationship type, phải hiểu rõ property nào chịu trách nhiệm quản lý liên kết. Nếu một phía được nạp đầy đủ nhưng phía còn lại là collection rỗng do custom mapping, một lần save có thể khiến hai mô tả ghi đè nhau.

Các test nên:

- Xác định rõ `direction` của `@Relationship`.
- Kiểm tra query theo chiều outgoing và incoming đúng với mô hình.
- Tránh khai báo hai collection độc lập cùng quản lý một relationship type nếu không có thiết kế mapping rõ ràng.
- Kiểm thử thao tác save từ cả hai node đầu/cuối nếu ứng dụng cho phép cập nhật từ hai phía.
- Kiểm tra relationship property không bị mất khi lưu qua một phía khác.

Không suy luận hướng relationship từ tên field Java. Hướng trong graph được quyết định bởi `@Relationship(direction = ...)` và pattern Cypher thực tế.

## 15. Aggregate boundary và phạm vi tải/lưu

Với graph lớn, tải mọi relationship của mọi node có thể rất tốn kém. SDN hỗ trợ aggregate boundary trong `@Node` để xác định ranh giới mà quá trình mapping không tiếp tục theo một số entity liên quan. Projections cũng có thể giới hạn field và relationship được tải hoặc lưu.

Đây là hai công cụ khác nhau:

- **Aggregate boundary:** định nghĩa ranh giới mapping ở cấp entity model.
- **Projection:** định nghĩa một view hoặc persistence mask cụ thể cho use case.

Khi một association nằm ngoài aggregate boundary, không nên mặc định nó đã được tải đầy đủ chỉ vì root entity đã được load. Nếu một use case cần thay đổi association đó, hãy truy vấn hoặc nạp association theo cách rõ ràng và kiểm thử lại sau save.

Không dùng aggregate boundary để che giấu việc một use case đang cần cập nhật relationship mà chưa nạp dữ liệu. Test phải mô tả rõ ranh giới nào được quản lý và relationship nào cần giữ nguyên.

## 16. Kiểm thử optimistic locking khi nhiều request cùng cập nhật

Partial save và concurrent save là hai vấn đề khác nhau nhưng có thể kết hợp. Nếu hai request cùng tải một `Person`, mỗi request thay đổi một phần graph rồi lưu, request thứ hai có thể ghi đè trạng thái mà request đầu vừa cập nhật.

SDN hỗ trợ optimistic locking với `@Version` trên field kiểu `Long`:

```java
@Node("Person")
public class VersionedPerson {

    @Id
    private String code;

    @Version
    private Long version;

    private String name;
}
```

Khi version hiện tại không còn khớp với version mà entity mang theo, save sẽ phát sinh `OptimisticLockingFailureException`. Ứng dụng cần tải lại dữ liệu hiện hành, áp dụng lại command trên trạng thái mới và thử lại theo chính sách nghiệp vụ.

Các entity `Person` và `Team` trong ví dụ đầu bài dùng business ID dạng `String`, vì vậy đã khai báo `@Version`. Khi tạo fixture trực tiếp bằng Cypher, đặt version ban đầu (`0`) để SDN nhận diện node là entity đã tồn tại. Khi tạo entity mới qua repository/template, để SDN khởi tạo version theo cơ chế của nó; không tự tăng version trong code nghiệp vụ.

Optimistic locking không thay thế việc tải đủ relationship cần lưu. Nó phát hiện xung đột phiên bản, nhưng không thể tự suy ra relationship nào bị bỏ sót khỏi một object partial.

## 17. Kiểm thử transaction rollback khi một phần graph không hợp lệ

Một thao tác save có thể cập nhật node và nhiều relationship. Nếu một bước trong transaction thất bại, test cần xác minh graph không ở trạng thái nửa hoàn tất.

Ví dụ kiểm thử service:

```java
@Test
void failedUpdateShouldRollbackNodeAndRelationshipChanges() {
    Person person = personRepository.findById("P-1").orElseThrow();
    person.setName("Should Not Persist");

    assertThatThrownBy(() -> personCommandService.updateAndFail(person))
        .isInstanceOf(IllegalStateException.class);

    Person reloaded = personRepository.findById("P-1").orElseThrow();
    assertThat(reloaded.getName()).isEqualTo("An");
    assertOriginalRelationshipsArePresent();
}
```

Ví dụ giả định `updateAndFail` chạy trong một Spring transaction, save entity rồi phát sinh unchecked exception trước khi commit. Test cần xác nhận cả property và relationship đã rollback. Nếu test slice tự mở transaction cho test, thao tác service phải tham gia transaction test hoặc test cần cấu hình transaction boundary riêng phù hợp.

## 18. Các assertion quan trọng cho regression test

Một test bảo toàn relationship tốt nên xác nhận nhiều lớp dữ liệu:

| Assertion | Điều cần chứng minh |
|---|---|
| Property của root node | Field cần thay đổi đã được lưu |
| Property không liên quan | Field khác không bị xóa hoặc ghi đè |
| Số relationship theo type | Không có liên kết bị mất hoặc tạo thừa |
| Endpoint ID/code | Relationship vẫn trỏ tới đúng node |
| Relationship properties | Metadata của cạnh được giữ nguyên |
| Relationship type khác | Một loại liên kết không làm ảnh hưởng loại khác |
| Hướng relationship | Liên kết không bị tạo ngược chiều ngoài ý muốn |
| Transaction rollback | Không có cập nhật một phần khi transaction thất bại |
| Optimistic lock | Concurrent update được phát hiện thay vì âm thầm ghi đè |

Không chỉ assert số lượng node hoặc quan sát object Java trong memory. Hãy query graph bằng `Neo4jClient` sau save để xác nhận trạng thái database.

## 19. Ma trận kiểm thử các đường ghi

| Đường ghi | Dữ liệu đầu vào | Kết quả cần kiểm tra |
|---|---|---|
| `repository.save(fullEntity)` | Entity đã tải đủ property và relationship cần quản lý | Thay đổi được lưu; liên kết không thay đổi vẫn tồn tại |
| `repository.save(partialEntity)` | Entity chỉ có ID và một số scalar field | Không dùng làm đường ghi hợp lệ; regression test phải phát hiện nguy cơ mất relationship |
| `Neo4jTemplate.saveAs(entity, Projection.class)` | Entity partial và projection giới hạn rõ field | Chỉ field/relationship trong projection được cập nhật |
| Repository trả DTO projection | Custom query trả một phần dữ liệu | DTO đọc đúng; không chuyển thành aggregate để save |
| `Neo4jClient` targeted Cypher | Query chỉ SET một property | Relationship ngoài phạm vi query vẫn nguyên vẹn |
| Custom query trả domain type đầy đủ | Query trả đủ node/relationship để hydrate entity | Save sau đó giữ đúng graph theo domain model |
| Transaction rollback | Save rồi phát sinh lỗi | Node property và relationship cùng rollback |
| Concurrent save | Hai transaction dùng cùng version cũ | Transaction sau nhận optimistic locking failure |

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Save đổi tên nhưng mất bạn bè | Entity được tạo mới, collection relationship rỗng | Tải aggregate đầy đủ hoặc dùng `saveAs` với projection scalar |
| Relationship bị xóa sau custom `@Query` | Query chỉ hydrate một phần domain object | Trả DTO hoặc viết query hydrate đầy đủ trước khi ghi |
| Số relationship không đổi nhưng endpoint bị sai | Test chỉ kiểm tra count | Assert danh sách ID/code của node đích |
| Relationship property bị mất | Mapping hoặc projection không bao gồm relationship properties cần thiết | Dùng `@RelationshipProperties` và kiểm tra property cạnh |
| Một relationship type khác bị xóa | Save đồng bộ các association được khai báo trong entity | Kiểm tra tất cả relationship field của aggregate |
| `saveAs` vẫn cập nhật association ngoài ý muốn | Projection vô tình khai báo association đó | Thu hẹp projection và kiểm thử mask |
| Dùng object trả về từ `saveAs` cho lần save tiếp theo bị mất dữ liệu | Object trả về chưa được hydrate đầy đủ | Tải lại full entity hoặc tiếp tục dùng persistence projection rõ ràng |
| Query read model bị dùng làm write model | Repository trả domain entity dù query chỉ có một phần field | Dùng DTO/interface projection riêng cho read path |
| Test pass nhưng graph thực tế vẫn sai | Chỉ assert trên object đang giữ trong memory | Query lại Neo4j để assert trạng thái persisted |
| Test reactive không rollback như mong đợi | Dùng imperative `@Transactional` test cho reactive flow | Dùng `TransactionalOperator` hoặc service reactive transaction boundary |
| Concurrent update ghi đè nhau | Không dùng optimistic locking hoặc không xử lý version conflict | Dùng `@Version`, reload và áp dụng lại command |

## 21. Quy trình kiểm thử save dữ liệu tải một phần

1. Xây fixture graph có ít nhất hai loại relationship, nhiều endpoint và relationship properties.
2. Ghi nhận trạng thái ban đầu bằng Cypher độc lập: endpoint, type, direction và property cạnh.
3. Kiểm thử đường save full aggregate: tải bằng repository, sửa scalar field, save và xác minh graph.
4. Kiểm thử partial write bằng `Neo4jTemplate.saveAs` với projection chỉ chứa field cần thay đổi.
5. Kiểm thử custom query trả DTO và xác nhận DTO không được dùng như domain entity để save.
6. Nếu có targeted Cypher, kiểm tra query chỉ thay đổi đúng property/relationship được yêu cầu.
7. Kiểm thử rollback để bảo đảm node và relationship cùng quay về trạng thái trước transaction.
8. Kiểm thử optimistic locking khi nhiều request có thể cùng cập nhật một aggregate.
9. Sau mỗi lần save, truy vấn lại Neo4j và so sánh endpoint/property với fixture ban đầu.
10. Chạy test trên Neo4j Testcontainers hoặc Test Harness tương thích với phiên bản server của ứng dụng.

## 22. Tự kiểm tra

1. Vì sao `repository.save()` không nên được xem như HTTP PATCH?
2. SDN đồng bộ relationship của entity đã tồn tại như thế nào khi save?
3. Vì sao một partial object có thể làm mất relationship chưa được tải?
4. Khác biệt giữa full aggregate, partial domain object và read projection là gì?
5. Vì sao custom `@Query` trả domain type một phần có thể gây mất dữ liệu khi save lại?
6. `Neo4jTemplate.saveAs(entity, Projection.class)` giới hạn phạm vi ghi như thế nào?
7. Vì sao test phải kiểm tra endpoint và property của relationship, không chỉ đếm cạnh?
8. Khi nào nên dùng `Neo4jClient` để cập nhật một property?
9. Aggregate boundary khác projection persistence mask ở điểm nào?
10. Vì sao `@Version` không thay thế việc tải đủ relationship cần ghi?
11. `@DataNeo4jTest` cung cấp những hạ tầng gì và có tự tạo database không?
12. Vì sao test reactive cần transaction setup khác với test imperative?

## Tài liệu tham khảo

- [Spring Data Neo4j — Query Creation: Save và Load](https://docs.spring.io/spring-data/neo4j/reference/appendix/query-creation.html)
- [Spring Data Neo4j — FAQ: Custom queries và partial domain mapping](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — Projections và Persistence of Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j — Neo4jTemplate API: save, saveAs và saveAllAs](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j — With Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j — Optimistic Locking](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
