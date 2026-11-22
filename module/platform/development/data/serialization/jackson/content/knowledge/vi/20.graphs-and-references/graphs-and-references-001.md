# Phân biệt dữ liệu dạng cây và đồ thị đối tượng có chu trình

JSON được tổ chức theo cấu trúc lồng nhau: object chứa property, array chứa phần tử, mỗi value lại có thể là object hoặc array khác. Cấu trúc này tạo thành một **cây dữ liệu**. Trong Java, các object có thể tham chiếu lẫn nhau, nhiều object có thể cùng trỏ đến một instance, và một object có thể tham chiếu ngược về object đã tạo ra nó. Vì vậy, mô hình Java có thể là một **đồ thị đối tượng**, kể cả đồ thị có chu trình.

Sự khác biệt này rất quan trọng khi dùng Jackson. Object graph có thể chứa vòng tham chiếu mà JSON lồng nhau thông thường không biểu diễn trực tiếp được. Nếu serialize graph có chu trình mà không có chiến lược xử lý, Jackson có thể lặp đệ quy, báo lỗi hoặc tràn stack. Ngược lại, nếu graph có nhiều tham chiếu cùng đến một object, JSON mặc định có thể ghi nội dung object đó nhiều lần và khi đọc lại tạo ra các instance riêng.

Để xử lý đúng, cần hiểu cấu trúc cây của JSON, cấu trúc tham chiếu của Java, rồi chọn cách biểu diễn phù hợp: chuyển graph thành DTO dạng cây, bỏ qua một chiều tham chiếu, dùng cặp managed/back reference, hoặc dùng object identity để giữ quan hệ tham chiếu.

## 1. Dữ liệu dạng cây là gì?

Một cây dữ liệu có một node gốc. Các node con được nối từ node cha xuống dưới. Trong cây thông thường, mỗi node (trừ root) có một node cha và không có đường đi nào quay ngược về node đã đi qua.

JSON object và array có thể lồng nhau:

~~~json
{
  "orderId": "ORD-100",
  "customer": {
    "id": "CUS-01",
    "name": "An"
  },
  "items": [
    {
      "sku": "KB-01",
      "quantity": 2
    },
    {
      "sku": "MS-02",
      "quantity": 1
    }
  ]
}
~~~

Có thể hình dung cấu trúc:

~~~mermaid
flowchart TD
    R[Root object] --> O[orderId]
    R --> C[customer]
    R --> I[items array]
    C --> CI[id]
    C --> CN[name]
    I --> E0[Item 0]
    I --> E1[Item 1]
    E0 --> S0[sku]
    E0 --> Q0[quantity]
    E1 --> S1[sku]
    E1 --> Q1[quantity]
~~~

Đặc điểm của biểu diễn này:

- Có một điểm bắt đầu là root.
- Mỗi property hoặc phần tử nằm bên trong một object/array cha.
- Dữ liệu được đi từ root xuống các nhánh con.
- Không có cú pháp JSON chuẩn để một value nói rằng nó chính là object đã xuất hiện ở một vị trí khác.
- Không có cú pháp JSON chuẩn để một node trỏ ngược lên cha của nó.

Một JSON document có thể lặp lại cùng nội dung ở nhiều nơi, nhưng mỗi lần xuất hiện vẫn là một value riêng trong document. JSON thuần không lưu khái niệm "hai vị trí này cùng tham chiếu đến một instance Java".

## 2. Đồ thị đối tượng Java là gì?

Trong Java, biến object lưu tham chiếu đến instance. Một instance có thể được nhiều object khác tham chiếu; một object cũng có thể giữ tham chiếu đến object khác. Khi biểu diễn các instance là node và các field tham chiếu là cạnh, ta có một đồ thị đối tượng (object graph).

Đồ thị có thể có:
- Một object cha tham chiếu đến nhiều object con.
- Một object con giữ tham chiếu ngược về object cha.
- Hai object cùng tham chiếu đến một object thứ ba.
- Các object tham chiếu vòng quanh thành chu trình.
- Nhiều đường khác nhau dẫn đến cùng một instance.

### 2.1. Tham chiếu một chiều

Ví dụ Order tham chiếu đến Customer:

~~~java
public class Order {
    private String id;
    private Customer customer;

    // Constructor, getter và setter.
}

public class Customer {
    private String name;

    // Constructor, getter và setter.
}
~~~

Quan hệ Java:

~~~mermaid
flowchart LR
    O[Order] --> C[Customer]
~~~

Đây là quan hệ một chiều, không tạo chu trình. Jackson có thể serialize thành JSON lồng nhau một cách tự nhiên:

~~~json
{
  "id": "ORD-100",
  "customer": {
    "name": "An"
  }
}
~~~

### 2.2. Tham chiếu hai chiều tạo chu trình

Trong mô hình quan hệ cha-con, object cha thường giữ danh sách con, còn mỗi object con lại giữ tham chiếu về cha:

~~~java
public class Department {
    private String name;
    private List<Employee> employees;

    // Constructor, getter và setter.
}

public class Employee {
    private String name;
    private Department department;

    // Constructor, getter và setter.
}
~~~

Khi gắn quan hệ:

~~~java
Department department = new Department();
department.setName("Engineering");

Employee employee = new Employee();
employee.setName("An");

employee.setDepartment(department);
department.setEmployees(List.of(employee));
~~~

Đồ thị lúc này có chu trình:

~~~mermaid
flowchart LR
    D[Department] -->|employees| E[Employee]
    E -->|department| D
~~~

Nếu Jackson serialize Department, nó đi đến employees, rồi đến department của Employee, rồi lại đến employees của Department. Quá trình có thể lặp lại liên tục vì mỗi object lại dẫn về object đã đi qua.

Đây là khác biệt căn bản giữa object graph và cây JSON: graph có cạnh quay về node cũ; JSON lồng nhau không có tham chiếu đối tượng như vậy.

## 3. Chia sẻ cùng một instance cũng khác với lặp lại dữ liệu

Không phải chỉ chu trình mới tạo ra khác biệt. Một đồ thị có thể không có chu trình nhưng vẫn có nhiều cạnh cùng trỏ đến một instance.

Ví dụ hai địa chỉ dùng chung một object Address:

~~~java
Address address = new Address("12 Nguyen Hue", "HCMC");

Customer customer = new Customer();
customer.setBillingAddress(address);
customer.setShippingAddress(address);
~~~

Đồ thị Java:

~~~mermaid
flowchart TD
    C[Customer] --> B[billingAddress]
    C --> S[shippingAddress]
    B --> A[Address instance]
    S --> A
~~~

billingAddress và shippingAddress là hai property nhưng cùng tham chiếu đến một instance Address.

Nếu serialize theo JSON lồng nhau mặc định, kết quả thường có dạng:

~~~json
{
  "billingAddress": {
    "street": "12 Nguyen Hue",
    "city": "HCMC"
  },
  "shippingAddress": {
    "street": "12 Nguyen Hue",
    "city": "HCMC"
  }
}
~~~

Nội dung Address được ghi hai lần. JSON không thể hiện rằng hai nhánh vốn cùng trỏ đến một instance.

Khi deserialize JSON trên thành Customer, Jackson thường tạo hai object Address độc lập. Dữ liệu có thể bằng nhau, nhưng quan hệ identity đã mất:

~~~java
assertEquals(
        customer.getBillingAddress(),
        customer.getShippingAddress()
);

// Không đúng nếu không có cơ chế object identity:
assertSame(
        customer.getBillingAddress(),
        customer.getShippingAddress()
);
~~~

assertEquals có thể đúng nếu Address triển khai equals theo giá trị. assertSame chỉ đúng khi hai property trỏ đến đúng cùng một instance.

Cần phân biệt:

- **Value equality**: hai object có dữ liệu tương đương.
- **Object identity**: hai tham chiếu cùng trỏ đến một instance.
- **Graph topology**: cách các instance liên kết với nhau.

JSON lồng nhau mặc định chủ yếu bảo toàn giá trị, không bảo toàn identity và toàn bộ topology của Java object graph.

## 4. Vì sao Jackson có thể gặp lỗi khi serialize chu trình?

Jackson Databind thường duyệt property của object để tạo JSON. Khi gặp property chứa object khác, serializer tiếp tục serialize object đó. Nếu object con lại tham chiếu đến object ban đầu, serializer có thể quay về node đã đi qua.

Ví dụ:

~~~java
public class Node {
    private String name;
    private Node next;

    // Getter và setter.
}
~~~

Tạo chu trình tự tham chiếu:

~~~java
Node node = new Node();
node.setName("A");
node.setNext(node);

String json = mapper.writeValueAsString(node);
~~~

Đồ thị là:

~~~mermaid
flowchart LR
    A[Node A] -->|next| A
~~~

Nếu không có cấu hình identity hoặc cách loại bỏ tham chiếu vòng, Jackson không thể biểu diễn chu trình này bằng JSON lồng nhau thông thường. Tùy hình dạng chu trình, serializer/cấu hình và phiên bản, nó có thể phát hiện self-reference trực tiếp rồi ném JsonMappingException, hoặc tiếp tục đệ quy với chu trình gián tiếp cho đến khi gặp lỗi/tràn stack.

Một chu trình gián tiếp:

~~~java
Node first = new Node();
Node second = new Node();

first.setName("A");
second.setName("B");

first.setNext(second);
second.setNext(first);
~~~

Quan hệ:

~~~mermaid
flowchart LR
    A[Node A] --> B[Node B]
    B --> A
~~~

Không nên dựa vào việc Jackson sẽ tự tìm ra cách cắt vòng. Ứng dụng phải quyết định biểu diễn JSON cho graph đó.

## 5. Cách 1: Chuyển object graph thành DTO dạng cây

Đối với REST API hoặc message trao đổi giữa các hệ thống, cách dễ kiểm soát thường là thiết kế DTO chỉ chứa dữ liệu client cần. DTO không nhất thiết sao chép toàn bộ quan hệ hai chiều của entity.

Ví dụ entity/domain có quan hệ hai chiều:

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

DTO có thể biểu diễn theo một chiều:

~~~java
public record DepartmentResponse(
        Long id,
        String name,
        List<EmployeeSummary> employees
) {
}

public record EmployeeSummary(
        Long id,
        String name
) {
}
~~~

Mapper thủ công:

~~~java
DepartmentResponse toResponse(Department department) {
    List<EmployeeSummary> employees = department.getEmployees()
            .stream()
            .map(employee -> new EmployeeSummary(
                    employee.getId(),
                    employee.getName()
            ))
            .toList();

    return new DepartmentResponse(
            department.getId(),
            department.getName(),
            employees
    );
}
~~~

JSON kết quả:

~~~json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {
      "id": 101,
      "name": "An"
    }
  ]
}
~~~

DTO không chứa lại Department trong từng EmployeeSummary, nên cấu trúc đầu ra là cây và không có chu trình.

Ưu điểm:
- Hợp đồng JSON rõ ràng, không phụ thuộc toàn bộ entity graph.
- Tránh serialize nhầm các quan hệ nội bộ.
- Kiểm soát được độ sâu và kích thước response.
- Dễ versioning API.
- Không cần đưa mọi quan hệ database ra ngoài.

Đây thường là lựa chọn tốt khi JSON là hợp đồng API công khai. Nếu client cần tải department từ employee, có thể trả departmentId hoặc endpoint tham chiếu riêng thay vì nhúng lại toàn bộ object cha.

## 6. Cách 2: @JsonManagedReference và @JsonBackReference

Jackson cung cấp cặp annotation để xử lý quan hệ cha-con hai chiều theo một hướng serialize.

- @JsonManagedReference: đánh dấu phía forward/parent reference được serialize bình thường.
- @JsonBackReference: đánh dấu phía back reference về parent, không serialize theo chiều ngược lại; khi deserialize, Jackson có thể gắn lại tham chiếu ngược.

### 6.1. Khai báo phía cha và phía con

~~~java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

public class Department {

    private String name;

    @JsonManagedReference
    private List<Employee> employees;

    public Department() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }

    public void setEmployees(List<Employee> employees) {
        this.employees = employees;
    }
}
~~~

~~~java
public class Employee {

    private String name;

    @JsonBackReference
    private Department department;

    public Employee() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Department getDepartment() {
        return department;
    }

    public void setDepartment(Department department) {
        this.department = department;
    }
}
~~~

### 6.2. Kết quả serialization

Khi serialize Department:

~~~java
String json = mapper.writeValueAsString(department);
~~~

JSON chỉ đi theo chiều Department -> employees:

~~~json
{
  "name": "Engineering",
  "employees": [
    {
      "name": "An"
    },
    {
      "name": "Binh"
    }
  ]
}
~~~

Property department trong Employee bị bỏ qua ở chiều serialize, nên không còn vòng lặp.

### 6.3. Kết quả deserialization

Khi đọc JSON vào Department:

~~~java
Department restored = mapper.readValue(json, Department.class);

Employee employee = restored.getEmployees().get(0);

assertSame(restored, employee.getDepartment());
~~~

Jackson có thể gắn back reference của Employee về đúng Department đang được tạo. Nhờ vậy, object graph Java có thể khôi phục quan hệ hai chiều dù JSON chỉ biểu diễn một chiều.

### 6.4. Giới hạn của managed/back reference

Cặp annotation này phù hợp với quan hệ cha-con có một chiều forward và một chiều back rõ ràng. Nó không phải giải pháp tổng quát cho mọi đồ thị:

- Một back reference phải tương ứng với managed reference phù hợp.
- Nếu có nhiều quan hệ cha-con trong cùng class, dùng tên value để đặt các cặp reference riêng.
- Back reference là chiều bị bỏ qua trong JSON; client không nhận lại đầy đủ cả hai hướng.
- Không phù hợp khi một node có nhiều parent độc lập hoặc graph có nhiều đường liên kết tùy ý.
- Không thay thế một định dạng graph có object identity rõ ràng.

Nếu có nhiều cặp quan hệ:

~~~java
@JsonManagedReference("department-employees")
private List<Employee> employees;

@JsonBackReference("department-employees")
private Department department;
~~~

Tên cặp giúp Jackson phân biệt các quan hệ khác nhau.

## 7. Cách 3: @JsonIgnore trên tham chiếu ngược

Nếu chỉ cần ngăn serialize một property gây vòng lặp và không cần Jackson tự gắn lại back reference khi deserialize, có thể dùng @JsonIgnore.

~~~java
public class Employee {

    private String name;

    @JsonIgnore
    private Department department;

    // Getter và setter.
}
~~~

Khi serialize Department, property department của Employee bị bỏ qua. JSON có cấu trúc một chiều tương tự managed/back reference.

Khác biệt quan trọng:
- @JsonIgnore loại property khỏi quá trình Jackson xử lý theo cấu hình annotation.
- @JsonBackReference là một phần của cặp quan hệ; Jackson hiểu cách gắn lại tham chiếu ngược khi deserialize.
- @JsonIgnore đơn giản hơn nếu back link chỉ là dữ liệu nội bộ và không cần khôi phục tự động.

Hãy chọn theo yêu cầu đọc lại. Nếu cần khôi phục quan hệ cha-con khi deserialize, managed/back reference thường diễn đạt ý định tốt hơn.

## 8. Cách 4: @JsonIdentityInfo để biểu diễn object identity

Nếu client cần giữ quan hệ tham chiếu giữa các object, chỉ cắt một chiều có thể làm mất thông tin. Khi đó có thể dùng object identity.

@JsonIdentityInfo yêu cầu Jackson nhận diện object bằng một ID. Khi một object đã xuất hiện trong JSON, các lần tham chiếu tiếp theo có thể được biểu diễn bằng ID thay vì serialize lại toàn bộ object.

### 8.1. Dùng ID có sẵn trong model

Ví dụ graph Node:

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class GraphNode {

    private String id;
    private List<GraphNode> neighbors;

    public GraphNode() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public List<GraphNode> getNeighbors() {
        return neighbors;
    }

    public void setNeighbors(List<GraphNode> neighbors) {
        this.neighbors = neighbors;
    }
}
~~~

Tạo chu trình:

~~~java
GraphNode a = new GraphNode();
a.setId("A");

GraphNode b = new GraphNode();
b.setId("B");

a.setNeighbors(new ArrayList<>(List.of(b)));
b.setNeighbors(new ArrayList<>(List.of(a)));
~~~

Quan hệ:

~~~mermaid
flowchart LR
    A[Node A] --> B[Node B]
    B --> A
~~~

Serialize:

~~~java
String json = mapper.writeValueAsString(a);
~~~

Một dạng JSON minh họa:

~~~json
{
  "id": "A",
  "neighbors": [
    {
      "id": "B",
      "neighbors": [
        "A"
      ]
    }
  ]
}
~~~

Object A được ghi đầy đủ ở lần xuất hiện đầu. Khi B tham chiếu lại A, Jackson có thể ghi ID "A" thay vì mở rộng A lần nữa. Nhờ vậy, chu trình được biểu diễn bằng tham chiếu ID.

Hình thức JSON cụ thể phụ thuộc vị trí object được gặp lần đầu và cấu hình identity. Điểm cốt lõi là một object được nhận diện bằng ID ổn định, còn các lần tham chiếu sau dùng ID đó.

### 8.2. Dùng PropertyGenerator

ObjectIdGenerators.PropertyGenerator dùng một property có sẵn trong class làm object ID. Ví dụ property id ở trên.

Điều kiện quan trọng:
- ID phải có giá trị khi serialize.
- ID phải duy nhất trong phạm vi identity mà Jackson quản lý.
- ID phải ổn định và không thay đổi trong lúc serialize.
- Các object cùng scope không được có ID trùng nếu cần phân biệt identity.

Nếu hai object khác nhau cùng có id "A", Jackson không thể dùng ID đó để phân biệt chính xác chúng.

### 8.3. Dùng sequence ID do Jackson tạo

Nếu model không có ID tự nhiên, có thể dùng generator tạo ID trong quá trình serialize:

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.IntSequenceGenerator.class,
        property = "@id"
)
public class GraphNode {
    // Các field và method.
}
~~~

Jackson sinh ID theo chuỗi số cho các object trong lần xử lý phù hợp. JSON có thể chứa property identity do serializer tạo ra và các tham chiếu sau dùng ID tương ứng.

Cách này hữu ích cho payload tạm thời không cần ID nghiệp vụ. Nếu JSON được lưu lâu dài hoặc trao đổi giữa nhiều hệ thống, ID nghiệp vụ ổn định thường dễ hiểu và dễ kiểm soát hơn ID được sinh theo thứ tự serialize.

### 8.4. Deserialize để khôi phục cùng instance

Khi JSON có identity ID và tham chiếu đến ID đã được khai báo, Jackson có thể liên kết các tham chiếu về cùng một object:

~~~java
GraphNode restored = mapper.readValue(json, GraphNode.class);

GraphNode restoredB = restored.getNeighbors().get(0);
GraphNode referenceToA = restoredB.getNeighbors().get(0);

assertSame(restored, referenceToA);
~~~

Điểm khác biệt so với JSON lồng nhau mặc định là topology của graph và identity của object có thể được khôi phục, không chỉ giá trị field.

Cần bảo đảm các ID và tham chiếu trong payload tuân theo quy tắc identity mà Jackson hỗ trợ. Tham chiếu không có object ID tương ứng có thể gây lỗi unresolved object id khi deserialize.

### 8.5. @JsonIdentityReference(alwaysAsId = true)

Có thể yêu cầu một property luôn serialize object dưới dạng ID thay vì mở rộng object tại property đó:

~~~java
public class OrderReference {

    @JsonIdentityReference(alwaysAsId = true)
    private GraphNode node;

    // Getter và setter.
}
~~~

Cách này cần đi cùng cơ chế object identity phù hợp trên kiểu được tham chiếu. Nó hữu ích khi một property chỉ cần liên kết đến object đã được định danh.

Hãy phân biệt:
- @JsonIdentityInfo xác định cách object được gán/nhận diện ID.
- @JsonIdentityReference điều khiển cách một tham chiếu được biểu diễn.
- @JsonManagedReference/@JsonBackReference cắt một chiều quan hệ cha-con.

## 9. So sánh các chiến lược xử lý chu trình

| Chiến lược | JSON biểu diễn | Khôi phục graph | Phù hợp với |
|---|---|---|---|
| DTO dạng cây | Chỉ chứa dữ liệu cần thiết theo một chiều | Tự xây dựng quan hệ nếu cần | REST API, response ổn định |
| @JsonManagedReference / @JsonBackReference | Ghi chiều forward, bỏ chiều back | Có thể gắn lại back reference | Quan hệ cha-con hai chiều |
| @JsonIgnore | Bỏ property được đánh dấu | Không tự khôi phục property bị bỏ qua | Tham chiếu nội bộ không cần xuất/nhập |
| @JsonIdentityInfo | Object đầy đủ lần đầu, lần sau tham chiếu ID | Có thể khôi phục cùng instance | Graph có shared reference hoặc chu trình |
| Custom serializer/deserializer | Theo schema do ứng dụng thiết kế | Theo logic custom | Định dạng đặc thù hoặc tích hợp phức tạp |

Không có lựa chọn tốt nhất cho mọi trường hợp. Nếu API chỉ cần dữ liệu hiển thị, DTO dạng cây thường dễ bảo trì. Nếu cần quan hệ cha-con hai chiều trong Java, managed/back reference có thể đủ. Nếu cần giữ identity và liên kết graph, object identity phù hợp hơn.

## 10. Jackson Tree Model và object graph Java

Jackson Tree Model biểu diễn JSON bằng các node như ObjectNode, ArrayNode, TextNode và NumericNode. Khi đọc một JSON document hợp lệ bằng readTree(), kết quả có cấu trúc lồng nhau tương ứng với cây JSON.

~~~java
JsonNode root = mapper.readTree(json);
JsonNode customer = root.path("customer");
JsonNode name = customer.path("name");
~~~

JsonNode tree không tự mang identity của object Java nguồn. Nếu hai property trong Java cùng trỏ đến một Address instance, khi serialize thành JSON thông thường, dữ liệu Address có thể được ghi ở hai nhánh. Khi đọc lại tree, hai nhánh là hai vị trí dữ liệu độc lập.

Tương tự, JSON không có cú pháp chuẩn để node con trỏ ngược về node cha. Nếu cần biểu diễn tham chiếu, phải dùng một quy ước như ID hoặc một định dạng graph cụ thể.

Streaming API cũng không tự bảo toàn object graph. JsonParser đọc token tuần tự; JsonGenerator ghi token tuần tự. Việc giữ hay khôi phục identity vẫn là trách nhiệm của schema và logic data binding.

## 11. Cẩn thận khi dùng entity làm response JSON

Một nguyên nhân phổ biến của vòng tham chiếu là serialize trực tiếp entity có quan hệ hai chiều, chẳng hạn mô hình ORM:

- Department có collection employees.
- Employee có field department.
- Jackson đi từ Department sang Employee rồi quay lại Department.

Ngay cả khi tránh được vòng lặp, serialize toàn bộ entity graph có thể gây:
- Response quá sâu hoặc quá lớn.
- Lộ property nội bộ không dành cho client.
- Truy cập lazy relationship ngoài dự kiến.
- Nhiều truy vấn database trong lúc serialize.
- Hợp đồng API thay đổi khi quan hệ entity thay đổi.

Một cách thiết kế thường dễ kiểm soát hơn là ánh xạ entity sang DTO trong service/application layer. DTO chỉ chứa dữ liệu cần trả về, có thể dùng ID thay cho object cha hoặc object liên quan.

Ví dụ EmployeeResponse:

~~~java
public record EmployeeResponse(
        Long id,
        String name,
        Long departmentId,
        String departmentName
) {
}
~~~

DTO này cho phép client biết nhân viên thuộc department nào mà không cần nhúng toàn bộ Department và danh sách Employee một lần nữa.

## 12. Chu trình còn ảnh hưởng đến equals, hashCode và toString

Vòng tham chiếu không chỉ gây vấn đề khi serialize JSON. Nếu các class dùng equals(), hashCode() hoặc toString() tự động duyệt tất cả field, quan hệ hai chiều có thể gây đệ quy.

Ví dụ:
- Department.equals() so sánh employees.
- Employee.equals() so sánh department.
- Department.equals() lại so sánh employees.
- Quá trình lặp lại.

Một số công cụ sinh code như Lombok @Data tạo equals, hashCode và toString dựa trên field. Khi model có quan hệ hai chiều, cần loại trừ các quan hệ gây chu trình hoặc triển khai phương thức theo identity/business key phù hợp.

Đây là vấn đề của object model Java, độc lập với Jackson. Dùng @JsonIgnore có thể giải quyết serialization nhưng không tự sửa equals/hashCode/toString.

## 13. Kiểm thử dữ liệu dạng cây và graph identity

Nên kiểm thử cả cấu trúc JSON và topology của object sau khi deserialize.

### 13.1. Kiểm thử managed/back reference

~~~java
@Test
void serializesParentChildWithoutBackCycle() throws Exception {
    Department department = createDepartmentWithEmployee();

    String json = mapper.writeValueAsString(department);

    assertFalse(json.contains("\"department\""));

    Department restored = mapper.readValue(json, Department.class);
    Employee employee = restored.getEmployees().get(0);

    assertSame(restored, employee.getDepartment());
}
~~~

Test xác nhận:
- JSON không chứa property back reference.
- Jackson có thể gắn employee về đúng department khi đọc lại.

### 13.2. Kiểm thử object identity

~~~java
@Test
void restoresCyclicGraphUsingObjectIdentity() throws Exception {
    GraphNode a = new GraphNode();
    a.setId("A");

    GraphNode b = new GraphNode();
    b.setId("B");

    a.setNeighbors(new ArrayList<>(List.of(b)));
    b.setNeighbors(new ArrayList<>(List.of(a)));

    String json = mapper.writeValueAsString(a);
    GraphNode restored = mapper.readValue(json, GraphNode.class);

    GraphNode restoredB = restored.getNeighbors().get(0);
    GraphNode referenceToA = restoredB.getNeighbors().get(0);

    assertSame(restored, referenceToA);
}
~~~

Test này xác nhận graph có chu trình được khôi phục với cùng object identity.

### 13.3. Kiểm thử shared reference

~~~java
@Test
void restoresSharedAddressIdentity() throws Exception {
    Address address = new Address("12 Nguyen Hue", "HCMC");

    Customer customer = new Customer();
    customer.setBillingAddress(address);
    customer.setShippingAddress(address);

    String json = mapper.writeValueAsString(customer);
    Customer restored = mapper.readValue(json, Customer.class);

    assertSame(
            restored.getBillingAddress(),
            restored.getShippingAddress()
    );
}
~~~

Test chỉ có thể đạt nếu Address được cấu hình object identity phù hợp và JSON chứa tham chiếu ID thay cho việc lặp lại hai object độc lập.

## 14. Cách chọn mô hình phù hợp cho từng nhu cầu

Trước khi serialize một object graph, hãy trả lời:

1. JSON có cần chứa mọi quan hệ của object Java không?
2. Client có cần biết object nào cùng là một instance hay chỉ cần dữ liệu bằng nhau?
3. Có quan hệ tham chiếu ngược tạo chu trình không?
4. Một node có thể được nhiều node khác tham chiếu không?
5. Cần khôi phục object graph khi deserialize hay chỉ cần tạo DTO mới?
6. ID của object có ổn định và duy nhất không?
7. Có thể thay object cha bằng một ID hoặc summary để tạo JSON dạng cây không?
8. Dữ liệu có phải entity nội bộ với lazy relationship hoặc field nhạy cảm không?

Gợi ý lựa chọn:

- API response thông thường: DTO dạng cây, giới hạn rõ dữ liệu cần gửi.
- Quan hệ cha-con hai chiều trong một object model: @JsonManagedReference và @JsonBackReference.
- Back reference chỉ là chi tiết nội bộ: @JsonIgnore.
- Graph có shared references hoặc chu trình và cần giữ identity: @JsonIdentityInfo.
- Định dạng đặc thù hoặc quy tắc liên kết phức tạp: custom serializer/deserializer hoặc schema graph riêng.

## 15. Những điểm cần nhớ

- JSON object/array tạo thành cấu trúc dữ liệu dạng cây; JSON thuần không có tham chiếu object hoặc chu trình.
- Java object graph có thể có nhiều tham chiếu đến cùng một instance và có thể chứa chu trình.
- Jackson serialize object graph thành JSON lồng nhau; nếu không có chiến lược xử lý, chu trình có thể dẫn đến lỗi hoặc đệ quy vô hạn.
- Shared reference thường bị ghi lặp thành các nhánh JSON riêng khi không bật object identity.
- Khi deserialize JSON lặp dữ liệu, các nhánh thường trở thành các instance riêng; value equality không đồng nghĩa object identity.
- DTO dạng cây là lựa chọn dễ kiểm soát cho API.
- @JsonManagedReference/@JsonBackReference phù hợp với quan hệ cha-con hai chiều.
- @JsonIgnore loại bỏ một property khỏi quá trình mapping nhưng không tự khôi phục back reference.
- @JsonIdentityInfo cho phép biểu diễn object bằng ID và tham chiếu lại object đã nhận diện.
- Tree Model và Streaming API không tự bảo toàn identity của graph Java.
- Chu trình còn có thể ảnh hưởng equals, hashCode và toString.
- Luôn kiểm thử cả JSON output lẫn quan hệ object sau khi deserialize nếu identity quan trọng.

Phân biệt dữ liệu dạng cây và đồ thị đối tượng có chu trình giúp lựa chọn đúng cách biểu diễn khi dùng Jackson. JSON lồng nhau phù hợp với dữ liệu dạng cây; Java có thể chứa graph phong phú hơn với shared reference và chu trình. Ứng dụng cần quyết định có chuyển graph thành DTO dạng cây, cắt một chiều tham chiếu, hay đưa object ID vào JSON để bảo toàn topology. Khi lựa chọn rõ ràng, serialization và deserialization sẽ có hành vi dự đoán được và hợp đồng JSON dễ duy trì hơn.
