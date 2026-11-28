# Phân biệt Map quan hệ động với Map thuộc tính tổng hợp

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt hai ý nghĩa khác nhau của Map trong Spring Data Neo4j: tập hợp relationship có kiểu thay đổi lúc chạy và tập hợp property của một node hoặc relationship.
- Ánh xạ dynamic relationship bằng Map có key là kiểu relationship và value là domain node.
- Ánh xạ composite property bằng @CompositeProperty.
- Đọc cấu trúc dữ liệu tương ứng trong Neo4j và viết Cypher để truy vấn.
- Chọn đúng mô hình, tránh nhầm lẫn giữa một liên kết đồ thị và một nhóm thuộc tính.

## 1. Vì sao cần phân biệt hai loại Map?

Trong Java, Map là cấu trúc key-value. Tuy nhiên, khi ánh xạ với Neo4j, một Map có thể diễn đạt hai ý nghĩa nghiệp vụ hoàn toàn khác nhau:

1. **Dynamic relationship map** mô tả các liên kết giữa node. Key của Map đại diện cho kiểu relationship; value là node đích hoặc tập hợp node đích.
2. **Composite property map** mô tả một nhóm thuộc tính của chính node hoặc relationship đang chứa Map. Key của Map được ghép với một prefix để tạo tên property trong Neo4j.

Hai trường đều có thể dùng Map trong Java, nhưng cấu trúc đồ thị được tạo ra khác nhau. Dynamic relationship tạo các cạnh nối những node riêng biệt. Composite property tạo nhiều property trên cùng một node hoặc relationship, không tạo thêm node hay cạnh.

Ví dụ, một Person có thể có các liên kết KNOWS và WORKS_WITH đến những Person khác. Cùng Person đó cũng có thể có một nhóm thuộc tính mở rộng như locale, theme hoặc sourceSystem. Nhóm đầu tiên là quan hệ đồ thị; nhóm thứ hai là metadata của Person.

## 2. Dynamic relationship map: key là kiểu relationship

Spring Data Neo4j hỗ trợ dynamic relationship thông qua Map có key là String hoặc Enum và value là một domain class được ánh xạ thành node. Với dynamic one-to-many association, Map có thể chứa Collection các node cho mỗi kiểu relationship.

Điểm quan trọng là **key của Map xác định relationship type**. Vì vậy, không khai báo một type cố định trong @Relationship. Annotation dùng để xác định hướng của relationship.

### Ví dụ Map<String, Set<Person>>

Giả sử một Person có thể liên kết với nhiều Person khác bằng nhiều kiểu quan hệ:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    @Relationship(direction = Relationship.Direction.OUTGOING)
    private Map<String, Set<Person>> links = new HashMap<>();

    public void addLink(String relationshipType, Person target) {
        links.computeIfAbsent(
            relationshipType,
            key -> new HashSet<>()
        ).add(target);
    }

    // Constructor và getter được lược bỏ.
}
~~~

Ứng dụng có thể thêm các liên kết như sau:

~~~java
Person an = new Person("p-1", "An");
Person binh = new Person("p-2", "Binh");
Person chi = new Person("p-3", "Chi");

an.addLink("KNOWS", binh);
an.addLink("WORKS_WITH", chi);
~~~

Khi Person An được lưu, Map biểu diễn hai kiểu relationship khác nhau:

~~~text
(An:Person)-[:KNOWS]->(Binh:Person)
(An:Person)-[:WORKS_WITH]->(Chi:Person)
~~~

Ở đây:

- links là thuộc tính ánh xạ relationship.
- Key KNOWS và WORKS_WITH trở thành kiểu relationship trong Neo4j.
- Các phần tử trong Set<Person> là node đích.
- Hướng OUTGOING áp dụng cho các relationship được mô tả bởi thuộc tính links.

Nếu một kiểu relationship có nhiều node đích, collection giữ các node đó dưới cùng key:

~~~java
an.addLink("KNOWS", binh);
an.addLink("KNOWS", chi);
~~~

Kết quả có dạng:

~~~text
(An:Person)-[:KNOWS]->(Binh:Person)
(An:Person)-[:KNOWS]->(Chi:Person)
~~~

### Dùng Enum làm key

Nếu ứng dụng chỉ cho phép một tập kiểu relationship đã biết, có thể dùng Enum làm key:

~~~java
public enum PersonLinkType {
    KNOWS,
    WORKS_WITH,
    REPORTS_TO
}

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Relationship(direction = Relationship.Direction.OUTGOING)
    private Map<PersonLinkType, Person> primaryLinks = new EnumMap<>(PersonLinkType.class);
}
~~~

Enum giúp giới hạn kiểu relationship mà mã ứng dụng có thể tạo. Với dynamic one-to-many, dùng Map có key String và value là Collection của domain node theo dạng được SDN hỗ trợ.

### Đọc dynamic relationship bằng Cypher

Có thể lấy các node đích cùng kiểu relationship bằng truy vấn:

~~~cypher
MATCH (p:Person {personId: $personId})-[r]->(target:Person)
RETURN type(r) AS relationshipType, target
ORDER BY relationshipType
~~~

Hàm type(r) trả về kiểu relationship thực tế. Điều này hữu ích khi ứng dụng cần đọc các liên kết có nhiều kiểu khác nhau từ cùng một thuộc tính Map.

### Khi nào nên dùng dynamic relationship?

Dynamic relationship phù hợp khi:

- Kiểu liên kết thay đổi theo dữ liệu hoặc cấu hình nghiệp vụ lúc chạy.
- Một domain class có nhiều kiểu relationship cùng trỏ đến một loại node.
- Ứng dụng cần duyệt các node đích theo từng kiểu liên kết.
- Danh sách kiểu relationship có thể được mở rộng mà không cần thêm một field Java cho từng kiểu.

Nếu kiểu relationship đã cố định và có ý nghĩa nghiệp vụ riêng, khai báo từng thuộc tính bằng @Relationship(type = "...") thường rõ ràng hơn, dễ kiểm tra kiểu hơn và giúp người đọc domain model hiểu ngay ý nghĩa của liên kết.

## 3. Composite property map: key tạo tên property

Một Map khác có thể dùng để lưu nhóm thuộc tính linh hoạt. Trong trường hợp này, các entry không đại diện cho node đích. Chúng trở thành nhiều property trên node hoặc relationship đang chứa Map.

Spring Data Neo4j cung cấp annotation @CompositeProperty cho mục đích này. Annotation này chủ yếu được dùng với Map<String, Object> hoặc Map có key là Enum. SDN tách Map thành các property riêng có chung prefix.

Ví dụ, một Product có nhóm thông số tùy biến:

~~~java
@Node("Product")
public class Product {

    @Id
    private String sku;

    @CompositeProperty(prefix = "spec", delimiter = "_")
    private Map<String, Object> specifications = new HashMap<>();

    public Product(String sku) {
        this.sku = sku;
    }

    // Getter được lược bỏ.
}
~~~

Ứng dụng điền dữ liệu:

~~~java
Product product = new Product("sku-100");

product.getSpecifications().put("color", "black");
product.getSpecifications().put("weightKg", 1.25);
product.getSpecifications().put("wireless", true);
~~~

Khi lưu Product, các entry của Map được ánh xạ thành property trên chính node Product:

~~~cypher
(:Product {
    sku: "sku-100",
    spec_color: "black",
    spec_weightKg: 1.25,
    spec_wireless: true
})
~~~

Không có node mới hay relationship nào được tạo từ các key color, weightKg hoặc wireless. Chúng chỉ là các property thuộc về Product.

### Prefix và delimiter

@CompositeProperty có hai tùy chọn quan trọng:

- **prefix** xác định phần đầu của tên property.
- **delimiter** xác định ký tự nối prefix với key của Map.

Nếu không chỉ định prefix, SDN dùng tên field Java. Delimiter mặc định là dấu chấm.

Ví dụ:

~~~java
@CompositeProperty
private Map<String, Object> metadata = new HashMap<>();
~~~

Entry có key createdBy sẽ được lưu dưới tên property metadata.createdBy.

Nếu khai báo:

~~~java
@CompositeProperty(prefix = "meta", delimiter = "_")
private Map<String, Object> metadata = new HashMap<>();
~~~

Entry createdBy sẽ được lưu thành meta_createdBy.

Hãy chọn prefix ổn định và không trùng với các property độc lập khác của node hoặc relationship. Nếu đổi prefix hoặc delimiter sau khi dữ liệu đã tồn tại, tên property mà ứng dụng đọc và ghi sẽ thay đổi; cần có kế hoạch chuyển đổi dữ liệu nếu vẫn muốn truy cập các property cũ.

### Kiểu dữ liệu và giới hạn

Composite property không phải một JSON document lồng nhau được lưu nguyên khối. Mỗi entry trở thành một property riêng của Neo4j.

Các giá trị phải chuyển đổi được sang kiểu property mà Neo4j hỗ trợ. SDN áp dụng các converter đã đăng ký cho từng giá trị. Nested Map không được hỗ trợ bởi converter composite mặc định.

Ví dụ này phù hợp:

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("color", "black");
attributes.put("weight", 1.25);
attributes.put("available", true);
~~~

Còn Map lồng nhau như sau không được hỗ trợ trực tiếp bởi composite converter mặc định:

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put(
    "dimensions",
    Map.of("width", 10, "height", 20)
);
~~~

Nếu cần ánh xạ một kiểu Java phức tạp thành nhiều property, có thể triển khai Neo4jPersistentPropertyToMapConverter và cấu hình converter cho @CompositeProperty. Converter phải biết cách phân rã đối tượng thành Map khi ghi và tái tạo đối tượng khi đọc.

### Composite property trên relationship

Neo4j cho phép property nằm trên relationship. Vì vậy, @CompositeProperty cũng có thể được dùng trên một thuộc tính của lớp được đánh dấu @RelationshipProperties. Khi đó các entry trở thành property của relationship tương ứng, vẫn theo quy tắc prefix và delimiter.

Ví dụ một relationship MEMBER_OF có nhóm thuộc tính điều kiện linh hoạt:

~~~java
@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long id;

    @TargetNode
    private Department department;

    @CompositeProperty(prefix = "rule", delimiter = "_")
    private Map<String, Object> rules = new HashMap<>();
}
~~~

Khi Membership được dùng làm kiểu relationship của một thuộc tính @Relationship, các entry trong rules trở thành property như rule_approvalRequired trên chính relationship MEMBER_OF. Department vẫn là node đích được chỉ ra bởi @TargetNode.

Điều này khác với dynamic relationship map: dynamic map chọn kiểu relationship và node đích; composite map bổ sung nhiều property cho một node hoặc relationship đã được xác định.

## 4. So sánh trực tiếp hai cách ánh xạ

| Khía cạnh | Dynamic relationship map | Composite property map |
|---|---|---|
| Annotation | @Relationship | @CompositeProperty |
| Ý nghĩa key | Kiểu relationship | Phần tên property sau prefix |
| Ý nghĩa value | Domain node hoặc collection domain node | Giá trị property |
| Kết quả trong Neo4j | Relationship nối các node | Nhiều property trên cùng node/relationship |
| Dùng Cypher | Duyệt cạnh và node đích | Đọc/lọc property |
| Ví dụ key | KNOWS, WORKS_WITH | color, weightKg, source |
| Cấu trúc Java | Map<String, Person> hoặc Map<String, Collection<Person>> | Map<String, Object> |
| Có tạo node đích không? | Có, value là domain node được ánh xạ | Không |
| Có tạo relationship không? | Có | Không |

Cách ghi nhớ:

- Nếu value của Map là một domain node và key mô tả loại liên kết giữa hai node, đó là dynamic relationship.
- Nếu value của Map là dữ liệu như String, Number hoặc Boolean và key chỉ là tên thuộc tính, đó là composite property.

## 5. Chọn đúng mô hình theo câu hỏi nghiệp vụ

Hãy xét hai yêu cầu sau.

**Yêu cầu A: Một người có thể theo dõi, quen biết hoặc làm việc cùng những người khác.**

Ứng dụng cần biết người đích là ai, kiểu liên kết là gì, và có thể duyệt từ người này sang người khác. Đây là cấu trúc đồ thị, vì vậy dynamic relationship map phù hợp.

**Yêu cầu B: Một sản phẩm có các thông số thay đổi tùy loại hàng.**

Một sản phẩm có thể có màu sắc, trọng lượng, kích thước, chất liệu hoặc thông tin do nhà cung cấp bổ sung. Những giá trị này mô tả chính sản phẩm và không cần trở thành node độc lập. Composite property map phù hợp.

Nếu một giá trị cần được chia sẻ, định danh riêng, có relationship riêng hoặc được truy vấn như một thực thể, hãy cân nhắc mô hình nó thành node. Nếu một quan hệ cần thuộc tính nghiệp vụ riêng như ngày bắt đầu, trạng thái hoặc vai trò, hãy cân nhắc @RelationshipProperties. Không nên dùng composite property để thay thế một mô hình đồ thị có thực thể và liên kết thực sự.

## 6. Truy vấn và kiểm tra dữ liệu

### Truy vấn dynamic relationship

Để tìm các liên kết KNOWS của một Person:

~~~cypher
MATCH (p:Person {personId: $personId})
      -[:KNOWS]->
      (friend:Person)
RETURN friend.personId, friend.fullName
~~~

Để lấy tất cả kiểu relationship mà Person đang có:

~~~cypher
MATCH (p:Person {personId: $personId})-[r]->(target)
RETURN type(r) AS type, target
ORDER BY type
~~~

### Truy vấn composite property

Với Product có prefix spec và delimiter _, có thể đọc từng property:

~~~cypher
MATCH (p:Product {sku: $sku})
RETURN p.spec_color AS color,
       p.spec_weightKg AS weightKg,
       p.spec_wireless AS wireless
~~~

Có thể lọc theo một property cụ thể:

~~~cypher
MATCH (p:Product)
WHERE p.spec_color = "black"
RETURN p.sku, p.spec_weightKg
~~~

Như vậy, dynamic relationship được truy vấn bằng pattern node-relationship-node. Composite property được truy vấn như các property thông thường trên node hoặc relationship.

## 7. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dynamic relationship không tạo đúng kiểu | Đã khai báo type cố định trong @Relationship trong khi muốn dùng key của Map | Bỏ type cố định, để key của Map xác định relationship type |
| Map relationship không ánh xạ được node đích | Value type không phải domain class được SDN quản lý | Dùng node entity hoặc collection node entity đúng kiểu |
| Không thấy relationship mong đợi | Map key không khớp relationship type mà ứng dụng đang truy vấn | Kiểm tra key thực tế và direction |
| Composite property không được ghi | Map chưa được đánh dấu @CompositeProperty | Thêm annotation cho field Map |
| Property có tên không như dự kiến | Prefix hoặc delimiter khác với tên được dùng trong Cypher | Kiểm tra cấu hình prefix/delimiter và tên property thực tế |
| Lưu composite map thất bại | Giá trị không chuyển đổi được thành kiểu property Neo4j hỗ trợ | Dùng kiểu dữ liệu phù hợp hoặc đăng ký converter |
| Map lồng nhau không được đọc/ghi | Composite converter mặc định không hỗ trợ nested Map | Làm phẳng cấu trúc hoặc viết converter tùy chỉnh |
| Dữ liệu cũ không được đọc sau khi đổi prefix | Tên property trong graph chưa được chuyển đổi | Lập kế hoạch migration và kiểm tra dữ liệu trước/sau |

## 8. Thực hành: cùng một Person có liên kết và metadata

Tạo một Person có dynamic relationship và composite properties:

~~~java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String fullName;

    @Relationship(direction = Relationship.Direction.OUTGOING)
    private Map<String, Set<Person>> links = new HashMap<>();

    @CompositeProperty(prefix = "profile", delimiter = "_")
    private Map<String, Object> profileData = new HashMap<>();

    // Constructor, getter và helper method được lược bỏ.
}
~~~

Tạo dữ liệu:

~~~java
Person an = new Person("p-1", "An");
Person binh = new Person("p-2", "Binh");

an.addLink("KNOWS", binh);
an.getProfileData().put("locale", "vi-VN");
an.getProfileData().put("theme", "dark");

people.save(an);
~~~

Sau khi lưu, hãy kiểm tra trong Neo4j:

~~~cypher
MATCH (p:Person {personId: "p-1"})
RETURN p
~~~

Và kiểm tra relationship:

~~~cypher
MATCH (p:Person {personId: "p-1"})-[r]->(target:Person)
RETURN type(r), target
~~~

Kết quả mong đợi:

- Node An có các property profile_locale và profile_theme.
- Có một relationship KNOWS từ An đến Bình.
- Node Bình vẫn là một node riêng.
- Các key locale và theme không tạo relationship hoặc node mới.

Tự kiểm tra:

1. Nếu key của dynamic map là WORKS_WITH, key đó đại diện cho điều gì trong Neo4j?
2. Nếu key của composite map là locale và prefix là profile, property được lưu tên gì khi delimiter là dấu gạch dưới?
3. Map<String, Set<Person>> nên được ánh xạ bằng @Relationship hay @CompositeProperty?
4. Vì sao Map<String, Object> có nested Map không được composite converter mặc định hỗ trợ?

Đáp án cần nắm: WORKS_WITH là relationship type; property có tên profile_locale; Map chứa node đích là dynamic relationship; nested Map không phải kiểu property phẳng mà converter mặc định hỗ trợ.

## Kết luận

Dynamic relationship map và composite property map đều sử dụng cấu trúc key-value trong Java, nhưng chúng mô tả hai phần khác nhau của đồ thị.

Dynamic relationship map dùng key để xác định relationship type và value để chỉ node đích. Composite property map dùng @CompositeProperty để trải các entry thành nhiều property có chung prefix trên node hoặc relationship hiện tại.

Hãy chọn dynamic relationship khi nghiệp vụ cần liên kết giữa các thực thể và truy vấn đường đi. Hãy chọn composite property khi cần lưu một nhóm thuộc tính linh hoạt của một thực thể hoặc relationship. Việc phân biệt đúng hai cách ánh xạ giúp domain model rõ ràng, Cypher dễ đọc và tránh tạo ra cấu trúc đồ thị sai với ý nghĩa nghiệp vụ.
