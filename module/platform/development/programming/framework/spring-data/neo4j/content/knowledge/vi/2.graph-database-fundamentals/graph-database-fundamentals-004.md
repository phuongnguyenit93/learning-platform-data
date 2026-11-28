# Phân biệt hướng lưu quan hệ với hướng duyệt đồ thị

Bài học này thuộc chương **Nền tảng đồ thị** của module **SPRING_DATA_NEO4J**. Module tập trung xây dựng tầng dữ liệu đồ thị với Spring Data Neo4j thông qua node entity, relationship, repository và truy vấn Cypher; đồng thời rèn cách mô hình hóa quan hệ, ánh xạ dữ liệu, quản lý transaction và tối ưu truy vấn trong ứng dụng sử dụng Neo4j.

Khi làm việc với cơ sở dữ liệu đồ thị, ta thường thấy mũi tên trên một relationship và cũng dùng mũi tên trong câu lệnh Cypher. Hai cách dùng này có liên quan nhưng không cùng một ý nghĩa: **hướng lưu quan hệ** mô tả chiều của relationship trong mô hình đồ thị, còn **hướng duyệt đồ thị** mô tả chiều mà một truy vấn đi qua relationship để tìm dữ liệu. Hiểu rõ sự khác biệt giúp mô hình hóa đúng nghiệp vụ và viết truy vấn, ánh xạ entity chính xác.

## 1. Relationship có hướng trong mô hình đồ thị

Trong mô hình property graph của Neo4j, dữ liệu được tổ chức quanh các thành phần chính:

- **Node** biểu diễn một thực thể, chẳng hạn `Person`, `Product` hoặc `Order`.
- **Relationship** biểu diễn mối liên hệ giữa hai node. Relationship có kiểu, có node bắt đầu, node kết thúc và có thể mang thuộc tính.
- **Property** lưu các giá trị mô tả node hoặc relationship, chẳng hạn tên, thời điểm tạo hoặc trạng thái.

Một relationship có hướng từ node bắt đầu đến node kết thúc. Ví dụ:

```cypher
CREATE (an:Person {name: 'An'})
       -[:FOLLOWS {since: 2024}]->
       (binh:Person {name: 'Bình'});
```

Đồ thị sau khi tạo có thể được đọc như sau:

```text
(An:Person) -[:FOLLOWS {since: 2024}]-> (Bình:Person)
```

Relationship `FOLLOWS` bắt đầu tại node An và kết thúc tại node Bình. Điều này thể hiện An theo dõi Bình. Nếu nghiệp vụ hỏi “ai theo dõi Bình?”, ta cần tìm các relationship `FOLLOWS` đi vào node Bình.

Trong bài học này, **hướng lưu quan hệ** là cách gọi ngắn cho chiều bắt đầu–kết thúc được xác định khi relationship được tạo và được biểu diễn trong mô hình đồ thị. Đây là ý nghĩa logic của relationship. Không nên suy diễn rằng mũi tên trong mô hình cho biết chính xác cách Neo4j bố trí từng byte trên thiết bị lưu trữ; chi tiết lưu trữ vật lý là phần triển khai nội bộ của cơ sở dữ liệu.

Hướng của relationship có ý nghĩa nghiệp vụ. Với các quan hệ bất đối xứng như `FOLLOWS`, `OWNS`, `PLACED` hoặc `REPORTS_TO`, đảo chiều sẽ làm thay đổi ý nghĩa. Ví dụ `An -[:OWNS]-> Laptop` có nghĩa An sở hữu Laptop; `Laptop -[:OWNS]-> An` biểu diễn một quan hệ khác và thường không đúng với mô hình đã chọn.

## 2. Hướng duyệt là lựa chọn của truy vấn

Hướng duyệt đồ thị là chiều mà truy vấn đi qua relationship từ một node đang xét. Truy vấn có thể đi theo chiều relationship, đi ngược chiều relationship hoặc chấp nhận cả hai chiều. Việc chọn chiều duyệt không làm thay đổi relationship đã lưu.

Giả sử đồ thị có relationship:

```text
(An) -[:FOLLOWS]-> (Bình)
```

### Duyệt theo chiều relationship

Để tìm những người mà An theo dõi, truy vấn đi từ An theo chiều mũi tên:

```cypher
MATCH (an:Person {name: 'An'})-[:FOLLOWS]->(person:Person)
RETURN person;
```

Mẫu `(an)-[:FOLLOWS]->(person)` yêu cầu relationship đi ra từ `an` và đi vào `person`. Với dữ liệu ví dụ, kết quả là Bình.

### Duyệt ngược chiều relationship

Để tìm những người theo dõi Bình, truy vấn bắt đầu ở Bình và đi ngược chiều mũi tên:

```cypher
MATCH (binh:Person {name: 'Bình'})<-[:FOLLOWS]-(follower:Person)
RETURN follower;
```

Mẫu `(binh)<-[:FOLLOWS]-(follower)` vẫn mô tả relationship bắt đầu ở `follower` và kết thúc ở `binh`. Nó chỉ yêu cầu truy vấn nhìn từ node Bình về phía các node nguồn. Với dữ liệu ví dụ, kết quả là An.

Hai mẫu dưới đây mô tả cùng một chiều relationship, chỉ khác node được đặt ở vị trí bắt đầu trong mẫu truy vấn:

```cypher
MATCH (an)-[:FOLLOWS]->(binh)
RETURN an, binh;

MATCH (binh)<-[:FOLLOWS]-(an)
RETURN an, binh;
```

### Duyệt không chỉ định chiều

Nếu câu hỏi nghiệp vụ chỉ cần tìm node có liên hệ với một node khác mà không quan tâm relationship đi vào hay đi ra, Cypher cho phép bỏ mũi tên ở hai đầu:

```cypher
MATCH (person:Person {name: 'An'})-[:FOLLOWS]-(connected:Person)
RETURN connected;
```

Mẫu không định hướng này có thể khớp relationship theo cả hai chiều. Tuy nhiên, relationship trong đồ thị vẫn có node bắt đầu và node kết thúc. Cú pháp truy vấn không chỉ định chiều **không biến relationship thành quan hệ vô hướng**, cũng không tạo thêm relationship đảo chiều.

### Duyệt qua nhiều relationship

Với mẫu quan hệ có độ dài thay đổi, mũi tên tiếp tục xác định hướng đi của đường dẫn. Ví dụ, tìm những node có thể đến từ An qua từ một đến ba bước `FOLLOWS`:

```cypher
MATCH path = (an:Person {name: 'An'})-[:FOLLOWS*1..3]->(person:Person)
RETURN path;
```

Nếu bỏ mũi tên ở mẫu quan hệ có độ dài thay đổi, truy vấn có thể duyệt theo cả hai chiều. Hãy chọn hướng dựa trên câu hỏi nghiệp vụ để tránh lấy thêm đường dẫn không cần thiết.

## 3. So sánh hai khái niệm

| Khía cạnh | Hướng lưu quan hệ | Hướng duyệt đồ thị |
|---|---|---|
| Trả lời câu hỏi | Relationship đi từ node nào đến node nào? | Truy vấn đi từ node nào qua relationship theo chiều nào? |
| Được xác định khi nào? | Khi mô hình hóa và tạo relationship | Khi viết mẫu truy vấn hoặc thực hiện thao tác duyệt |
| Phạm vi tác động | Ý nghĩa của dữ liệu quan hệ trong đồ thị | Những đường đi mà truy vấn xem xét |
| Có làm thay đổi dữ liệu không? | Có, nếu tạo relationship theo chiều khác | Không, chỉ chọn cách đọc/duyệt dữ liệu |
| Ví dụ | `(An)-[:FOLLOWS]->(Bình)` | Từ An đi ra, từ Bình đi vào, hoặc khớp cả hai chiều |

Một cách kiểm tra nhanh là tự hỏi: “Tôi đang quyết định relationship sẽ mang ý nghĩa từ node nào đến node nào, hay chỉ đang quyết định truy vấn sẽ đi qua relationship theo chiều nào?”. Câu hỏi thứ nhất thuộc mô hình dữ liệu; câu hỏi thứ hai thuộc truy vấn.

## 4. Ánh xạ hướng relationship trong Spring Data Neo4j

Spring Data Neo4j ánh xạ node thành các lớp có `@Node` và relationship thành thuộc tính được đánh dấu bằng `@Relationship`. Thuộc tính `direction` cho biết hướng relationship được ánh xạ **so với node chứa thuộc tính đó**.

Ví dụ, lớp `Person` có danh sách những người mà người đó theo dõi:

```java
import java.util.List;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Relationship(
        type = "FOLLOWS",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Person> follows;
}
```

Với `direction = OUTGOING`, mỗi phần tử trong `follows` được nối từ node `Person` hiện tại đi ra. Nếu An có Bình trong danh sách `follows`, relationship được hiểu là:

```text
(An:Person) -[:FOLLOWS]-> (Bình:Person)
```

Nếu muốn ánh xạ các node có relationship `FOLLOWS` đi vào node hiện tại, có thể khai báo `direction = INCOMING`:

```java
@Relationship(
    type = "FOLLOWS",
    direction = Relationship.Direction.INCOMING
)
private List<Person> followers;
```

Khi thuộc tính `followers` nằm trên node Bình, các phần tử trong danh sách là những node nguồn như An. Relationship vẫn có chiều từ An đến Bình. `INCOMING` chỉ diễn tả chiều relationship so với node Bình đang được ánh xạ.

Nếu bỏ qua `direction`, Spring Data Neo4j mặc định sử dụng `OUTGOING`. Dù vậy, nên khai báo tường minh khi hướng có ý nghĩa quan trọng đối với nghiệp vụ, để người đọc entity dễ nhận ra node nguồn và node đích.

### Ánh xạ thuộc tính trên relationship

Relationship có thể chứa dữ liệu riêng, ví dụ thời điểm bắt đầu theo dõi. Khi cần ánh xạ các thuộc tính này, dùng `@RelationshipProperties` và `@TargetNode`:

```java
import java.time.LocalDate;
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Follow {

    @RelationshipId
    private Long relationshipId;

    private LocalDate since;

    @TargetNode
    private Person person;
}
```

Thuộc tính trên node nguồn có thể dùng lớp `Follow` thay cho `List<Person>`:

```java
@Relationship(
    type = "FOLLOWS",
    direction = Relationship.Direction.OUTGOING
)
private List<Follow> follows;
```

Trong ánh xạ này, `person` là node đích của relationship và `since` là thuộc tính của chính relationship. Việc dùng lớp quan hệ không thay đổi nguyên tắc về hướng: `OUTGOING` vẫn được tính từ node chứa thuộc tính `follows`.

## 5. Kết hợp hướng duyệt với repository và Cypher

Repository của Spring Data Neo4j có thể dùng phương thức dẫn xuất hoặc truy vấn Cypher tùy nhu cầu. Khi nghiệp vụ cần một hướng cụ thể, mẫu Cypher trong `@Query` nên thể hiện rõ mũi tên.

Ví dụ, repository sau tìm những người đang theo dõi một người có `id` cho trước:

```java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {id: $id})<-[:FOLLOWS]-(follower:Person)
        RETURN follower
        """)
    List<Person> findFollowers(@Param("id") String id);
}
```

Truy vấn bắt đầu ở `person` và tìm relationship đi vào node đó. Mũi tên `<-` thể hiện hướng duyệt ngược từ `person` về node nguồn `follower`; relationship trong dữ liệu vẫn có chiều `follower -[:FOLLOWS]-> person`.

Khi cần truy vấn bằng `Neo4jClient` hoặc dùng trực tiếp Cypher ở nơi khác trong tầng dữ liệu, nguyên tắc cũng giống như trên: mẫu quan hệ quyết định hướng khớp, còn dữ liệu relationship đã lưu giữ nguyên chiều của nó.

## 6. Chọn hướng mô hình hóa phù hợp

Hãy bắt đầu từ ý nghĩa nghiệp vụ của quan hệ:

1. **Xác định quan hệ có bất đối xứng hay không.** `FOLLOWS`, `OWNS` và `PLACED` thường có chiều rõ ràng. `KNOWS` hoặc `CONNECTED_TO` có thể được nghiệp vụ xem là đối xứng, nhưng relationship Neo4j vẫn được lưu với một chiều cụ thể.
2. **Chọn quy ước chiều nhất quán.** Ví dụ, luôn tạo `(:Person)-[:FOLLOWS]->(:Person)` từ người theo dõi đến người được theo dõi. Quy ước này làm cho dữ liệu, entity và truy vấn dễ đọc hơn.
3. **Chọn hướng duyệt theo câu hỏi.** Tìm người mà An theo dõi thì dùng `OUTGOING`; tìm người theo dõi An thì dùng `INCOMING`; tìm người có liên hệ bất kể chiều thì cân nhắc mẫu không định hướng.
4. **Ánh xạ từ đúng góc nhìn của node.** Với `@Relationship`, hãy đọc `OUTGOING` hoặc `INCOMING` so với node đang khai báo thuộc tính, không phải so với toàn bộ ứng dụng hay node được truy vấn đầu tiên.
5. **Đo hiệu năng trên truy vấn thực tế.** Khi đường đi dài hoặc đồ thị lớn, xem xét điểm bắt đầu, điều kiện lọc và số relationship được mở rộng. Dùng `EXPLAIN` để xem kế hoạch thực thi và `PROFILE` để đo truy vấn trên dữ liệu phù hợp.

Với quan hệ có ý nghĩa đối xứng, không nhất thiết phải tạo hai relationship ngược chiều chỉ để có thể truy vấn từ cả hai phía. Có thể dùng mẫu không định hướng khi phù hợp với yêu cầu. Chỉ tạo relationship theo cả hai chiều khi hai chiều thực sự đại diện cho hai sự kiện hoặc hai ý nghĩa nghiệp vụ độc lập, và cần có quy tắc duy trì nhất quán cho chúng.

## 7. Những nhầm lẫn thường gặp

**Cho rằng truy vấn đi ngược sẽ đảo chiều dữ liệu.** Mẫu `(b)<-[:FOLLOWS]-(a)` chỉ tìm relationship có chiều từ `a` đến `b`. Nó không sửa relationship thành `b -> a`.

**Cho rằng bỏ mũi tên nghĩa là relationship không có hướng.** Mẫu `(a)-[:FOLLOWS]-(b)` cho phép truy vấn khớp theo cả hai chiều. Bản thân relationship vẫn có node bắt đầu và node kết thúc.

**Tạo hai relationship đối nghịch cho mọi quan hệ.** Với một quan hệ đối xứng, việc lưu hai bản sao có thể làm tăng dữ liệu trùng lặp và khiến việc cập nhật, xóa hoặc đếm quan hệ phức tạp hơn. Hãy xác định rõ liệu hai chiều có phải hai sự kiện riêng hay chỉ là hai góc nhìn của cùng một relationship.

**Đọc sai `direction` trong entity.** `OUTGOING` không có nghĩa là “đi ra khỏi ứng dụng” hay “đi theo thứ tự truy vấn”. Nó luôn được xác định từ node mà thuộc tính `@Relationship` đang thuộc về.

**Dùng tên thuộc tính không thể hiện vai trò.** Các tên như `relatedPeople` thường không cho biết node nào là nguồn hay đích. Tên như `follows`, `followers`, `manager` hoặc `reports` giúp làm rõ góc nhìn của thuộc tính, miễn là nhất quán với mô hình nghiệp vụ.

## 8. Tự kiểm tra cách hiểu

Cho relationship:

```text
(Mai:Person) -[:REPORTS_TO]-> (Lan:Person)
```

- Muốn tìm người mà Mai báo cáo cho, truy vấn đi từ Mai theo chiều `OUTGOING`.
- Muốn tìm những người báo cáo cho Lan, truy vấn bắt đầu ở Lan và khớp relationship theo chiều `INCOMING`.
- Muốn tìm node có quan hệ `REPORTS_TO` với Lan mà chưa quan tâm chiều, có thể dùng mẫu không định hướng; tuy nhiên kết quả cần được diễn giải theo chiều thật của relationship.

Ba truy vấn minh họa:

```cypher
// Người mà Mai báo cáo cho
MATCH (mai:Person {name: 'Mai'})-[:REPORTS_TO]->(manager:Person)
RETURN manager;

// Những người báo cáo cho Lan
MATCH (lan:Person {name: 'Lan'})<-[:REPORTS_TO]-(report:Person)
RETURN report;

// Các node liên hệ với Lan theo một trong hai chiều
MATCH (lan:Person {name: 'Lan'})-[:REPORTS_TO]-(person:Person)
RETURN person;
```

Điểm cần nhớ là mũi tên khi tạo relationship xác định ý nghĩa và chiều của dữ liệu. Mũi tên trong Cypher và `direction` trong Spring Data Neo4j cho biết cách truy vấn hoặc ánh xạ relationship từ góc nhìn của node đang xét. Phân biệt được hai lớp này là nền tảng để thiết kế đồ thị nhất quán và khai thác Neo4j chính xác.
