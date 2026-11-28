# Khi nào cần `@RelationshipProperties`?

Trong Neo4j, relationship không chỉ nối hai node mà còn có thể mang các property mô tả chính mối liên kết đó. Ví dụ, một nhân viên thuộc một nhóm với vai trò `LEAD`, một diễn viên tham gia một bộ phim với vai diễn cụ thể, hoặc một đơn hàng chứa sản phẩm với số lượng và đơn giá tại thời điểm mua. Những dữ liệu này phụ thuộc vào từng liên kết, không phải thuộc tính cố định của riêng một đầu node.

Khi ứng dụng dùng Spring Data Neo4j (SDN), `@RelationshipProperties` giúp ánh xạ một relationship có dữ liệu riêng thành một lớp Java. Lớp này chứa các property của relationship và một field `@TargetNode` trỏ đến node ở đầu kia. Annotation này hữu ích khi cần truy cập, tạo hoặc cập nhật dữ liệu trên mối liên kết cùng với entity.

Không phải relationship nào cũng cần lớp riêng. Nếu relationship chỉ biểu diễn sự kết nối giữa hai node và không có property, ánh xạ trực tiếp đến entity đích thường đơn giản hơn. Nếu dữ liệu liên kết phát triển thành một khái niệm nghiệp vụ có định danh, vòng đời và các quan hệ riêng, hãy cân nhắc mô hình nó thành node trung gian.

## 1. Bắt đầu từ câu hỏi: dữ liệu thuộc về ai?

Giả sử hệ thống bán hàng có hai node `Order` và `Product`. Một sản phẩm có thể xuất hiện trong nhiều đơn hàng; mỗi đơn hàng có thể chứa nhiều sản phẩm. Các câu hỏi nghiệp vụ gồm:

- Đơn hàng nào chứa sản phẩm này?
- Trong một đơn hàng, sản phẩm có số lượng bao nhiêu?
- Đơn giá tại thời điểm đặt hàng là bao nhiêu?
- Có áp dụng mức giảm giá nào cho dòng hàng này không?

`quantity`, `unitPrice` và `discount` không mô tả bản thân `Product`, vì cùng một sản phẩm có thể được mua với số lượng và mức giá khác nhau trong các đơn hàng khác nhau. Chúng cũng không mô tả riêng `Order`, vì mỗi sản phẩm trong đơn hàng có thể có giá trị khác nhau. Chúng mô tả lần sản phẩm xuất hiện trong đơn hàng, tức relationship giữa `Order` và `Product`.

```cypher
(:Order)-[:CONTAINS {
    quantity: 2,
    unitPrice: 850000,
    discount: 50000
}]->(:Product)
```

Trong ví dụ, `CONTAINS` là relationship type, còn `quantity`, `unitPrice` và `discount` là relationship properties.

Một quy tắc thực tế để quyết định vị trí dữ liệu:

| Câu hỏi | Nơi phù hợp |
| --- | --- |
| Giá niêm yết hiện tại của sản phẩm là bao nhiêu? | Property của node `Product` |
| Giá sản phẩm được chốt trong đơn hàng này là bao nhiêu? | Property của relationship `CONTAINS` |
| Tên và email của khách hàng là gì? | Property của node `Customer` |
| Khách hàng giữ vai trò nào trong nhóm này? | Property của relationship `MEMBER_OF` |
| Đơn hàng có trạng thái gì? | Property của node `Order` |

Nếu dữ liệu thay đổi theo từng cặp node hoặc từng lần kết nối, hãy kiểm tra khả năng đó là relationship property trước khi đặt nó lên một trong hai node đầu mút.

## 2. Khi relationship không có property: ánh xạ trực tiếp

Với liên kết đơn giản, không mang dữ liệu riêng, SDN có thể ánh xạ relationship trực tiếp thành entity đích. Ví dụ, một người có thể quản lý một nhóm và relationship chỉ cần thể hiện sự kết nối:

```cypher
(:Person)-[:MANAGES]->(:Team)
```

Entity Java có thể khai báo:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Relationship(type = "MANAGES")
    private Team team;
}
```

Ở đây, field `team` nhận node `Team` ở đầu kia. Không cần tạo thêm một lớp chỉ để đại diện cho relationship nếu nó không có property hoặc hành vi cần quản lý riêng.

Relationship có thể được ánh xạ dưới dạng một node đơn, collection hoặc kiểu collection khác tùy cardinality nghiệp vụ. Hãy chọn kiểu phù hợp với dữ liệu thực tế và cách ứng dụng sử dụng kết quả.

## 3. Khi relationship có dữ liệu riêng: dùng `@RelationshipProperties`

Khi relationship có một hoặc nhiều property cần đọc/ghi cùng entity, SDN cho phép khai báo lớp Java với `@RelationshipProperties`. Lớp này cần một field `@TargetNode` để xác định node ở đầu kia. Các field còn lại đại diện cho property của relationship.

Ví dụ, thành viên của nhóm có vai trò và ngày gia nhập riêng:

```cypher
(:Person)-[:MEMBER_OF {
    role: "LEAD",
    joinedAt: date("2025-03-01"),
    active: true
}]->(:Team)
```

Lớp relationship properties:

```java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class TeamMembership {

    private String role;

    private LocalDate joinedAt;

    private boolean active;

    @TargetNode
    private Team team;
}
```

Entity nguồn khai báo relationship bằng lớp vừa tạo:

```java
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    @Relationship(type = "MEMBER_OF")
    private Set<TeamMembership> memberships;
}
```

`TeamMembership` không phải node entity. Nó là mô hình Java cho relationship `MEMBER_OF`. Field `team` được đánh dấu `@TargetNode` để SDN biết node đích; `role`, `joinedAt` và `active` được ánh xạ thành property trên relationship.

Khi duyệt `person.getMemberships()`, ứng dụng có thể lấy cả thông tin của nhóm và thông tin của lần tham gia nhóm. Nhờ vậy, dữ liệu liên kết được giữ đúng vị trí và không bị trộn vào node `Person` hoặc `Team`.

## 4. Ví dụ thực tế: dòng hàng trong đơn hàng

Một ví dụ điển hình khác là relationship `CONTAINS` giữa `Order` và `Product`. Mỗi dòng hàng có thể lưu số lượng, đơn giá tại thời điểm mua và mức giảm giá:

```java
import java.math.BigDecimal;

import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class OrderLine {

    private int quantity;

    private BigDecimal unitPrice;

    private BigDecimal discount;

    @TargetNode
    private Product product;
}
```

Node `Order` giữ danh sách các dòng hàng:

```java
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Order")
public class PurchaseOrder {

    @Id
    private String orderNumber;

    private String status;

    @Relationship(type = "CONTAINS")
    private List<OrderLine> lines;
}
```

Khi lưu `PurchaseOrder` qua repository hoặc `Neo4jTemplate`, SDN sử dụng metadata relationship để lưu các liên kết và property tương ứng trong phạm vi aggregate được quản lý. Cần cấu hình mapping và transaction phù hợp với cách ứng dụng thay đổi graph; không nên giả định một thao tác lưu entity sẽ tự quản lý mọi node không thuộc aggregate đó.

Truy vấn tạo một dòng hàng trong Cypher:

```cypher
MATCH (o:Order {orderNumber: $orderNumber})
MATCH (p:Product {sku: $sku})
CREATE (o)-[:CONTAINS {
    quantity: $quantity,
    unitPrice: $unitPrice,
    discount: $discount
}]->(p)
```

Truy vấn đọc dữ liệu trên relationship:

```cypher
MATCH (o:Order {orderNumber: $orderNumber})
      -[line:CONTAINS]->(p:Product)
RETURN p.sku AS sku,
       p.name AS productName,
       line.quantity AS quantity,
       line.unitPrice AS unitPrice,
       line.discount AS discount
```

Tổng tiền của đơn có thể được tính từ property trên từng relationship:

```cypher
MATCH (o:Order {orderNumber: $orderNumber})
      -[line:CONTAINS]->(:Product)
RETURN sum(line.quantity * line.unitPrice - coalesce(line.discount, 0))
       AS total
```

Ví dụ cho thấy relationship properties hữu ích không chỉ khi mapping Java mà cả khi lọc, sắp xếp và tính toán trực tiếp trong Cypher.

## 5. Phân biệt relationship properties với node trung gian

Không phải cứ relationship có nhiều property là phải chuyển thành node. Cần xét liệu mối liên kết có thực sự trở thành một thực thể nghiệp vụ độc lập hay không.

| Tiêu chí | `@RelationshipProperties` | Node trung gian |
| --- | --- | --- |
| Ý nghĩa | Dữ liệu mô tả một liên kết giữa hai node | Một khái niệm nghiệp vụ có danh tính riêng |
| Định danh | Không cần business ID riêng trong đa số trường hợp | Thường cần ID hoặc business key |
| Vòng đời | Phụ thuộc vào liên kết và hai đầu node | Có thể tồn tại, thay đổi hoặc được tham chiếu độc lập |
| Quan hệ tiếp theo | Chủ yếu nối hai node đầu mút | Có thể nối thêm nhiều loại node khác |
| Ví dụ | Vai trò thành viên, số lượng trong dòng hàng | Hợp đồng thành viên, phiếu giao hàng, hồ sơ phân công |

Ví dụ, nếu `MEMBER_OF` chỉ cần `role`, `joinedAt` và `active`, relationship properties là đủ. Nhưng nếu mỗi lần tham gia nhóm có mã hồ sơ, quy trình phê duyệt, lịch sử thay đổi, người phê duyệt và nhiều tài liệu đính kèm, `Membership` có thể là node riêng:

```cypher
(:Person)-[:HAS_MEMBERSHIP]->(:Membership)
(:Membership)-[:IN_TEAM]->(:Team)
(:Membership)-[:APPROVED_BY]->(:Person)
```

Trong trường hợp đó, `Membership` có thể được truy vấn, cập nhật và liên kết độc lập. Mô hình node trung gian giúp biểu diễn vòng đời và các quan hệ mở rộng của chính membership.

Đừng chuyển relationship thành node chỉ để có chỗ đặt một vài field đơn giản. Mỗi node trung gian tạo thêm một bước duyệt và thêm một loại entity cần quản lý. Ngược lại, nếu một mối liên kết có định danh, vòng đời hoặc quan hệ riêng, giữ tất cả trong relationship properties sẽ làm mô hình khó mở rộng.

## 6. Relationship properties có thể xuất hiện nhiều lần giữa cùng hai node

Neo4j cho phép nhiều relationship cùng type giữa cùng một cặp node. Điều này hữu ích khi các liên kết đại diện cho những sự kiện khác nhau, ví dụ một người tham gia nhiều dự án theo từng giai đoạn hoặc cùng một sản phẩm xuất hiện ở nhiều dòng hàng của một đơn hàng.

```cypher
MATCH (p:Person {personId: $personId})
MATCH (t:Team {teamId: $teamId})
CREATE (p)-[:MEMBER_OF {
    role: "MEMBER",
    joinedAt: date("2024-01-01"),
    leftAt: date("2024-12-31")
}]->(t)
CREATE (p)-[:MEMBER_OF {
    role: "LEAD",
    joinedAt: date("2025-02-01"),
    leftAt: null
}]->(t)
```

Nếu cần lưu lịch sử nhiều giai đoạn, relationship properties có thể chứa `joinedAt`, `leftAt` hoặc `role` cho từng liên kết. Khi mapping vào Java, cần chọn collection có thể biểu diễn nhiều relationship, chẳng hạn `Set<TeamMembership>` hoặc `List<TeamMembership>`.

Hãy xác định quy tắc nghiệp vụ về việc có cho phép hai liên kết trùng nhau hay không. Neo4j không tự áp đặt uniqueness cho relationship chỉ vì chúng có cùng type và cùng hai đầu node. Nếu chỉ được có một membership đang hoạt động, ứng dụng cần kiểm tra và bảo đảm quy tắc đó trong transaction hoặc bằng thiết kế dữ liệu phù hợp.

## 7. Các lưu ý khi ánh xạ bằng SDN

**`@TargetNode` là bắt buộc cho lớp relationship properties.** Field này chỉ node ở đầu kia của relationship theo góc nhìn entity đang khai báo collection. Không dùng `@Node` trên lớp relationship properties như thể nó là một node entity độc lập.

**Đặt `@Relationship` trên field của entity nguồn.** Type phải khớp relationship type trong Neo4j; direction phải đúng theo hướng được lưu. Hướng mặc định là `OUTGOING`, vì vậy hãy khai báo rõ `INCOMING` nếu field được đặt ở đầu đích.

**Property trong lớp relationship properties phải là dữ liệu của liên kết.** Các field như `role`, `quantity`, `joinedAt` hoặc `unitPrice` là ví dụ phù hợp. Thông tin tên, mô tả hay trạng thái của node đích nên nằm trong entity node tương ứng.

**Chọn kiểu Java tương thích.** Dùng `BigDecimal` cho giá trị tiền trong domain Java nếu cần độ chính xác thập phân; dùng `LocalDate` cho ngày không có thời gian. Kiểm tra converter và kiểu property thực tế trong Neo4j.

**Không nhầm relationship ID với business ID.** Nếu dùng `@RelationshipId` trong phiên bản SDN của dự án, đó là định danh kỹ thuật do Neo4j quản lý cho relationship mapping. Nó không thay thế mã nghiệp vụ như `membershipNumber` hoặc `orderLineCode`. Nếu liên kết cần business key độc lập, cân nhắc mô hình node trung gian.

**Chú ý cập nhật và xóa liên kết.** Khi lưu aggregate có collection relationship, SDN cần đối chiếu trạng thái entity với các liên kết được quản lý. Hãy đọc tài liệu phiên bản SDN đang dùng và kiểm thử trường hợp thêm, sửa, bỏ relationship để chắc chắn dữ liệu thay đổi đúng như mong muốn. Nếu có nhiều ứng dụng cùng ghi vào một graph, xác định rõ quyền sở hữu các relationship để tránh ghi đè thay đổi của hệ thống khác.

## 8. Kiểm tra và truy vấn relationship properties

Trước khi mapping, có thể khảo sát relationship và property đang tồn tại:

```cypher
MATCH (source)-[r:MEMBER_OF]->(target)
RETURN source.personId AS personId,
       target.teamId AS teamId,
       properties(r) AS membership
LIMIT 20
```

Truy vấn này giúp xác nhận type, hướng và tên property. Nếu relationship lưu `joined_at` nhưng Java field là `joinedAt`, hãy khai báo alias mapping bằng `@Property("joined_at")` trên field tương ứng trong lớp relationship properties nếu schema yêu cầu tên khác.

Ví dụ lọc thành viên có vai trò lead:

```cypher
MATCH (p:Person)-[membership:MEMBER_OF]->(t:Team)
WHERE membership.role = "LEAD"
RETURN p.name AS personName,
       t.name AS teamName,
       membership.joinedAt AS joinedAt
ORDER BY joinedAt DESC
```

Với truy vấn cần kết quả tùy biến, có thể dùng `Neo4jClient` để ánh xạ record sang DTO. Khi cần entity graph, hãy trả về node và relationship đúng cấu trúc thay vì chỉ trả các scalar rồi kỳ vọng SDN dựng đầy đủ object.

## 9. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không đọc được property của relationship | Ánh xạ trực tiếp đến entity đích | Dùng `@RelationshipProperties` và `@TargetNode` |
| Relationship collection luôn rỗng | Sai type hoặc direction | Kiểm tra mẫu Cypher `(source)-[r:TYPE]->(target)` |
| Property xuất hiện trên sai node | Đặt dữ liệu phụ thuộc liên kết vào entity đầu mút | Chuyển sang lớp relationship properties |
| Chỉ đọc được một liên kết trong khi có nhiều liên kết | Dùng field đơn thay vì collection hoặc mô hình cardinality không đúng | Chọn `Set`/`List` theo nghiệp vụ |
| Không thể quản lý lịch sử liên kết phức tạp | Relationship đang gánh vòng đời của một thực thể độc lập | Tạo node trung gian có định danh |
| Thay đổi collection làm mất cập nhật từ hệ thống khác | Nhiều ứng dụng cùng quản lý relationship nhưng không thống nhất quyền ghi | Xác định aggregate ownership và quy trình cập nhật |
| Giá trị ngày/tiền bị sai kiểu | Kiểu Java và Neo4j không tương thích hoặc converter chưa cấu hình | Chọn kiểu domain và converter phù hợp |

## 10. Quy trình quyết định

Khi thiết kế một liên kết, hãy đi theo các bước:

1. Xác định hai node đầu mút và ý nghĩa relationship giữa chúng.
2. Kiểm tra liên kết có dữ liệu riêng hay không.
3. Nếu không có property, ánh xạ trực tiếp đến entity đích bằng `@Relationship`.
4. Nếu có property phụ thuộc từng liên kết, tạo lớp `@RelationshipProperties` và đánh dấu node đích bằng `@TargetNode`.
5. Nếu liên kết có business ID, vòng đời hoặc nhiều quan hệ riêng, cân nhắc chuyển nó thành node trung gian.
6. Xác định cardinality, hướng, khả năng có nhiều relationship cùng type và quy tắc cập nhật/xóa.
7. Kiểm tra mapping bằng truy vấn Cypher và các thao tác đọc/ghi trong transaction phù hợp.

## Kết luận

Dùng `@RelationshipProperties` khi một relationship cần mang dữ liệu riêng có ý nghĩa nghiệp vụ, chẳng hạn vai trò, thời điểm tham gia, số lượng hoặc đơn giá của một lần liên kết. Lớp này mô tả property của relationship và dùng `@TargetNode` để tham chiếu node ở đầu kia. Nếu liên kết không có dữ liệu riêng, ánh xạ trực tiếp bằng `@Relationship` đơn giản hơn; nếu liên kết trở thành thực thể có định danh và vòng đời độc lập, hãy dùng node trung gian. Quyết định đúng vị trí dữ liệu giúp graph rõ nghĩa và entity SDN dễ đọc, ghi, truy vấn.
