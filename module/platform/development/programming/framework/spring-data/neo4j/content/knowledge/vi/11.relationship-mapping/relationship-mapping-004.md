# Ánh xạ nhiều quan hệ bằng List hoặc Set

Bài học này thuộc chương **Ánh xạ quan hệ** của module **SPRING_DATA_NEO4J**. Trong mô hình đồ thị, một node thường liên kết với nhiều node khác: một nhóm có nhiều thành viên, một tác giả viết nhiều bài, một khách hàng đặt nhiều đơn hàng. Spring Data Neo4j ánh xạ các quan hệ này vào thuộc tính collection trong entity, phổ biến nhất là `List` và `Set`.

Việc chọn collection ảnh hưởng đến cách ứng dụng biểu diễn và thao tác dữ liệu sau khi đọc từ Neo4j. `List` giữ các phần tử theo cấu trúc danh sách của Java; `Set` biểu diễn tập hợp phần tử không trùng theo quy tắc `equals()` và `hashCode()` của đối tượng. Cả hai đều có thể dùng để ánh xạ nhiều relationship, nhưng chúng không thay đổi hướng hay kiểu relationship trong đồ thị và cũng không tự tạo ràng buộc duy nhất ở cơ sở dữ liệu.

## 1. Quan hệ nhiều phần tử trong đồ thị

Trong Neo4j, một relationship nối một node nguồn với một node đích. Một node có thể có nhiều relationship cùng kiểu đi ra hoặc đi vào. Ví dụ một `Team` có nhiều thành viên:

```text
(Team:Platform)
   ├──[:HAS_MEMBER]──> (Person:An)
   ├──[:HAS_MEMBER]──> (Person:Bình)
   └──[:HAS_MEMBER]──> (Person:Chi)
```

Khi ánh xạ từ `Team`, thuộc tính `members` có thể là `List<Person>` hoặc `Set<Person>`. Mỗi phần tử đại diện một node đích được nối bởi relationship `HAS_MEMBER`.

Spring Data Neo4j xác định quan hệ thông qua `@Relationship`. Hai thông tin quan trọng là:

- `type`: tên kiểu relationship trong Neo4j, ví dụ `HAS_MEMBER`.
- `direction`: chiều relationship so với node chứa thuộc tính. `OUTGOING` nghĩa là relationship đi ra khỏi node hiện tại; `INCOMING` nghĩa là relationship đi vào node hiện tại.

Nếu bỏ qua `direction`, mặc định là `OUTGOING`. Nên khai báo tường minh khi mô hình có nhiều quan hệ hoặc chiều có ý nghĩa nghiệp vụ.

## 2. Ánh xạ nhiều node đích bằng List

Dùng `List<T>` khi ứng dụng cần biểu diễn một danh sách có thể lặp phần tử, cần thao tác theo chỉ số hoặc muốn giữ thứ tự xử lý trong bộ nhớ. Ví dụ:

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

    @Relationship(
        type = "HAS_MEMBER",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Person> members = new ArrayList<>();
}
```

Node đích có thể được ánh xạ thành entity riêng:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;
}
```

Với entity trên, `team.getMembers()` trả về danh sách thành viên mà `Team` hiện tại có relationship `HAS_MEMBER` đi ra. Ứng dụng có thể thêm, xóa hoặc duyệt các phần tử trong collection trước khi lưu aggregate.

`List` cho phép một đối tượng Java xuất hiện nhiều lần trong danh sách. Tuy nhiên, thứ tự của các relationship trong Neo4j không được bảo đảm chỉ vì thuộc tính entity có kiểu `List`. Cơ sở dữ liệu đồ thị không lưu thứ tự tự nhiên cho các relationship cùng kiểu. Khi đọc dữ liệu, nếu thứ tự nghiệp vụ quan trọng, cần biểu diễn tiêu chí sắp xếp và truy vấn với `ORDER BY`.

## 3. Ánh xạ nhiều node đích bằng Set

Dùng `Set<T>` khi mô hình Java muốn mỗi node đích chỉ xuất hiện một lần trong collection. Ví dụ:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Team")
public class Team {

    @Id
    private String id;

    private String name;

    @Relationship(
        type = "HAS_MEMBER",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Person> members = new HashSet<>();
}
```

`Set` loại bỏ các phần tử được xem là trùng theo `equals()` và `hashCode()` của lớp phần tử. Vì vậy, entity `Person` cần có quy tắc equality phù hợp. Nếu hai object `Person` đại diện cùng một node nhưng không có equality theo định danh, `HashSet` có thể giữ cả hai object. Ngược lại, nếu equality được định nghĩa theo ID, hai object có cùng ID được xem là một phần tử.

Không nên tự động dùng `Set` chỉ để “chặn relationship trùng” trong Neo4j. `Set` chỉ áp dụng quy tắc tập hợp ở Java. Nó không tạo unique constraint trên relationship, không ngăn một client khác tạo thêm relationship, và không bảo đảm dữ liệu trong graph không có nhiều cạnh cùng kiểu giữa cùng hai node.

Ngoài ra, `HashSet` không bảo đảm thứ tự lặp. `LinkedHashSet` có thể giữ thứ tự chèn trong bộ nhớ, nhưng không làm cho thứ tự relationship trong cơ sở dữ liệu trở nên bền vững. Khi cần thứ tự rõ ràng, hãy lưu một thuộc tính sắp xếp và truy vấn có `ORDER BY`.

## 4. So sánh List và Set

| Tiêu chí | `List<T>` | `Set<T>` |
|---|---|---|
| Phần tử lặp trong collection | Cho phép | Loại bỏ phần tử bằng nhau theo equality của Java |
| Truy cập theo chỉ số | Có | Không |
| Thứ tự trong bộ nhớ | Có thứ tự theo danh sách | Tùy implementation; `HashSet` không bảo đảm thứ tự |
| Phù hợp khi | Cần danh sách, xử lý theo thứ tự hoặc cần giữ các mục lặp | Cần tập node đích duy nhất theo quy tắc equality |
| Điều kiện cần chú ý | Thứ tự đọc từ graph cần được truy vấn xác định | `equals()` và `hashCode()` phải được thiết kế đúng |
| Ràng buộc duy nhất trong Neo4j | Không tạo | Không tạo |

Việc chọn kiểu collection nên xuất phát từ ngữ nghĩa domain. Nếu một nhóm có nhiều thành viên và mỗi người chỉ cần xuất hiện một lần trong danh sách thành viên, `Set<Person>` có thể diễn tả đúng ý định. Nếu ứng dụng cần giữ từng mục tham chiếu hoặc xử lý theo vị trí, `List` thuận tiện hơn, nhưng vị trí cần được mô hình hóa rõ nếu phải duy trì qua lần lưu và lần đọc.

## 5. Phân biệt node đích và relationship

Một collection kiểu `List<Person>` hoặc `Set<Person>` chủ yếu biểu diễn các node đích có liên hệ với node hiện tại. Nếu relationship chỉ đóng vai trò liên kết và không có dữ liệu riêng, cách ánh xạ này thường đủ.

Trong nhiều nghiệp vụ, chính relationship cũng có thuộc tính: ngày tham gia, vai trò, trạng thái, điểm số hoặc vị trí. Khi đó, nên ánh xạ relationship thành một lớp riêng bằng `@RelationshipProperties`. Mỗi phần tử collection lúc này đại diện cho một relationship cụ thể, thay vì chỉ đại diện node đích.

Ví dụ một nhóm có thể có nhiều lần ghi nhận việc một người tham gia theo các giai đoạn hoặc vai trò khác nhau:

```text
(Team)-[:HAS_MEMBER {role: 'LEAD', joinedAt: 2024-01-10}]->(Person:An)
(Team)-[:HAS_MEMBER {role: 'REVIEWER', joinedAt: 2025-03-01}]->(Person:An)
```

Hai relationship cùng nối `Team` với `Person:An`, nhưng mang ý nghĩa và thuộc tính khác nhau. Một `Set<Person>` không thể biểu diễn đầy đủ hai lần tham gia này, vì nó chỉ giữ node đích theo equality của `Person`.

## 6. Dùng List hoặc Set với RelationshipProperties

Khai báo lớp đại diện relationship:

```java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long relationshipId;

    private String role;

    private LocalDate joinedAt;

    @TargetNode
    private Person person;
}
```

`@RelationshipProperties` đánh dấu lớp chứa thuộc tính của relationship. `@TargetNode` xác định node ở đầu còn lại của relationship. `@RelationshipId` là metadata định danh relationship do persistence quản lý; không tự gán giá trị này hoặc sử dụng nó làm ID công khai của nghiệp vụ.

Trong `Team`, ánh xạ collection các relationship:

```java
@Relationship(
    type = "HAS_MEMBER",
    direction = Relationship.Direction.OUTGOING
)
private List<Membership> memberships = new ArrayList<>();
```

Khi đó, mỗi phần tử `Membership` chứa một `Person` đích cùng `role` và `joinedAt` của chính relationship. `List<Membership>` phù hợp nếu cần giữ từng relationship riêng, kể cả khi nhiều relationship cùng nối một cặp node.

Có thể dùng `Set<Membership>` khi domain thực sự cần tập relationship duy nhất. Nhưng equality/hashCode của `Membership` phải được định nghĩa theo một khóa nghiệp vụ ổn định. Không nên dựa vào `relationshipId` do Neo4j cấp nếu giá trị này chưa tồn tại khi tạo mới hoặc có thể thay đổi trong quá trình persist. Trong trường hợp chưa có quy tắc equality rõ ràng, `List<Membership>` thường là lựa chọn dễ hiểu hơn.

## 7. Khi nào nên dùng List, Set hoặc relationship entity?

| Nhu cầu domain | Cách ánh xạ nên cân nhắc | Lý do |
|---|---|---|
| Một nhóm có các thành viên, không có thuộc tính trên cạnh | `Set<Person>` | Biểu diễn tập thành viên duy nhất theo equality của node |
| Một bài viết có nhiều tag và cần thao tác theo danh sách | `List<Tag>` hoặc `Set<Tag>` tùy quy tắc domain | Chọn theo việc có cho phép lặp và có cần thứ tự hay không |
| Một đơn hàng có nhiều dòng hàng, mỗi dòng có quantity và price | `List<OrderLine>` với `@RelationshipProperties` hoặc mô hình hóa dòng hàng thành node nếu có vòng đời riêng | Thuộc tính thuộc về từng liên kết/dòng hàng |
| Cùng một cặp node có nhiều relationship khác nhau | `List<RelationshipProperties>` | Mỗi phần tử biểu diễn một relationship độc lập |
| Cần thứ tự bền vững như vị trí trong playlist | Relationship properties có `position`, truy vấn `ORDER BY position` | Thứ tự là dữ liệu nghiệp vụ được lưu rõ ràng |

Không nên chọn `Set` chỉ vì hiệu năng được cho là tốt hơn `List`. Kích thước collection, cách định nghĩa equality, số lượng relationship và truy vấn thực tế mới là yếu tố cần xem xét. Đo hiệu năng bằng dữ liệu đại diện thay vì giả định rằng một interface collection luôn nhanh hơn.

## 8. Truy vấn collection với repository và Cypher

Spring Data Neo4j có thể ánh xạ collection thông qua entity graph khi repository tải node gốc. Nếu cần lọc hoặc sắp xếp node liên quan theo điều kiện cụ thể, có thể dùng `@Query` với Cypher.

Ví dụ lấy các thành viên đang hoạt động của một nhóm, sắp xếp theo tên:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (team:Team {id: $teamId})-[:HAS_MEMBER]->(person:Person)
        WHERE person.active = true
        RETURN person
        ORDER BY person.name
        """)
    List<Person> findActiveMembers(
        @Param("teamId") String teamId
    );
}
```

Ở đây, `ORDER BY person.name` xác định thứ tự kết quả của truy vấn. Nếu bỏ `ORDER BY`, Neo4j không cam kết thứ tự trả về. Việc method trả `List<Person>` chỉ là kiểu collection phía Java; nó không tự sắp xếp kết quả theo tên.

Nếu truy vấn trả về relationship properties, cần trả về các cột và cấu trúc mà mapping của Spring Data Neo4j có thể ánh xạ vào lớp relationship tương ứng. Với truy vấn phức tạp, hãy kiểm tra mapping bằng integration test thay vì giả định mọi hình dạng `RETURN` đều được chuyển tự động thành entity graph.

## 9. Cập nhật collection và ranh giới aggregate

Khi lưu entity gốc qua repository hoặc template, Spring Data Neo4j xử lý các relationship được biểu diễn trong entity graph theo mapping metadata. Vì vậy, cần xác định collection đang chứa toàn bộ quan hệ cần quản lý hay chỉ là một phần kết quả được lọc.

Ví dụ, nếu service chỉ tải các thành viên đang hoạt động bằng một truy vấn tùy biến rồi gán danh sách đó vào `team.members`, không nên mặc định rằng danh sách này đại diện cho toàn bộ relationship `HAS_MEMBER`. Lưu aggregate sau một truy vấn lọc có thể dẫn đến thay đổi relationship ngoài ý muốn nếu collection được dùng như trạng thái đầy đủ của aggregate.

Một số nguyên tắc hữu ích:

1. Chọn node gốc (aggregate root) chịu trách nhiệm quản lý vòng đời collection relationship.
2. Khi tải aggregate để cập nhật, lấy đủ relationship thuộc phạm vi mà thao tác sẽ thay đổi.
3. Không dùng một collection chỉ chứa kết quả phân trang hoặc lọc làm trạng thái đầy đủ để lưu lại aggregate.
4. Với thao tác thêm/xóa relationship riêng lẻ, cân nhắc câu Cypher chuyên biệt có tham số thay vì tải và ghi lại toàn bộ graph.
5. Bao thao tác cập nhật nhiều bước trong transaction khi chúng phải thành công hoặc rollback cùng nhau.

Ví dụ thêm một thành viên bằng Cypher:

```java
neo4jClient.query("""
        MATCH (team:Team {id: $teamId})
        MATCH (person:Person {id: $personId})
        MERGE (team)-[:HAS_MEMBER]->(person)
        """)
    .bind(teamId).to("teamId")
    .bind(personId).to("personId")
    .run();
```

`MERGE` trong ví dụ này đảm bảo không tạo thêm relationship cùng pattern đã chỉ định khi pattern đó đã tồn tại tại thời điểm thực thi. Nó không phải constraint duy nhất tổng quát cho mọi thao tác đồng thời; nếu tính duy nhất là quy tắc quan trọng, cần thiết kế ràng buộc dữ liệu phù hợp và kiểm soát transaction/concurrency.

## 10. Equality, hashCode và vòng lặp object graph

Với `Set`, hành vi loại bỏ phần tử trùng phụ thuộc trực tiếp vào `equals()` và `hashCode()`. Một entity nên có quy tắc equality ổn định trong suốt thời gian nằm trong collection. Tránh dùng các field có thể thay đổi, chẳng hạn `name`, `status` hoặc collection relationship khác, làm thành phần hash code.

Không nên để `equals()` hoặc `hashCode()` duyệt toàn bộ relationship hai chiều. Ví dụ `Team` chứa `Person`, còn `Person` lại chứa `Team`; nếu equality của hai lớp đi qua nhau, có thể gây đệ quy, stack overflow hoặc hiệu năng kém. Các annotation kiểu Lombok `@Data` tạo equality/hashCode từ nhiều field có thể không phù hợp với entity graph có quan hệ hai chiều.

Một cách tiếp cận là định nghĩa equality theo ID ứng dụng bất biến. Nếu ID chỉ được sinh sau khi lưu, cần quy tắc cho entity mới chưa có ID, hoặc chọn `List` cho đến khi có một khóa nghiệp vụ ổn định. Đừng dùng ID nội bộ Neo4j như danh tính công khai chỉ để tiện triển khai equality.

## 11. Kiểm tra ánh xạ collection

Nên kiểm tra cả cấu trúc graph và kết quả entity bằng integration test với Neo4j test harness hoặc Testcontainers. Một bộ kiểm tra cơ bản có thể gồm:

1. Tạo một `Team` với nhiều `Person` và lưu qua repository.
2. Đọc lại `Team` và xác minh số lượng phần tử trong `List` hoặc `Set`.
3. Kiểm tra hướng relationship bằng Cypher để chắc chắn relationship đi từ node gốc tới node đích như thiết kế.
4. Với `Set`, kiểm tra equality/hashCode của các object đại diện cùng node.
5. Tạo hai relationship cùng nối một cặp node nhưng có thuộc tính khác nhau; xác minh `List<Membership>` giữ được từng relationship.
6. Nếu cần thứ tự, kiểm tra truy vấn có `ORDER BY` trả về đúng thứ tự mong muốn.
7. Kiểm tra thao tác cập nhật collection trong transaction, đặc biệt khi collection trước đó được tải bằng truy vấn lọc.

## 12. Nguyên tắc lựa chọn

- Dùng `List<T>` khi cần danh sách Java, có thể chứa phần tử bằng nhau và cần thao tác theo vị trí.
- Dùng `Set<T>` khi domain định nghĩa rõ tập node đích duy nhất và equality/hashCode được triển khai ổn định.
- Không suy ra thứ tự lưu trữ từ `List`; dùng thuộc tính sắp xếp và `ORDER BY` khi thứ tự có ý nghĩa.
- Dùng `@RelationshipProperties` khi mỗi relationship có thuộc tính riêng hoặc cần phân biệt nhiều relationship giữa cùng một cặp node.
- Không xem `Set` hoặc `MERGE` là thay thế cho ràng buộc duy nhất và chiến lược concurrency ở database.
- Chỉ lưu aggregate từ collection đầy đủ; xử lý collection lọc/phân trang như dữ liệu đọc riêng.

`List` và `Set` là lựa chọn ở lớp Java để biểu diễn nhiều relationship. Muốn ánh xạ đúng, hãy bắt đầu từ câu hỏi domain đang cần tập node đích hay tập relationship độc lập. Khi cạnh có thuộc tính, có thể lặp giữa cùng hai node hoặc có vòng đời riêng, hãy biểu diễn cạnh bằng lớp `@RelationshipProperties`; khi thứ tự có ý nghĩa, lưu thứ tự thành dữ liệu và truy vấn một cách tường minh.
