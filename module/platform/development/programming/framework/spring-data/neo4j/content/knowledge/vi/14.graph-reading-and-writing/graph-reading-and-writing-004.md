# Đồng bộ relationship từ trạng thái đồ thị đối tượng

Trong Spring Data Neo4j (SDN), một entity có thể chứa các thuộc tính `@Relationship` để biểu diễn những node liên quan. Khi lưu entity, SDN dùng object graph cùng metadata ánh xạ để ghi node và các relationship thuộc phạm vi thao tác. Vì vậy, collection quan hệ trong Java cần được hiểu là một phần trạng thái graph mà ứng dụng đang muốn duy trì.

Điểm quan trọng là phân biệt thao tác lưu trạng thái của một object graph với thao tác cập nhật một relationship đơn lẻ. Nếu collection được dùng làm trạng thái đầy đủ của quan hệ nhưng entity lại được đọc thiếu dữ liệu, việc lưu có thể tạo ra kết quả ngoài ý muốn. Bài học này trình bày cách đồng bộ thêm, xóa, thay thế quan hệ và cách chọn Cypher tường minh khi không có toàn bộ graph cần thiết.

## 1. Graph lưu trữ và object graph trong Java

Giả sử một nhóm dự án có nhiều thành viên. Trong Neo4j, graph được biểu diễn bằng node và relationship:

~~~text
(Team)-[:HAS_MEMBER]->(Person)
~~~

Một entity SDN có thể mô tả các thành viên của nhóm:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Team")
public class Team {
    @Id
    private String id;

    private String name;

    @Relationship(type = "HAS_MEMBER", direction = Relationship.Direction.OUTGOING)
    private Set<Person> members = new HashSet<>();

    public void addMember(Person person) {
        members.add(person);
    }

    public void removeMember(Person person) {
        members.remove(person);
    }

    public void replaceMembers(Set<Person> newMembers) {
        members = new HashSet<>(newMembers);
    }

    // Constructor, getter và setter được lược bỏ.
}
~~~

Trong database, mỗi thành viên được nối với nhóm bằng một relationship riêng. Trong Java, `members` là collection các node `Person` mà SDN ánh xạ từ những relationship đó. Collection không phải property dạng danh sách được lưu nguyên khối trên node `Team`.

Object graph là hình dạng dữ liệu đã được đọc vào bộ nhớ. Nó có thể chứa node gốc, các node liên quan và relationship properties trong phạm vi mà thao tác đọc đã tải. Graph trong database có thể lớn hơn object graph hiện tại nhiều lần.

## 2. `save()` đồng bộ trạng thái quan hệ như thế nào?

Khi lưu một entity có các trường `@Relationship`, SDN sử dụng những trường đó để xác định các relationship thuộc graph được ánh xạ cho lần lưu. Với collection được tải đầy đủ và được dùng như trạng thái quan hệ của entity, việc thêm hoặc loại phần tử rồi gọi `save()` sẽ đồng bộ thay đổi tương ứng xuống Neo4j.

Ví dụ thêm thành viên:

~~~java
Team team = teamRepository.findById(teamId)
    .orElseThrow();
Person person = personRepository.findById(personId)
    .orElseThrow();

team.addMember(person);
Team saved = teamRepository.save(team);
~~~

Sau khi lưu, graph có relationship `HAS_MEMBER` từ `Team` đến `Person`. Dùng entity trả về từ `save()` khi cần trạng thái đã được SDN cập nhật, chẳng hạn ID hoặc version do framework quản lý.

Điều tương tự áp dụng khi xóa một thành viên khỏi collection đã được tải đầy đủ:

~~~java
team.removeMember(person);
teamRepository.save(team);
~~~
Khi collection đại diện cho trạng thái đầy đủ của relationship trong phạm vi ánh xạ, phần tử bị loại khỏi collection có thể tương ứng với relationship bị xóa khỏi graph. Vì vậy, thao tác xóa khỏi collection là một thay đổi persistence có ý nghĩa, không chỉ là thay đổi giao diện Java.

Không nên gọi `save()` với một entity mới chỉ có ID và collection rỗng nếu ý định chỉ là cập nhật tên nhóm. Một object như vậy không chứa các quan hệ hiện có mà thao tác lưu có thể cần duy trì. Hãy đọc entity cùng quan hệ cần quản lý, hoặc dùng một truy vấn cập nhật thuộc tính đơn giản nếu chỉ muốn đổi tên.

## 3. Thêm, xóa và thay thế collection

Ba thao tác này có ngữ nghĩa khác nhau và cần được thể hiện rõ trong API nghiệp vụ.

| Thao tác | Ý nghĩa | Trước khi lưu cần xác nhận |
| --- | --- | --- |
| Thêm một phần tử | Tạo relationship mới nếu chưa có theo quy tắc mô hình | Node nguồn và node đích tồn tại; quan hệ có được phép lặp không |
| Xóa một phần tử | Gỡ relationship nối đến node đích đó | Đã xác định đúng relationship cần xóa |
| Thay thế collection | Đặt tập relationship mong muốn bằng toàn bộ tập mới | Collection đầu vào là trạng thái đầy đủ, không phải trang dữ liệu |

Ví dụ thay thế toàn bộ danh sách thành viên:

~~~java
import java.util.HashSet;
import java.util.Set;

import org.springframework.transaction.annotation.Transactional;

@Transactional
public void replaceTeamMembers(String teamId, Set<String> personIds) {
    Team team = teamRepository.findById(teamId)
        .orElseThrow();

    Set<Person> members = new HashSet<>();
    personRepository.findAllById(personIds).forEach(members::add);

    if (members.size() != personIds.size()) {
        throw new IllegalArgumentException("Một hoặc nhiều thành viên không tồn tại");
    }

    team.replaceMembers(members);
    teamRepository.save(team);
}
~~~

Phương thức trên diễn tả rõ rằng `personIds` là danh sách đầy đủ các thành viên mong muốn sau cập nhật. Nếu `personIds` rỗng, nhóm sẽ không còn thành viên theo trạng thái mới. Đây là hành vi khác hẳn với yêu cầu thêm một thành viên.

Với API HTTP, nên phân biệt rõ lệnh thay thế toàn bộ collection và lệnh thêm/xóa một phần tử. Một request chứa danh sách rỗng có thể mang ý nghĩa xóa hết quan hệ nếu endpoint được thiết kế theo kiểu replace; đừng dùng cùng một payload cho cả hai ý nghĩa.

Không dựa vào giá trị `null` của collection để ngầm biểu thị “không cập nhật quan hệ”. Hãy thiết kế lệnh nghiệp vụ rõ ràng như `addMember`, `removeMember` hoặc `replaceMembers`, và xác định collection đã được nạp đầy đủ hay chưa trước khi lưu.

## 4. Không đồng bộ từ một object graph đọc thiếu

Một thao tác đọc không phải lúc nào cũng tải mọi relationship của node. Độ sâu mapping, truy vấn tùy chỉnh, projection, điều kiện lọc và giới hạn kết quả đều có thể làm object graph chỉ chứa một phần dữ liệu.

Ví dụ, database có năm thành viên nhưng truy vấn đọc chỉ trả về hai thành viên để hiển thị trang đầu. Collection hai phần tử đó không phải trạng thái đầy đủ của nhóm. Nếu dùng collection này để thay thế toàn bộ relationship khi lưu, ba relationship còn lại có thể bị mất.

Các tình huống cần đặc biệt chú ý:

- Truy vấn dùng `LIMIT`, `SKIP` hoặc điều kiện lọc trên relationship.
- Repository trả về projection hoặc DTO chỉ có một phần dữ liệu.
- Entity được đọc ở độ sâu không bao gồm các quan hệ mà use case định cập nhật.
- Object được giữ lâu trong bộ nhớ và graph đã bị transaction khác thay đổi.
- Ứng dụng tạo entity mới với ID đã có nhưng không nạp trạng thái quan hệ hiện tại.

Quy tắc thực hành: chỉ dùng collection làm trạng thái thay thế khi đã biết nó được tải đầy đủ cho phạm vi quan hệ cần quản lý. Nếu chỉ cần thêm hoặc xóa một relationship cụ thể, hãy dùng truy vấn Cypher nhắm đúng cặp node và quan hệ.

## 5. Cập nhật một relationship bằng Cypher

Khi không muốn tải toàn bộ collection, có thể thao tác trực tiếp trên relationship. Ví dụ thêm thành viên:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface TeamRepository extends Neo4jRepository<Team, String> {

@Query("""
    MATCH (team:Team {id: $teamId})
    MATCH (person:Person {id: $personId})
    MERGE (team)-[:HAS_MEMBER]->(person)
    """)
void addMember(@Param("teamId") String teamId,
               @Param("personId") String personId);
}
~~~

Xóa relationship giữa một nhóm và một người:

~~~java
@Query("""
    MATCH (team:Team {id: $teamId})
          -[membership:HAS_MEMBER]->
          (person:Person {id: $personId})
    DELETE membership
    """)
void removeMember(@Param("teamId") String teamId,
                  @Param("personId") String personId);
~~~

Các phương thức này có thể đặt trong `TeamRepository` kế thừa `Neo4jRepository<Team, String>`. Cần import `@Query` và `@Param` từ Spring Data Neo4j/Spring Data Repository tương ứng.

`MERGE` tìm hoặc tạo pattern relationship giữa hai node, nên các lần gọi tuần tự với cùng pattern sẽ dùng lại relationship đã có. Nếu mô hình cho phép nhiều relationship cùng loại giữa cùng hai node, cần bổ sung thuộc tính phân biệt vào pattern hoặc điều kiện truy vấn. Không xem riêng `MERGE` là ràng buộc duy nhất tuyệt đối dưới mọi tình huống đồng thời.

Truy vấn `DELETE membership` ở trên xóa mọi relationship `HAS_MEMBER` khớp với cặp node. Nếu chỉ muốn xóa một bản ghi quan hệ cụ thể trong mô hình có nhiều edge song song, hãy xác định relationship bằng ID nghiệp vụ hoặc thuộc tính riêng.

## 6. Đồng bộ relationship có thuộc tính

Nếu quan hệ có dữ liệu riêng như vai trò, ngày tham gia hoặc trạng thái, collection nên chứa lớp được đánh dấu `@RelationshipProperties` thay vì chỉ chứa node đích.

~~~java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {
    @RelationshipId
    private Long id;

    private String role;

    private LocalDate joinedAt;

    private String status;

    @TargetNode
    private Person person;
}
~~~

Trong `Team`, khai báo quan hệ tương ứng:

Thay trường `Set<Person> members` ở ví dụ đầu bài bằng trường `memberships` dưới đây:

~~~java
@Relationship(type = "HAS_MEMBER", direction = Relationship.Direction.OUTGOING)
private Set<Membership> memberships = new HashSet<>();
~~~

Khi đồng bộ collection này, ứng dụng không chỉ quản lý việc một người có thuộc nhóm hay không mà còn quản lý trạng thái của từng membership. Đổi `role` trên một phần tử là cập nhật property của relationship; loại phần tử khỏi collection có thể mang ý nghĩa xóa relationship; thêm phần tử mới có thể tạo relationship mới.

`@RelationshipId` là định danh nội bộ SDN sử dụng để nhận diện relationship đã ánh xạ. Nếu nghiệp vụ cần giữ lịch sử tham gia hoặc định danh ổn định, hãy thêm property nghiệp vụ riêng và thiết kế quy tắc vòng đời rõ ràng. Không xóa rồi tạo lại relationship nếu việc đó làm mất dữ liệu lịch sử cần bảo toàn.

## 7. Giao dịch và cập nhật đồng thời

Các bước đọc entity, kiểm tra điều kiện, thay đổi collection và lưu thường nên nằm trong một transaction nếu chúng tạo thành một nghiệp vụ nguyên tử:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TeamService {
    private final TeamRepository teamRepository;
    private final PersonRepository personRepository;

    public TeamService(TeamRepository teamRepository,
                      PersonRepository personRepository) {
        this.teamRepository = teamRepository;
        this.personRepository = personRepository;
    }

    @Transactional
    public void addMember(String teamId, String personId) {
        Team team = teamRepository.findById(teamId)
            .orElseThrow();
        Person person = personRepository.findById(personId)
            .orElseThrow();

        team.addMember(person);
        teamRepository.save(team);
    }
}
~~~

Transaction giúp các thao tác persistence tham gia cùng một đơn vị công việc, nhưng không tự giải quyết mọi xung đột logic. Hai request có thể cùng đọc một collection cũ rồi ghi các trạng thái khác nhau. Với entity có `@Version`, SDN có thể dùng optimistic locking cho thao tác lưu entity được quản lý bởi mapping. Với custom Cypher, cần tự đưa điều kiện version hoặc cơ chế kiểm soát cạnh tranh vào truy vấn nếu nghiệp vụ yêu cầu.

Đặc biệt, `@Version` trên node không tự biến mọi câu Cypher tùy chỉnh ghi relationship thành thao tác optimistic locking. Nếu truy vấn cập nhật relationship trực tiếp, hãy xác định cách kiểm tra phiên bản hoặc khóa nghiệp vụ phù hợp.

## 8. Phân biệt lưu trạng thái graph với lệnh nghiệp vụ

Một số use case phù hợp với cách tải entity, thay đổi collection rồi gọi `save()`. Ví dụ, màn hình quản trị cho phép chỉnh sửa toàn bộ danh sách thành viên của một nhóm và backend đã tải đầy đủ danh sách đó.

Những use case khác phù hợp hơn với lệnh nghiệp vụ tường minh:

- Thêm một thành viên vào nhóm có hàng nghìn thành viên.
- Xóa một membership được nhận diện bằng mã riêng.
- Đổi trạng thái một relationship mà không cần tải toàn bộ nhóm.
- Đếm thành viên hoặc kiểm tra tồn tại mà không cần tạo object graph.

Trong các trường hợp này, Cypher targeted update thường giảm lượng dữ liệu phải đọc và giúp phạm vi thay đổi rõ ràng. Có thể dùng `Neo4jClient` hoặc repository `@Query` tùy mức độ cần thiết của thao tác.

## 9. Kiểm thử đồng bộ object graph

Nên kiểm tra cả trạng thái Java sau khi lưu và graph thực tế trong Neo4j:

1. **Tạo quan hệ:** thêm một `Person` vào `Team.members`, lưu rồi xác nhận relationship `HAS_MEMBER` tồn tại.
2. **Xóa quan hệ:** xóa thành viên khỏi collection đầy đủ, lưu và xác nhận relationship tương ứng đã mất.
3. **Thay thế collection:** cung cấp tập thành viên mới đầy đủ và xác nhận graph chỉ còn các quan hệ mong muốn.
4. **Collection chưa đầy đủ:** đọc một phần danh sách, sau đó xác nhận ứng dụng không dùng phần đó để thay thế toàn bộ quan hệ.
5. **Relationship properties:** đổi `role` hoặc `status` và xác nhận property của đúng relationship được cập nhật.
6. **Cạnh tranh:** mô phỏng hai transaction cùng thay đổi quan hệ và xác nhận quy tắc xung đột được thực thi.

Có thể kiểm tra graph bằng truy vấn:

~~~cypher
MATCH (team:Team {id: $teamId})-[r:HAS_MEMBER]->(person:Person)
RETURN count(r) AS membershipCount,
       collect(person.id) AS memberIds
~~~

Khi cần so sánh danh sách, hãy sắp xếp kết quả hoặc so sánh theo tập ID thay vì dựa vào thứ tự mặc định của Neo4j.

## 10. Bài tập tự kiểm tra

1. `Team.members` biểu diễn dữ liệu gì trong object graph và Neo4j lưu dữ liệu đó ra sao?
2. Khi nào việc xóa một phần tử khỏi collection có thể dẫn đến xóa relationship trong database?
3. Vì sao không nên thay thế collection đầy đủ bằng một trang kết quả có `LIMIT`?
4. Khi nào nên dùng `save(team)` và khi nào nên dùng Cypher để thêm hoặc xóa một relationship đơn lẻ?
5. `@RelationshipProperties` thay đổi cách collection biểu diễn relationship như thế nào?
6. Vì sao `@Version` trên entity không tự bảo vệ mọi truy vấn Cypher tùy chỉnh?

Khi hoàn thành bài học, bạn cần hiểu cách SDN đồng bộ relationship từ object graph, phân biệt cập nhật toàn bộ trạng thái quan hệ với một lệnh ghi có phạm vi hẹp và biết cách bảo vệ graph khi entity được đọc thiếu hoặc nhiều transaction cùng cập nhật.
