# Entity gốc bị trùng và collection quan hệ bị thiếu

Khi dùng custom Cypher trong Spring Data Neo4j (SDN), một lỗi dễ gây nhầm lẫn là repository trả về nhiều bản sao của cùng entity gốc, trong khi collection relationship trên mỗi bản sao chỉ có một phần dữ liệu hoặc bị rỗng. Nguyên nhân thường nằm ở hình dạng result set: Cypher trả nhiều record cho cùng một root node, hoặc chỉ trả node gốc mà không trả đủ relationship và node đích để SDN dựng object graph.

SDN xử lý kết quả custom query theo từng record. Nếu một Team có năm thành viên và query trả năm record, mỗi record chứa cùng Team nhưng chỉ một Membership và một Person, SDN có thể ánh xạ thành năm Team lặp lại; mỗi object chỉ có dữ liệu relationship xuất hiện trong record tương ứng. Cách sửa là thiết kế kết quả có một record cho mỗi root entity và gom các relationship cùng node đích vào collection trong record đó.

Bài học này tập trung vào cách nhận diện lỗi do cardinality của query, phân biệt với node trùng thật trong graph, xây dựng custom query đúng hình dạng và kiểm thử đầy đủ collection relationship.

## 1. Hiểu hai triệu chứng thường xuất hiện cùng nhau

Giả sử domain có Team và Person. Một Team có nhiều Person thông qua relationship MEMBER_OF. Entity Team khai báo collection quan hệ:

~~~java
@Node("Team")
public class Team {

    @Id
    private String id;

    private String name;

    @Relationship(
        type = "MEMBER_OF",
        direction = Relationship.Direction.INCOMING
    )
    private Set<Person> members = new HashSet<>();

    // Constructor và accessor được lược bỏ.
}
~~~

Một Team có ba thành viên: An, Bình và Chi. Nếu custom query trả một dòng cho mỗi thành viên, result set có thể giống như sau:

| Record | team | membership | person |
| --- | --- | --- | --- |
| 1 | Platform | MEMBER_OF | An |
| 2 | Platform | MEMBER_OF | Bình |
| 3 | Platform | MEMBER_OF | Chi |

Root node Platform xuất hiện ba lần. Vì SDN ánh xạ record theo từng dòng, kết quả dạng List có thể chứa ba object Team tương ứng cùng root. Mỗi record chỉ mang một relationship và một Person, nên collection trên từng object không nhất thiết có đủ cả ba thành viên.

Hai triệu chứng cần phân biệt:

- **Root bị lặp do result set:** graph chỉ có một Team, nhưng query tạo nhiều record cho Team đó.
- **Collection thiếu do record không đầy đủ:** query không gom các relationship và node đích thành một collection trong cùng record cho root.

Đây thường là một vấn đề thiết kế custom query, không phải SDN tự nhân bản node trong Neo4j.

## 2. Vì sao custom query cần một record cho mỗi root?

SDN làm việc với result record của Neo4j. Đối với custom query ánh xạ thành entity có relationship, kết quả cần chứa đủ dữ liệu để dựng object graph. Với một root entity, mục tiêu là một record chứa:

- Node gốc cần ánh xạ.
- Các relationship thuộc những field được map.
- Các node đích ở đầu còn lại của relationship.
- Các property trên relationship nếu dùng @RelationshipProperties.

Ví dụ một Team có nhiều Membership. Query trả team, membership, person riêng trên từng dòng tạo nhiều record. Thay vào đó, query cần trả team, collection Membership và collection Person trong một record.

Đây là khác biệt giữa hai hình dạng kết quả:

~~~text
Không phù hợp cho một root có nhiều relationship:

record 1: team + relationship 1 + person 1
record 2: team + relationship 2 + person 2
record 3: team + relationship 3 + person 3

Phù hợp:

record 1: team + [relationship 1, relationship 2, relationship 3]
               + [person 1, person 2, person 3]
~~~

Không nên chỉ nhìn số dòng trả về. Hãy kiểm tra mỗi dòng chứa những cột nào và các relationship có được gom theo root hay không.

## 3. Tái hiện lỗi bằng custom query trả nhiều record

Query sau tìm một Team và các thành viên:

~~~cypher
MATCH (team:Team {id: $teamId})
      <-[membership:MEMBER_OF]-
      (person:Person)
RETURN team, membership, person
~~~

Nếu Team có ba thành viên, query trả ba record. Khi repository trả List<Team>, root Team có thể xuất hiện lặp lại theo số relationship được match.

Ví dụ repository:

~~~java
public interface TeamRepository extends Neo4jRepository<Team, String> {

    @Query("""
        MATCH (team:Team {id: $teamId})
              <-[membership:MEMBER_OF]-
              (person:Person)
        RETURN team, membership, person
        """)
    List<Team> findWithMembersIncorrectly(
        @Param("teamId") String teamId
    );
}
~~~

Tên method có chữ Incorrectly chỉ dùng để minh họa lỗi. Query trả nhiều record có cùng root và không gom relationship. Không dùng mẫu này để hydrate một Team có đầy đủ collection thành viên.

Nếu query chỉ trả team:

~~~cypher
MATCH (team:Team {id: $teamId})
RETURN team
~~~

SDN nhận được root node nhưng custom result không mang theo các relationship và node đích cần thiết để dựng collection. Một field Java đã khởi tạo bằng new HashSet<>() có thể vẫn rỗng; điều đó không chứng minh graph không có relationship.

## 4. Sửa bằng collect để có một record cho mỗi root

Với một loại relationship, gom relationship và node đích bằng collect():

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team,
       collect(DISTINCT membership) AS memberships,
       collect(DISTINCT person) AS people
~~~

Kết quả cho một Team có ba thành viên là một record:

| team | memberships | people |
| --- | --- | --- |
| Platform | [Membership 1, Membership 2, Membership 3] | [An, Bình, Chi] |

SDN có thể sử dụng root node cùng collection relationship và node đích để dựng collection members trong entity Team.

DISTINCT trong từng collection giúp loại trùng relationship hoặc node đích khi query có nhiều đường dẫn dẫn đến cùng một phần tử. Nó không thay thế việc gom dữ liệu thành một record cho root.

Nếu muốn lấy nhiều Team, query vẫn có thể trả một record cho mỗi Team:

~~~cypher
MATCH (team:Team)
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team,
       collect(DISTINCT membership) AS memberships,
       collect(DISTINCT person) AS people
ORDER BY team.name
~~~

Cypher nhóm kết quả theo các biểu thức không aggregate, ở đây là team. Mỗi Team trở thành một nhóm và các relationship/person được gom vào collection tương ứng.

Đưa query vào repository:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface TeamRepository extends Neo4jRepository<Team, String> {

    @Query("""
        MATCH (team:Team {id: $teamId})
        OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
        RETURN team,
               collect(DISTINCT membership) AS memberships,
               collect(DISTINCT person) AS people
        """)
    Optional<Team> findWithMembers(@Param("teamId") String teamId);
}
~~~

Vì query xác định một Team theo ID duy nhất, kiểu Optional<Team> thể hiện rõ có thể không tìm thấy root. Nếu query trả nhiều Team, dùng kiểu collection và giữ nguyên nguyên tắc một record cho mỗi Team.

## 5. Dùng OPTIONAL MATCH để giữ root không có relationship

Nếu dùng MATCH bắt buộc:

~~~cypher
MATCH (team:Team {id: $teamId})
MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team, collect(membership), collect(person)
~~~

Team không có thành viên sẽ không xuất hiện trong kết quả vì pattern thứ hai không match.

Nếu use case cần trả Team kể cả khi collection rỗng, dùng OPTIONAL MATCH:

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team,
       collect(DISTINCT membership) AS memberships,
       collect(DISTINCT person) AS people
~~~

Khi không có relationship, collect() bỏ qua giá trị null và trả collection rỗng. Root vẫn được trả về.

Phân biệt ba tình huống:

| Kết quả | Ý nghĩa |
| --- | --- |
| Không có record root | Root không tồn tại hoặc một MATCH bắt buộc ở phía sau đã loại root |
| Có root, collection rỗng | Root tồn tại nhưng không có relationship phù hợp với pattern |
| Có root, collection có một phần tử | Query chỉ tìm thấy một relationship hoặc đã lọc xuống một phần tử |

Đừng thay MATCH bằng OPTIONAL MATCH một cách máy móc. Chọn theo hợp đồng nghiệp vụ: nếu chỉ muốn trả Team có thành viên thì MATCH là đúng; nếu muốn trả mọi Team và collection có thể rỗng thì dùng OPTIONAL MATCH.

## 6. Map relationship có property bằng @RelationshipProperties

Khi relationship có dữ liệu riêng như joinedAt, role hoặc approvedBy, entity nên map relationship bằng @RelationshipProperties.

Ví dụ:

~~~java
@Node("Team")
public class Team {

    @Id
    private String id;

    private String name;

    @Relationship(
        type = "MEMBER_OF",
        direction = Relationship.Direction.INCOMING
    )
    private Set<Membership> memberships = new HashSet<>();

    // Constructor và accessor được lược bỏ.
}
~~~

~~~java
@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long id;

    private Instant joinedAt;

    private String role;

    @TargetNode
    private Person person;

    // Constructor và accessor được lược bỏ.
}
~~~

Query cần trả cả relationship và target node:

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team,
       collect(DISTINCT membership) AS memberships,
       collect(DISTINCT person) AS people
~~~

collect(membership) giữ relationship cùng property joinedAt và role. collect(person) cung cấp node đích để SDN gắn vào @TargetNode. Nếu chỉ trả collect(person), SDN không có đầy đủ relationship record để dựng Membership và các property trên cạnh.

Khi test, hãy kiểm tra cả số lượng Membership, target Person và giá trị relationship properties. Chỉ kiểm tra memberships.size() có thể bỏ sót trường hợp property trên relationship bị mất hoặc target node bị ánh xạ sai.

## 7. Tránh Cartesian product khi một root có nhiều collection

Một Team có thể có nhiều thành viên và nhiều tag:

- 3 relationship MEMBER_OF.
- 2 relationship HAS_TAG.

Query tuần tự hai pattern độc lập:

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
OPTIONAL MATCH (team)-[tagging:HAS_TAG]->(tag:Tag)
RETURN team,
       collect(DISTINCT membership) AS memberships,
       collect(DISTINCT person) AS people,
       collect(DISTINCT tagging) AS taggings,
       collect(DISTINCT tag) AS tags
~~~

Hai nhánh có thể tạo 3 × 2 = 6 dòng trung gian. collect(DISTINCT ...) có thể loại phần tử trùng khỏi collection cuối, nhưng không ngăn database tạo tích giữa hai nhánh trước khi aggregate. Truy vấn vẫn tốn tài nguyên và dễ gây nhầm khi thêm điều kiện.

Tách mỗi nhánh thành một correlated subquery để aggregate độc lập:

~~~cypher
MATCH (team:Team {id: $teamId})
CALL {
    WITH team
    OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
    RETURN collect(DISTINCT membership) AS memberships,
           collect(DISTINCT person) AS people
}
CALL {
    WITH team
    OPTIONAL MATCH (team)-[tagging:HAS_TAG]->(tag:Tag)
    RETURN collect(DISTINCT tagging) AS taggings,
           collect(DISTINCT tag) AS tags
}
RETURN team, memberships, people, taggings, tags
~~~

Mỗi subquery nhận một Team, xử lý một nhánh và trả về các collection đã aggregate. Hai nhánh không nhân chéo các dòng thành viên với các dòng tag.

Cách này đặc biệt hữu ích khi một root có nhiều collection relationship độc lập. Hãy kiểm tra execution plan và lượng dữ liệu thực tế; subquery giúp tránh tích Descartes nhưng không làm biến mất chi phí đọc mọi relationship cần trả về.

## 8. DISTINCT root không phải cách sửa đầy đủ

Một cách thử thường gặp là:

~~~cypher
MATCH (team:Team {id: $teamId})
      <-[membership:MEMBER_OF]-
      (person:Person)
RETURN DISTINCT team
~~~

Query chỉ trả root một lần, nhưng không trả membership hoặc person. Collection quan hệ không có dữ liệu từ result record để hydrate.

Một cách khác:

~~~cypher
MATCH (team:Team {id: $teamId})
      <-[membership:MEMBER_OF]-
      (person:Person)
RETURN DISTINCT team, membership, person
~~~

DISTINCT áp dụng cho toàn bộ tuple. Mỗi relationship/person khác nhau vẫn tạo một record khác nhau. Root vẫn lặp theo số tuple.

Mẫu cần dùng là aggregate theo root:

~~~cypher
MATCH (team:Team {id: $teamId})
      <-[membership:MEMBER_OF]-
      (person:Person)
RETURN team,
       collect(DISTINCT membership),
       collect(DISTINCT person)
~~~

Hãy nhớ:

- DISTINCT root chỉ khử trùng lặp root.
- DISTINCT root, relationship, target khử tuple trùng hoàn toàn.
- root, collect(DISTINCT relationship), collect(DISTINCT target) tạo một record cho root và giữ collection cần hydrate.

## 9. Phân biệt duplicate record với node trùng thật trong Neo4j

Không phải mọi trường hợp repository trả hai Team cùng business ID đều do result set. Graph có thể thực sự chứa hai node khác nhau có cùng business key, ví dụ do dùng CREATE lặp lại hoặc MERGE theo một tập property không ổn định.

Dùng query chẩn đoán số node root và số record sau khi match relationship:

~~~cypher
MATCH (team:Team {businessId: $businessId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN count(*) AS rows,
       count(DISTINCT team) AS rootNodes,
       count(DISTINCT membership) AS memberships,
       count(DISTINCT person) AS people
~~~

Diễn giải:

- rootNodes = 1, rows > 1: một node Team được nhân thành nhiều record do relationship match.
- rootNodes > 1: có nhiều node Team thật cùng businessId.
- memberships nhỏ hơn rows: một hoặc nhiều relationship bị lặp qua các nhánh query hoặc các pattern khác.
- people nhỏ hơn memberships: một Person có thể tham gia qua nhiều relationship hoặc một người xuất hiện ở nhiều nhánh.

Để kiểm tra node trùng thật, chỉ truy vấn node:

~~~cypher
MATCH (team:Team {businessId: $businessId})
RETURN count(team) AS matchingNodes,
       collect(elementId(team)) AS nodeElements
~~~

elementId() hữu ích để phân biệt node vật lý trong chẩn đoán. Không dùng element ID như khóa nghiệp vụ bền vững trong ứng dụng; hãy dùng property ID do domain quản lý.

Nếu businessId phải duy nhất trên toàn database, tạo uniqueness constraint sau khi xử lý dữ liệu trùng hiện có:

~~~cypher
CREATE CONSTRAINT team_business_id_unique IF NOT EXISTS
FOR (team:Team)
REQUIRE team.businessId IS UNIQUE
~~~

Nếu businessId chỉ duy nhất trong từng tenant, dùng composite uniqueness constraint:

~~~cypher
CREATE CONSTRAINT team_tenant_business_id_unique IF NOT EXISTS
FOR (team:Team)
REQUIRE (team.tenantId, team.businessId) IS UNIQUE
~~~

Constraint bảo vệ tính duy nhất của dữ liệu tương lai. Nó không tự xóa các node trùng đã tồn tại; cần tìm, đối soát relationship và xử lý dữ liệu trước khi tạo constraint.

## 10. Kiểm tra hướng relationship và loại relationship

Collection có thể rỗng dù node và relationship tồn tại nếu query match sai hướng hoặc sai type so với domain mapping.

Ví dụ entity khai báo:

~~~java
@Relationship(type = "MEMBER_OF", direction = Relationship.Direction.INCOMING)
private Set<Person> members;
~~~

Pattern từ Team phải phản ánh relationship đi vào Team:

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
RETURN team,
       collect(DISTINCT membership),
       collect(DISTINCT person)
~~~

Nếu graph thực tế lưu relationship theo chiều (team)-[:MEMBER_OF]->(person), query trên sẽ không match. Hãy kiểm tra direction thực tế trong graph và sửa model hoặc query theo đúng quy ước domain.

Cũng kiểm tra:

- Tên relationship type có khớp chính xác với @Relationship(type = "...") không.
- Collection khai báo INCOMING, OUTGOING hay UNDIRECTED có đúng với graph không.
- Query có lọc property trên relationship làm mất các cạnh hợp lệ không.
- Điều kiện WHERE có được gắn trực tiếp với OPTIONAL MATCH hay được áp dụng ở một WITH/WHERE phía sau.
- Relationship property có đúng tên và kiểu mà @RelationshipProperties mong đợi không.

Trong Cypher, WHERE đặt ngay sau OPTIONAL MATCH là một phần của pattern tùy chọn; nó lọc những relationship/node được ghép và vẫn giữ root với giá trị null nếu không có kết quả phù hợp. Ngược lại, nếu chuyển dữ liệu qua WITH rồi áp dụng WHERE ở phần tiếp theo, các dòng có node đích null có thể bị loại, khiến root biến mất. Ví dụ sau giữ Team kể cả khi không có thành viên active:

~~~cypher
MATCH (team:Team {id: $teamId})
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
WHERE person.status = $status
RETURN team,
       collect(DISTINCT membership),
       collect(DISTINCT person)
~~~

Hãy đặt predicate ở đúng vị trí theo semantics mong muốn, đặc biệt khi chuyển query sang correlated subquery hoặc thêm nhiều giai đoạn WITH.

## 11. Khi cần ánh xạ graph sâu hơn một tầng

Một query gom relationship trực tiếp từ Team tới Person chỉ đủ cho graph shape ở tầng đó. Nếu Person cũng có relationship cần hydrate, record phải mang thêm các node và relationship của tầng sâu.

SDN cần dữ liệu record để dựng object graph. Không giả định rằng một custom query chỉ trả Team sẽ tự động tải mọi nhánh sâu như finder query được SDN tạo sẵn.

Với graph được tạo bởi các path, có thể gom node và relationship từ path vào các collection:

~~~cypher
MATCH path =
    (team:Team {id: $teamId})
    <-[:MEMBER_OF]-
    (:Person)
    -[:INTERESTED_IN]->
    (:Topic)
RETURN team,
       collect(nodes(path)),
       collect(relationships(path))
~~~

SDN hỗ trợ các collection lồng nhau của node và relationship trong custom result và có thể làm phẳng chúng trong quá trình mapping. Cách này hữu ích khi cần cung cấp nhiều nhánh graph từ các path. Hãy bảo đảm mọi node và relationship cần cho entity mapping đều có trong record.

Nếu graph sâu có nhiều path trùng lặp, cân nhắc giảm trùng ở database bằng reduce() hoặc gom ở client. Database-side reduction tạo các path và danh sách trung gian trong bộ nhớ database; client-side reduction chuyển nhiều dữ liệu hơn qua network và dùng bộ nhớ ứng dụng. Chọn theo kích thước graph, số path và giới hạn tài nguyên.

## 12. Không trả entity khi query chỉ tạo dữ liệu báo cáo

Nếu use case chỉ cần thống kê hoặc projection, đừng cố ánh xạ kết quả thành entity có relationship collection.

Ví dụ cần đếm số thành viên theo Team:

~~~cypher
MATCH (team:Team)
OPTIONAL MATCH (team)<-[:MEMBER_OF]-(person:Person)
RETURN team.id AS teamId,
       team.name AS teamName,
       count(DISTINCT person) AS memberCount
~~~

Kết quả phù hợp với DTO:

~~~java
public record TeamMemberCount(
    String teamId,
    String teamName,
    long memberCount
) {}
~~~

Với projection/DTO, result record là dữ liệu scalar theo đúng hợp đồng. Không cần trả node/relationship graph chỉ để lấy số lượng.

Ngược lại, nếu method trả Team, query cần trả graph shape đủ để hydrate Team. Chọn return type theo mục tiêu: entity cho object graph cần thao tác tiếp, DTO cho báo cáo hoặc dữ liệu đọc chuyên biệt.

## 13. Kiểm thử repository để bắt lỗi duplicate root và thiếu collection

Unit test mock repository không thể xác nhận SDN mapping custom result. Hãy dùng repository test với Neo4j thật, ví dụ qua @DataNeo4jTest hoặc @SpringBootTest và Testcontainers.

Fixture nên có:

- Một Team gốc.
- Ít nhất ba Person là thành viên.
- Một Person có nhiều relationship nếu domain cho phép.
- Một Team khác để xác nhận query không trả nhầm root.
- Một Team không có thành viên để kiểm tra collection rỗng nếu use case yêu cầu.

Test ví dụ:

~~~java
@Test
void returnsOneTeamWithAllMemberships() {
    List<Team> result = teamRepository.findWithMembers("team-1");

    assertEquals(1, result.size());

    Team team = result.get(0);
    assertEquals("team-1", team.getId());
    assertEquals(3, team.getMembers().size());
}
~~~

Với @RelationshipProperties, kiểm tra thêm target và relationship data:

~~~java
@Test
void mapsRelationshipPropertiesForEveryMember() {
    Team team = teamRepository.findWithMemberships("team-1")
        .orElseThrow();

    assertEquals(3, team.getMemberships().size());
    assertTrue(
        team.getMemberships().stream()
            .allMatch(membership -> membership.getJoinedAt() != null)
    );
    assertTrue(
        team.getMemberships().stream()
            .allMatch(membership -> membership.getPerson() != null)
    );
}
~~~

Các method và accessor trong ví dụ là minh họa; điều chỉnh theo domain model thực tế. Assertion quan trọng gồm:

1. Số root entity đúng.
2. Không có root lặp theo số relationship.
3. Collection có đủ phần tử.
4. Không có target node ngoài tenant hoặc ngoài điều kiện query.
5. Relationship properties được ánh xạ đủ.
6. Root không có relationship vẫn được trả về khi hợp đồng yêu cầu.
7. Query nhiều collection không tạo phần tử lặp do Cartesian product.

## 14. Phân trang root entity sau khi aggregate

Nếu repository trả page hoặc slice các root có collection, hãy áp dụng SKIP/LIMIT ở cấp root sau khi gom relationship cho từng root.

Ví dụ:

~~~cypher
MATCH (team:Team)
OPTIONAL MATCH (team)<-[membership:MEMBER_OF]-(person:Person)
WITH team,
     collect(DISTINCT membership) AS memberships,
     collect(DISTINCT person) AS people
ORDER BY team.name, team.id
SKIP $skip
LIMIT $limit
RETURN team, memberships, people
~~~

Nếu giới hạn dòng trước khi collect(), một Team có nhiều thành viên có thể bị cắt mất một phần collection. Sắp xếp ổn định bằng khóa phụ như team.id giúp phân trang nhất quán khi nhiều Team có cùng tên.

Với custom repository query trả Page, count query cần đếm số root Team, không đếm số relationship record. Nếu đếm sau khi expand relationship, tổng phần tử có thể lớn hơn số root entity và metadata phân trang sẽ sai.

## 15. Checklist chẩn đoán

Khi repository trả root bị trùng hoặc collection relationship bị thiếu, kiểm tra theo thứ tự:

1. Chạy Cypher trong Neo4j Browser với cùng parameter.
2. Đếm tổng số record và số root node phân biệt.
3. Xác định có nhiều node thật cùng business key hay chỉ một root bị lặp theo relationship.
4. Kiểm tra mỗi record có chứa root, relationship và target node không.
5. Nếu có nhiều record cho một root, gom relationship và target bằng collect().
6. Dùng OPTIONAL MATCH nếu cần giữ root có collection rỗng.
7. Dùng collect(DISTINCT ...) khi nhiều path có thể lặp cùng node/relationship.
8. Nếu có nhiều collection độc lập, tách nhánh bằng correlated subquery để tránh tích Descartes.
9. Kiểm tra relationship type, direction và property filter.
10. Nếu cần graph sâu, trả đủ node/relationship của các tầng cần hydrate.
11. Nếu chỉ cần thống kê, chuyển sang DTO/projection.
12. Nếu có phân trang, aggregate trước rồi mới SKIP/LIMIT root.
13. Viết repository test với nhiều relationship và cả trường hợp collection rỗng.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Một Team xuất hiện nhiều lần trong List | Query trả nhiều record cho cùng root | Aggregate theo root để có một record/root |
| Mỗi Team chỉ có một thành viên dù graph có nhiều | Mỗi record chỉ trả một relationship/target | collect(relationship) và collect(target) |
| DISTINCT team làm collection rỗng | Query chỉ trả root sau khi khử trùng | Trả root cùng collection relationship và target |
| Team không có thành viên biến mất | Dùng MATCH bắt buộc cho relationship | Dùng OPTIONAL MATCH nếu cần giữ root |
| Thành viên không được hydrate | Thiếu node đích hoặc relationship trong result | Trả cả hai đầu và relationship |
| Relationship properties bị null | Chỉ trả target node | Trả relationship record trong collection |
| Collection có phần tử trùng | Nhiều path hoặc nhiều nhánh tạo record lặp | Dùng collect(DISTINCT ...) và kiểm tra Cartesian product |
| Query chạy nặng khi có nhiều collection | Các nhánh relationship nhân chéo | Aggregate từng nhánh trong subquery |
| Collection rỗng dù relationship tồn tại | Sai type, direction hoặc predicate | Đối chiếu graph pattern với mapping |
| Kết quả page thiếu relationship | SKIP/LIMIT trước aggregation | Aggregate theo root trước khi phân trang |

## 17. Bài tập tự kiểm tra

1. Vì sao custom query trả một record cho mỗi relationship có thể làm root entity lặp lại?
2. Vì sao mỗi bản sao root có thể chỉ chứa một phần collection?
3. collect(relationship) và collect(target) có vai trò gì khi SDN hydrate entity?
4. Vì sao RETURN DISTINCT root không sửa được collection relationship bị thiếu?
5. Khi nào dùng OPTIONAL MATCH thay cho MATCH?
6. collect(DISTINCT ...) giải quyết loại trùng nào?
7. Vì sao hai nhánh relationship độc lập có thể tạo Cartesian product?
8. Correlated subquery giúp aggregate nhiều collection như thế nào?
9. Làm sao phân biệt nhiều result record với nhiều node trùng thật trong graph?
10. Vì sao @RelationshipProperties cần trả cả relationship và target node?
11. Khi nào nên trả DTO thay vì entity graph?
12. Vì sao phải aggregate root trước khi áp dụng phân trang?

Khi hoàn thành bài học, bạn cần đọc được hình dạng result set của custom Cypher, tạo một record đầy đủ cho mỗi root entity, gom đúng relationship và node đích, đồng thời phân biệt lỗi mapping với dữ liệu graph trùng thật. Đây là kỹ năng quan trọng khi dùng @Query hoặc custom Cypher để trả entity graph trong Spring Data Neo4j.

## Tài liệu tham khảo

- [Spring Data Neo4j – Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – Custom queries and custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Cypher Manual – Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual – OPTIONAL MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/)
- [Neo4j Cypher Manual – CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)

