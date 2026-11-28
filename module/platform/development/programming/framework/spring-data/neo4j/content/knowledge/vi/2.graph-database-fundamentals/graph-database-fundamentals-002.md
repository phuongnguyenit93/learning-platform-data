# Node, nhiều label và ý nghĩa của label trong truy vấn

Trong Neo4j, node biểu diễn một thực thể trong miền nghiệp vụ, còn label cho biết node thuộc những nhóm thực thể nào. Một node có thể mang nhiều label cùng lúc. Hiểu đúng quan hệ giữa node và label giúp ta mô hình hóa dữ liệu rõ ràng, viết truy vấn Cypher chính xác và ánh xạ entity phù hợp bằng Spring Data Neo4j.

## 1. Node lưu thực thể và thuộc tính

Neo4j là cơ sở dữ liệu đồ thị thuộc mô hình property graph. Một đồ thị thường gồm ba thành phần:

- **Node** biểu diễn một thực thể, chẳng hạn nhân viên, phòng ban, sản phẩm hoặc cơ sở dữ liệu.
- **Relationship** biểu diễn liên kết có hướng giữa hai node, chẳng hạn nhân viên `WORKS_IN` phòng ban.
- **Property** là cặp khóa–giá trị gắn với node hoặc relationship, chẳng hạn `employeeId`, `name` hay `createdAt`.

Ví dụ, node sau biểu diễn một nhân viên:

```cypher
CREATE (p:Person {
    employeeId: 'E-104',
    name: 'Lan',
    department: 'Platform'
})
RETURN p;
```

Trong ví dụ này, `Person` là label; `employeeId`, `name` và `department` là property. Label phân loại node, còn property mô tả dữ liệu của một node cụ thể. Vì vậy, `Person` không phải property và `name: 'Lan'` cũng không phải label.

Một node có thể tồn tại mà chưa có label hoặc property. Tuy nhiên, trong mô hình ứng dụng, ta thường gắn ít nhất một label để xác định loại thực thể và giúp truy vấn bắt đầu từ một tập node phù hợp.

## 2. Một node có thể có nhiều label

Label là tập các nhãn phân loại gắn với node. Một node có thể có nhiều label đồng thời, ví dụ một người vừa là `Person`, vừa là `Employee`:

```cypher
CREATE (p:Person:Employee {
    employeeId: 'E-104',
    name: 'Lan',
    department: 'Platform'
})
RETURN p, labels(p) AS nodeLabels;
```

Node trên có hai label là `Person` và `Employee`. Hai label cùng mô tả một node; chúng không tạo ra hai node riêng biệt và cũng không tạo relationship giữa hai loại dữ liệu.

Một số điểm cần nhớ:

- Label có tính phân loại. `Person` có thể mô tả nhóm người, còn `Employee` mô tả nhóm người có vai trò nhân viên.
- Nhiều label có thể cùng tồn tại trên một node. Một node có thể mang `Person`, `Employee` và `Manager` nếu các phân loại đó phù hợp với miền nghiệp vụ.
- Label không tạo ra cơ chế kế thừa kiểu dữ liệu. Gắn `Employee` lên node không tự động làm node có các property bắt buộc của một lớp `Employee` trong Java.
- Label không quy định schema property. Hai node cùng mang `Person` vẫn có thể có các tập property khác nhau, trừ khi ứng dụng hoặc constraint kiểm soát điều đó.
- Tên label phân biệt chữ hoa và chữ thường. Nên thống nhất quy ước đặt tên, ví dụ dùng `Person` thay vì lúc thì `person`, lúc thì `PERSON`.

Label cũng khác relationship type. `Employee` có thể là label của node, trong khi `WORKS_IN` là relationship type nối node nhân viên với node phòng ban:

```cypher
MATCH (p:Person:Employee), (d:Department)
CREATE (p)-[:WORKS_IN]->(d);
```

## 3. Label quyết định điều kiện khớp trong Cypher

Khi đặt label trong pattern của `MATCH`, Cypher chỉ trả về node có label được yêu cầu. Với nhiều label viết liền nhau, node phải có **tất cả** các label đó.

```cypher
// Mọi node được phân loại là Person
MATCH (p:Person)
RETURN p;

// Chỉ node đồng thời có cả Person và Employee
MATCH (p:Person:Employee)
RETURN p;
```

Nếu node chỉ có `Person`, truy vấn thứ nhất có thể tìm thấy node đó, còn truy vấn thứ hai sẽ không khớp. Thứ tự các label trong pattern không làm thay đổi ý nghĩa điều kiện: `:Person:Employee` yêu cầu cùng lúc hai label.

Ta cũng có thể kiểm tra label trong mệnh đề `WHERE`:

```cypher
MATCH (n:Person)
WHERE n:Employee
RETURN n;
```

Truy vấn trên tương đương về ý nghĩa với `MATCH (n:Person:Employee)`. Cách viết điều kiện trong `WHERE` hữu ích khi điều kiện label cần kết hợp với các điều kiện khác:

```cypher
MATCH (p:Person)
WHERE p:Employee
  AND p.department = 'Platform'
RETURN p.employeeId, p.name;
```

### Tìm node có một trong nhiều label

Nếu mục tiêu là lấy node thuộc nhóm `Person` **hoặc** `Organization`, không viết hai label liền nhau vì cách đó mang nghĩa AND. Có thể dùng điều kiện OR:

```cypher
MATCH (n)
WHERE n:Person OR n:Organization
RETURN n;
```

Tương tự, có thể loại một nhóm node bằng `NOT`:

```cypher
MATCH (p:Person)
WHERE NOT p:Employee
RETURN p;
```

Truy vấn cuối trả về các node có label `Person` nhưng không có label `Employee`.

### Đọc danh sách label của node

Hàm `labels()` trả về danh sách label đang gắn với một node:

```cypher
MATCH (n)
WHERE n.employeeId = 'E-104'
RETURN labels(n) AS labels;
```

Kết quả là một danh sách. Không nên dựa vào thứ tự phần tử trong danh sách để suy ra label nào là chính hay phụ; hãy kiểm tra sự hiện diện của label theo đúng nhu cầu.

## 4. Thêm và gỡ label

Cypher cung cấp `SET` để thêm label và `REMOVE` để gỡ label. Các thao tác này cập nhật chính node đang được khớp:

```cypher
// Thêm label Employee cho một Person
MATCH (p:Person {employeeId: 'E-104'})
SET p:Employee
RETURN p;

// Gỡ label Employee, vẫn giữ node và các property
MATCH (p:Person {employeeId: 'E-104'})
REMOVE p:Employee
RETURN p;
```

`REMOVE p:Employee` chỉ gỡ label được chỉ định; nó không xóa node và không xóa các property. Ngược lại, `DELETE p` xóa node, và chỉ thực hiện được khi node không còn relationship; `DETACH DELETE p` xóa cả các relationship gắn với node. Hãy chọn đúng thao tác theo mục đích nghiệp vụ.

Khi thêm label, cần đảm bảo điều kiện tìm node đủ chính xác. Nếu dùng một thuộc tính định danh nghiệp vụ như `employeeId`, hãy bảo đảm giá trị đó là duy nhất trong phạm vi label tương ứng bằng constraint phù hợp. Điều này giúp tránh cập nhật nhầm nhiều node và hỗ trợ truy vấn ổn định.

## 5. Ánh xạ node và label với Spring Data Neo4j

Spring Data Neo4j (SDN) ánh xạ node trong Neo4j thành các đối tượng Java. Annotation `@Node` xác định label chính dùng cho entity:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeId;

    private String name;
    private String department;

    protected Person() {
    }

    public Person(String employeeId, String name, String department) {
        this.employeeId = employeeId;
        this.name = name;
        this.department = department;
    }

    // Getter và setter được lược bỏ để tập trung vào ánh xạ node.
}
```

Khi lưu một `Person`, SDN ánh xạ đối tượng thành node mang label `Person` và các property tương ứng. Trường `employeeId` ở ví dụ này là định danh do ứng dụng cung cấp; vì vậy ứng dụng phải bảo đảm nó có giá trị và tính duy nhất theo quy tắc dữ liệu của mình. Trong dự án dùng định danh do Neo4j sinh, hãy chọn cách khai báo `@Id` và `@GeneratedValue` tương ứng với phiên bản SDN đang sử dụng.

Một repository có thể khai báo truy vấn Cypher để lọc đồng thời nhiều label:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person:Employee)
        WHERE p.department = $department
        RETURN p
        """)
    List<Person> findEmployeesByDepartment(String department);
}
```

Phương thức trên trả về các node có cả `Person` và `Employee`, đồng thời có `department` bằng giá trị tham số. Tham số được truyền riêng thay vì nối chuỗi đầu vào vào Cypher, giúp truy vấn rõ ràng và tránh lỗi do dữ liệu đầu vào chứa ký tự đặc biệt.

Nếu ứng dụng cần label bổ sung thay đổi theo nghiệp vụ, hãy xác định rõ nơi quản lý chúng. Có thể cập nhật label bằng truy vấn Cypher trong repository, hoặc ánh xạ các label động bằng cơ chế `@DynamicLabels` của SDN khi mô hình entity cần đọc/ghi tập label đó. Không nên giả định mọi label bổ sung trên node đều tương ứng với một lớp Java riêng.

Ví dụ repository cập nhật label trong một câu lệnh:

```java
@Query("""
    MATCH (p:Person {employeeId: $employeeId})
    SET p:Employee
    RETURN p
    """)
Person markAsEmployee(String employeeId);
```

Khi thao tác cập nhật label là một phần của quy trình ghi gồm nhiều bước, đặt các thao tác liên quan trong cùng transaction bằng cơ chế transaction của Spring, chẳng hạn `@Transactional` ở service. Nhờ đó, các thay đổi dữ liệu cần đi cùng nhau được commit hoặc rollback cùng nhau.

## 6. Dùng label để viết truy vấn dễ tối ưu

Label không chỉ giúp đọc truy vấn dễ hơn. Neo4j có thể dùng label để giới hạn tập node cần xét và chọn các index gắn với label cùng property. Ví dụ, nếu ứng dụng thường tìm nhân viên theo mã định danh, hãy tạo constraint hoặc index trên property đó:

```cypher
CREATE CONSTRAINT person_employee_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeId IS UNIQUE;
```

Sau đó truy vấn có thể chỉ rõ label và property:

```cypher
MATCH (p:Person {employeeId: $employeeId})
RETURN p;
```

Constraint duy nhất vừa bảo vệ tính toàn vẹn của dữ liệu vừa tạo backing index để hỗ trợ tra cứu. Cú pháp constraint ở trên dành cho các phiên bản Neo4j hỗ trợ cú pháp hiện đại; hãy đối chiếu phiên bản máy chủ nếu dự án đang dùng bản cũ hơn.

Một số nguyên tắc thực tế:

1. Đặt label theo khái niệm miền nghiệp vụ ổn định, ví dụ `Person`, `Product`, `Department`.
2. Dùng nhiều label khi một node thực sự thuộc nhiều nhóm có ý nghĩa độc lập, ví dụ `Person` và `Employee`.
3. Trong truy vấn, nêu label càng cụ thể càng tốt để giới hạn tập node và thể hiện rõ ý định.
4. Tạo index hoặc constraint cho các property thường dùng để tìm kiếm, kết hợp với label tương ứng.
5. Tránh tạo label tùy tiện từ dữ liệu người dùng hoặc dùng label thay cho mọi loại phân loại linh hoạt. Với dữ liệu biến động cao, property hoặc node phân loại liên kết bằng relationship có thể phù hợp hơn.

Để kiểm tra kế hoạch thực thi, dùng `EXPLAIN` để xem kế hoạch mà không chạy truy vấn, hoặc `PROFILE` để chạy truy vấn và thu thập số liệu thực tế:

```cypher
EXPLAIN
MATCH (p:Person {employeeId: 'E-104'})
RETURN p;
```

Kế hoạch có thể thay đổi theo phiên bản Neo4j, index hiện có, thống kê dữ liệu và độ chọn lọc của điều kiện. Vì vậy, hãy đánh giá bằng truy vấn và dữ liệu gần với tải thực tế của ứng dụng.

## 7. Những lỗi thường gặp

| Cách viết hoặc giả định | Vấn đề | Cách xử lý |
|---|---|---|
| `MATCH (n:Person:Employee)` với ý định OR | Cypher yêu cầu node có cả hai label | Dùng `WHERE n:Person OR n:Employee` |
| Xem label như property | Label và property có vai trò khác nhau | Dùng `labels(n)` để kiểm tra label; truy cập `n.name` để đọc property |
| Cho rằng label tạo kế thừa Java | Neo4j không tự tạo cấu trúc lớp hay property bắt buộc từ label | Thiết kế mapping và kiểm tra dữ liệu ở tầng ứng dụng hoặc constraint |
| Dùng `REMOVE` khi muốn xóa node | `REMOVE` chỉ gỡ label hoặc property được chỉ định | Dùng `DELETE` hoặc `DETACH DELETE` khi thực sự muốn xóa node |
| Truy vấn `MATCH (n)` rồi lọc sau dù đã biết loại node | Có thể phải xét tập node rộng và làm ý định truy vấn khó đọc | Bổ sung label phù hợp ngay trong pattern |
| Dùng tên hiển thị làm định danh duy nhất | Nhiều thực thể có thể trùng tên hoặc đổi tên | Dùng khóa nghiệp vụ ổn định và constraint duy nhất |

## 8. Thực hành tổng hợp

Tạo một vài node có label khác nhau:

```cypher
CREATE
  (:Person:Employee {employeeId: 'E-104', name: 'Lan', department: 'Platform'}),
  (:Person {employeeId: 'C-201', name: 'Minh'}),
  (:Organization {organizationId: 'ORG-01', name: 'Rental App'});
```

Thử lần lượt các truy vấn sau và giải thích sự khác nhau:

```cypher
// A. Tất cả node là Person
MATCH (n:Person)
RETURN n;

// B. Chỉ Person đồng thời là Employee
MATCH (n:Person:Employee)
RETURN n;

// C. Person hoặc Organization
MATCH (n)
WHERE n:Person OR n:Organization
RETURN n;

// D. Xem label của từng node
MATCH (n)
RETURN n.name, labels(n);
```

Kết quả cần nhận ra: truy vấn A trả về Lan và Minh; truy vấn B chỉ trả về Lan; truy vấn C trả về cả hai node Person và node Organization. Truy vấn D cho thấy mỗi node có thể có một hoặc nhiều label. Từ đó, hãy chọn label phù hợp cho từng entity trong SDN và viết repository query dựa trên đúng điều kiện phân loại của dữ liệu.

## Kết luận

Node là thực thể, property mô tả thực thể, còn label phân loại node. Một node có thể mang nhiều label và truy vấn Cypher với nhiều label liền nhau yêu cầu node thỏa mãn tất cả các label đó. Khi dùng Spring Data Neo4j, hãy ánh xạ label chính bằng `@Node`, quản lý label bổ sung có chủ đích và viết repository query thể hiện đúng ngữ nghĩa AND/OR. Cách mô hình hóa này giúp dữ liệu đồ thị dễ hiểu, truy vấn chính xác và có cơ hội tận dụng index hiệu quả.
