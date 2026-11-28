# Entity thiếu ID, relationship thiếu định danh hoặc metadata không hợp lệ

## Mục tiêu

Sau bài học này, bạn có thể:

- Nhận biết vì sao một node entity cần trường định danh được SDN nhận diện.
- Chọn đúng giữa ID sinh tự động, UUID do ứng dụng sinh và business ID.
- Hiểu vai trò của @Version khi entity dùng business ID được gán trước.
- Phân biệt ID của node với ID nội bộ của relationship.
- Khai báo đúng @RelationshipProperties, @RelationshipId và @TargetNode.
- Phát hiện metadata mapping sai như import nhầm @Id, thiếu target node hoặc khai báo relationship sai hướng.
- Dùng Cypher để tìm dữ liệu cũ thiếu ID, trùng khóa hoặc sai property cần thiết.
- Xây dựng checklist kiểm tra mapping trước khi lưu entity và relationship.

## 1. Vì sao định danh quan trọng trong Spring Data Neo4j?

Spring Data Neo4j (SDN) ánh xạ object Java thành node, relationship và property trong Neo4j. Để cập nhật đúng một node khi ứng dụng gọi repository.save(entity), SDN phải biết object đó đại diện cho node nào.

Trường định danh là cầu nối giữa object và node. SDN dùng nó để:

- Xác định node tương ứng khi đọc dữ liệu.
- Nhận biết entity mới hoặc entity đã tồn tại.
- Tạo hoặc cập nhật node khi lưu.
- Theo dõi trạng thái optimistic locking nếu entity có @Version.
- Giữ các relationship hiện có khi ghi lại graph được ánh xạ.

Một entity thiếu ID hoặc có ID nhưng SDN không nhận diện được có thể khiến thao tác lưu thất bại, tạo node mới ngoài dự kiến hoặc cập nhật không đúng node.

Relationship có thêm một lớp metadata. Với relationship được ánh xạ thành class có thuộc tính, SDN cần biết relationship instance nào đã tồn tại để có thể cập nhật an toàn mà không vô tình thay thế relationship khác hoặc làm mất property. Vì vậy, lớp @RelationshipProperties có yêu cầu riêng về @RelationshipId và @TargetNode.

Hãy phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Node ID | Định danh một entity Java tương ứng với một node |
| Relationship ID | Định danh nội bộ của một relationship mà SDN dùng để theo dõi quan hệ |
| Business ID | Khóa nghiệp vụ ổn định như mã khách hàng, SKU hoặc mã nhóm |

Business ID có thể là node ID mà ứng dụng chọn. Relationship ID do SDN quản lý không phải business ID của quan hệ và không nên được dùng làm mã nghiệp vụ.

## 2. Khai báo ID cho node entity

Một class được ánh xạ thành node cần có một trường định danh được SDN nhận diện bằng annotation @Id.

Ví dụ:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.annotation.Version;

@Node("Customer")
public class Customer {

    @Id
    private String customerCode;

    @Version
    private Long version;

    private String displayName;

    protected Customer() {
    }

    public Customer(String customerCode, String displayName) {
        this.customerCode = customerCode;
        this.displayName = displayName;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Trong ví dụ này, customerCode là business ID. Ứng dụng phải cung cấp giá trị không null khi tạo Customer. Nếu gọi save với customerCode chưa được gán, SDN không có khóa để định danh node.

Không nên chỉ đặt tên một field là id rồi cho rằng SDN tự hiểu đó là khóa. Hãy khai báo @Id rõ ràng. Dùng annotation thuộc SDN hoặc Spring Data Commons; không dùng nhầm jakarta.persistence.Id hay javax.persistence.Id của JPA.

Nếu nâng cấp từ Neo4j-OGM hoặc SDN đời cũ, hãy rà soát các annotation cũ như @GraphId, @NodeEntity và @RelationshipEntity. SDN hiện đại dùng @Id, @Node, @Relationship và @RelationshipProperties; không trộn hai hệ annotation trong cùng mapping model.

Hai import hợp lệ thường dùng là:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
~~~

hoặc:

~~~java
import org.springframework.data.annotation.Id;
~~~

Annotation @Id của SDN được tích hợp với Spring Data Commons. Một annotation có cùng tên từ persistence framework khác không tự động có cùng ý nghĩa với SDN.

## 3. Chọn chiến lược ID phù hợp

SDN hỗ trợ các cách định danh phổ biến sau:

| Chiến lược | Khai báo | Giá trị đến từ | Lưu ý |
|---|---|---|---|
| Internal ID | @Id @GeneratedValue trên Long | Neo4j | ID nội bộ, không phải khóa nghiệp vụ |
| Internal element ID | @Id @GeneratedValue trên String | Neo4j | Ánh xạ elementId của Neo4j 5 trở lên |
| UUID do ứng dụng sinh | @Id @GeneratedValue(UUIDStringGenerator.class) trên String | Ứng dụng/SDN | Phù hợp khi cần khóa surrogate ổn định hơn |
| Business ID | @Id trên field được ứng dụng gán | Ứng dụng | Cần ổn định, duy nhất và đi cùng @Version |

@GeneratedValue phải được đặt cùng field có @Id. Không đặt @GeneratedValue trên một field khác rồi kỳ vọng SDN dùng nó làm khóa. Với custom ID type, hãy xác nhận kiểu đó được SDN hỗ trợ trực tiếp hoặc có converter phù hợp.

### Dùng ID nội bộ do Neo4j cấp

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

Khi tạo Product mới, id để null. SDN dùng ID generator mặc định để nhận ID nội bộ từ Neo4j. Nên dùng Long thay vì long cho trường hợp này vì null biểu thị rõ entity chưa được cấp ID.

Không tự gán ID nội bộ vào field này. Cũng không nên dùng internal ID làm mã public trong API, file export hoặc hệ thống khác. ID nội bộ gắn với vòng đời database và không phải định danh nghiệp vụ bền vững.

### Dùng UUID do ứng dụng sinh

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Product")
public class Product {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public String getId() {
        return id;
    }
}
~~~

UUIDStringGenerator tạo UUID dạng String ở phía ứng dụng. Đây là surrogate key do ứng dụng sinh, khác với String ID mặc định ánh xạ elementId của Neo4j.

Khi chạy nhiều application instance, generator tự viết phải có chiến lược tránh trùng ID trên toàn hệ thống. Một bộ đếm AtomicInteger trong bộ nhớ chỉ duy nhất trong một instance và có thể bắt đầu lại sau restart; không dùng nó làm ID phân tán nếu không có cơ chế cấp số dùng chung.

### Dùng business ID

Nếu hệ thống đã có mã nghiệp vụ ổn định, có thể dùng mã đó làm ID:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Team")
public class Team {

    @Id
    private String teamCode;

    @Version
    private Long version;

    private String name;

    protected Team() {
    }

    public Team(String teamCode, String name) {
        this.teamCode = teamCode;
        this.name = name;
    }

    public String getTeamCode() {
        return teamCode;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Business ID được gán ngay khi object được tạo. Chỉ nhìn vào ID, SDN không thể biết object là entity mới hay entity đã được đọc từ database. Vì vậy, SDN yêu cầu field @Version khi dùng business ID. Version giúp phân biệt trạng thái mới/đã tồn tại và hỗ trợ optimistic locking.

SDN quản lý giá trị version và tăng nó khi cập nhật. Không tự đặt version mới trong code nghiệp vụ hoặc custom mapping. Nếu hai transaction cùng cập nhật một entity từ cùng version, lần cập nhật sau có thể nhận OptimisticLockingFailureException; hãy đọc lại entity với version mới rồi xử lý lại theo quy tắc ứng dụng.

### Đảm bảo tính duy nhất trong database

Annotation @Id mô tả identity cho SDN. Hãy bảo vệ business ID bằng uniqueness constraint ở Neo4j để các đường ghi khác như Cypher trực tiếp hoặc import cũng không tạo khóa trùng.

~~~cypher
CREATE CONSTRAINT team_code_unique IF NOT EXISTS
FOR (t:Team)
REQUIRE t.teamCode IS UNIQUE
~~~

Trước khi tạo constraint trên database đã có dữ liệu, cần kiểm tra và xử lý các node thiếu hoặc trùng teamCode. Việc tạo constraint sẽ thất bại nếu dữ liệu hiện tại vi phạm điều kiện.

## 4. Entity bất biến và ID được sinh tự động

Với entity mutable, SDN có thể gán ID sinh tự động vào field. Với entity immutable có field ID final, ứng dụng phải cho phép SDN tạo instance mới mang ID sau khi lưu, thường thông qua một wither.

Ví dụ rút gọn:

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Article")
public class Article {

    @Id
    @GeneratedValue
    private final Long id;

    private final String title;

    public Article(String title) {
        this(null, title);
    }

    private Article(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Article withId(Long newId) {
        if (newId.equals(this.id)) {
            return this;
        }

        return new Article(newId, title);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Nếu immutable entity thiếu setter hoặc wither phù hợp cho ID được sinh tự động, SDN không có cách cập nhật instance với ID mới theo mô hình object đó. Khi chẩn đoán lỗi, kiểm tra cả constructor, persistence creator và khả năng tạo instance mới.

Với business ID bất biến, constructor phải nhận business ID hợp lệ. Không cần wither sinh ID nếu ứng dụng đã cung cấp khóa trước khi lưu.

## 5. Relationship thông thường không cần class ID riêng

Nếu relationship không có property nghiệp vụ, hãy ánh xạ trực tiếp node ở hai đầu:

~~~java
import java.util.List;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Team")
public class Team {

    @Id
    private String teamCode;

    @Version
    private Long version;

    @Relationship(
        type = "HAS_MEMBER",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Person> members;
}
~~~

Ở đây, mỗi phần tử Person là node ở đầu kia của relationship. Không cần tạo class relationship properties chỉ để thêm một ID vào quan hệ.

Neo4j tự quản lý identity nội bộ của relationship. Ứng dụng không cần tạo field business ID riêng nếu quan hệ chỉ biểu diễn liên kết đơn giản.

## 6. Relationship có thuộc tính cần metadata riêng

Khi relationship có dữ liệu như role, joinedAt, weight hoặc createdBy, dùng class được đánh dấu @RelationshipProperties.

Trong class này, SDN cần:

- Một field @RelationshipId để theo dõi internal ID của relationship.
- Chính xác một field @TargetNode để chỉ node ở đầu kia.
- Các field còn lại biểu diễn relationship properties của ứng dụng.

Node ở đầu kia cũng cần định danh riêng. Ví dụ Person dùng UUID do ứng dụng sinh:

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    private String id;

    private String displayName;

    protected Person() {
    }

    public String getId() {
        return id;
    }
}
~~~

Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long relationshipId;

    private String role;

    private Instant joinedAt;

    @TargetNode
    private Person person;

    protected Membership() {
    }

    public Membership(Person person, String role, Instant joinedAt) {
        this.person = person;
        this.role = role;
        this.joinedAt = joinedAt;
    }

    public Person getPerson() {
        return person;
    }

    public String getRole() {
        return role;
    }

    public Instant getJoinedAt() {
        return joinedAt;
    }
}
~~~

Entity Team khai báo quan hệ:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Team")
public class Team {

    @Id
    private String teamCode;

    @Version
    private Long version;

    @Relationship(
        type = "HAS_MEMBER",
        direction = Relationship.Direction.OUTGOING
    )
    private List<Membership> memberships = new ArrayList<>();

    protected Team() {
    }

    public Team(String code) {
        this.teamCode = code;
    }

    public List<Membership> getMemberships() {
        return memberships;
    }
}
~~~

Relationship được mô hình hóa theo hướng Team → Person. Field person có @TargetNode để SDN biết endpoint đích. Field relationshipId có @RelationshipId để SDN theo dõi quan hệ hiện hữu khi lưu aggregate.

Không tự gán relationshipId. Đây là metadata nội bộ do SDN/Neo4j quản lý, không phải mã thành viên, mã hợp đồng hoặc mã nghiệp vụ. Nếu ứng dụng cần mã nghiệp vụ cho quan hệ, hãy tạo property riêng, ví dụ membershipCode, và thiết kế constraint phù hợp với phiên bản Neo4j đang dùng.

Nếu lớp @RelationshipProperties không có field @RelationshipId, SDN không có metadata cần thiết để phân biệt các relationship khi ghi và có thể báo lỗi ngay trong giai đoạn khởi tạo mapping. Nếu thiếu @TargetNode hoặc khai báo nhiều field @TargetNode, metadata relationship không đáp ứng hợp đồng ánh xạ.

## 7. Phân biệt @Id và @RelationshipId

Hai annotation này có mục đích khác nhau:

| Annotation | Đặt ở đâu | Đại diện cho | Có tự gán giá trị không? |
|---|---|---|---|
| @Id | Node entity | Identity của entity/node | Tùy chiến lược: ứng dụng gán hoặc SDN/Neo4j sinh |
| @RelationshipId | Class @RelationshipProperties | Internal identity của relationship | Do SDN/Neo4j quản lý |
| @TargetNode | Class @RelationshipProperties | Node ở đầu kia của relationship | Được ánh xạ từ object graph |

Không thay @RelationshipId bằng @Id trong class relationship properties. Cũng không dùng @RelationshipId cho node entity.

Một relationship thuần được khai báo bằng @Relationship tới node entity không cần class có @RelationshipId. Chỉ khi dùng @RelationshipProperties mới cần metadata relationship tương ứng.

## 8. Metadata relationship sai hướng hoặc sai kiểu

Ngay cả khi class có đủ ID, SDN vẫn có thể không đọc hoặc ghi đúng relationship nếu type và direction không khớp với graph.

Ví dụ graph thực tế:

~~~cypher
(:Person)-[:MEMBER_OF]->(:Team)
~~~

Nếu field trong Team khai báo relationship mặc định OUTGOING, SDN sẽ tìm quan hệ từ Team đi ra Person. Nhưng graph đang lưu theo hướng Person → Team. Cần khai báo INCOMING từ góc nhìn Team:

~~~java
@Relationship(
    type = "MEMBER_OF",
    direction = Relationship.Direction.INCOMING
)
private List<Membership> members;
~~~

Mặc định direction của @Relationship là OUTGOING. Luôn so sánh hướng từ góc nhìn class đang chứa field relationship với hướng thực tế trong database.

Ngoài ra, cần kiểm tra:

- Type trong @Relationship có trùng chính xác với relationship type trong graph không.
- @TargetNode có trỏ đến đúng loại node cần ánh xạ không.
- Node ở đầu kia có label phù hợp với class đích không.
- Field relationship có kiểu node entity hoặc relationship properties class phù hợp không.
- Relationship properties có đúng một @TargetNode.
- Không khai báo hai field @TargetNode cho cùng một relationship properties class.

## 9. Những nguyên nhân thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Lưu entity mới thất bại vì thiếu identifier | Field @Id không tồn tại hoặc giá trị business ID đang null | Khai báo @Id và gán ID hoặc dùng @GeneratedValue |
| Có field id nhưng SDN vẫn báo thiếu ID | Import nhầm JPA Id hoặc annotation không được SDN nhận diện | Dùng SDN Id hoặc Spring Data Id |
| ID không được sinh | Có @Id nhưng thiếu @GeneratedValue, hoặc generator không hợp lệ | Chọn một chiến lược ID rõ ràng |
| Business ID được gán nhưng save tạo node mới | Không có @Version để SDN nhận biết entity đã tồn tại | Thêm field @Version kiểu Long |
| Hai node có cùng business ID | Database chưa có uniqueness constraint hoặc dữ liệu cũ đã trùng | Dọn dữ liệu rồi tạo constraint |
| ID immutable vẫn null sau save | Thiếu setter, wither hoặc cơ chế tạo instance mới | Bổ sung wither/constructor phù hợp |
| Ứng dụng lỗi khi khởi động mapping context | Class @RelationshipProperties thiếu @RelationshipId | Thêm field Long có @RelationshipId |
| Relationship properties không tìm được endpoint | Thiếu @TargetNode hoặc khai báo sai class | Khai báo đúng một target node |
| Relationship không được đọc | Sai relationship type hoặc direction | Đối chiếu graph và @Relationship |
| Lưu lại relationship làm mất property hoặc tạo quan hệ bất thường | Thiếu relationship identity hoặc mapping graph không nhất quán | Bổ sung @RelationshipId và kiểm tra aggregate graph |
| Dùng @RelationshipId như mã nghiệp vụ | Nhầm internal ID với business key | Tạo property nghiệp vụ riêng |
| Custom ID class không được mapping | Kiểu ID không phải simple type được hỗ trợ | Dùng kiểu đơn giản hoặc cấu hình converter phù hợp |

## 10. Dùng Cypher để tìm dữ liệu có định danh không hợp lệ

Khi entity được ánh xạ từ dữ liệu đã tồn tại, vấn đề có thể nằm trong graph chứ không phải Java class. Hãy truy vấn dữ liệu trước khi thay đổi schema hoặc thêm constraint.

### Tìm node thiếu business ID

Ví dụ Team dùng teamCode làm business ID:

~~~cypher
MATCH (t:Team)
WHERE t.teamCode IS NULL OR trim(t.teamCode) = ''
RETURN elementId(t) AS nodeRef,
       labels(t) AS labels,
       t.teamCode AS teamCode
~~~

elementId chỉ dùng để xác định node trong phiên chẩn đoán. Không lưu giá trị này làm business ID lâu dài.

### Tìm business ID trùng lặp

~~~cypher
MATCH (t:Team)
WHERE t.teamCode IS NOT NULL
WITH t.teamCode AS teamCode,
     collect(elementId(t)) AS nodeRefs
WHERE size(nodeRefs) > 1
RETURN teamCode, nodeRefs
~~~

Hãy quyết định node nào là bản ghi chính, hợp nhất quan hệ và xử lý node trùng trước khi tạo uniqueness constraint.

### Tìm relationship thiếu property bắt buộc

~~~cypher
MATCH (t:Team)-[r:HAS_MEMBER]->(p:Person)
WHERE r.role IS NULL
   OR r.joinedAt IS NULL
RETURN t.teamCode AS teamCode,
       p.id AS personId,
       elementId(r) AS relationshipRef,
       properties(r) AS relationshipProperties
~~~

Query này kiểm tra property nghiệp vụ của relationship. Nó không kiểm tra @RelationshipId, vì relationship ID nội bộ không phải property Cypher thông thường.

### Tìm relationship trỏ tới node có label không đúng

~~~cypher
MATCH (t:Team)-[r:HAS_MEMBER]->(target)
WHERE NOT target:Person
RETURN t.teamCode AS teamCode,
       elementId(r) AS relationshipRef,
       labels(target) AS targetLabels
~~~

Kết quả giúp phát hiện graph có relationship type đúng nhưng endpoint không mang label mà class đích mong đợi.

### Tìm relationship trùng theo cặp endpoint

Nếu nghiệp vụ chỉ cho phép một quan hệ HAS_MEMBER giữa một Team và một Person:

~~~cypher
MATCH (t:Team)-[r:HAS_MEMBER]->(p:Person)
WITH t, p, collect(r) AS relationships
WHERE size(relationships) > 1
RETURN t.teamCode AS teamCode,
       p.id AS personId,
       [r IN relationships | elementId(r)] AS relationshipRefs
~~~

Neo4j cho phép nhiều relationship cùng type giữa cùng hai node. Nếu nghiệp vụ không cho phép điều đó, ứng dụng phải có quy tắc upsert và kiểm soát cạnh tranh phù hợp. Không dựa vào @RelationshipId để tự ngăn quan hệ trùng.

## 11. Quy trình chẩn đoán theo thứ tự

Khi gặp lỗi ID hoặc relationship metadata, hãy kiểm tra theo trình tự:

1. **Định danh node:** class có @Id được SDN nhận diện chưa? Annotation có import đúng package không?
2. **Chiến lược cấp ID:** field được ứng dụng gán hay sinh tự động? Có đang trộn business ID và generated ID không?
3. **Kiểu dữ liệu:** generated ID có dùng kiểu được hỗ trợ? Với internal ID, ưu tiên Long thay vì long để biểu diễn trạng thái chưa lưu.
4. **Newness detection:** nếu ID được gán trước, entity đã có @Version chưa?
5. **Khả năng cập nhật ID:** entity immutable có setter/wither hoặc constructor phù hợp không?
6. **Relationship properties:** class có @RelationshipProperties, đúng một @TargetNode và field @RelationshipId chưa?
7. **Relationship metadata:** type, direction và target node có khớp graph thực tế không?
8. **Dữ liệu cũ:** có node thiếu ID, ID trùng hoặc relationship thiếu property nghiệp vụ không?
9. **Database constraints:** uniqueness constraint đã bảo vệ business key chưa?
10. **Kiểm thử:** thử tạo mới, đọc lại và cập nhật entity cùng relationship trên Neo4j test database.

Đọc root cause của exception và xác định lỗi xảy ra ở giai đoạn nào: Spring khởi tạo mapping context, SDN chuyển entity thành dữ liệu ghi, Neo4j thực thi query hay database constraint từ chối dữ liệu. Các giai đoạn khác nhau cần cách sửa khác nhau.

## 12. Kiểm thử để ngăn lỗi định danh quay lại

Một bộ test persistence nên có các tình huống:

| Test case | Điều cần xác nhận |
|---|---|
| Tạo node mới với generated ID | ID được cấp sau khi save |
| Tạo node mới với business ID | ID được lưu đúng và version được khởi tạo |
| Lưu lại entity đã đọc | Cập nhật node hiện hữu, không tạo node trùng |
| Cập nhật hai transaction cạnh tranh | Optimistic locking phát hiện version cũ |
| Tạo relationship properties | Relationship được ghi cùng property và target node |
| Lưu lại relationship đã đọc | SDN nhận diện relationship cũ bằng @RelationshipId |
| Đọc relationship theo direction | Kết quả khớp hướng được khai báo |
| Thiếu @RelationshipId | Mapping metadata bị phát hiện sớm |
| Thiếu hoặc khai báo sai @TargetNode | Mapping metadata bị phát hiện |
| Trùng business ID | Uniqueness constraint từ chối ghi trùng |

Unit test có thể kiểm tra logic tạo ID, quy tắc business key và cách domain object thay đổi. Nhưng unit test không thể xác nhận SDN mapping metadata được diễn giải đúng hoặc database constraint hoạt động. Dùng integration test với Neo4j thật hoặc Neo4j Test Harness cho các hành vi đó.

## 13. Những điều nên tránh

- Không dùng một field tự đặt tên id mà thiếu @Id.
- Không import jakarta.persistence.Id hoặc javax.persistence.Id thay cho annotation Spring Data.
- Không dùng cùng lúc nhiều chiến lược ID trên cùng một entity.
- Không tự gán ID nội bộ do Neo4j quản lý.
- Không dùng internal node ID hoặc relationship ID làm mã nghiệp vụ.
- Không bỏ @Version khi dùng business ID được gán trước.
- Không tự tăng hoặc đặt giá trị @Version trong code nghiệp vụ.
- Không khai báo @RelationshipProperties mà thiếu @RelationshipId.
- Không bỏ @TargetNode hoặc khai báo nhiều target node trong cùng class relationship properties.
- Không thêm @RelationshipId cho quan hệ đơn giản không dùng relationship properties.
- Không đoán direction; hãy đối chiếu với graph thực tế.
- Không tạo uniqueness constraint trước khi kiểm tra dữ liệu trùng hiện có.

## 14. Bài tập thực hành

Xây dựng mô hình Team và Person, trong đó một Team có nhiều Person thông qua quan hệ HAS_MEMBER. Relationship lưu role và joinedAt.

Thực hiện:

1. Tạo Person dùng UUIDStringGenerator.
2. Tạo Team dùng business ID teamCode và @Version.
3. Khai báo Membership bằng @RelationshipProperties.
4. Bổ sung @RelationshipId và đúng một @TargetNode.
5. Khai báo relationship HAS_MEMBER theo hướng Team đi tới Person.
6. Lưu Team cùng hai Membership.
7. Đọc lại Team và kiểm tra role, joinedAt.
8. Thay đổi role rồi lưu lại để xác nhận relationship được cập nhật đúng.
9. Viết Cypher tìm node Team thiếu teamCode.
10. Viết Cypher tìm teamCode trùng.
11. Tạo uniqueness constraint cho Team.teamCode.
12. Thử lưu hai Team cùng teamCode và quan sát lỗi.
13. Thử bỏ @RelationshipId trong môi trường test để quan sát lỗi metadata.
14. Đổi hướng relationship trong annotation rồi so sánh kết quả đọc với graph thực tế.

Câu hỏi tự kiểm tra:

- Vì sao mỗi node entity cần @Id?
- @GeneratedValue khác business ID ở điểm nào?
- Vì sao nên dùng Long thay vì long cho internal generated ID?
- Khi dùng business ID, @Version giải quyết vấn đề gì?
- Vì sao immutable entity có generated ID cần wither hoặc cơ chế tương đương?
- @RelationshipId khác @Id ra sao?
- Vì sao @RelationshipProperties cần đúng một @TargetNode?
- Quan hệ đơn giản không có properties có cần @RelationshipId không?
- Vì sao relationship direction sai có thể khiến SDN không đọc được dữ liệu mong muốn?
- Làm thế nào tìm node có ID null hoặc business ID trùng bằng Cypher?

## Kết luận

Lỗi định danh trong Spring Data Neo4j thường xuất phát từ việc thiếu @Id, chọn sai chiến lược ID, import nhầm annotation hoặc dùng business ID mà không có @Version. Với relationship có thuộc tính, SDN cần @RelationshipId để theo dõi quan hệ và đúng một @TargetNode để xác định endpoint còn lại. Type và direction của @Relationship cũng phải khớp với cấu trúc graph.

Hãy chọn một chiến lược ID rõ ràng cho mỗi node, bảo vệ business key bằng uniqueness constraint và để SDN quản lý generated ID cùng version. Với relationship properties, phân biệt internal relationship ID với property nghiệp vụ. Kết hợp kiểm tra metadata, truy vấn Cypher dữ liệu cũ và integration test tạo/đọc/cập nhật để tìm đúng nguyên nhân thay vì sửa ngẫu nhiên annotation.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2: Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j 8.2: Handling and provisioning of unique IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Neo4j Cypher Manual: Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual: Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
