# Giải quyết đồ thị có chu trình bằng DTO hoặc định danh tham chiếu

Object graph trong Java thường có quan hệ hai chiều hoặc nhiều đường dẫn cùng trỏ đến một object. Ví dụ một Department chứa danh sách Employee, trong khi mỗi Employee lại tham chiếu Department; một Node có parent và children; hoặc hai object cùng tham chiếu một Address. Những quan hệ này hợp lý trong bộ nhớ, nhưng JSON được biểu diễn như cây. Nếu serialize trực tiếp graph có chu trình, Jackson có thể đi theo reference mãi cho đến khi tràn stack hoặc tạo ra output lặp lớn.

Có hai hướng xử lý chính:

- **Chuyển graph thành DTO có cấu trúc rõ ràng**: chọn dữ liệu và hướng liên kết mà API thực sự cần, thường dùng ID thay cho object reference ngược.
- **Biểu diễn identity/reference trong output**: dùng các annotation như **@JsonManagedReference**, **@JsonBackReference** hoặc **@JsonIdentityInfo** để Jackson biết quan hệ nào được ghi đầy đủ và quan hệ nào được biểu diễn bằng tham chiếu.

DTO thường là lựa chọn dễ kiểm soát nhất cho API công khai. Annotation identity hữu ích khi consumer cần tái tạo graph hoặc khi cấu trúc object đã được xác định rõ. Hãy chọn dựa trên wire contract, cách consumer đọc dữ liệu và semantics cần bảo toàn, không chỉ dựa trên việc làm cho lỗi recursion biến mất.

## 1. Object graph khác với JSON tree như thế nào?

Trong Java, object có thể trỏ đến object khác qua field, collection hoặc map. Một object có thể được tham chiếu từ nhiều nơi và một chu trình có thể quay trở lại object ban đầu.

Ví dụ:

~~~text
Department A
    |
    | employees
    v
Employee 1 -------- department --------+
    |                                   |
    +-----------------------------------+
                                        |
                                        v
                                   Department A
~~~

Trong bộ nhớ, đây là một graph. JSON object và array được lồng theo cấu trúc cây:

~~~json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {
      "id": 101,
      "name": "Linh"
    }
  ]
}
~~~

JSON không có cú pháp reference object chuẩn như con trỏ Java. Nếu ghi toàn bộ Department bên trong Employee rồi lại ghi Employee bên trong Department, output sẽ cần lặp vô hạn hoặc cần một quy ước identity riêng.

Cần phân biệt:

- **Chu trình (cycle)**: đi theo một chuỗi reference rồi quay lại object đã gặp, ví dụ A → B → A.
- **Reference dùng chung (shared reference)**: hai property cùng trỏ đến một object, nhưng không nhất thiết tạo chu trình.
- **Graph có nhiều đường đi**: cùng một object có thể được truy cập qua nhiều nhánh khác nhau.
- **Tree**: mỗi node (trừ root) có đúng một parent và không có chu trình.

Chu trình và shared reference là hai vấn đề khác nhau. Một serializer có thể tránh recursion nhưng vẫn nhân đôi cùng một object ở nhiều nhánh, làm mất identity khi đọc lại. Nếu identity là yêu cầu nghiệp vụ, cần chọn representation có ID hoặc reference rõ ràng.

## 2. Vì sao serialize trực tiếp có thể gây recursion?

Giả sử hai class có quan hệ hai chiều:

~~~java
public class Department {
    private Long id;
    private String name;
    private List<Employee> employees;
}

public class Employee {
    private Long id;
    private String name;
    private Department department;
}
~~~

Khi Jackson serialize Department:
1. Đọc property employees.
2. Serialize từng Employee.
3. Employee có property department.
4. Serialize Department lần nữa.
5. Department lại có employees.
6. Quay lại Employee ban đầu.

Nếu không có cơ chế xử lý identity/reference, quá trình có thể tiếp tục cho đến khi stack overflow hoặc bị giới hạn bởi một cơ chế khác.

Một số dấu hiệu:
- StackOverflowError trong lúc ghi JSON.
- JSON output bị lặp nhiều tầng và rất lớn.
- Test serialize chạy rất lâu hoặc treo.
- Một request API thất bại khi object graph có dữ liệu liên kết đầy đủ.
- Object có thể serialize khi chỉ có một phía relation được load, nhưng lỗi khi relation hai chiều được load đồng thời.

Không nên chỉ bắt StackOverflowError rồi trả JSON rỗng. Cần xác định graph nào đang tạo chu trình và chọn một wire representation có chủ đích.

## 3. Xác định consumer cần cây hay graph

Trước khi chọn annotation, trả lời các câu hỏi:

1. Consumer có cần đi từ child về parent không?
2. Có cần bảo toàn shared reference, tức hai property phải trỏ đến cùng một object sau deserialize không?
3. Consumer có cần thay đổi object rồi ghi ngược lại mà vẫn giữ quan hệ identity không?
4. Graph có thể lớn hoặc sâu đến mức cần phân trang/lazy loading không?
5. ID trong graph có phải public identifier hay chỉ là database primary key nội bộ?
6. Có nhiều loại relation khác nhau giữa cùng hai object không?
7. Dữ liệu sẽ được dùng bởi Java consumer hay nhiều ngôn ngữ khác nhau?

Nếu consumer chỉ cần hiển thị danh sách Employee trong Department, không cần serialize Department bên trong mỗi Employee. Một DTO một chiều là đủ.

Nếu consumer cần chỉnh sửa graph và phải biết các node có cùng identity, JSON nên chứa ID/reference hoặc một danh sách node phẳng cùng danh sách edge.

Nếu graph là cây thật, có thể serialize thành nested DTO. Nếu graph có shared node hoặc chu trình, nên dùng ID hoặc một mô hình graph riêng.

## 4. Cách 1: Dùng DTO để cắt chu trình ngay tại wire boundary

DTO là object dành cho việc trao đổi dữ liệu. Nó không cần sao chép toàn bộ quan hệ của domain entity.

Thay vì:

~~~java
class Department {
    Long id;
    List<Employee> employees;
}

class Employee {
    Long id;
    Department department;
}
~~~

Tạo response model:

~~~java
public record DepartmentResponse(
    Long id,
    String name,
    List<EmployeeSummary> employees
) {}

public record EmployeeSummary(
    Long id,
    String name
) {}
~~~

EmployeeSummary không có property Department. Vì vậy graph domain được chuyển thành cây JSON có giới hạn:

~~~json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {"id": 101, "name": "Linh"},
    {"id": 102, "name": "Minh"}
  ]
}
~~~

Cách này có một số lợi ích:
- Không phụ thuộc vào annotation serialization trên entity.
- Kiểm soát rõ field được public.
- Tránh lộ field nội bộ, lazy proxy và relation không cần thiết.
- Có thể thay đổi domain model mà không làm đổi API.
- Giới hạn độ sâu và kích thước response.
- Dễ tài liệu hóa bằng OpenAPI hoặc JSON Schema.

DTO không chỉ là cách tránh cycle. Nó là contract độc lập giữa producer và consumer.

## 5. Dùng ID thay cho object reference ngược trong DTO

Nếu consumer cần biết Employee thuộc Department nào, thêm identifier:

~~~java
public record DepartmentResponse(
    Long id,
    String name,
    List<EmployeeResponse> employees
) {}

public record EmployeeResponse(
    Long id,
    String name,
    Long departmentId
) {}
~~~

JSON:

~~~json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {
      "id": 101,
      "name": "Linh",
      "departmentId": 10
    }
  ]
}
~~~

Consumer có thể liên kết employee với department theo ID mà không cần lồng Department lần nữa.

Một mô hình khác là response phẳng:

~~~json
{
  "departments": [
    {"id": 10, "name": "Engineering"}
  ],
  "employees": [
    {"id": 101, "name": "Linh", "departmentId": 10}
  ]
}
~~~

Mô hình phẳng đặc biệt hữu ích khi nhiều node được dùng chung hoặc graph có nhiều chu trình. Mỗi node xuất hiện một lần; relation được biểu diễn bằng ID.

Cần dùng identifier phù hợp với public contract. Không mặc định expose database key nếu nó là chi tiết nội bộ hoặc có thể thay đổi. Có thể dùng UUID/public key hoặc một identifier ổn định khác.

## 6. Map entity sang DTO một cách tường minh

Một mapper thủ công đơn giản:

~~~java
DepartmentResponse toResponse(Department department) {
    List<EmployeeResponse> employees =
        department.getEmployees().stream()
            .map(employee -> new EmployeeResponse(
                employee.getId(),
                employee.getName(),
                department.getId()
            ))
            .toList();

    return new DepartmentResponse(
        department.getId(),
        department.getName(),
        employees
    );
}
~~~

Mapper chỉ đi theo hướng cần thiết và không gọi ngược employee.getDepartment() để serialize toàn bộ Department lần nữa.

Với graph phức tạp, có thể tách mapper theo use case:
- toDepartmentSummary()
- toDepartmentDetail()
- toEmployeeDetail()
- toGraphSnapshot()

Đừng tạo một mapper tổng quát luôn đi qua tất cả relation. Nó dễ kích hoạt lazy loading, recursion và truy vấn database ngoài dự kiến.

Nếu dùng MapStruct hoặc thư viện mapping khác, vẫn cần định nghĩa rõ relation nào bị cắt và field nào chuyển thành ID. Công cụ mapping không tự quyết định wire contract.

## 7. Nested DTO cần giới hạn độ sâu

Có trường hợp consumer muốn xem cây phân cấp, ví dụ Category có children. Nếu dữ liệu là cây thật, có thể dùng nested DTO:

~~~java
public record CategoryTree(
    Long id,
    String name,
    List<CategoryTree> children
) {}
~~~

Nhưng nếu domain cho phép một Category có nhiều parent hoặc có cycle, mô hình này có thể nhân đôi node hoặc lặp vô hạn.

Có thể giới hạn depth:

~~~java
CategoryTree toTree(Category category, int depth, int maxDepth) {
    if (depth >= maxDepth) {
        return new CategoryTree(
            category.getId(),
            category.getName(),
            List.of()
        );
    }

    List<CategoryTree> children =
        category.getChildren().stream()
            .map(child -> toTree(child, depth + 1, maxDepth))
            .toList();

    return new CategoryTree(
        category.getId(),
        category.getName(),
        children
    );
}
~~~

Giới hạn depth ngăn cây quá sâu, nhưng không tự xử lý shared reference hoặc chu trình. Nếu một node có thể xuất hiện ở nhiều nhánh hoặc quay về ancestor, cần visited set hoặc biểu diễn relation bằng ID.

Không nên âm thầm cắt dữ liệu nếu consumer cần biết response bị giới hạn. Có thể trả metadata như truncated, nextPageToken hoặc endpoint lấy children riêng.

## 8. Dùng visited set khi chuyển graph sang DTO

Khi duyệt graph, có thể theo dõi các object đã gặp bằng identity semantics. IdentityHashMap so sánh reference bằng ==, phù hợp khi cần nhận biết đúng cùng một instance Java.

Ví dụ duyệt để tạo danh sách node phẳng:

~~~java
void visit(
        Node node,
        Set<Node> visited,
        List<NodeSummary> result) {

    if (node == null || !visited.add(node)) {
        return;
    }

    result.add(new NodeSummary(node.getId(), node.getName()));

    for (Node child : node.getChildren()) {
        visit(child, visited, result);
    }
}
~~~

Khởi tạo visited set:

~~~java
Set<Node> visited =
    Collections.newSetFromMap(new IdentityHashMap<>());
~~~

Sau khi thu thập node, tạo edge list bằng ID:

~~~java
public record NodeSummary(Long id, String name) {}

public record Edge(Long fromId, Long toId, String relation) {}

public record GraphResponse(
    List<NodeSummary> nodes,
    List<Edge> edges
) {}
~~~

Visited set ngăn duyệt lại cùng instance và tránh recursion vô hạn. Tuy nhiên, nó chỉ là cơ chế duyệt graph; không thay thế việc định nghĩa output. Consumer vẫn cần node ID và edge semantics để tái tạo quan hệ.

Nếu domain dùng nhiều object instance khác nhau nhưng cùng database ID, IdentityHashMap coi chúng là hai object riêng. Nếu muốn deduplicate theo business ID, dùng map theo ID và xác định cách xử lý khi hai instance cùng ID nhưng dữ liệu khác nhau.

## 9. Cách 2: @JsonManagedReference và @JsonBackReference

Jackson Databind cung cấp hai annotation để xử lý quan hệ hai chiều phổ biến:

- **@JsonManagedReference** đánh dấu phía forward/parent. Phía này được serialize bình thường.
- **@JsonBackReference** đánh dấu phía back/child. Phía này bị bỏ qua khi serialize để không quay lại parent.

Ví dụ:

~~~java
public class Department {

    private Long id;
    private String name;

    @JsonManagedReference("department-employees")
    private List<Employee> employees;

    // getters/setters
}

public class Employee {

    private Long id;
    private String name;

    @JsonBackReference("department-employees")
    private Department department;

    // getters/setters
}
~~~

Khi serialize Department, output chứa employees nhưng mỗi Employee không lồng Department trở lại:

~~~json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {"id": 101, "name": "Linh"},
    {"id": 102, "name": "Minh"}
  ]
}
~~~

Đây là mô hình phù hợp khi:
- Quan hệ có một hướng chính để serialize.
- Parent chứa collection children.
- Child có một property trỏ ngược về parent.
- Consumer không cần nhận parent lặp lại trong từng child.

## 10. @JsonManagedReference và @JsonBackReference khi deserialize

Hai annotation không chỉ tác động lúc ghi. Khi deserialize quan hệ managed/back reference, Jackson có thể gắn child back reference về parent sau khi tạo các child từ property managed.

Ví dụ:

~~~java
Department department =
    mapper.readValue(json, Department.class);

Employee employee = department.getEmployees().get(0);

assertSame(department, employee.getDepartment());
~~~

Assertion assertSame kiểm tra đúng cùng một object instance, không chỉ hai object có cùng ID hoặc bằng nhau.

Đây là điểm khác với DTO chỉ chứa departmentId. DTO truyền identifier; managed/back reference có thể khôi phục object reference trong graph Java khi đọc đúng cấu trúc.

Một back reference cần trỏ về một object đơn, không phải collection/array/map. Phía managed có thể là property chứa một object hoặc collection. Nếu relation không phù hợp với mô hình parent-child này, hãy cân nhắc JsonIdentityInfo hoặc DTO.

Không dùng hai annotation này để mô hình hóa mọi loại graph. Chúng phù hợp nhất cho một quan hệ hai chiều có hướng serialize rõ ràng.
## 11. Đặt tên reference khi có nhiều quan hệ

Mặc định hai annotation dùng tên reference mặc định. Nếu một class có nhiều relation, hãy đặt tên riêng cho từng cặp:

~~~java
public class Project {

    @JsonManagedReference("project-tasks")
    private List<Task> tasks;

    @JsonManagedReference("project-members")
    private List<Member> members;
}

public class Task {

    @JsonBackReference("project-tasks")
    private Project project;
}

public class Member {

    @JsonBackReference("project-members")
    private Project project;
}
~~~

Tên phải khớp giữa managed và back reference tương ứng. Không dùng cùng tên cho các relation độc lập vì Jackson có thể không xác định được cặp cần gắn.

Nếu cùng hai class có nhiều relation khác nhau, ví dụ Employee có department và approver, hãy cân nhắc tên riêng và test từng đường. Cấu trúc relation không rõ ràng có thể tạo lỗi lúc introspection hoặc deserialize.

## 12. Giới hạn của managed/back reference

Managed/back reference không phải object identity tổng quát:

- Chỉ một phía được serialize theo hướng forward; back property bị bỏ.
- Nếu serialize child làm root, parent back reference vẫn không được ghi ra.
- Không biểu diễn tốt graph có shared references tùy ý.
- Không giải quyết việc nhiều node cùng trỏ đến một node theo nhiều đường.
- Back reference được thiết kế cho một property đơn trỏ về managed parent.
- Không tự động cung cấp public ID/reference cho consumer ở định dạng JSON.

Nếu consumer cần parent ID trong từng child, hãy thêm field ID vào DTO hoặc dùng property khác có chủ đích. Không giả định JsonBackReference sẽ serialize parent thành ID.

Khi một model có nhiều quan hệ phức tạp, dùng annotation để loại một chu trình có thể chỉ che được một đường recursion; một đường khác vẫn có thể quay lại graph.

## 13. Cách 3: @JsonIdentityInfo để ghi object ID và reference

@JsonIdentityInfo cho phép Jackson biểu diễn object bằng một object identifier. Lần đầu object xuất hiện có thể được ghi đầy đủ cùng ID; những lần tham chiếu sau có thể được ghi dưới dạng ID thay vì lặp toàn bộ object.

Ví dụ dùng property id:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class Node {

    private Long id;
    private String name;
    private Node parent;
    private List<Node> children;

    // getters/setters
}
~~~

Nếu root và child tham chiếu qua lại, Jackson có thể ghi object đầy đủ một lần rồi dùng ID cho reference tiếp theo. Hình dạng chính xác của JSON phụ thuộc vào thứ tự duyệt và cấu hình annotation, nhưng ý nghĩa là một node có identity được chia sẻ thay vì được lồng lặp vô hạn.

Một ví dụ giản lược:

~~~json
{
  "id": 1,
  "name": "root",
  "children": [
    {
      "id": 2,
      "name": "child",
      "parent": 1
    }
  ]
}
~~~

Ở đây parent: 1 biểu diễn reference về object có ID 1 đã được định danh. Đây là một phần của contract JSON; consumer phải hiểu ID reference thay vì mong parent luôn là object lồng đầy đủ.

## 14. Chọn ObjectIdGenerator phù hợp

Jackson cung cấp nhiều loại generator, thường gặp:

| Generator | Ý nghĩa |
|---|---|
| PropertyGenerator | Dùng giá trị của một property trên object, ví dụ id |
| IntSequenceGenerator | Tạo ID số tuần tự trong phạm vi serialization |
| UUIDGenerator | Tạo UUID |
| StringIdGenerator | Tạo string identifier theo generator |

Với API hoặc event cần ID ổn định, PropertyGenerator thường dễ hiểu vì ID nằm trong domain/wire model. Tuy nhiên property phải có giá trị và duy nhất trong phạm vi identity mà Jackson quản lý.

Ví dụ:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Node.class
)
public class Node {
    public Long id;
    public String name;
}
~~~

Không dùng một ID có thể trùng giữa các node trong cùng scope nếu consumer cần phân biệt chúng. Nếu nhiều loại object dùng cùng ID nhưng có thể tham chiếu lẫn nhau, hãy xác định scope và kiểu identity rõ ràng.

IntSequenceGenerator tiện cho một tài liệu tạm thời, nhưng ID sinh ra không phải database ID và không nên được xem là identifier bền vững qua nhiều message.

## 15. Scope và vòng đời của object identity

Object identity của Jackson có phạm vi theo cơ chế serializer/deserializer và object ID generator/resolver. Nó không tự động biến ID thành truy vấn database.

Các điểm cần nhớ:
- PropertyGenerator dùng giá trị property làm ID.
- ID cần duy nhất trong phạm vi type/scope đã xác định.
- Scope có thể giúp phân biệt các miền identity.
- Reference ID chỉ có ý nghĩa trong tài liệu hoặc luồng dữ liệu mà consumer có thể giải quyết.
- Default resolver không tự load entity từ database theo ID.
- Không nên lưu một ID reference rời rạc rồi kỳ vọng mapper tự tìm object ở request khác.

Nếu input chứa một ID mà object tương ứng chưa được đọc/đăng ký trong cùng quá trình deserialize, Jackson có thể báo unresolved object ID. Nếu API muốn nhận một database ID và load entity, dùng DTO chứa ID rồi gọi repository/service để resolve theo authorization và transaction phù hợp.

Không nhầm Jackson object identity với JPA persistence identity. Hai cơ chế có mục tiêu và lifecycle khác nhau.

## 16. @JsonIdentityReference(alwaysAsId = true)

@JsonIdentityReference điều chỉnh cách một property tham chiếu đến object đã có identity. Khi bật alwaysAsId = true, property được ghi như ID ngay cả khi object chưa xuất hiện đầy đủ ở vị trí trước đó trong traversal.

Ví dụ:

~~~java
public class GraphEnvelope {

    private Node root;

    @JsonIdentityReference(alwaysAsId = true)
    private List<Node> relatedNodes;
}
~~~

Nếu Node có @JsonIdentityInfo, relatedNodes có thể được biểu diễn như danh sách ID thay vì danh sách object đầy đủ.

Điều này có thể làm output ngắn và tránh lặp dữ liệu, nhưng consumer cần biết cách resolve ID. Khi deserialize, alwaysAsId không tự gọi database hoặc service để tìm object. ID phải được giải quyết trong context identity của Jackson hoặc bằng một cơ chế custom mà ứng dụng chủ động cung cấp.

Dùng annotation này khi contract thực sự muốn property đó luôn là reference. Không áp dụng toàn cục nếu một số consumer cần object đầy đủ.

## 17. So sánh managed/back reference với object identity

| Tiêu chí | Managed/back reference | Object identity |
|---|---|---|
| Mục tiêu | Cắt một quan hệ parent-child hai chiều | Bảo toàn identity/reference trong graph |
| Output | Forward object; back property bị bỏ | Object đầy đủ lần đầu, reference ID ở lần sau |
| Consumer cần hiểu ID | Không nhất thiết | Có |
| Deserialize | Có thể tự gắn back reference | Resolve ID trong object identity context |
| Shared references | Không phải mục tiêu chính | Phù hợp hơn |
| Graph nhiều loại quan hệ | Hạn chế | Linh hoạt hơn nhưng contract phức tạp |
| Public API | Tốt khi chỉ cần một chiều | Tốt khi consumer thật sự cần graph identity |
| Độ rõ ràng với consumer đa ngôn ngữ | Dễ hiểu nếu output là tree | Cần quy ước ID reference rõ ràng |

Nếu consumer không cần graph identity, DTO thường còn rõ hơn cả hai annotation. Nếu cần bảo toàn graph trong Java, JsonIdentityInfo có thể phù hợp.

## 18. Mô hình graph phẳng với nodes và edges

Đối với graph có nhiều chu trình, một cách biểu diễn rõ ràng là tách node và edge:

~~~java
public record GraphNodeDto(
    String id,
    String label
) {}

public record GraphEdgeDto(
    String from,
    String to,
    String relation
) {}

public record GraphDto(
    List<GraphNodeDto> nodes,
    List<GraphEdgeDto> edges
) {}
~~~

JSON:

~~~json
{
  "nodes": [
    {"id": "A", "label": "Node A"},
    {"id": "B", "label": "Node B"},
    {"id": "C", "label": "Node C"}
  ],
  "edges": [
    {"from": "A", "to": "B", "relation": "parent"},
    {"from": "B", "to": "A", "relation": "child"},
    {"from": "A", "to": "C", "relation": "related"}
  ]
}
~~~

Consumer dựng map ID → node trước, sau đó duyệt edges để gắn quan hệ. Mô hình này:
- Không có nested cycle.
- Mỗi node được phát một lần.
- Hỗ trợ shared references và nhiều relation.
- Có thể phân trang node/edge.
- Dễ kiểm tra ID trùng và edge trỏ đến node không tồn tại.

Đổi lại, consumer cần bước dựng graph sau khi parse. Đây là lựa chọn tốt cho graph thực sự là dữ liệu chính, chẳng hạn sơ đồ phụ thuộc, mạng lưới hoặc workflow graph.

## 19. Custom serializer khi wire format cần được thiết kế riêng

Khi DTO hoặc annotation không diễn đạt được output mong muốn, có thể dùng custom serializer. Ví dụ chỉ ghi ID của relation:

~~~java
public class EmployeeSerializer
        extends StdSerializer<Employee> {

    public EmployeeSerializer() {
        super(Employee.class);
    }

    @Override
    public void serialize(
            Employee employee,
            JsonGenerator generator,
            SerializerProvider provider)
            throws IOException {

        generator.writeStartObject();
        generator.writeNumberField("id", employee.getId());
        generator.writeStringField("name", employee.getName());

        Department department = employee.getDepartment();

        if (department == null) {
            generator.writeNullField("departmentId");
        } else {
            generator.writeNumberField(
                "departmentId",
                department.getId()
            );
        }

        generator.writeEndObject();
    }
}
~~~

Serializer này không đi theo object reference Department, nên không tạo cycle. Tuy nhiên, custom serializer làm tăng trách nhiệm bảo trì:
- Phải giữ output đồng bộ với contract.
- Phải xử lý null và kiểu dữ liệu.
- Có thể bỏ sót field khi DTO thay đổi.
- Cần serializer/deserializer tương ứng nếu muốn đọc lại.
- Phải test bằng mapper production.

Nếu logic mapping phức tạp, DTO mapper thường dễ kiểm tra hơn custom serializer gắn trực tiếp vào domain entity.

## 20. @JsonIgnore hoặc bỏ một chiều quan hệ

Trong một số trường hợp đơn giản, có thể bỏ property ngược:

~~~java
public class Employee {
    private Long id;
    private String name;

    @JsonIgnore
    private Department department;
}
~~~

Cách này tránh serialize relation department từ Employee. Nhưng nó có nghĩa property bị ignore theo cấu hình annotation trong cả serialization/deserialization thông thường, trừ khi có access mode hoặc cấu hình khác.

Nếu cần đọc property nhưng không ghi, dùng access mode phù hợp:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String secret;
~~~

Đối với relation, hãy cẩn thận: @JsonIgnore có thể làm mất khả năng khôi phục graph khi deserialize. Nó phù hợp khi property không thuộc wire contract hoặc chỉ cần một chiều rõ ràng.

Không dùng @JsonIgnore chỉ để dập recursion mà chưa xác định consumer có cần dữ liệu bị bỏ hay không.
## 21. JPA/Hibernate và lazy relation

Entity JPA thường có quan hệ hai chiều:

~~~java
@Entity
class DepartmentEntity {

    @OneToMany(mappedBy = "department")
    private List<EmployeeEntity> employees;
}

@Entity
class EmployeeEntity {

    @ManyToOne
    private DepartmentEntity department;
}
~~~

Serialize entity trực tiếp có thể:
- Kích hoạt lazy loading khi Jackson gọi getter.
- Tạo nhiều truy vấn N+1.
- Kéo graph lớn ngoài dự kiến.
- Gặp proxy type hoặc collection wrapper.
- Gặp recursion qua relation hai chiều.
- Tiết lộ field persistence không thuộc API.

Cách ổn định thường là query đúng dữ liệu cho use case, rồi map sang DTO trong transaction phù hợp. Fetch strategy cần được thiết kế riêng; đừng dùng serializer annotation để thay thế query plan.

Nếu cần nested response, dùng projection/fetch join/entity graph có giới hạn và map DTO ngay sau khi load. Tránh để Jackson vô tình quyết định database traversal bằng cách gọi getter.

## 22. Không expose database entity chỉ vì Jackson có thể serialize

Entity là model persistence; DTO là contract trao đổi. Hai loại có vòng đời và mục tiêu khác nhau.

Entity có thể chứa:
- Internal ID.
- Audit metadata.
- Version field.
- Relation không được phép public.
- Lazy proxy.
- Password hash hoặc token.
- Field chỉ dùng cho transaction.
- Relation có thể tạo cycle.

Nếu trả entity trực tiếp, một thay đổi mapping database có thể làm API output đổi theo. DTO giúp chọn field và định dạng độc lập.

Đặc biệt, không để @JsonIdentityInfo khiến database ID nội bộ tự động trở thành public reference nếu chưa đánh giá quyền riêng tư, enumeration risk và khả năng lộ cấu trúc dữ liệu.

## 23. Giới hạn kích thước và độ sâu graph

Ngay cả khi đã giải quyết cycle, graph có thể rất lớn. Một root node có hàng trăm nghìn descendants sẽ tạo JSON khổng lồ.

Cần giới hạn:
- Số node.
- Số edge.
- Độ sâu traversal.
- Số child mỗi node.
- Tổng byte response.
- Số relation được mở rộng.
- Thời gian và số truy vấn database.

Với graph lớn, dùng pagination hoặc endpoint riêng để lấy neighbor/children thay vì nhúng toàn bộ graph. Có thể trả metadata như nextCursor, hasMore hoặc truncated để consumer biết dữ liệu chưa đầy đủ.

StreamReadConstraints bảo vệ parser khi đọc input; nó không tự giới hạn số node mà ứng dụng quyết định serialize. Giới hạn graph cần được thực hiện ở query, mapper hoặc domain service.

## 24. Bảo vệ deserialization khỏi ID reference không hợp lệ

Nếu JSON chứa object identity, input có thể:
- Tham chiếu đến ID không tồn tại trong document.
- Dùng ID trùng lặp.
- Dùng ID sai kiểu.
- Tạo graph rất lớn.
- Tạo chu trình không được nghiệp vụ cho phép.
- Trỏ tới object không thuộc quyền truy cập của caller.

Jackson có thể resolve identity trong document, nhưng không thay thế validation nghiệp vụ. Sau deserialize, cần kiểm tra:
- Mọi reference đều được resolve.
- ID duy nhất theo contract.
- Relation được phép theo domain.
- Không có edge trái phép.
- Node count và depth nằm trong giới hạn.
- Caller được phép tham chiếu các resource tương ứng nếu ID là external identifier.

Nếu ID đại diện cho database resource, resolve qua service/repository và kiểm tra authorization. Không tin rằng có ID trong JSON nghĩa là caller được quyền gắn object đó vào graph.

## 25. Kiểm tra chu trình hợp lệ và chu trình không hợp lệ

Không phải mọi cycle đều là lỗi. Ví dụ graph phụ thuộc có thể cho phép cycle về mặt dữ liệu nhưng thuật toán downstream cần phát hiện nó. Một cây phân cấp tổ chức có thể cấm employee làm manager của chính mình hoặc tạo vòng quản lý.

Sau khi deserialize:
- Dùng DFS với trạng thái unvisited/visiting/visited để phát hiện back edge.
- Hoặc dùng thuật toán strongly connected components nếu cần tìm toàn bộ thành phần chu trình.
- Kiểm tra invariant domain, không chỉ kiểm tra Jackson đọc thành công.

Ví dụ DFS phát hiện cycle:

~~~java
boolean hasCycle(Node node, Set<Node> visiting, Set<Node> visited) {
    if (visiting.contains(node)) {
        return true;
    }

    if (visited.contains(node)) {
        return false;
    }

    visiting.add(node);

    for (Node child : node.getChildren()) {
        if (hasCycle(child, visiting, visited)) {
            return true;
        }
    }

    visiting.remove(node);
    visited.add(node);
    return false;
}
~~~

Đoạn code giả định graph được duyệt theo một chiều children và không có mutation đồng thời. Với graph lớn, cân nhắc iterative DFS để tránh stack overflow trong chính thuật toán kiểm tra.

Cycle detection ở domain là bước validation độc lập. JsonIdentityInfo cho phép biểu diễn identity, không khẳng định mọi cycle đều hợp lệ.

## 26. Kiểm thử serialization không còn recursion

Với managed/back reference, kiểm tra output và quan hệ sau deserialize:

~~~java
@Test
void managedAndBackReferencesSerializeAndRestore() throws Exception {
    Department department = new Department();
    department.setId(10L);

    Employee employee = new Employee();
    employee.setId(101L);

    department.setEmployees(List.of(employee));
    employee.setDepartment(department);

    String json = mapper.writeValueAsString(department);

    assertFalse(json.contains("\"department\":"));

    Department restored =
        mapper.readValue(json, Department.class);

    assertSame(
        restored,
        restored.getEmployees().get(0).getDepartment()
    );
}
~~~

Ví dụ giả định getter/setter và constructor phù hợp với Databind. Nếu dùng immutable record hoặc custom creator, kiểm tra cách Jackson hỗ trợ back reference trong phiên bản đang dùng.

Đừng chỉ assert serialize không ném exception. Cần xác nhận output có shape đúng và graph khôi phục đúng invariant mong đợi.

## 27. Kiểm thử @JsonIdentityInfo và shared reference

Một test identity nên kiểm tra hai property trỏ đến cùng instance sau deserialize:

~~~java
@Test
void preservesSharedObjectIdentity() throws Exception {
    Node shared = new Node(3L, "shared");

    GraphEnvelope original = new GraphEnvelope(
        new Node(1L, "root", List.of(shared)),
        shared
    );

    String json = mapper.writeValueAsString(original);

    GraphEnvelope restored =
        mapper.readValue(json, GraphEnvelope.class);

    assertSame(
        restored.root().children().get(0),
        restored.relatedNode()
    );
}
~~~

Test này chỉ minh họa invariant. Model và property annotation phải được cấu hình sao cho cả hai property cùng dùng identity của Node. Nếu relatedNode dùng alwaysAsId = true, cần đảm bảo node ID được resolve trong quá trình deserialize theo cấu trúc input.

Thêm test:
- ID trùng.
- Reference không có target.
- Target xuất hiện sau reference nếu contract cho phép forward reference.
- Null relation.
- Nhiều node cùng ID ở scope khác nhau.
- Object có ID chưa được gán.

Đừng chỉ kiểm tra JSON chứa số ID. Hãy xác nhận reader thật khôi phục đúng object graph.

## 28. Kiểm thử DTO không lộ chu trình

Với DTO, test nên xác nhận output chỉ có các field được công bố:

~~~java
@Test
void departmentResponseContainsOnlyPublicEmployeeSummary()
        throws Exception {

    DepartmentResponse response = mapper.toResponse(sampleDepartment());

    String json = objectMapper.writeValueAsString(response);
    JsonNode tree = objectMapper.readTree(json);

    assertTrue(tree.path("employees").isArray());
    assertFalse(
        tree.path("employees").get(0).has("department")
    );
    assertTrue(
        tree.path("employees").get(0).has("departmentId")
    );
}
~~~

Ngoài output shape, kiểm tra:
- Số employee đúng.
- ID relation đúng.
- Null semantics đúng.
- Không kích hoạt lazy loading ngoài dự kiến.
- Query count nằm trong giới hạn nếu test dùng JPA.
- Depth/size response tuân thủ contract.

DTO test thường dễ đọc và ít phụ thuộc vào chi tiết Jackson annotation hơn.

## 29. Chọn chiến lược theo tình huống

| Tình huống | Chiến lược phù hợp |
|---|---|
| REST response chỉ cần một hướng quan hệ | DTO projection |
| Child cần parent ID | DTO với identifier |
| Quan hệ parent-child hai chiều đơn giản và muốn khôi phục graph | Managed/back reference |
| Shared reference cần giữ cùng object instance | Object identity |
| Graph có nhiều cycle và nhiều loại edge | Nodes + edges DTO |
| JSON chỉ cần bỏ relation ngược | JsonIgnore hoặc DTO |
| Entity JPA có lazy relation phức tạp | Query/projection + DTO |
| Consumer đa ngôn ngữ | DTO với ID/reference contract rõ |
| Graph lớn hoặc sâu | Pagination, bounded traversal và ID reference |

Một nguyên tắc hữu ích: nếu consumer không yêu cầu object identity, đừng đưa identity metadata vào wire format chỉ để tiết kiệm vài dòng JSON. Mô hình ID reference làm consumer phức tạp hơn và cần validation riêng.

## 30. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách thay thế |
|---|---|---|
| Serialize entity hai chiều trực tiếp | Recursion hoặc output phình lớn | DTO projection |
| Chỉ bắt StackOverflowError | Che nguyên nhân và response không xác định | Cắt cycle tại wire boundary |
| Dùng JsonIgnore khắp entity | API khó hiểu, mất dữ liệu khi đọc | DTO hoặc reference rõ ràng |
| Dùng managed/back cho graph tùy ý | Không biểu diễn shared reference tổng quát | Object identity hoặc nodes/edges |
| Dùng ID database mà không xem public contract | Lộ internal key | Public identifier hoặc DTO mapping |
| Tin Jackson ID sẽ load entity từ DB | Reference unresolved hoặc sai security | Resolve qua service/repository |
| Duyệt graph không có visited set | Lặp node hoặc recursion vô hạn | Identity/ID-based traversal |
| Nhúng toàn bộ graph lớn | Heap và response tăng mạnh | Pagination, bounded depth |
| Dùng cùng ObjectMapper test và production giả lập | Bỏ sót cấu hình thực tế | Test mapper/converter production |

## 31. Quy trình triển khai

Khi xử lý graph có chu trình:

1. Vẽ graph domain và xác định cycle/shared reference.
2. Ghi rõ consumer cần cây, object identity hay danh sách relation.
3. Nếu consumer không cần graph identity, thiết kế DTO và dùng ID cho relation ngược.
4. Nếu quan hệ parent-child hai chiều đơn giản, cân nhắc @JsonManagedReference và @JsonBackReference.
5. Nếu cần bảo toàn shared object identity, cấu hình @JsonIdentityInfo và ID duy nhất.
6. Chỉ dùng @JsonIdentityReference(alwaysAsId = true) khi consumer hiểu ID-only reference.
7. Với graph phức tạp, cân nhắc mô hình nodes/edges.
8. Giới hạn depth, node count, edge count và response size.
9. Nếu dùng JPA, query đúng relation và map DTO trong transaction phù hợp.
10. Validate ID, reference, authorization và cycle rules sau deserialize.
11. Test output shape, reference resolution và identity bằng assertSame khi cần.
12. Kiểm tra bằng mapper và consumer configuration thực tế.

## Kết luận

Chu trình trong object graph là đặc điểm hợp lệ của mô hình Java, nhưng JSON mặc định là cấu trúc cây nên không thể lồng object vô hạn. Cần quyết định rõ dữ liệu nào được mở rộng, dữ liệu nào được cắt và relation nào được biểu diễn bằng ID.

DTO là lựa chọn dễ kiểm soát cho API và integration; @JsonManagedReference/@JsonBackReference phù hợp với quan hệ parent-child hai chiều; @JsonIdentityInfo hữu ích khi consumer cần bảo toàn identity và shared references. Với graph phức tạp, mô hình nodes/edges thường minh bạch hơn. Dù chọn cách nào, hãy kiểm tra output contract, giới hạn kích thước graph và xác minh deserialization khôi phục đúng quan hệ mà ứng dụng cần.



