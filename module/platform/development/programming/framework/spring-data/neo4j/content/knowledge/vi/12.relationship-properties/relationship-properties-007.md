# Hướng INCOMING và ý nghĩa TargetNode theo phía đang ánh xạ

Bài học này thuộc chương **Thuộc tính quan hệ** của module **SPRING_DATA_NEO4J**. Khi Spring Data Neo4j ánh xạ một relationship có thuộc tính, lớp `@RelationshipProperties` cần một trường `@TargetNode` để tham chiếu node ở đầu còn lại. Ý nghĩa của trường này phụ thuộc vào phía entity đang khai báo relationship. Đây là điểm đặc biệt dễ nhầm khi dùng `direction = INCOMING`.

Trong Neo4j, relationship luôn có chiều từ node bắt đầu đến node kết thúc. Nhưng khi đọc graph từ một entity, ứng dụng có thể nhìn relationship từ node ở đầu mũi tên hoặc node ở cuối mũi tên. Với `OUTGOING`, `@TargetNode` là node mà relationship đi tới. Với `INCOMING`, `@TargetNode` là node mà relationship đi ra từ đó. Nói cách khác, `@TargetNode` trỏ tới **node ở đầu còn lại so với entity đang được ánh xạ**, không phải lúc nào cũng là node ở đầu mũi tên trong graph.

## 1. Phân biệt chiều relationship trong graph và góc nhìn ánh xạ

Giả sử An theo dõi Bình:

```text
(An:Person) -[:FOLLOWS {since: 2024}]-> (Bình:Person)
```

Trong graph:

- An là node bắt đầu (start node/source) của relationship.
- Bình là node kết thúc (end node/target) của relationship.
- `since` là thuộc tính của relationship `FOLLOWS`.

Nếu entity gốc đang được tải là An, relationship đi ra khỏi An. Nếu entity gốc đang được tải là Bình, relationship đi vào Bình. Dữ liệu graph vẫn là một relationship An → Bình trong cả hai trường hợp; chỉ góc nhìn ánh xạ thay đổi.

| Entity đang ánh xạ | `direction` | Relationship trong graph | Node được gán vào `@TargetNode` |
|---|---|---|---|
| An | `OUTGOING` | An → Bình | Bình |
| Bình | `INCOMING` | An → Bình | An |

Vì vậy, khi đọc một thuộc tính `@TargetNode`, hãy hỏi “entity hiện tại đang nhìn sang node nào ở đầu còn lại?” thay vì mặc định “đây là node ở cuối mũi tên”.

## 2. Khai báo relationship properties với INCOMING

Ví dụ, cần tải danh sách người theo dõi một `Person`. Trong graph, relationship có chiều từ người theo dõi đến người được theo dõi:

```text
(An)-[:FOLLOWS {since: 2024}]->(Bình)
(Chi)-[:FOLLOWS {since: 2025}]->(Bình)
```

Khi entity gốc là Bình, các relationship `FOLLOWS` đi vào node đó. Khai báo entity như sau:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.Relationship.Direction;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Relationship(type = "FOLLOWS", direction = Direction.INCOMING)
    private List<FollowLink> followers = new ArrayList<>();

    public List<FollowLink> getFollowers() {
        return followers;
    }
}
```

Lớp mô tả relationship:

```java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class FollowLink {

    @RelationshipId
    private Long id;

    private LocalDate since;

    @TargetNode
    private Person person;

    public Person getPerson() {
        return person;
    }

    public LocalDate getSince() {
        return since;
    }
}
```

Khi tải Bình, mỗi phần tử trong `followers` đại diện một relationship `FOLLOWS` đi vào Bình. Trường `FollowLink.person` chứa node ở đầu còn lại, tức người theo dõi như An hoặc Chi. Dù tên annotation là `@TargetNode`, trong ngữ cảnh `INCOMING`, node này là nguồn của relationship theo chiều lưu trong graph.

Ví dụ kết quả có thể hình dung như sau:

```text
Person(Bình)
  followers:
    - FollowLink(since=2024, person=Person(An))
    - FollowLink(since=2025, person=Person(Chi))
```

`since` nằm trên relationship, còn `person` là node liên quan ở đầu còn lại. Không đặt `since` vào `Person` nếu thời điểm đó mô tả riêng lần An bắt đầu theo dõi Bình.

## 3. Vì sao TargetNode thay đổi theo phía đang ánh xạ?

`@RelationshipProperties` mô tả phần dữ liệu nằm trên cạnh và cung cấp tham chiếu tới node còn lại của cạnh. Nó được sử dụng từ một node gốc cụ thể. Khi chiều relationship thay đổi so với node gốc, node ở đầu còn lại cũng được xác định theo góc nhìn đó.

Với ví dụ `An -[:FOLLOWS]-> Bình`:

- Từ An, relationship là `OUTGOING`; `@TargetNode` trỏ tới Bình.
- Từ Bình, relationship là `INCOMING`; `@TargetNode` trỏ tới An.

`@TargetNode` không phải annotation để khai báo start node hoặc end node cố định trong database. Nó không thay thế hai đầu mút vật lý của relationship và cũng không thay đổi mũi tên. Trong Spring Data Neo4j, annotation này chỉ ra node entity ở phía đối diện với node đang sở hữu thuộc tính relationship.

Đây cũng là lý do cùng một lớp relationship properties có thể được sử dụng từ các entity có góc nhìn khác nhau, miễn là kiểu `@TargetNode` phù hợp với node ở đầu còn lại. Tên trường nên thể hiện vai trò theo domain hoặc dùng tên trung tính như `otherPerson` nếu lớp được dùng từ nhiều phía.

## 4. So sánh OUTGOING và INCOMING

Nếu entity gốc là An và cần lấy những người An theo dõi, dùng `OUTGOING`:

```java
@Relationship(type = "FOLLOWS", direction = Direction.OUTGOING)
private List<FollowLink> followees = new ArrayList<>();
```

Với cùng lớp `FollowLink`, `@TargetNode` của từng phần tử lúc này là người được theo dõi, ví dụ Bình. Relationship vẫn lưu `since` trên cạnh.

| Khía cạnh | `OUTGOING` | `INCOMING` |
|---|---|---|
| Góc nhìn | Đi từ node gốc theo mũi tên | Đi từ node gốc ngược về phía nguồn |
| Hình dạng Cypher | `(root)-[:FOLLOWS]->(other)` | `(root)<-[:FOLLOWS]-(other)` |
| `@TargetNode` | Node đích của relationship trong graph | Node nguồn của relationship trong graph |
| Ví dụ khi root là Bình | Những người Bình theo dõi qua relationship đi ra từ Bình | Những người theo dõi Bình qua relationship đi vào Bình |

Chiều mặc định của `@Relationship` là `OUTGOING`. Các thuộc tính cần ánh xạ relationship đi vào phải khai báo rõ `direction = Direction.INCOMING`; nếu quên, SDN sẽ tìm quan hệ theo chiều mặc định và có thể không tải được các node mong muốn.

## 5. Truy vấn Cypher tương đương

Khi entity gốc là Bình, mẫu Cypher tìm người theo dõi Bình là:

```cypher
MATCH (person:Person {id: $id})<-[r:FOLLOWS]-(follower:Person)
RETURN person, r, follower;
```

Trong mẫu trên:

- `person` là node gốc được tìm theo ID, tương ứng Bình.
- `r` là relationship `FOLLOWS`, có thuộc tính `since`.
- `follower` là node nguồn của relationship, tương ứng An hoặc Chi.

Mẫu này có thể đọc theo chiều từ Bình nhìn ngược qua mũi tên đến người theo dõi. Nó không có nghĩa relationship được lưu thành `Bình → An`.

Nếu muốn chỉ lấy những người theo dõi từ một ngày nhất định, có thể lọc trên thuộc tính relationship:

```cypher
MATCH (person:Person {id: $id})<-[r:FOLLOWS]-(follower:Person)
WHERE r.since >= date('2025-01-01')
RETURN follower, r.since AS since
ORDER BY since;
```

Điều kiện lọc và `ORDER BY` được thực hiện trong Cypher. Kiểu collection Java như `List<FollowLink>` không tự quy định thứ tự bền vững của relationship trong Neo4j; nếu thứ tự quan trọng, hãy xác định thứ tự trong truy vấn hoặc lưu một thuộc tính thứ tự trên relationship.

## 6. Vai trò của RelationshipId

Lớp `@RelationshipProperties` cần có một trường `@RelationshipId` để Spring Data Neo4j nhận diện relationship đã tồn tại khi ghi lại entity graph. ID này là định danh nội bộ do persistence quản lý, không phải khóa nghiệp vụ của cạnh.

Ví dụ:

```java
@RelationshipProperties
public class FollowLink {

    @RelationshipId
    private Long id;

    private LocalDate since;

    @TargetNode
    private Person person;
}
```

Khi một relationship đã được tải, SDN có thể dùng ID nội bộ đó để xác định cạnh tương ứng khi cập nhật và tránh ghi đè nhầm relationship properties. Với relationship mới, ứng dụng không tự gán ID nội bộ. Hãy để framework và Neo4j quản lý giá trị này.

Nếu nghiệp vụ cần một mã công khai cho lần theo dõi, chẳng hạn mã sự kiện hoặc mã đăng ký, hãy khai báo một property riêng như `followEventId` và tạo ràng buộc duy nhất phù hợp. Không dùng `@RelationshipId` làm ID công khai hoặc tham chiếu lâu dài từ hệ thống khác.

## 7. Một relationship properties class cần đúng một TargetNode

Mỗi lớp `@RelationshipProperties` phải khai báo đúng một trường `@TargetNode` để chỉ node ở đầu còn lại. Ví dụ hợp lệ:

```java
@RelationshipProperties
public class FollowLink {

    @RelationshipId
    private Long id;

    private LocalDate since;

    private boolean notificationsEnabled;

    @TargetNode
    private Person otherPerson;
}
```

Không khai báo hai trường `@TargetNode` trong cùng lớp để cố lưu cả hai đầu của relationship. Node gốc đã được xác định bởi entity chứa thuộc tính `@Relationship`; `@TargetNode` xác định đầu còn lại. Nếu cần truy cập cả hai đầu một cách độc lập hoặc relationship có vòng đời nghiệp vụ phức tạp, hãy cân nhắc mô hình hóa mối quan hệ thành node trung gian có ID ứng dụng.

## 8. Lưu ý khi ánh xạ hai chiều

Có thể khai báo quan hệ ở cả hai entity, ví dụ An có danh sách `followees` theo `OUTGOING`, còn Bình có danh sách `followers` theo `INCOMING`. Tuy nhiên, hai thuộc tính này mô tả cùng một tập relationship từ hai góc nhìn.

Việc ánh xạ hai chiều có thể làm entity graph phức tạp hơn. Khi SDN tải một node, nó có thể tiếp tục tải các quan hệ được khai báo ở node liên quan. Nếu nhiều lớp liên kết hai chiều với nhau, phạm vi graph cần ánh xạ có thể mở rộng đáng kể. Vì vậy:

- Chỉ khai báo cả hai chiều khi use case thực sự cần điều hướng từ cả hai phía.
- Đảm bảo type và direction mô tả cùng một relationship vật lý, theo hai góc nhìn đối nhau.
- Tránh để `equals()`, `hashCode()` hoặc `toString()` đi đệ quy qua graph hai chiều.
- Dùng projection hoặc truy vấn chuyên biệt nếu chỉ cần một phần dữ liệu.
- Kiểm tra integration test để xác nhận việc lưu từ một phía không tạo relationship trùng ngoài ý muốn.

Nếu chỉ cần tải người theo dõi một người, một thuộc tính `INCOMING` trên entity gốc có thể là đủ. Không cần thêm thuộc tính ngược ở mọi entity chỉ để tiện truy cập trong bộ nhớ.

## 9. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@TargetNode` chứa nhầm node | Hiểu target luôn là đầu mũi tên của graph | Xác định node gốc; với `INCOMING`, target node của mapping là node nguồn của relationship |
| Không tải được quan hệ đi vào | Bỏ qua `direction`, nên SDN dùng mặc định `OUTGOING` | Khai báo `direction = Direction.INCOMING` |
| Đưa thuộc tính cạnh vào node | Không dùng `@RelationshipProperties` | Tạo lớp quan hệ và đánh dấu `@RelationshipProperties` |
| Thiếu `@RelationshipId` | SDN không thể nhận diện relationship hiện có khi cập nhật graph | Thêm trường `@RelationshipId` theo yêu cầu mapping |
| Có nhiều trường `@TargetNode` | Cố biểu diễn cả hai đầu trong lớp relationship properties | Chỉ giữ một trường cho node ở đầu còn lại |
| Dùng relationship ID làm mã nghiệp vụ | Nhầm ID persistence với ID công khai | Tạo property nghiệp vụ riêng và constraint phù hợp |
| Graph tải quá rộng | Khai báo quan hệ hai chiều xuyên nhiều entity | Giới hạn graph, dùng projection hoặc truy vấn riêng |

## 10. Kiểm tra ánh xạ INCOMING

Với dữ liệu:

```cypher
CREATE (an:Person {id: 'p-an', name: 'An'})
CREATE (binh:Person {id: 'p-binh', name: 'Bình'})
CREATE (an)-[:FOLLOWS {since: date('2024-01-01')}]->(binh);
```

Hãy kiểm tra các điểm sau bằng integration test:

1. Tải entity Bình bằng ID `p-binh`.
2. Xác nhận thuộc tính `followers` có một phần tử.
3. Xác nhận `followers.get(0).getPerson()` là An (`p-an`), tức node ở đầu còn lại của relationship.
4. Xác nhận thuộc tính `since` thuộc về relationship và giữ đúng ngày.
5. Kiểm tra Cypher trực tiếp vẫn cho thấy relationship bắt đầu tại An và kết thúc tại Bình.
6. Thay đổi thuộc tính relationship, lưu lại aggregate theo đúng phạm vi quản lý và xác minh property trên cạnh được cập nhật.
7. Xóa một phần tử khỏi collection đầy đủ rồi kiểm tra hành vi xóa relationship theo mapping và transaction của ứng dụng.

Các kiểm tra này xác nhận đồng thời hai việc: mũi tên trong graph không bị đảo và `@TargetNode` được ánh xạ theo node gốc đang xét.

## 11. Nguyên tắc cần nhớ

- Relationship trong Neo4j luôn có start node và end node cố định theo hướng đã lưu.
- `direction = INCOMING` có nghĩa relationship đi vào entity đang ánh xạ.
- `@TargetNode` chỉ node ở đầu còn lại so với entity gốc.
- Với `OUTGOING`, node ở đầu còn lại là node đích trong graph; với `INCOMING`, node ở đầu còn lại là node nguồn trong graph.
- Lớp `@RelationshipProperties` cần đúng một `@TargetNode` và một trường `@RelationshipId` theo mapping của Spring Data Neo4j.
- Không sử dụng relationship ID nội bộ làm mã nghiệp vụ hoặc ID công khai.
- Chỉ ánh xạ hai chiều khi cần thiết và kiểm tra phạm vi graph được tải.

Khi đọc một relationship properties object, hãy luôn xác định entity nào đang sở hữu thuộc tính relationship. Đối với `INCOMING`, `@TargetNode` chính là node mà relationship đi ra từ đó. Nắm được góc nhìn này giúp ánh xạ chính xác các quan hệ đi vào, giữ nguyên ý nghĩa của dữ liệu graph và tránh đảo nhầm vai trò giữa hai node.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1 – Metadata-based Mapping: Map relationship properties](https://docs.spring.io/spring-data/neo4j/reference/8.1/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j – Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
