# Phân biệt thuộc tính chưa được tải, null và collection rỗng

Bài học này thuộc chương **Đọc và ghi đồ thị** của module **SPRING_DATA_NEO4J**. Khi đọc dữ liệu từ Neo4j, một thuộc tính Java có thể đang chứa `null`, một collection rỗng hoặc dữ liệu đã được tải. Ba trạng thái này trông có vẻ gần nhau nhưng mang ý nghĩa khác nhau. Nhầm lẫn chúng có thể khiến API trả lời sai, hoặc khiến một thao tác `save` vô tình xóa relationship mà ứng dụng chưa từng tải.

Trong Neo4j, node và relationship lưu dữ liệu theo mô hình property graph. Property không lưu giá trị `null`; khi gán `null`, property được xóa. Relationship cũng không có trạng thái “collection rỗng” được lưu trên node. Một collection trong entity là cách Java biểu diễn các relationship mà truy vấn đã đưa vào kết quả. Vì vậy, **chưa được tải là trạng thái của dữ liệu trong lần đọc hoặc read model; `null` và collection rỗng là trạng thái của object Java**.

## 1. Ba trạng thái cần phân biệt

Giả sử entity `Team` có thuộc tính tên và danh sách thành viên:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Team")
public class Team {

    @Id
    private String id;

    private String name;

    @Relationship(type = "HAS_MEMBER", direction = Relationship.Direction.OUTGOING)
    private List<Person> members = new ArrayList<>();
}
```

Ba khái niệm cần hiểu như sau:

| Trạng thái | Ý nghĩa trong Java | Có thể kết luận gì về graph? |
|---|---|---|
| Chưa được tải | Truy vấn hoặc projection chưa cung cấp dữ liệu cho trường đó | Chưa thể kết luận có hay không có property/relationship |
| `null` | Tham chiếu Java không trỏ tới giá trị nào | Với scalar, property có thể không tồn tại; với relationship, không thể suy ra nếu truy vấn chưa tải quan hệ |
| Collection rỗng | Collection tồn tại nhưng có 0 phần tử | Chỉ kết luận không có phần tử phù hợp nếu truy vấn đã tải đầy đủ đúng relationship cần xét |

Ví dụ, một `Team` có thể thực sự không có thành viên. Nếu truy vấn đã tải toàn bộ `HAS_MEMBER` và không tìm thấy cạnh nào, `members` rỗng là kết quả hợp lý. Nhưng nếu một custom query chỉ trả về node `Team` mà không trả relationship, collection được khởi tạo sẵn thành `new ArrayList<>()` cũng có thể vẫn rỗng. Trong trường hợp thứ hai, collection rỗng không chứng minh rằng team không có thành viên.

## 2. Neo4j không lưu property có giá trị null

Property của node hoặc relationship chỉ tồn tại khi có giá trị hợp lệ. Cypher không lưu `null` như một property độc lập. Ví dụ:

```cypher
MATCH (c:Customer {id: $id})
SET c.nickname = null;
```

Câu lệnh trên xóa property `nickname` khỏi node. Khi đọc:

```cypher
MATCH (c:Customer {id: $id})
RETURN c.nickname AS nickname;
```

nếu property không tồn tại, biểu thức `c.nickname` trả về `null`. Vì vậy, với một node đã được đọc đầy đủ, field Java `String nickname` có giá trị `null` thường biểu diễn việc property tương ứng không có trong graph.

Tuy nhiên, cần phân biệt trường hợp node không tồn tại. Truy vấn:

```cypher
MATCH (c:Customer {id: $id})
RETURN c;
```

không trả record nào nếu không tìm thấy customer. Đây là kết quả `Optional.empty()` ở tầng repository, khác với một customer tồn tại nhưng thiếu property `nickname`.

Với relationship, nếu không có cạnh nối tới node khác thì không có relationship object để ánh xạ. Không có một property `members = null` hoặc `members = []` được ghi vào node `Team`; đó chỉ là cách object Java biểu diễn kết quả đọc.

## 3. Collection rỗng có ý nghĩa khi đã tải đầy đủ

Giả sử graph chứa:

```text
(Team:Platform)-[:HAS_MEMBER]->(Person:An)
(Team:Platform)-[:HAS_MEMBER]->(Person:Bình)
```

Nếu truy vấn đã lấy đầy đủ relationship `HAS_MEMBER`, `members` cần có hai phần tử. Nếu team thực sự không có relationship loại này, collection được tải đầy đủ sẽ không có phần tử.

Collection rỗng có thể diễn đạt hai tình huống khác nhau tùy hợp đồng truy vấn:

- **Đã tải và không có kết quả:** truy vấn kiểm tra toàn bộ `HAS_MEMBER` của team, nhưng không tìm thấy relationship phù hợp.
- **Chưa tải:** truy vấn chỉ lấy node gốc hoặc chỉ lấy một projection không chứa `members`; collection rỗng có thể chỉ là giá trị khởi tạo trong Java.

Ngoài ra, một collection có thể được tải theo bộ lọc. Ví dụ, truy vấn chỉ lấy thành viên đang hoạt động. Collection rỗng khi đó có nghĩa “không có thành viên đang hoạt động phù hợp với điều kiện”, không có nghĩa “team không có bất kỳ thành viên nào”.

Do đó, đừng diễn giải `isEmpty()` như một sự thật về toàn bộ graph nếu chưa biết dữ liệu được tải bằng truy vấn nào và điều kiện lọc ra sao.

## 4. Spring Data Neo4j tải graph theo kết quả truy vấn

Spring Data Neo4j ánh xạ node và relationship dựa trên metadata của entity cùng dữ liệu mà truy vấn trả về. Các finder được tạo tự động từ repository sử dụng mapping metadata để lấy những relationship đã khai báo trong entity.

Với custom query, ứng dụng chịu trách nhiệm trả đủ dữ liệu để SDN có thể hydrate entity. Một truy vấn chỉ trả node gốc:

```cypher
MATCH (t:Team {id: $id})
RETURN t;
```

không mang theo tập relationship `HAS_MEMBER` trong record. Không được xem collection chưa được cung cấp là bằng chứng rằng graph không có thành viên.

Khi muốn ánh xạ một team cùng các thành viên, custom query cần trả node gốc, relationship và các node liên quan trong cùng một record. Ví dụ:

```cypher
MATCH (t:Team {id: $id})
OPTIONAL MATCH (t)-[r:HAS_MEMBER]->(p:Person)
RETURN t, collect(r), collect(p);
```

`OPTIONAL MATCH` giữ lại team ngay cả khi không có thành viên. `collect()` gom các relationship và node đích vào một record cho mỗi team; khi không có kết quả phù hợp, các collection được gom là rỗng. Hình dạng kết quả này giúp SDN có đủ thông tin để ánh xạ collection relationship.

Trong repository, có thể khai báo truy vấn này như sau:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface TeamRepository extends Neo4jRepository<Team, String> {

    @Query("""
        MATCH (t:Team {id: $id})
        OPTIONAL MATCH (t)-[r:HAS_MEMBER]->(p:Person)
        RETURN t, collect(r), collect(p)
        """)
    Optional<Team> findWithMembersById(@Param("id") String id);
}
```

Nếu truy vấn trả nhiều record cho cùng một root node, chẳng hạn một record cho mỗi thành viên, việc ánh xạ có thể tạo root trùng hoặc không gom đầy đủ relationship như mong đợi. Tài liệu SDN khuyến nghị thu thập các relationship và node liên quan để có một record cho mỗi root node.

## 5. Không có cờ unloaded tự động trong collection Java

Một entity Java thông thường không tự mang theo thông tin cho biết mỗi relationship collection đã được tải đầy đủ hay chưa. Ví dụ:

```java
@Relationship(type = "HAS_MEMBER")
private List<Person> members = new ArrayList<>();
```

Sau khi tạo object mới, `members` đã rỗng dù chưa truy vấn Neo4j. Nếu một truy vấn tùy biến chỉ trả node `Team`, field vẫn có thể giữ collection rỗng đã khởi tạo. Từ riêng giá trị `members.isEmpty()`, code không thể biết collection rỗng vì không có relationship hay vì query không đưa relationship vào kết quả.

Tương tự, nếu field không được khởi tạo:

```java
@Relationship(type = "HAS_MEMBER")
private List<Person> members;
```

giá trị `null` chỉ cho biết tham chiếu Java hiện không có collection. Nó không phải một cờ được SDN đảm bảo để biểu thị “chưa tải”. Constructor, factory, mapper tùy chỉnh hoặc logic ứng dụng đều có thể ảnh hưởng tới giá trị này.

Vì vậy, hãy xác định trạng thái tải từ hợp đồng của phương thức đọc, projection hoặc DTO. Không suy đoán trạng thái tải chỉ từ `null` hay `isEmpty()`.

## 6. Dùng read model để biểu diễn rõ dữ liệu đã tải

Nếu một use case chỉ cần một phần graph, nên tạo projection hoặc DTO dành riêng cho thao tác đọc. Ví dụ:

```java
import java.util.List;

public record PersonSummary(String id, String name) {
}

public record TeamMembersView(
    String id,
    String name,
    List<PersonSummary> members,
    boolean membersLoaded
) {
}
```

Service có thể dùng `Neo4jClient` để trả một read model với danh sách thành viên đã được tải:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;

public Optional<TeamMembersView> findTeamWithMembers(String teamId) {
    return neo4jClient.query("""
            MATCH (t:Team {id: $id})
            OPTIONAL MATCH (t)-[:HAS_MEMBER]->(p:Person)
            RETURN t.id AS id,
                   t.name AS name,
                   collect(p{.id, .name}) AS members
            """)
        .bind(teamId).to("id")
        .fetchAs(TeamMembersView.class)
        .mappedBy((typeSystem, record) -> new TeamMembersView(
            record.get("id").asString(),
            record.get("name").asString(),
            record.get("members").asList(member -> new PersonSummary(
                member.get("id").asString(),
                member.get("name").asString()
            )),
            true
        ))
        .one();
}
```

Với phương thức này:

- `Optional.empty()` nghĩa là không tìm thấy team.
- `Optional` có giá trị và `members` rỗng nghĩa là team tồn tại, truy vấn đã kiểm tra relationship `HAS_MEMBER`, nhưng không có thành viên phù hợp.
- `membersLoaded = true` cho biết read model này đã tải danh sách thành viên theo đúng hợp đồng truy vấn.

Nếu một use case khác chỉ lấy thông tin cơ bản của team, có thể dùng DTO khác không chứa `members`, hoặc thêm trạng thái tải rõ ràng. Không nên dùng một entity ghi chung cho mọi read shape nếu các truy vấn chỉ tải những phần graph khác nhau.

## 7. Dùng @ReadOnlyProperty cho association chỉ đọc

Nếu entity cần hiển thị một relationship nhưng ứng dụng không muốn persistence của entity đó ghi collection này, có thể đánh dấu `@ReadOnlyProperty`:

```java
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.neo4j.core.schema.Relationship;

@ReadOnlyProperty
@Relationship(type = "HAS_MEMBER")
private List<Person> members = new ArrayList<>();
```

`@ReadOnlyProperty` cho phép property được hydrate khi đọc nhưng không tham gia ghi như property thông thường. Khi áp dụng lên relationship, cần lưu ý các node liên quan trong collection sẽ không được persist thông qua association này nếu chúng không được liên kết ở nơi khác.

Annotation này phù hợp với association dùng để hiển thị hoặc đọc báo cáo. Nó không phải lazy-loading marker và cũng không tự ghi nhận collection đã được tải hay chưa. Nếu use case cần cập nhật thành viên, hãy dùng một mô hình ghi riêng hoặc câu lệnh Cypher rõ ràng.

## 8. Vì sao lưu entity chưa tải đầy đủ có thể làm mất relationship?

`save()` của repository hoặc `Neo4jTemplate` lưu entity cùng các relationship mà object graph mô tả. Nếu một entity được đọc bằng custom query không tải đủ relationship, rồi ứng dụng thay đổi một field và gọi `save()` trên object đó, collection chưa tải có thể bị hiểu như trạng thái collection mà object muốn ghi.

Ví dụ nguy hiểm:

```java
Team team = teamRepository.findSummaryById(teamId)
    .orElseThrow(); // Query chỉ trả node Team, không tải HAS_MEMBER

team.setName("Platform Engineering");
teamRepository.save(team); // Không nên giả định các relationship chưa tải được giữ nguyên
```

Vấn đề nằm ở chỗ object `team` không đại diện đầy đủ graph nhưng lại được dùng như một entity ghi toàn bộ. Tài liệu Spring Data Neo4j cảnh báo các entity được hydrate một phần nếu tái sử dụng cho thao tác lưu tiếp theo có thể gây mất dữ liệu.

Các cách xử lý phù hợp:

1. **Tải đầy đủ aggregate trước khi ghi.** Dùng finder hoặc custom query trả đủ các relationship thuộc phạm vi quản lý, sau đó thay đổi và lưu.
2. **Dùng read model riêng.** DTO/projection chỉ phục vụ đọc, không chuyển ngược thành entity rồi gọi `save()`.
3. **Cập nhật trực tiếp thuộc tính cần đổi bằng Cypher.** Cách này tránh ghi lại các association không liên quan.
4. **Dùng `@ReadOnlyProperty` cho association chỉ đọc.** Chỉ áp dụng khi collection đó không được quản lý bởi thao tác save của entity.
5. **Dùng projection có chủ đích khi lưu.** `saveAs` và `saveAllAs` cho phép giới hạn phần graph được ghi; cần hiểu rõ projection và không tái sử dụng instance trả về như một aggregate đã hydrate đầy đủ.

Ví dụ cập nhật riêng tên team bằng Cypher:

```java
neo4jClient.query("""
        MATCH (t:Team {id: $id})
        SET t.name = $name
        """)
    .bind(teamId).to("id")
    .bind("Platform Engineering").to("name")
    .run();
```

Với thao tác cập nhật nhiều node hoặc relationship phải thành công cùng nhau, đặt câu lệnh trong transaction phù hợp.

## 9. Collection được lọc không đại diện cho toàn bộ relationship

Một truy vấn có thể chỉ tải các thành viên đang hoạt động:

```cypher
MATCH (t:Team {id: $id})
OPTIONAL MATCH (t)-[:HAS_MEMBER]->(p:Person)
WHERE p.active = true
RETURN t, collect(p) AS activeMembers;
```

Collection kết quả mô tả các thành viên thỏa điều kiện `active = true`. Nếu danh sách rỗng, vẫn có thể tồn tại các thành viên không hoạt động. Do đó, không dùng danh sách lọc làm collection đầy đủ để thay thế quan hệ `HAS_MEMBER` trong entity rồi lưu lại.

Phân trang cũng tạo ra vấn đề tương tự. Một trang đầu tiên chỉ chứa một phần relationship; nó không phải toàn bộ collection. Nếu cần chỉnh sửa aggregate, hãy tải đầy đủ phần quan hệ thuộc quyền quản lý hoặc thực hiện lệnh ghi nhắm đúng relationship cần thay đổi.

## 10. Phân biệt trong service và API

Hãy đặt hợp đồng rõ ràng cho từng phương thức:

| Hợp đồng | Kết quả khi không có dữ liệu liên quan | Ý nghĩa |
|---|---|---|
| `findTeamById` tải đầy đủ `members` | `members = []` | Team tồn tại và không có thành viên |
| `findTeamSummary` không tải `members` | Không có field `members` trong DTO | Use case không yêu cầu tải thành viên |
| `findActiveMembers` tải theo điều kiện active | Danh sách rỗng | Không có thành viên phù hợp điều kiện, không khẳng định không có thành viên khác |
| `findTeamById` không tìm thấy root | `Optional.empty()` | Team không tồn tại |
| Scalar property `nickname` không tồn tại trên node đã đọc | `nickname = null` | Node tồn tại nhưng property không được lưu |

Nếu API cần phân biệt “chưa yêu cầu tải” với “đã tải nhưng rỗng”, hãy thể hiện điều đó trong kiểu response hoặc metadata. Không nên để client suy luận từ `null` một cách ngầm định nếu hợp đồng API không quy định rõ.

## 11. Kiểm tra hành vi bằng integration test

Nên tạo các trường hợp riêng để tránh test chỉ kiểm tra collection không null:

1. **Team không có thành viên:** tạo node `Team` không có `HAS_MEMBER`, dùng truy vấn tải đầy đủ và xác nhận collection rỗng.
2. **Team có thành viên:** tạo hai relationship, tải đầy đủ và xác nhận collection có hai phần tử.
3. **Chỉ tải node gốc:** dùng custom query không trả relationship và xác nhận read model không tuyên bố rằng danh sách đã được tải đầy đủ.
4. **Collection lọc:** truy vấn chỉ lấy thành viên hoạt động, xác nhận kết quả không được dùng để kết luận tổng số thành viên.
5. **Scalar property vắng mặt:** đọc node không có `nickname`, xác nhận field reference là `null` trong mapping đầy đủ.
6. **Không tìm thấy node:** xác nhận repository trả `Optional.empty()` thay vì một entity có field null.
7. **Không làm mất relationship khi cập nhật:** đọc một read model rút gọn, cập nhật scalar bằng Cypher hoặc tải đầy đủ aggregate trước khi save, rồi xác nhận relationship vẫn còn.

Với custom query có relationship, hãy kiểm tra record shape. Spring Data Neo4j làm việc theo record; query nên trả một record cho mỗi root node và gom các relationship cùng node liên quan bằng `collect()` khi cần ánh xạ collection.

## 12. Nguyên tắc cần nhớ

- Neo4j không lưu property có giá trị `null`; gán `null` sẽ xóa property.
- Relationship không được lưu dưới dạng property collection trên node; collection Java biểu diễn các relationship được ánh xạ.
- `null` là trạng thái tham chiếu Java, không phải cờ unloaded do SDN bảo đảm.
- Collection rỗng chỉ chứng minh không có kết quả khi truy vấn đã tải đầy đủ đúng relationship và điều kiện lọc đã được hiểu rõ.
- Custom query phải trả đủ dữ liệu để hydrate entity; với nhiều relationship, thường cần `collect()` để có một record cho mỗi root.
- Không lưu lại entity hydrate một phần như thể nó là toàn bộ aggregate.
- Dùng DTO/projection cho read model, `@ReadOnlyProperty` cho association chỉ đọc, và Cypher nhắm mục tiêu cho cập nhật cục bộ.

Khi nhìn thấy `null` hoặc collection rỗng, hãy kiểm tra hợp đồng truy vấn trước khi kết luận về graph. Chỉ khi biết field đã được tải đầy đủ, phạm vi lọc và node gốc được xác định rõ, ứng dụng mới có thể diễn giải trạng thái Java thành ý nghĩa dữ liệu chính xác.

## Tài liệu tham khảo

- [Spring Data Neo4j – Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – Metadata-based mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4jOperations API – save and saveAs](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jOperations.html)
