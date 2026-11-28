# Primary label, label bổ sung và quy ước tên mặc định

Trong Neo4j, một node có thể mang nhiều label cùng lúc. Label giúp phân loại node và cho phép truy vấn chọn đúng nhóm dữ liệu, ví dụ `Person`, `Employee` hoặc `Auditable`. Khi dùng Spring Data Neo4j (SDN), label còn là một phần quan trọng của cơ chế ánh xạ: SDN dựa vào label chính để xác định node nào tương ứng với một lớp Java.

Vì vậy, khi thiết kế node entity, cần phân biệt ba khái niệm: **primary label** xác định loại entity mà SDN ánh xạ; **label bổ sung** mô tả thêm đặc điểm hoặc vai trò của node; **dynamic label** là tập label được quản lý bằng dữ liệu tại runtime. Hiểu đúng quy ước mặc định giúp tránh lỗi khi đổi tên lớp, dùng nhiều entity có cùng tên hoặc kết nối với một graph schema đã tồn tại.

## 1. Label trong Neo4j và vai trò của primary label

Label là nhãn gắn trên node. Một node có thể có một hoặc nhiều label, còn relationship có kiểu quan hệ riêng. Ví dụ, node một nhân viên có thể được lưu như sau:

```cypher
CREATE (:Person:Employee:Auditable {
    employeeId: "E-104",
    name: "Mai Anh"
})
```

Node này mang đồng thời ba label `Person`, `Employee` và `Auditable`. Truy vấn `MATCH (p:Person)` tìm các node có label `Person`; truy vấn `MATCH (p:Person:Employee)` chỉ khớp các node có cả hai label.

Trong SDN, primary label là nhãn chính dùng để nhận diện loại entity. Khi một entity được lưu thông qua repository hoặc `Neo4jTemplate`, node được ghi sẽ có ít nhất primary label đã cấu hình. Khi đọc, các node có primary label tương ứng sẽ được ánh xạ thành instance của lớp Java đó.

Primary label nên thể hiện loại miền nghiệp vụ cụ thể nhất mà lớp đại diện. Ví dụ, `Employee` phù hợp hơn `Entity` nếu lớp Java mô tả nhân viên. Những nhãn mang ý nghĩa phân loại dùng chung như `Auditable` có thể là label bổ sung.

## 2. Quy ước tên mặc định của `@Node`

Đánh dấu một lớp bằng `@Node` cho biết đây là domain class được SDN quản lý. Nếu không chỉ định label, SDN dùng **tên đơn giản của lớp Java** (simple class name) làm primary label.

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node
public class Movie {

    @Id
    private String title;

    private Integer released;
}
```

Với khai báo trên, label mặc định là `Movie`. Tên package không được ghép vào label; SDN cũng không tự chuyển tên lớp sang chữ hoa hoặc `snake_case`. Ví dụ, lớp `MovieRecord` mặc định tương ứng với label `MovieRecord`, không phải `MOVIE_RECORD` hay `movie_record`.

Nếu graph đã có label theo quy ước khác, hoặc muốn giữ label ổn định khi đổi tên lớp Java, hãy khai báo rõ label:

```java
@Node("Film")
public class Movie {

    @Id
    private String title;
}
```

`value` là alias của thuộc tính `labels` trong `@Node`, vì vậy `@Node("Film")` chỉ định label `Film` làm primary label. Có thể viết tường minh bằng `@Node(labels = "Film")`.

Quy ước này có một hệ quả cần chú ý: hai lớp Java ở hai package khác nhau nhưng có cùng simple class name sẽ cùng suy ra một label mặc định. Nếu chúng đại diện cho hai loại node khác nhau, hãy đặt primary label tường minh để tránh xung đột ánh xạ.

## 3. Khai báo label bổ sung tĩnh

Một entity có thể cần nhiều label cố định. SDN cho phép khai báo chúng bằng thuộc tính `labels` của `@Node`. Nếu không chỉ định `primaryLabel` riêng, phần tử đầu tiên trong mảng `labels` được xem là primary label; các phần tử còn lại là label bổ sung.

```java
@Node(labels = {"Employee", "Person", "Auditable"})
public class Employee {

    @Id
    private String employeeId;

    private String name;
}
```

Trong ví dụ này, `Employee` là primary label, còn `Person` và `Auditable` là label bổ sung. Primary label nên là nhãn cụ thể nhất phản ánh lớp Java. Để tránh phụ thuộc vào thứ tự phần tử, có thể khai báo primary label riêng:

```java
@Node(
    primaryLabel = "Employee",
    labels = {"Person", "Auditable", "Searchable"}
)
public class Employee {

    @Id
    private String employeeId;

    private String name;
}
```

Ở cách viết này, `Employee` là primary label; `Person`, `Auditable` và `Searchable` là các label bổ sung. `primaryLabel` giúp thể hiện rõ label dùng để ánh xạ lớp, còn `labels` liệt kê những nhãn tĩnh đi kèm.

Các label tĩnh là một phần của metadata lớp, không phải thuộc tính để thay đổi tùy từng instance. Chọn label bổ sung khi mọi node của entity đều cần cùng một nhãn, chẳng hạn tất cả nhân viên đều là `Auditable`. Nếu mỗi nhân viên có một tập nhãn khác nhau theo dữ liệu nghiệp vụ, hãy cân nhắc `@DynamicLabels`.

## 4. Quản lý label thay đổi tại runtime với `@DynamicLabels`

`@DynamicLabels` đánh dấu một thuộc tính kiểu `Collection<String>` như `Set<String>` hoặc `List<String>` làm nơi lưu các label bổ sung có thể thay đổi theo từng entity. Khi đọc node, SDN thu thập các label không được khai báo tĩnh vào collection này. Khi ghi entity, SDN thay thế tập label trên node bằng các label tĩnh cộng với nội dung collection.

Ví dụ, mỗi nhân viên có thể được gắn nhãn động `Mentor`, `OnCall` hoặc `ProjectLead` tùy nhiệm vụ:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.DynamicLabels;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Employee")
public class Employee {

    @Id
    private String employeeId;

    private String name;

    @DynamicLabels
    private Set<String> labels = new HashSet<>();

    public void addLabel(String label) {
        labels.add(label);
    }

    public void removeLabel(String label) {
        labels.remove(label);
    }
}
```

Khi ứng dụng gọi `addLabel("Mentor")` rồi lưu entity, node có thể mang cả label tĩnh `Employee` và label động `Mentor`. Truy vấn Cypher có thể dùng `MATCH (e:Employee:Mentor)` để tìm nhóm nhân viên đang có vai trò mentor.

Điểm quan trọng là collection được đánh dấu `@DynamicLabels` trở thành nguồn sự thật cho toàn bộ label của node khi ghi. Các label được đọc từ node nhưng không thuộc metadata tĩnh sẽ được đưa vào collection; lúc lưu, SDN ghi lại tập label tĩnh cộng với collection đó. Vì thế, nếu một hệ thống khác tự thêm label vào node sau khi entity đã được tải, lần lưu entity với collection cũ có thể loại bỏ label mới đó. Không nên dùng `@DynamicLabels` khi có ứng dụng khác cùng quản lý label trên những node này mà không có cơ chế đồng bộ rõ ràng.

Hãy dùng dynamic label cho các phân loại có số lượng hữu hạn và có ý nghĩa truy vấn. Nếu giá trị có tính cá thể cao, thay đổi thường xuyên hoặc thực chất là dữ liệu mô tả như `departmentCode`, `score` hay `createdAt`, nên lưu thành property thay vì tạo một label mới cho từng giá trị.

## 5. Quy ước tên mặc định của property và relationship

Label không phải thành phần duy nhất có quy ước mặc định. Trong một lớp `@Node`, tên thuộc tính Java được dùng làm tên property của node nếu không có cấu hình khác. SDN không tự đổi camelCase thành snake_case.

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Employee")
public class Employee {

    @Id
    private String employeeId;

    private String displayName; // property mặc định: displayName

    @Property("display_name")
    private String legalName;   // property trong Neo4j: display_name
}
```

Sử dụng `@Property` khi cần ánh xạ sang tên property đã có trong database hoặc muốn duy trì một quy ước đặt tên độc lập với tên field Java. Hãy nhất quán giữa các entity để câu Cypher dễ đọc và giảm lỗi do nhầm tên.

Với relationship, khai báo `@Relationship` để xác định kiểu và hướng khi mô hình cần một quy ước rõ ràng:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Employee")
public class Employee {

    @Id
    private String employeeId;

    @Relationship(type = "REPORTS_TO", direction = Relationship.Direction.OUTGOING)
    private Employee manager;
}
```

Trong SDN, hướng relationship mặc định là `OUTGOING`. Với mô hình miền nghiệp vụ, nên ghi rõ `type` và `direction` khi tên quan hệ hoặc hướng đi có ý nghĩa quan trọng. Việc đặt tên relationship type là quy ước riêng của graph schema; không nên suy luận rằng tên field Java luôn được chuyển thành một kiểu relationship theo một định dạng chữ hoa cụ thể.

Bảng sau tóm tắt các quy ước thường dùng:

| Thành phần Java | Mặc định hoặc cấu hình | Kết quả ánh xạ |
| --- | --- | --- |
| Lớp `@Node` không ghi label | Tên đơn giản của lớp | Primary label, ví dụ `MovieRecord` |
| `@Node("Film")` | `value` là alias của `labels` | Primary label `Film` |
| `@Node(labels = {"Person", "Auditable"})` | Phần tử đầu tiên là primary nếu không đặt `primaryLabel` | `Person` là primary, `Auditable` là label bổ sung |
| `@Node(primaryLabel = "Employee", labels = {"Person"})` | Chỉ định primary riêng | `Employee` là primary, `Person` là label bổ sung |
| Field `displayName` | Tên field Java | Property `displayName` |
| `@Property("display_name")` | Chỉ định tên property | Property `display_name` |
| `@Relationship(direction = ...)` | Hướng mặc định là `OUTGOING` | Hướng relationship đi ra từ node hiện tại |

## 6. Label trong kế thừa entity

Khi mô hình có lớp cơ sở và lớp cụ thể, cần khai báo rõ label ở từng cấp phù hợp. `@Node` không tự được kế thừa từ superclass hoặc interface. SDN hỗ trợ mô hình đa hình với lớp cơ sở trừu tượng được đánh dấu `@Node`; các label của lớp cơ sở được dùng như label bổ sung cùng với label của lớp triển khai cụ thể.

```java
@Node("Content")
public abstract class Content {

    @Id
    protected String id;

    protected String title;
}

@Node("Article")
public class Article extends Content {

    private String body;
}
```

Với mô hình này, label `Article` nhận diện loại entity cụ thể, còn `Content` cho phép truy vấn theo lớp cơ sở. Chẳng hạn `MATCH (c:Content)` có thể tìm các node thuộc các loại nội dung cụ thể trong hệ phân cấp. Chỉ nên áp dụng kế thừa entity khi quan hệ “là một loại của” thực sự tồn tại trong miền nghiệp vụ; đừng tạo superclass chỉ để gom những field tình cờ giống nhau.

## 7. Chọn và duy trì label an toàn

Khi thiết kế label, có thể áp dụng các nguyên tắc sau:

1. Chọn primary label phản ánh loại node cụ thể và ổn định, ví dụ `Employee`, `Movie` hoặc `Department`.
2. Dùng label bổ sung tĩnh cho đặc điểm chung của toàn bộ entity, ví dụ `Auditable` hoặc `Searchable`.
3. Dùng `@DynamicLabels` khi từng node cần tập label có thể thay đổi và ứng dụng kiểm soát toàn bộ tập đó.
4. Dùng property cho dữ liệu biến thiên hoặc giá trị có nhiều khả năng khác nhau; không tạo label mới cho từng mã, tên hoặc giá trị đo lường.
5. Khai báo label tường minh khi đổi tên lớp Java, khi có các lớp trùng simple name hoặc khi tích hợp với schema có sẵn.
6. Giữ cách viết hoa và chính tả label nhất quán. Label trong Cypher phân biệt chữ hoa chữ thường, vì vậy `Employee` và `employee` là hai cách viết khác nhau.

Label chỉ phân loại node và hỗ trợ truy vấn. Bản thân label không đảm bảo một property là duy nhất hay bắt buộc phải có. Nếu `employeeId` phải duy nhất, cần khai báo uniqueness constraint trong Neo4j, ví dụ:

```cypher
CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.employeeId IS UNIQUE
```

Khi đổi primary label của một entity đã có dữ liệu, hãy xem đó là thay đổi schema cần phối hợp với dữ liệu hiện hữu, truy vấn Cypher, index và constraint. Chỉ đổi annotation trong Java không tự động đổi toàn bộ label của các node cũ trong database.

## Kết luận

SDN dùng simple class name làm primary label khi `@Node` không chỉ định label. Có thể cấu hình primary label và các label bổ sung tĩnh bằng `@Node`, còn `@DynamicLabels` quản lý các label thay đổi theo từng node. Tên property mặc định giữ nguyên tên field Java và có thể đổi bằng `@Property`; hướng relationship mặc định là `OUTGOING`. Chọn tên label ổn định, phân biệt rõ label tĩnh với label động và đồng bộ chúng với graph schema sẽ giúp ánh xạ node entity chính xác, dễ truy vấn và dễ bảo trì.
