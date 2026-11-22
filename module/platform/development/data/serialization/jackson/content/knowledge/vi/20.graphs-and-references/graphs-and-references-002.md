# Nhận diện đệ quy vô hạn khi tuần tự hóa quan hệ hai chiều

Trong Java, một object có thể tham chiếu đến object khác, và object đó lại tham chiếu ngược về object ban đầu. Quan hệ này rất phổ biến trong mô hình cha-con, danh mục-sản phẩm, phòng-ban-nhân viên hoặc entity quan hệ trong JPA. Nhưng JSON là một cấu trúc lồng nhau gồm object, array và giá trị; nó không tự biểu diễn được một vòng tham chiếu object theo cách Java heap đang giữ.

Khi Jackson serialize một object graph có chu trình mà không có cơ chế xử lý tham chiếu, thư viện có thể đi theo các getter lặp lại vô hạn: A chứa B, B lại chứa A, rồi A lại chứa B. Kết quả thường là lỗi đệ quy, chẳng hạn `JsonMappingException` có thông báo về infinite recursion hoặc `StackOverflowError` với stack trace lặp lại các frame serializer.

Để xử lý đúng, trước hết cần nhận diện object graph có chu trình và xác định API thực sự muốn biểu diễn mối quan hệ đó như thế nào. Jackson cung cấp `@JsonManagedReference`/`@JsonBackReference` và `@JsonIdentityInfo`; có thể bỏ một hướng tham chiếu bằng `@JsonIgnore`. Với API công khai, DTO được thiết kế theo nhu cầu response thường là cách kiểm soát hợp đồng rõ ràng nhất.

## 1. Vì sao quan hệ hai chiều tạo ra đệ quy?

Giả sử một danh mục có nhiều sản phẩm. Mỗi sản phẩm cũng giữ tham chiếu đến danh mục chứa nó:

```java
public class Category {
    private Long id;
    private String name;
    private List<Product> products;
}

public class Product {
    private Long id;
    private String name;
    private Category category;
}
```

Quan hệ trong bộ nhớ:

```text
Category
   |
   | products
   v
 Product A ------------------+
   |                         |
   | category                |
   +-------------------------+
```

Khi serialize `Category`, Jackson đọc `products` và serialize từng `Product`. Đến `Product.category`, Jackson gặp lại chính `Category` ban đầu. Jackson lại đọc `Category.products`, sau đó lại đến `Product.category`, cứ thế tiếp tục.

Luồng gọi có thể lặp như sau:

```text
serialize(Category)
  -> serialize(Category.products)
      -> serialize(Product)
          -> serialize(Product.category)
              -> serialize(Category.products)
                  -> serialize(Product)
                      -> ...
```

Đây không phải lỗi cú pháp JSON ở dữ liệu đầu vào. Đây là vấn đề khi chuyển một object graph có chu trình thành một biểu diễn JSON lồng nhau mà không có quy tắc tham chiếu.

## 2. Phân biệt chu trình thật và tham chiếu dùng chung

Không phải mọi object được tham chiếu từ nhiều nơi đều tạo ra đệ quy vô hạn.

### 2.1. Chu trình (cycle)

Một chu trình xuất hiện khi có thể đi theo các reference và quay lại object đã gặp:

```text
A -> B -> A
```

Hoặc dài hơn:

```text
Order -> Customer -> Account -> Order
```

Khi serializer tiếp tục đi theo mọi reference, nó có thể không bao giờ thoát khỏi chu trình.

### 2.2. Tham chiếu dùng chung nhưng không có chu trình

Ví dụ hai đơn hàng cùng tham chiếu một khách hàng, nhưng khách hàng không tham chiếu ngược về đơn hàng:

```text
Order A ----+
            +----> Customer
Order B ----+
```

Đây là một object được chia sẻ (shared reference), nhưng không có đường đi quay lại `Order A` hoặc `Order B`. Serializer mặc định có thể ghi nội dung khách hàng hai lần ở hai nhánh. Điều đó có thể làm JSON lớn hơn, nhưng không nhất thiết gây đệ quy vô hạn.

### 2.3. Tự tham chiếu trực tiếp

Một object có thể tham chiếu chính nó:

```java
Node node = new Node();
node.setNext(node);
```

Đây là chu trình có độ dài một. Nó cũng cần được xử lý, nhưng một số cấu hình Jackson có feature riêng cho direct self-reference. Không nên nhầm việc phát hiện tự tham chiếu trực tiếp với khả năng xử lý mọi chu trình nhiều object.

## 3. Nhận diện lỗi trong stack trace

Khi endpoint trả về lỗi trong lúc serialize, hãy tìm nguyên nhân ở quá trình ghi response, không chỉ ở controller hoặc repository.

Các dấu hiệu thường gặp:

- Thông báo `Infinite recursion (StackOverflowError)` trong `JsonMappingException`.
- `StackOverflowError` với nhiều frame lặp lại giữa serializer của hai kiểu liên quan.
- Reference path trong exception lặp theo chuỗi property, ví dụ `Category["products"] -> Product["category"] -> Category["products"]`.
- Lỗi chỉ xuất hiện khi serialize một entity có quan hệ hai chiều; DTO đơn giản hoặc object không có quan hệ ngược vẫn hoạt động.
- Lỗi xuất hiện khi thêm một getter hoặc thay đổi fetch graph, dù controller không thay đổi nhiều.

Một reference path minh họa:

```text
Category["products"]
  -> Product["category"]
      -> Category["products"]
          -> Product["category"]
              -> ...
```

Tên class và property trong stack trace giúp xác định cặp tham chiếu. Hãy kiểm tra field, getter, record accessor hoặc annotation mà Jackson đang nhận diện. Một quan hệ có thể không hiển thị rõ trong field nếu getter trả về object cha hoặc collection con.

Không nên chỉ tăng stack size của JVM hoặc bắt `StackOverflowError` rồi trả JSON rỗng. Điều đó không giải quyết chu trình trong mô hình và có thể làm response không nhất quán.

## 4. Ví dụ tối giản tái hiện vấn đề

```java
public class Department {
    private String name;
    private List<Employee> employees = new ArrayList<>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}

public class Employee {
    private String name;
    private Department department;

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
```

Tạo graph hai chiều:

```java
Department department = new Department();
department.setName("Engineering");

Employee employee = new Employee();
employee.setName("Lan");
employee.setDepartment(department);

department.getEmployees().add(employee);
```

Thử serialize:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(department);
```

Jackson bắt đầu ở `department`, đi xuống `employees`, rồi từ `employee` quay lại `department`. Nếu không có annotation hoặc cơ chế identity phù hợp, việc duyệt graph sẽ lặp.

Lưu ý: `toString()` của Lombok `@Data` hoặc IDE-generated method cũng có thể đệ quy khi log object graph. Đó là một vấn đề riêng với việc gọi `toString()`, không phải serialization của Jackson, dù cùng xuất phát từ quan hệ hai chiều. Nếu stack trace nằm trong `toString`, hãy kiểm tra Lombok `@ToString.Exclude` hoặc tự thiết kế `toString()` ngắn gọn; không coi đó là lỗi `ObjectMapper`.

## 5. Cách 1: Dùng @JsonManagedReference và @JsonBackReference

Jackson cung cấp cặp annotation để mô tả hai phía của một quan hệ cha-con:

- `@JsonManagedReference`: đánh dấu phía chính được serialize bình thường, thường là collection con trong object cha.
- `@JsonBackReference`: đánh dấu phía ngược; phía này bị bỏ qua khi serialize để tránh quay lại object cha.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;
import java.util.ArrayList;
import java.util.List;

public class Department {
    private String name;

    @JsonManagedReference
    private List<Employee> employees = new ArrayList<>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}

public class Employee {
    private String name;

    @JsonBackReference
    private Department department;

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
```

Serialize `Department` sẽ tạo JSON dạng:

```json
{
  "name": "Engineering",
  "employees": [
    {
      "name": "Lan"
    }
  ]
}
```

`Employee.department` không được ghi trong JSON nên serializer không quay lại `Department`.

### 5.1. Vai trò khi deserialize

Hai annotation này còn hỗ trợ khôi phục quan hệ ngược khi đọc JSON. Khi Jackson deserialize `Department` cùng danh sách `employees`, phía managed được đọc; Jackson có thể gán lại reference cha vào property được đánh dấu back reference của từng employee.

Ví dụ:

```java
Department restored = mapper.readValue(json, Department.class);
Employee first = restored.getEmployees().get(0);

assertSame(restored, first.getDepartment());
```

Quan hệ cha-con trong bộ nhớ được khôi phục dù JSON không chứa trường `department` bên trong mỗi employee.

### 5.2. Đặt tên cho nhiều cặp quan hệ

Mặc định, cả hai annotation dùng tên tham chiếu `defaultReference`. Nếu một class có nhiều quan hệ hai chiều, hãy đặt tên riêng cho từng cặp:

```java
public class School {
    @JsonManagedReference("school-classes")
    private List<SchoolClass> classes;

    @JsonManagedReference("school-events")
    private List<SchoolEvent> events;
}

public class SchoolClass {
    @JsonBackReference("school-classes")
    private School school;
}

public class SchoolEvent {
    @JsonBackReference("school-events")
    private School school;
}
```

Tên trên `@JsonManagedReference` phải khớp với tên trên `@JsonBackReference` tương ứng. Việc đặt tên giúp Jackson biết reference nào cần khôi phục cho property nào.

### 5.3. Hạn chế của managed/back references

- Cách này phù hợp với quan hệ có một hướng chính và một hướng ngược rõ ràng.
- Property back reference phải là một tham chiếu đơn tới object cha; không dùng collection, map hoặc array làm back reference.
- JSON không thể hiện liên kết ngược ở phía con khi serialize.
- Nếu consumer cần duyệt ngược từ con sang cha trong JSON, cách này không giữ đầy đủ graph topology.
- Với nhiều cặp quan hệ, phải đặt reference name riêng và khớp chính xác.
- Lớp bất biến, constructor phức tạp hoặc mô hình không có setter có thể cần thiết kế deserialize riêng; không nên giả định mọi kiểu object đều khôi phục back reference tự động như JavaBean đơn giản.

Chọn cách này khi hợp đồng JSON tự nhiên là cây cha chứa danh sách con, còn reference ngược chỉ cần tồn tại trong object graph Java sau khi deserialize.

## 6. Cách 2: Dùng @JsonIdentityInfo để biểu diễn object bằng ID

Nếu JSON cần giữ mối liên hệ giữa các object, có thể dùng object identity thay vì loại bỏ reference ngược. `@JsonIdentityInfo` cho Jackson biết cách gán một ID cho mỗi object và tham chiếu lại object bằng ID khi gặp lần sau.

Ví dụ dùng thuộc tính `id` làm object ID:

```java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class Department {
    private Long id;
    private String name;
    private List<Employee> employees = new ArrayList<>();

    // Getter và setter.
}

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class Employee {
    private Long id;
    private String name;
    private Department department;

    // Getter và setter.
}
```

Khi serialize một object lần đầu, Jackson ghi object đầy đủ cùng ID. Khi gặp lại chính object đó qua một reference khác, Jackson có thể ghi ID thay cho việc serialize toàn bộ object lần nữa.

JSON minh họa có thể giống:

```json
{
  "id": 10,
  "name": "Engineering",
  "employees": [
    {
      "id": 101,
      "name": "Lan",
      "department": 10
    }
  ]
}
```

Ở đây `department: 10` là tham chiếu tới object `Department` đã được ghi trước đó, thay vì mở rộng department thêm lần nữa.

### 6.1. Yêu cầu đối với object ID

Khi dùng `PropertyGenerator`, property được chọn làm ID phải tồn tại và có giá trị phù hợp khi serialize. ID cần duy nhất trong phạm vi identity scope của kiểu object. Nếu nhiều object cùng kiểu có ID null hoặc trùng nhau, việc tham chiếu có thể không đúng hoặc Jackson không thể tạo identity như mong muốn.

Ví dụ, nếu mỗi loại object có `id` riêng, có thể dùng class scope mặc định để phân biệt loại. Nếu ID có phạm vi đặc biệt, cần hiểu các tùy chọn `scope` và resolver của Jackson.

Nếu object chưa có property ID, có thể dùng generator tuần tự:

```java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.IntSequenceGenerator.class,
    property = "@objectId"
)
public class GraphNode {
    private String name;
    private GraphNode next;

    // Getter và setter.
}
```

Generator tuần tự phù hợp khi identity chỉ cần trong tài liệu serialize hiện tại. Nếu JSON được lưu lâu dài hoặc gửi cho client để tham chiếu sau, ID nghiệp vụ ổn định thường dễ hiểu và dễ xử lý hơn ID sinh theo lần serialize.

### 6.2. Luôn ghi reference bằng ID

`@JsonIdentityReference(alwaysAsId = true)` có thể yêu cầu một property được biểu diễn bằng ID thay vì object đầy đủ:

```java
@JsonIdentityReference(alwaysAsId = true)
private Department department;
```

Điều này có thể tạo JSON gọn hơn, nhưng consumer cần biết cách tra cứu ID và xử lý tham chiếu. Nếu ID được phát ra trước khi object đầy đủ xuất hiện, hoặc object không có trong tài liệu, quá trình deserialize có thể cần xử lý unresolved reference. Hãy kiểm thử thứ tự và phạm vi ID theo hợp đồng.

### 6.3. Khi nào nên dùng object identity?

Phù hợp khi:

- Consumer cần giữ quan hệ giữa các object và không muốn loại bỏ reference ngược.
- JSON đại diện cho một graph có nhiều shared references.
- Các object có ID ổn định, duy nhất và có thể được tham chiếu.
- Consumer hiểu định dạng reference bằng ID và có thể khôi phục graph.

Không nên chọn chỉ vì muốn tránh lỗi stack overflow mà không xem xét hợp đồng. JSON chứa ID reference không còn là một cây object tự mô tả hoàn toàn; consumer cần hiểu identity semantics.

## 7. Cách 3: Dùng @JsonIgnore để bỏ một phía tham chiếu

Nếu API chỉ cần một hướng quan hệ, có thể bỏ property ngược:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Employee {
    private String name;

    @JsonIgnore
    private Department department;

    // Getter và setter.
}
```

Khi serialize `Department`, employee được ghi nhưng `department` bị bỏ qua. Đây là cách đơn giản khi không cần reference ngược trong JSON.

Tuy nhiên, `@JsonIgnore` thường loại property khỏi cả quá trình serialize và deserialize. Nếu muốn bỏ property khỏi JSON đầu ra nhưng vẫn cho phép nhận giá trị khi đọc JSON, có thể dùng access mode hoặc `@JsonIgnoreProperties` với `allowSetters` tùy hợp đồng.

Ví dụ:

```java
@JsonIgnoreProperties(value = "department", allowSetters = true)
public class Employee {
    private String name;
    private Department department;
}
```

`allowSetters = true` cho phép setter được dùng trong quá trình deserialize đối với property bị ignore trong serialization. Cần kiểm thử với cấu hình accessor thực tế, nhất là khi có annotation khác trên field/getter.

`@JsonIgnore` là lựa chọn nhanh nhưng có thể làm mất thông tin khi round-trip. Nếu cần khôi phục quan hệ cha-con trong object graph sau deserialize, `@JsonManagedReference`/`@JsonBackReference` thường diễn đạt mục đích tốt hơn.

## 8. Cách 4: Dùng DTO để định hình response không có chu trình

Với API công khai, thường không nên serialize trực tiếp entity có quan hệ hai chiều. Thay vào đó, tạo DTO thể hiện đúng dữ liệu mà endpoint cần trả.

Ví dụ response cho một danh mục:

```java
public record CategoryResponse(
    Long id,
    String name,
    List<ProductSummary> products
) {
}

public record ProductSummary(
    Long id,
    String name
) {
}
```

Mapper chuyển entity sang DTO:

```java
public CategoryResponse toResponse(Category category) {
    List<ProductSummary> products = category.getProducts().stream()
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName()
        ))
        .toList();

    return new CategoryResponse(
        category.getId(),
        category.getName(),
        products
    );
}
```

JSON đầu ra:

```json
{
  "id": 10,
  "name": "Books",
  "products": [
    {"id": 101, "name": "Java Basics"},
    {"id": 102, "name": "Jackson Guide"}
  ]
}
```

`ProductSummary` không chứa `Category` nên không thể quay lại parent. Response là một cây có cấu trúc hữu hạn và đúng nhu cầu endpoint.

Nếu endpoint cần lấy chi tiết một sản phẩm, có thể định nghĩa `ProductResponse` với `categoryId` hoặc `CategorySummary` thay vì nhúng toàn bộ `Category` cùng danh sách sản phẩm. Cách này tránh việc response phình ra theo quan hệ lồng nhau.

### 8.1. DTO giúp kiểm soát nhiều hơn việc tránh vòng lặp

- Chỉ đưa field được phép công khai vào response.
- Không vô tình trả password hash, token, trạng thái nội bộ hoặc audit metadata.
- Không làm JSON phụ thuộc trực tiếp vào schema database.
- Có thể giới hạn độ sâu và số lượng phần tử trong collection.
- Dễ versioning và kiểm thử hợp đồng API.
- Có thể chọn projection khác nhau cho list, detail, admin và public endpoint.

Vì vậy, DTO thường là lựa chọn tốt nhất khi response là hợp đồng API chứ không phải bản sao toàn bộ object graph.

## 9. So sánh các cách xử lý

| Cách | Hình thức JSON | Có giữ reference ngược? | Phù hợp khi |
|---|---|---|---|
| `@JsonManagedReference` / `@JsonBackReference` | Chỉ serialize phía managed; phía back bị bỏ qua | Có thể khôi phục khi deserialize | Quan hệ cha-con có một hướng chính |
| `@JsonIdentityInfo` | Object đầu tiên đầy đủ, lần tham chiếu sau dùng ID | Có, theo identity | Consumer cần giữ graph/shared references |
| `@JsonIgnore` | Bỏ property được đánh dấu | Thường không qua property bị ignore | Không cần phía tham chiếu đó |
| DTO riêng | Chỉ gồm các field được thiết kế | Chỉ giữ những liên kết được mô hình hóa rõ | API công khai, response ổn định và an toàn |
| Custom serializer | Do ứng dụng tự định nghĩa | Tùy logic serializer | Cấu trúc đặc biệt không thể diễn đạt gọn bằng annotation |

Không có annotation nào tự quyết định cấu trúc API đúng. Hãy chọn theo cách consumer cần đọc dữ liệu và cách ứng dụng cần khôi phục object graph.

## 10. Quan hệ hai chiều trong JPA/Hibernate

Quan hệ hai chiều rất phổ biến trong entity JPA:

```java
@Entity
public class Category {
    @Id
    private Long id;

    @OneToMany(mappedBy = "category")
    private List<Product> products = new ArrayList<>();
}

@Entity
public class Product {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Category category;
}
```

Trong quan hệ này:

- `Category.products` là phía inverse của quan hệ `OneToMany`.
- `Product.category` là phía owning side thường chứa foreign key.
- Hai phía trong Java cần được đồng bộ khi thêm/xóa phần tử.
- Jackson có thể nhìn thấy cả hai phía khi serialize và đi vào chu trình.

### 10.1. Đồng bộ hai phía trong domain model

Có thể tạo helper để giữ quan hệ nhất quán:

```java
public void addProduct(Product product) {
    products.add(product);
    product.setCategory(this);
}

public void removeProduct(Product product) {
    products.remove(product);
    product.setCategory(null);
}
```

Đây là quy tắc nhất quán của object graph và persistence relationship. Nó không tự giải quyết serialization; Jackson vẫn cần một chính sách biểu diễn graph.

### 10.2. Lazy loading và truy vấn phát sinh khi serialize

Khi Jackson gọi getter của collection hoặc association lazy, Hibernate có thể tải dữ liệu từ database. Việc serialize entity vì thế có thể:

- Kích hoạt truy vấn bổ sung ngoài dự kiến.
- Gây N+1 queries khi serialize danh sách entity.
- Ném `LazyInitializationException` nếu session đã đóng.
- Kéo theo graph lớn hơn nhiều so với response cần.
- Đi vào chu trình giữa các entity.

Module Jackson dành cho Hibernate có thể hỗ trợ cách xử lý proxy/lazy association theo cấu hình của phiên bản tương ứng. Nhưng module đó không thay thế thiết kế response và không tự giải quyết mọi chu trình hai chiều. Hãy kiểm soát fetch plan và chuyển entity thành DTO trong transaction/use case phù hợp.

## 11. Cẩn thận với Lombok và getter tự tạo

Jackson thường introspect getter, setter và field theo cấu hình. Một getter có thể trả về reference ngược dù field không được serialize trực tiếp:

```java
public Department getDepartment() {
    return department;
}
```

Do đó, kiểm tra stack trace theo property mà Jackson đọc, không chỉ kiểm tra field annotation.

Lombok `@Data` tạo getter/setter và `equals`, `hashCode`, `toString`. Với entity có quan hệ hai chiều, `toString()` hoặc `equals()` được sinh tự động cũng có thể đệ quy hoặc kích hoạt lazy loading. Nên giới hạn các field tham gia `toString`, `equals` và `hashCode`:

```java
@ToString.Exclude
@EqualsAndHashCode.Exclude
private Category category;
```

Các annotation Lombok này xử lý phương thức do Lombok sinh, không phải annotation của Jackson. Nếu lỗi xảy ra trong serializer, cần dùng annotation hoặc DTO phù hợp với Jackson; nếu lỗi xảy ra trong logging/`toString`, xử lý riêng phần Lombok.

## 12. Direct self-reference và FAIL_ON_SELF_REFERENCES

Jackson có feature `SerializationFeature.FAIL_ON_SELF_REFERENCES` dành cho trường hợp một bean tham chiếu trực tiếp tới chính nó mà không có object identity handling. Feature này mặc định được bật trong cấu hình Jackson Databind thông dụng.

Ví dụ:

```java
Node node = new Node();
node.setNext(node);
```

Feature này có thể khiến Jackson báo lỗi rõ ràng cho direct self-reference. Tuy nhiên, không nên coi nó là cơ chế phát hiện đầy đủ mọi chu trình nhiều object như `Department -> Employee -> Department`. Chu trình gián tiếp vẫn cần được mô hình hóa bằng managed/back reference, object identity, ignore hoặc DTO.

Một số phiên bản Jackson có thêm feature liên quan đến việc ghi direct self-reference thành null. Không nên bật cách xử lý đó như giải pháp chung vì nó có thể âm thầm làm mất liên kết và không giải quyết các chu trình gián tiếp. Hãy kiểm tra tài liệu phiên bản Jackson đang dùng nếu cần điều chỉnh hành vi self-reference.

## 13. Không nên sửa chu trình bằng cách tăng stack hoặc bắt lỗi

Các cách sau không giải quyết nguyên nhân:

```text
-Xss tăng kích thước stack
```

Tăng stack có thể trì hoãn thời điểm lỗi nhưng serializer vẫn đi theo chu trình. Bắt `StackOverflowError` cũng không bảo đảm JVM và request pipeline còn ở trạng thái phù hợp để tiếp tục.

Tương tự, tắt `FAIL_ON_SELF_REFERENCES` không làm cho graph hai chiều tự chuyển thành JSON hữu hạn. Cần chọn chính sách biểu diễn rõ ràng trước khi serialize.

## 14. Kiểm thử quan hệ hai chiều

Khi sửa lỗi, cần kiểm thử cả JSON đầu ra và object graph sau deserialize nếu hợp đồng yêu cầu khôi phục liên kết.

### 14.1. Test managed/back reference

```java
class DepartmentJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void serializesChildrenWithoutBackReference() throws Exception {
        Department department = new Department();
        department.setName("Engineering");

        Employee employee = new Employee();
        employee.setName("Lan");
        employee.setDepartment(department);
        department.getEmployees().add(employee);

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(department)
        );

        assertEquals("Engineering", json.path("name").asText());
        assertEquals("Lan", json.path("employees").get(0)
            .path("name").asText());
        assertFalse(json.path("employees").get(0).has("department"));
    }

    @Test
    void restoresBackReferenceWhenDeserializing() throws Exception {
        String json = """
            {
              "name": "Engineering",
              "employees": [
                {"name": "Lan"}
              ]
            }
            """;

        Department department = mapper.readValue(json, Department.class);

        assertSame(
            department,
            department.getEmployees().get(0).getDepartment()
        );
    }
}
```

Test này xác nhận JSON không chứa reference ngược và Jackson khôi phục quan hệ trong object graph khi đọc lại.

### 14.2. Test object identity

Với `@JsonIdentityInfo`, nên kiểm tra:

- Object lần đầu được serialize với ID và nội dung theo hợp đồng.
- Reference tiếp theo dùng ID thay vì lặp toàn bộ object.
- ID là duy nhất trong phạm vi cần thiết.
- Deserialize khôi phục các reference về cùng object instance khi dữ liệu có đủ identity.
- Hành vi với object được tham chiếu nhưng chưa xuất hiện hoặc ID không tồn tại.

### 14.3. Test DTO response

Với DTO, kiểm tra field được phép xuất hiện và field không được phép xuất hiện. Không chỉ test rằng request không còn ném `StackOverflowError`; response phải đúng hợp đồng và không lộ dữ liệu ngoài dự kiến.

## 15. Quy trình điều tra lỗi infinite recursion

Khi Jackson báo lỗi đệ quy khi serialize:

1. Xác định lỗi xảy ra trong serialize response, log `toString()` hay một bước khác.
2. Đọc reference path trong exception để tìm cặp property lặp lại.
3. Kiểm tra các getter, field, collection và association hai chiều liên quan.
4. Vẽ object graph nhỏ với các reference đi và quay lại.
5. Xác định JSON cần giữ quan hệ ngược, chỉ cần một hướng hay chỉ cần summary.
6. Chọn `@JsonManagedReference`/`@JsonBackReference`, `@JsonIdentityInfo`, `@JsonIgnore` hoặc DTO.
7. Với JPA, kiểm tra lazy loading, fetch plan và persistence context.
8. Viết test cho serialize; nếu cần, test deserialize và identity/reference restoration.
9. Kiểm tra response thực tế không có field nhạy cảm hoặc graph lớn ngoài dự kiến.
10. Không dựa vào tăng stack size hoặc bắt `StackOverflowError` để che chu trình.

## 16. Chọn chiến lược theo mục tiêu API

| Mục tiêu | Gợi ý |
|---|---|
| JSON là cây cha chứa danh sách con; không cần parent trong mỗi child | `@JsonManagedReference` + `@JsonBackReference` |
| JSON cần giữ graph và nhiều reference dùng chung | `@JsonIdentityInfo` |
| Không cần property ngược ở cả hai chiều | `@JsonIgnore` |
| Chỉ muốn bỏ property khi serialize nhưng vẫn nhận khi deserialize | `@JsonIgnoreProperties(..., allowSetters = true)` hoặc access rule phù hợp |
| API công khai cần response gọn, ổn định, an toàn | DTO/projection riêng |
| Cấu trúc đặc biệt cần kiểm soát thủ công | Custom serializer/deserializer |
| Entity JPA có lazy association và nhiều quan hệ | Fetch có chủ đích, chuyển sang DTO trước khi serialize |

## 17. Kết luận

Đệ quy vô hạn xuất hiện khi Jackson đi theo một object reference rồi quay lại object đã gặp, thường do quan hệ hai chiều như cha-con hoặc entity JPA. Hãy tìm cặp property lặp trong reference path của exception và phân biệt chu trình thật với một object chỉ được dùng chung ở nhiều nhánh.

Nếu JSON chỉ cần một hướng cha-con, `@JsonManagedReference` và `@JsonBackReference` thường phù hợp. Nếu cần giữ graph bằng ID, dùng `@JsonIdentityInfo` với ID duy nhất và hợp đồng mà consumer hiểu được. Nếu không cần reference ngược, có thể bỏ nó bằng `@JsonIgnore`. Với API công khai, DTO thường cho phép kiểm soát cấu trúc, dữ liệu nhạy cảm, độ sâu và kích thước tốt nhất. Đối với JPA/Hibernate, hãy kiểm soát cả fetch plan và lazy loading; tránh để serializer tự duyệt toàn bộ entity graph.
