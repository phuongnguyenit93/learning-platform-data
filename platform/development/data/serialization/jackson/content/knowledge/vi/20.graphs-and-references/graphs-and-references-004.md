# Vai trò của JsonManagedReference và JsonBackReference

Trong Java, các object thường tham chiếu lẫn nhau để mô tả quan hệ cha-con. Ví dụ, một `Department` giữ danh sách `Employee`, còn mỗi `Employee` lại giữ tham chiếu ngược về `Department` của mình. Cấu trúc này thuận tiện khi thao tác trong bộ nhớ, nhưng tạo ra vòng tham chiếu khi chuyển thành JSON.

Nếu Jackson serialize `Department`, nó đi vào danh sách nhân viên, rồi từ mỗi nhân viên lại đi về phòng ban, sau đó lại đi vào danh sách nhân viên. Quá trình có thể lặp vô hạn và dẫn đến lỗi do vòng lặp tham chiếu.

Jackson cung cấp cặp annotation `@JsonManagedReference` và `@JsonBackReference` để mô tả hai phía của một quan hệ hai chiều:

- **Managed reference** là phía chính (forward link), thường là cha giữ con. Jackson serialize phía này như property thông thường.
- **Back reference** là phía ngược (back link), thường là con trỏ về cha. Jackson không serialize property này, và khi deserialize, Jackson thiết lập lại tham chiếu ngược về object cha tương ứng.

Cặp annotation giúp JSON biểu diễn quan hệ theo một hướng để tránh đệ quy, đồng thời vẫn khôi phục được liên kết hai chiều trong object graph sau khi đọc JSON.

## 1. Vấn đề vòng tham chiếu trong object graph

Giả sử một phòng ban có nhiều nhân viên:

```java
public class Department {
    private String name;
    private List<Employee> employees = new ArrayList<>();
}
```

Mỗi nhân viên có tham chiếu đến phòng ban:

```java
public class Employee {
    private String name;
    private Department department;
}
```

Trong bộ nhớ, mối quan hệ có dạng:

```text
Department
   │
   ├── employees[0] ──> Employee A
   │                       │
   │                       └── department ──┐
   │                                        │
   └────────────────────────────────────────┘
```

Nếu serialize toàn bộ object graph mà không có quy tắc xử lý tham chiếu, Jackson có thể đi theo chu trình:

```text
Department -> employees -> Employee -> department
     ^                                  |
     |                                  v
     +---------- employees <------------+
```

JSON vốn là cấu trúc cây, trong khi object graph có thể chứa chu trình. Để tạo JSON hữu hạn, ứng dụng phải chọn cách biểu diễn quan hệ: bỏ một hướng, dùng object identity, hoặc tự thiết kế DTO không có vòng tham chiếu.

## 2. Đánh dấu phía cha bằng @JsonManagedReference

`@JsonManagedReference` được đặt trên property đại diện cho phía chính của quan hệ. Trong quan hệ một-nhiều, property này thường là collection chứa các object con.

```java
import com.fasterxml.jackson.annotation.JsonManagedReference;

import java.util.ArrayList;
import java.util.List;

public class Department {
    private String name;

    @JsonManagedReference
    private List<Employee> employees = new ArrayList<>();

    public Department() {
    }

    public Department(String name) {
        this.name = name;
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
```

Jackson vẫn serialize `employees` như một property bình thường. Các nhân viên được đưa vào JSON dưới dạng array. Annotation cho Jackson biết đây là phía managed của một cặp tham chiếu; nó cần tìm back reference tương ứng ở kiểu con khi deserialize.

## 3. Đánh dấu phía con bằng @JsonBackReference

`@JsonBackReference` được đặt trên property trỏ ngược từ object con về object cha. Với ví dụ trên, `Employee.department` là back reference:

```java
import com.fasterxml.jackson.annotation.JsonBackReference;

public class Employee {
    private String name;

    @JsonBackReference
    private Department department;

    public Employee() {
    }

    public Employee(String name) {
        this.name = name;
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
```

Property `department` không được ghi ra JSON khi serialize `Employee` qua quan hệ này. Khi Jackson deserialize danh sách `employees` bên trong một `Department`, nó tạo từng `Employee` rồi thiết lập property back reference của nhân viên trỏ về `Department` đang chứa nó.

Điểm quan trọng: `@JsonBackReference` không có nghĩa là field bị xóa khỏi object Java. Nó chỉ điều khiển cách Jackson xử lý property trong cặp quan hệ khi chuyển đổi JSON.

## 4. JSON đầu ra chỉ chứa phía managed

Tạo object graph:

```java
Department department = new Department("Engineering");

Employee an = new Employee("An");
an.setDepartment(department);

Employee binh = new Employee("Binh");
binh.setDepartment(department);

department.setEmployees(List.of(an, binh));
```

Serialize:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(department);
System.out.println(json);
```

JSON có cấu trúc tương đương:

```json
{
  "name": "Engineering",
  "employees": [
    { "name": "An" },
    { "name": "Binh" }
  ]
}
```

Property `employees` được ghi vì đó là managed reference. Property `department` của mỗi nhân viên bị bỏ qua vì đó là back reference. Nhờ vậy, Jackson không quay ngược lên cha để serialize lại toàn bộ graph.

Nếu serialize trực tiếp một `Employee`, property back reference `department` vẫn không được ghi. Annotation gắn với property, nên nó tiếp tục có hiệu lực dù object con là root của lần serialize.

## 5. Deserialize và khôi phục liên kết hai chiều

Điểm hữu ích của cặp annotation là Jackson có thể khôi phục back reference khi đọc JSON, dù JSON không chứa property trỏ ngược.

```java
String json = """
        {
          "name": "Engineering",
          "employees": [
            { "name": "An" },
            { "name": "Binh" }
          ]
        }
        """;

Department restored = mapper.readValue(json, Department.class);

Employee first = restored.getEmployees().get(0);
System.out.println(first.getName()); // An
System.out.println(first.getDepartment().getName()); // Engineering
System.out.println(first.getDepartment() == restored); // true
```

Trong quá trình deserialize, Jackson đọc `Department`, tạo danh sách `Employee`, rồi gán back reference của từng nhân viên về đúng instance cha. Dòng so sánh `==` minh họa rằng nhân viên trỏ đến chính object `Department` vừa được tạo, không phải một bản sao khác.

Điều này đặc biệt hữu ích khi code nghiệp vụ sau deserialize cần đi từ child lên parent, dù JSON chỉ biểu diễn quan hệ từ parent xuống child.

## 6. Ghép cặp bằng tên reference

Mặc định, `@JsonManagedReference` và `@JsonBackReference` dùng tên reference `defaultReference`. Điều này đủ cho một cặp quan hệ trong một kiểu dữ liệu đơn giản.

Khi một class có nhiều quan hệ hai chiều, hãy đặt tên riêng cho từng cặp. Giá trị `value` của managed reference và back reference phải khớp nhau.

Ví dụ một `Project` có danh sách task, còn mỗi task trỏ về project:

```java
public class Project {
    @JsonManagedReference("project-tasks")
    private List<Task> tasks = new ArrayList<>();
}
```

```java
public class Task {
    @JsonBackReference("project-tasks")
    private Project project;
}
```

Tên `project-tasks` liên kết hai phía của cùng một quan hệ. Nếu tên không khớp, Jackson không thể tìm đúng managed reference để thiết lập back reference và quá trình deserialize có thể phát sinh lỗi.

### 6.1. Ví dụ nhiều cặp reference trên một kiểu

Giả sử `Task` có một project chứa nó và một employee chịu trách nhiệm thực hiện. Mỗi quan hệ có tên riêng:

```java
public class Project {
    @JsonManagedReference("project-tasks")
    private List<Task> tasks = new ArrayList<>();
}
```

```java
public class Employee {
    @JsonManagedReference("employee-tasks")
    private List<Task> assignedTasks = new ArrayList<>();
}
```

```java
public class Task {
    @JsonBackReference("project-tasks")
    private Project project;

    @JsonBackReference("employee-tasks")
    private Employee assignee;
}
```

Ở đây có hai cặp độc lập:

- `Project.tasks` ↔ `Task.project` qua tên `project-tasks`.
- `Employee.assignedTasks` ↔ `Task.assignee` qua tên `employee-tasks`.

Việc đặt tên giúp Jackson và người đọc code phân biệt các liên kết. Không nên để nhiều cặp cùng dùng `defaultReference` nếu có thể gây nhập nhằng hoặc xung đột.

## 7. Hướng của managed và back reference

Tên annotation có thể gây nhầm lẫn nếu chỉ nhìn vào quan hệ trong database. Hãy xác định hướng JSON cần serialize:

```text
Department (cha)
     |
     | @JsonManagedReference
     v
Employee (con)
     ^
     | @JsonBackReference
     |
Department
```

Quy ước thường dùng:

| Phía quan hệ | Annotation | Khi serialize | Khi deserialize |
| --- | --- | --- | --- |
| Parent → Child | `@JsonManagedReference` | Được ghi như property bình thường | Được đọc; các child nhận back reference về parent |
| Child → Parent | `@JsonBackReference` | Không được ghi | Được thiết lập từ managed parent tương ứng |

Managed reference là phía được đưa vào JSON. Back reference là phía được khôi phục trong object graph. Hãy chọn hướng dựa trên cấu trúc JSON mong muốn, không dựa đơn thuần vào tên bảng hoặc chiều khóa ngoại trong database.

## 8. Giới hạn của @JsonBackReference

Back reference được thiết kế cho property đơn trỏ về object cha. Property được đánh dấu `@JsonBackReference` không nên là collection, map hoặc array; các kiểu container phù hợp hơn với phía managed. Ví dụ hợp lệ thường là `Employee.department` có kiểu `Department`, trong khi `Department.employees` có kiểu `List<Employee>`.

Ngoài ra, một back reference phải có managed reference tương ứng trên kiểu cha. Nếu Jackson không tìm được cặp phù hợp, deserialize có thể báo lỗi về back reference không tồn tại hoặc không hợp lệ.

Hai annotation cũng không phải cơ chế tổng quát để biểu diễn mọi đồ thị object tùy ý. Chúng phù hợp nhất với quan hệ hai chiều có một hướng chính rõ ràng, chẳng hạn parent-child hoặc owner-items. Nếu một object con có nhiều parent độc lập, hoặc cùng một object được chia sẻ bởi nhiều nhánh graph, mô hình managed/back có thể không diễn tả đúng identity của toàn bộ graph.

## 9. So sánh với @JsonIgnore

Một cách đơn giản để tránh vòng lặp là bỏ qua property trỏ ngược:

```java
public class Employee {
    private String name;

    @JsonIgnore
    private Department department;
}
```

`@JsonIgnore` cũng ngăn Jackson serialize/deserialze property đó theo quy tắc ignore mặc định. Tuy nhiên, khi deserialize `Department` cùng danh sách nhân viên, Jackson không tự khôi phục `Employee.department` về parent như cặp managed/back reference.

So sánh:

| Tiêu chí | `@JsonIgnore` | `@JsonManagedReference` / `@JsonBackReference` |
| --- | --- | --- |
| Mục đích | Bỏ qua property cụ thể | Mô tả một cặp liên kết hai chiều |
| Tránh serialize vòng lặp | Có, nếu bỏ qua một phía | Có, bằng cách chỉ ghi phía managed |
| Khôi phục liên kết ngược khi deserialize | Không tự khôi phục | Có, back reference được thiết lập từ managed parent |
| Nhiều cặp quan hệ | Không có cơ chế ghép cặp | Có thể đặt tên riêng bằng `value` |

Nếu chỉ cần loại một field khỏi JSON ở cả hai chiều, `@JsonIgnore` đơn giản hơn. Nếu muốn JSON chỉ chứa một hướng nhưng object sau deserialize vẫn có quan hệ hai chiều, cặp managed/back phù hợp hơn.

## 10. So sánh với @JsonIdentityInfo

`@JsonIdentityInfo` giải quyết vòng tham chiếu theo cách khác: gắn object id để lần xuất hiện sau của cùng object có thể được biểu diễn bằng tham chiếu identity thay vì serialize lại toàn bộ object.

Ví dụ khái quát:

```json
{
  "id": 1,
  "name": "Engineering",
  "employees": [
    {
      "id": 10,
      "name": "An",
      "department": 1
    }
  ]
}
```

Hình thức JSON chính xác phụ thuộc cấu hình identity generator, property id và cách Jackson xử lý lần xuất hiện đầu tiên của object. Ý tưởng là các object có identity được tham chiếu bằng id, giúp biểu diễn graph có chia sẻ object hoặc nhiều liên kết hơn mô hình một chiều đơn giản.

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Quan hệ cha-con hai chiều, JSON chỉ cần ghi parent → child | `@JsonManagedReference` / `@JsonBackReference` |
| Bỏ hẳn một property khỏi JSON | `@JsonIgnore` |
| Biểu diễn object graph có identity và tham chiếu lặp | `@JsonIdentityInfo` |
| API cần cấu trúc response riêng, không muốn lộ entity graph | DTO riêng cho request/response |

Không có annotation nào tự động thay thế thiết kế API. Nếu graph phức tạp, DTO riêng thường giúp hợp đồng JSON dễ kiểm soát hơn entity ORM trực tiếp.

## 11. Ví dụ đầy đủ có tên reference

Một ví dụ hoàn chỉnh hơn dùng tên reference rõ ràng:

```java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

import java.util.ArrayList;
import java.util.List;

public class Department {
    private String code;
    private String name;

    @JsonManagedReference("department-employees")
    private List<Employee> employees = new ArrayList<>();

    public Department() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
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

public class Employee {
    private String employeeId;
    private String name;

    @JsonBackReference("department-employees")
    private Department department;

    public Employee() {
    }

    public String getEmployeeId() {
        return employeeId;
    }

    public void setEmployeeId(String employeeId) {
        this.employeeId = employeeId;
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
```

Tạo dữ liệu:

```java
Department department = new Department();
department.setCode("ENG");
department.setName("Engineering");

Employee employee = new Employee();
employee.setEmployeeId("E-100");
employee.setName("An");
employee.setDepartment(department);

department.setEmployees(List.of(employee));
```

Serialize và deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(department);

Department copy = mapper.readValue(json, Department.class);
Employee restoredEmployee = copy.getEmployees().get(0);

if (restoredEmployee.getDepartment() != copy) {
    throw new IllegalStateException("Back reference chưa được khôi phục");
}
```

JSON chỉ chứa `Department` cùng danh sách nhân viên. Sau deserialize, `restoredEmployee.getDepartment()` trỏ về chính instance `copy`.

Trong ví dụ minh họa, mỗi class nên được đặt trong file Java riêng nếu dùng làm mã nguồn thực tế. Các getter/setter và constructor không tham số được trình bày tường minh để thấy cách Jackson có thể tạo object và gán quan hệ.

## 12. Lưu ý khi dùng với JPA/Hibernate

Entity ORM thường có quan hệ hai chiều, ví dụ `@OneToMany` và `@ManyToOne`. Khi serialize entity trực tiếp, vòng tham chiếu có thể xuất hiện đúng như ví dụ Department/Employee.

Cặp `@JsonManagedReference`/`@JsonBackReference` có thể đặt cùng annotation ORM trên các property tương ứng, nhưng cần nhớ:

- Annotation Jackson chỉ điều khiển JSON serialization/deserialization; nó không thay thế mapping JPA.
- `@JsonManagedReference` không tự thiết lập quan hệ nghiệp vụ trong mọi luồng tạo entity; nó chỉ xử lý cặp reference khi Jackson deserialize.
- Entity có lazy proxy hoặc collection chưa được tải có thể phát sinh truy vấn ngoài ý muốn hoặc lỗi session đã đóng khi serialize.
- Không nên nhận trực tiếp entity từ request nếu client có thể thay đổi các quan hệ nhạy cảm; DTO và service thường phù hợp hơn để kiểm soát dữ liệu.
- Các phương thức `toString()`, `equals()` và `hashCode()` do Lombok hoặc code tự viết có thể vẫn đi qua vòng tham chiếu; annotation Jackson không ngăn các vòng lặp đó.

Nếu dùng Lombok, hãy kiểm tra `@Data` hoặc `@ToString` trên hai phía của quan hệ. Có thể cần loại field back reference khỏi `toString`, `equals` hoặc `hashCode` theo thiết kế domain.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Serialize vẫn đệ quy | Annotation đặt sai phía hoặc property đang serialize không thuộc cặp đã cấu hình | Đặt managed trên phía được ghi, back trên property trỏ ngược |
| Deserialize báo không tìm thấy back reference | Tên `value` giữa hai annotation không khớp hoặc thiếu cặp tương ứng | Dùng cùng tên cho managed/back reference |
| Back reference không được khôi phục | Back property không được Jackson nhận diện/không có managed property tương ứng | Kiểm tra visibility, accessor, tên reference và kiểu property |
| Muốn đặt `@JsonBackReference` trên List | Back property là container, không phải một object cha đơn | Đặt managed trên collection, back trên property đơn của child |
| Một child có nhiều quan hệ ngược | Dùng chung tên mặc định hoặc mô hình không phải quan hệ cha-con đơn giản | Đặt tên riêng cho từng cặp hoặc cân nhắc `@JsonIdentityInfo`/DTO |
| Lombok `toString()` vẫn đệ quy | Annotation Jackson không ảnh hưởng `toString()` | Loại field quan hệ khỏi `toString()` hoặc tự định nghĩa method |

Khi điều tra, hãy xác định chính xác object root, hướng property được serialize, tên reference và loại Java của property back. Đừng chỉ thêm annotation ngẫu nhiên cho đến khi lỗi biến mất; cần hiểu cặp nào đại diện cho quan hệ nào.

## 14. Quy trình chọn và cấu hình cặp reference

1. Xác định object root của JSON và hướng quan hệ muốn xuất ra.
2. Chọn property chính sẽ được ghi, thường là parent giữ collection child.
3. Đánh dấu property chính bằng `@JsonManagedReference`.
4. Đánh dấu property child trỏ ngược bằng `@JsonBackReference`.
5. Nếu có nhiều quan hệ, đặt `value` riêng cho từng cặp và bảo đảm tên khớp.
6. Serialize thử để xác nhận JSON không còn lặp vòng.
7. Deserialize lại và kiểm tra child trỏ về đúng parent instance.
8. Nếu object graph có chia sẻ identity hoặc nhiều liên kết phức tạp, đánh giá `@JsonIdentityInfo` hoặc DTO riêng.

## 15. Ghi nhớ

- `@JsonManagedReference` đánh dấu phía chính của quan hệ hai chiều; property này được serialize bình thường.
- `@JsonBackReference` đánh dấu phía trỏ ngược; property này không được serialize và được Jackson khôi phục khi deserialize qua managed reference tương ứng.
- Mặc định hai annotation dùng tên `defaultReference`; khi có nhiều cặp, đặt `value` riêng và ghép đúng tên.
- Managed reference thường đặt trên collection phía cha; back reference phải là property đơn trỏ về cha, không phải collection/map/array.
- Cặp annotation tránh vòng lặp bằng cách chỉ biểu diễn một hướng trong JSON nhưng vẫn giữ quan hệ hai chiều trong object graph sau khi đọc.
- `@JsonIgnore` bỏ property nhưng không tự khôi phục liên kết ngược.
- `@JsonIdentityInfo` phù hợp hơn khi cần biểu diễn object identity và các tham chiếu lặp phức tạp.
- Annotation Jackson không thay thế quan hệ JPA, không kiểm soát `toString()`/`equals()`/`hashCode()` và không thay thế thiết kế DTO cho API.

Khi một object graph có quan hệ cha-con hai chiều, hãy quyết định hướng nào cần xuất hiện trong JSON. Đặt `@JsonManagedReference` ở hướng đó và `@JsonBackReference` ở hướng ngược lại. Jackson sẽ serialize một phía để tránh đệ quy, rồi thiết lập lại tham chiếu về cha khi deserialize, giúp cấu trúc JSON gọn mà object graph trong Java vẫn giữ được liên kết cần thiết.
