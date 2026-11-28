# Tái sử dụng thành phần truy vấn, projection và thứ tự sắp xếp

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách Cypher-DSL biểu diễn câu Cypher thành các thành phần có thể tái sử dụng.
- Tách node, relationship, property và condition thành các hàm hỗ trợ để ghép truy vấn.
- Dùng tham số của Cypher-DSL để truyền dữ liệu an toàn và tránh nối chuỗi truy vấn.
- Kết hợp Cypher-DSL với `CypherdslConditionExecutor` và `CypherdslStatementExecutor` của Spring Data Neo4j.
- Trả về entity hoặc projection tùy nhu cầu, đồng thời áp dụng thứ tự sắp xếp bằng `SortItem`, `Sort` hoặc `Pageable`.

## 1. Vì sao cần tái sử dụng thành phần truy vấn?

Khi một ứng dụng có nhiều màn hình tìm kiếm, các truy vấn thường chia sẻ một phần cấu trúc. Ví dụ, màn hình danh bạ, quản trị người dùng và báo cáo hoạt động đều có thể bắt đầu từ node `Person`, lọc theo trạng thái, ngày tạo hoặc phòng ban, sau đó sắp xếp theo tên hay thời điểm cập nhật.

Nếu mỗi truy vấn được viết thành một chuỗi Cypher riêng, các đoạn điều kiện và quy tắc sắp xếp dễ bị lặp. Khi nghiệp vụ thay đổi, nhà phát triển phải tìm và sửa nhiều nơi. Nối chuỗi còn khiến việc kiểm soát tham số, dấu ngoặc và cấu trúc truy vấn khó hơn.

Cypher-DSL là thư viện Java cung cấp API dạng builder để mô tả câu Cypher bằng các đối tượng. Thay vì ghép chuỗi, ứng dụng tạo các thành phần như node, relationship, property, condition, sort item và cuối cùng xây dựng thành một `Statement`.

Một thành phần truy vấn có thể được tách thành hàm Java rồi dùng lại ở nhiều câu truy vấn. Ví dụ, hàm tạo điều kiện lọc trạng thái có thể được ghép với điều kiện theo phòng ban trong một màn hình và điều kiện theo ngày tạo trong màn hình khác.

Cypher-DSL tạo Abstract Syntax Tree (AST) và cung cấp kiểm tra cấu trúc ở thời điểm biên dịch. Nó giúp giảm lỗi cú pháp khi xây dựng truy vấn, nhưng không tự kiểm tra rằng label, relationship type hay property có thực sự tồn tại trong dữ liệu Neo4j.

## 2. Những khối xây dựng có thể tái sử dụng

Các kiểu thường gặp trong Cypher-DSL gồm:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Node` | Mô tả node và label | `Cypher.node("Person").named("p")` |
| `Relationship` | Mô tả liên kết giữa các node | `p.relationshipTo(d, "MEMBER_OF")` |
| `Property` | Tham chiếu property của node hoặc relationship | `p.property("name")` |
| `Condition` | Biểu diễn điều kiện lọc | `name.isEqualTo(...)` |
| `SortItem` | Biểu diễn một tiêu chí sắp xếp | `name.ascending()` |
| `Statement` | Câu truy vấn đã xây dựng hoàn chỉnh | `Cypher.match(p).returning(p).build()` |

Ví dụ tạo node, property và câu truy vấn:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Property;
import org.neo4j.cypherdsl.core.Statement;

Node person = Cypher.node("Person").named("p");
Property name = person.property("name");

Statement statement = Cypher.match(person)
    .returning(name)
    .build();
```

Biến `person` được dùng trong `MATCH`, còn property `name` được lấy từ chính node đó để dùng trong `RETURN`. Không cần tạo một chuỗi Cypher riêng cho từng phần.

Các thành phần này là đối tượng mô tả cấu trúc truy vấn. Có thể truyền chúng vào hàm hỗ trợ, kết hợp với nhau rồi xây dựng thành một statement ở nơi cần thực thi.

## 3. Tách điều kiện thành các hàm có thể ghép

Giả sử nhiều màn hình cần tìm người đang hoạt động và lọc theo tên. Có thể tách từng điều kiện thành hàm nhận node gốc:

```java
import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;

public final class PersonConditions {

    private PersonConditions() {
    }

    public static Condition isActive(Node person) {
        return person.property("active")
            .isEqualTo(Cypher.literalOf(true));
    }

    public static Condition hasName(Node person, String name) {
        return person.property("name")
            .isEqualTo(Cypher.parameter("personName", name));
    }

    public static Condition belongsToDepartment(
            Node person,
            String departmentCode) {
        return person.property("departmentCode")
            .isEqualTo(Cypher.parameter("departmentCode", departmentCode));
    }
}
```

Các hàm trả về `Condition`, không trả về cả câu truy vấn. Vì vậy, điều kiện có thể được kết hợp trong nhiều ngữ cảnh:

```java
Node person = Cypher.node("Person").named("p");

Condition activePeople =
    PersonConditions.isActive(person);

Condition namedActivePeople =
    activePeople.and(PersonConditions.hasName(person, "An"));

Condition departmentPeople =
    activePeople.and(
        PersonConditions.belongsToDepartment(person, "ENG")
    );
```

`and()` và `or()` giúp ghép các điều kiện nhỏ thành biểu thức lớn. Cùng một điều kiện `isActive` có thể được dùng lại mà không phải viết lại property hoặc phép so sánh.

Khi điều kiện là tùy chọn, service có thể chỉ ghép điều kiện nếu người dùng đã cung cấp giá trị:

```java
Condition condition = PersonConditions.isActive(person);

if (departmentCode != null && !departmentCode.isBlank()) {
    condition = condition.and(
        PersonConditions.belongsToDepartment(person, departmentCode)
    );
}

if (name != null && !name.isBlank()) {
    condition = condition.and(
        PersonConditions.hasName(person, name)
    );
}
```

Cách làm này phù hợp với màn hình tìm kiếm có nhiều bộ lọc tùy chọn. Hãy xác định rõ cách xử lý chuỗi rỗng, null và giá trị mặc định trước khi tạo điều kiện.

## 4. Tái sử dụng node, relationship và property

Không chỉ điều kiện lọc mới có thể tái sử dụng. Node và relationship pattern cũng có thể được tạo bằng các hàm hỗ trợ.

Ví dụ, một người thuộc một phòng ban:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Relationship;

public final class PersonPatterns {

    private PersonPatterns() {
    }

    public static Node person(String variable) {
        return Cypher.node("Person").named(variable);
    }

    public static Node department(String variable) {
        return Cypher.node("Department").named(variable);
    }

    public static Relationship membership(
            Node person,
            Node department) {
        return person.relationshipTo(department, "MEMBER_OF");
    }
}
```

Có thể dùng pattern này trong truy vấn:

```java
Node person = PersonPatterns.person("p");
Node department = PersonPatterns.department("d");

var membership = PersonPatterns.membership(person, department);

var statement = Cypher.match(membership)
    .where(
        department.property("code")
            .isEqualTo(Cypher.parameter("code", "ENG"))
    )
    .returning(person, department)
    .build();
```

Hàm `membership()` chỉ mô tả relationship pattern. Điều kiện, phần trả về và cách sắp xếp được quyết định ở truy vấn gọi nó. Đây là cách giữ riêng trách nhiệm mô hình hóa graph và trách nhiệm của từng truy vấn nghiệp vụ.

Nên tạo node với biến riêng cho từng lần xây dựng statement. Tránh dùng chung một biến node có alias cố định cho các nhánh truy vấn độc lập nếu việc ghép có thể gây trùng symbolic name hoặc làm truy vấn khó đọc.

## 5. Truyền tham số thay vì ghép giá trị vào chuỗi

Cypher-DSL hỗ trợ tham số có tên và tham số ẩn danh:

```java
Cypher.parameter("personName", name)
Cypher.anonParameter(name)
```

Tham số có tên được render thành `$personName`. Tham số ẩn danh được DSL tự đặt tên phù hợp. Các giá trị gắn với tham số được lưu trong catalog của statement để tầng thực thi sử dụng.

Ví dụ:

```java
Node person = Cypher.node("Person").named("p");

var statement = Cypher.match(person)
    .where(
        person.property("name")
            .isEqualTo(Cypher.parameter("name", "An"))
    )
    .returning(person)
    .build();
```

Cypher được tạo có dạng:

```cypher
MATCH (p:Person)
WHERE p.name = $name
RETURN p
```

Giá trị `An` được gắn với tham số `name`; nó không được nối trực tiếp vào câu truy vấn. Điều này giúp tái sử dụng statement với dữ liệu đầu vào khác nhau và giảm nguy cơ Cypher injection.

Khi dùng cùng tên tham số nhiều lần trong một statement, hãy bảo đảm các vị trí đó có cùng giá trị. Nếu cùng một tên được gắn với các giá trị xung đột, Cypher-DSL có thể báo lỗi khi thu thập tham số.

## 6. Dùng CypherdslConditionExecutor để thêm điều kiện vào truy vấn SDN

Nếu chỉ cần thêm điều kiện động vào truy vấn do Spring Data Neo4j tạo, có thể mở rộng repository bằng `CypherdslConditionExecutor<T>`.

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslConditionExecutor;

public interface PersonRepository
        extends Neo4jRepository<Person, Long>,
                CypherdslConditionExecutor<Person> {
}
```

Sau đó, xây dựng điều kiện bằng Cypher-DSL và truyền cho repository:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Property;

Node person = Cypher.node("Person").named("person");
Property firstName = person.property("firstName");
Property lastName = person.property("lastName");

var condition = firstName
    .isEqualTo(Cypher.anonParameter("Helge"))
    .or(lastName.isEqualTo(Cypher.parameter("lastName", "B.")));

var people = personRepository.findAll(
    condition,
    lastName.descending()
);
```

Ở đây, SDN tạo truy vấn theo domain type `Person`, sau đó thêm `Condition` do ứng dụng cung cấp. Đối số `lastName.descending()` là `SortItem` của Cypher-DSL và xác định thứ tự sắp xếp.

`CypherdslConditionExecutor` còn cung cấp các overload nhận `Sort` của Spring Data hoặc `Pageable`, cùng các thao tác `findOne`, `count` và `exists`. Hãy dùng nó khi cấu trúc truy vấn chính vẫn theo entity mapping của SDN và phần thay đổi chủ yếu là điều kiện lọc hoặc thứ tự.

Executor này trả về domain type của repository. Nếu cần một câu truy vấn hoàn toàn tùy chỉnh hoặc projection riêng, hãy cân nhắc `CypherdslStatementExecutor`.

## 7. Dùng CypherdslStatementExecutor cho statement tùy chỉnh

Khi cần tự kiểm soát cấu trúc `MATCH`, relationship, `WHERE` và `RETURN`, repository có thể mở rộng `CypherdslStatementExecutor<T>`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslStatementExecutor;

public interface PersonRepository
        extends Neo4jRepository<Person, Long>,
                CypherdslStatementExecutor<Person> {
}
```

Ví dụ này là một cách khai báo repository độc lập. Nếu ứng dụng cần cả hai kiểu mở rộng, có thể cho cùng interface kế thừa đồng thời `CypherdslConditionExecutor<Person>` và `CypherdslStatementExecutor<Person>`.

Executor này nhận một `Statement` hoàn chỉnh và cung cấp các thao tác như:

- `findOne(statement)`: ánh xạ tối đa một kết quả thành domain type.
- `findAll(statement)`: ánh xạ nhiều kết quả thành domain type.
- `findOne(statement, projectionClass)`: ánh xạ một kết quả thành kiểu projection.
- `findAll(statement, projectionClass)`: ánh xạ nhiều kết quả thành kiểu projection.

Ví dụ tạo statement trong hàm riêng:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Statement;

public final class PersonQueries {

    private PersonQueries() {
    }

    public static Statement peopleByFirstName(String firstName) {
        Node person = Cypher.node("Person").named("p");

        return Cypher.match(person)
            .where(
                person.property("firstName")
                    .isEqualTo(Cypher.anonParameter(firstName))
            )
            .returning(person.getRequiredSymbolicName())
            .build();
    }
}
```

Gọi từ service:

```java
import java.util.Collection;

Collection<Person> people =
    personRepository.findAll(
        PersonQueries.peopleByFirstName("Helge")
    );
```

Việc đóng gói statement trong hàm `peopleByFirstName` giúp tái sử dụng truy vấn ở nhiều service hoặc use case. Nếu điều kiện nghiệp vụ thay đổi, có thể sửa một hàm xây dựng thay vì sửa các chuỗi Cypher rải rác.

## 8. Projection khi dùng Cypher-DSL

Khi repository cần trả về một góc nhìn hẹp hơn domain entity, có thể dùng overload nhận `projectionClass`.

Ví dụ projection interface:

```java
public interface PersonNames {

    String getFirstName();

    String getLastName();
}
```

Dùng statement executor:

```java
import java.util.Collection;

Collection<PersonNames> names =
    personRepository.findAll(
        PersonQueries.peopleByFirstName("Helge"),
        PersonNames.class
    );
```

`PersonNames.class` cho biết kiểu projection mà SDN cần tạo. Projection giúp tầng gọi chỉ phụ thuộc vào những accessor được công khai, thay vì toàn bộ API của entity `Person`.

Khi thiết kế statement, hãy trả về các node, relationship và property cần thiết cho việc ánh xạ kết quả. Nếu projection cần property ở node liên quan hoặc relationship properties, statement phải chứa dữ liệu tương ứng. Việc chỉ trả một node gốc có thể không đủ cho projection cần dữ liệu từ các nhánh quan hệ.

Projection và statement có trách nhiệm khác nhau: statement xác định graph và dữ liệu được truy vấn; projection xác định kiểu dữ liệu mà ứng dụng nhận. Không nên nhầm projection với một câu truy vấn tự động giới hạn mọi nhánh graph nếu statement vẫn yêu cầu các phần tử đó.

## 9. Sắp xếp bằng SortItem

Cypher-DSL biểu diễn thứ tự bằng `SortItem`. Một `Property` có thể tạo sort item tăng dần hoặc giảm dần:

```java
Node person = Cypher.node("Person").named("p");

var name = person.property("name");
var createdAt = person.property("createdAt");

var statement = Cypher.match(person)
    .returning(person)
    .orderBy(
        name.ascending(),
        createdAt.descending()
    )
    .build();
```

Truy vấn tương ứng có dạng:

```cypher
MATCH (p:Person)
RETURN p
ORDER BY p.name ASC, p.createdAt DESC
```

Thứ tự được áp dụng theo thứ tự các `SortItem` được truyền vào. Trong ví dụ, Neo4j sắp xếp theo tên tăng dần trước, sau đó dùng thời điểm tạo giảm dần để phân biệt các bản ghi có cùng tên.

Có thể đóng gói tiêu chí sắp xếp thành hàm dùng chung:

```java
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.SortItem;

public final class PersonSorts {

    private PersonSorts() {
    }

    public static SortItem byNameAscending(Node person) {
        return person.property("name").ascending();
    }

    public static SortItem byCreatedAtDescending(Node person) {
        return person.property("createdAt").descending();
    }
}
```

Khi dùng trong statement, truyền các sort item theo đúng thứ tự ưu tiên. Nếu phân trang, nên bổ sung một khóa duy nhất làm tiêu chí phụ để kết quả có thứ tự ổn định hơn.

## 10. Sắp xếp và phân trang bằng Pageable

Với `CypherdslStatementExecutor`, SDN có overload nhận một phần statement đang ở bước đọc và trả về, một statement đếm, cùng `Pageable`. Executor thêm thứ tự, `SKIP` và `LIMIT` từ `Pageable` vào truy vấn chính.

Ví dụ:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;

Node person = Cypher.node("Person").named("p");

var pageQuery = Cypher.match(person)
    .where(
        person.property("active")
            .isEqualTo(Cypher.literalOf(true))
    )
    .returning(person);

Node countPerson = Cypher.node("Person").named("p");

var countQuery = Cypher.match(countPerson)
    .where(
        countPerson.property("active")
            .isEqualTo(Cypher.literalOf(true))
    )
    .returning(Cypher.count(Cypher.asterisk()))
    .build();

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending().and(Sort.by("id").ascending())
);

Page<PersonNames> page = personRepository.findAll(
    pageQuery,
    countQuery,
    pageable,
    PersonNames.class
);
```

Trong ví dụ:

- `pageQuery` chứa phần `MATCH`, `WHERE` và `RETURN` của truy vấn chính.
- `countQuery` đếm tập node thỏa cùng điều kiện.
- `Pageable` cung cấp số trang, kích thước trang và thứ tự sắp xếp.
- `PersonNames.class` xác định projection của từng phần tử.

Truy vấn đếm cần phản ánh cùng điều kiện với truy vấn chính để tổng số phần tử của `Page` chính xác. Nếu statement có nhiều relationship khiến một node gốc xuất hiện trong nhiều dòng, hãy xác định rõ đang phân trang theo dòng, relationship hay node duy nhất và điều chỉnh cả truy vấn chính lẫn truy vấn đếm.

Với `CypherdslConditionExecutor`, có thể truyền `Pageable` trực tiếp vào `findAll(condition, pageable)` khi muốn SDN tạo truy vấn domain đầy đủ và thêm điều kiện động. Với `CypherdslStatementExecutor`, ứng dụng kiểm soát statement và cung cấp count query riêng cho overload phân trang.

## 11. Static metamodel để giảm tên property dạng chuỗi

Trong ví dụ cơ bản, label, relationship type và property thường được khai báo bằng chuỗi như `"Person"`, `"MEMBER_OF"` hoặc `"firstName"`. Cypher-DSL vẫn kiểm tra cấu trúc cú pháp của statement, nhưng không thể tự biết một property được viết sai tên có tồn tại trong graph hay không.

Nếu muốn kiểm tra tên property tốt hơn ở thời điểm biên dịch, có thể dùng static metamodel. Cypher-DSL cung cấp annotation processor cho các entity Spring Data Neo4j được đánh dấu bằng `@Node` và `@RelationshipProperties`. Processor tạo các lớp metamodel dựa trên mapping của entity, từ đó giúp truy vấn tham chiếu property và relationship theo mô hình Java.

Static metamodel là tùy chọn. Với truy vấn đơn giản, dùng chuỗi tên trực tiếp vẫn hợp lệ. Với dự án lớn có nhiều truy vấn và refactor entity thường xuyên, metamodel có thể giảm lỗi đánh máy và giúp IDE hỗ trợ điều hướng tốt hơn.

Hãy cấu hình processor theo tài liệu của phiên bản Cypher-DSL và SDN đang dùng, thường ở annotation processor path thay vì đóng gói processor như dependency runtime. Không nên tự chọn một phiên bản processor khác với dependency Cypher-DSL mà dự án đang quản lý.

## 12. AST bất biến và cách tổ chức hàm hỗ trợ

Cypher-DSL xây dựng AST và các bước trung gian theo hướng bất biến. Các thao tác builder tạo ra bước mới thay vì sửa trực tiếp đối tượng cũ. Vì vậy, hãy luôn tiếp tục từ giá trị trả về của lời gọi builder.

Ví dụ:

```java
var query = Cypher.match(person)
    .where(condition)
    .returning(person);

var statement = query
    .orderBy(person.property("name").ascending())
    .build();
```

Không nên gọi một phương thức builder rồi bỏ qua giá trị trả về nếu bước tiếp theo cần dùng kết quả mới. Hãy dùng biến trung gian hoặc nối chuỗi để thể hiện rõ luồng xây dựng.

Một cách tổ chức code dễ bảo trì:

| Thành phần | Trách nhiệm |
| --- | --- |
| Pattern factory | Tạo node và relationship pattern |
| Condition helper | Tạo các điều kiện lọc có thể kết hợp |
| Sort helper | Định nghĩa thứ tự dùng chung |
| Query factory | Ghép pattern, condition, projection và tạo statement |
| Repository | Thực thi statement hoặc condition bằng SDN executor |
| Service | Chọn bộ lọc theo nghiệp vụ và gọi repository |

Không nên biến mọi đoạn Cypher thành một hàm nhỏ nếu chúng chỉ được dùng một lần và không có ý nghĩa riêng. Hãy tách thành phần khi nó có khả năng tái sử dụng, có quy tắc nghiệp vụ rõ ràng hoặc giúp một truy vấn dài dễ đọc hơn.

## 13. Chọn executor phù hợp

Spring Data Neo4j cung cấp hai mixin Cypher-DSL với mục tiêu khác nhau:

| Tiêu chí | `CypherdslConditionExecutor` | `CypherdslStatementExecutor` |
| --- | --- | --- |
| Truy vấn nền | SDN tự tạo theo domain entity | Ứng dụng tự xây dựng statement |
| Phần tùy chỉnh | Condition và thứ tự | Pattern, điều kiện, projection và thứ tự |
| Kết quả | Domain type của repository | Domain type hoặc projection class |
| Phân trang | Có overload nhận `Pageable` | Có overload nhận statement, count query và `Pageable` |
| Phù hợp khi | Chỉ cần lọc động trên entity mapping | Cần kiểm soát đầy đủ cấu trúc graph hoặc projection |

Nếu dùng repository reactive, hãy mở rộng bằng `ReactiveCypherdslConditionExecutor` hoặc `ReactiveCypherdslStatementExecutor` tương ứng với loại truy vấn. Không dùng imperative executor trên `ReactiveNeo4jRepository`.

Một statement Cypher-DSL cũng có thể được truyền trực tiếp vào `Neo4jTemplate` hoặc `ReactiveNeo4jTemplate` ở các phiên bản SDN hỗ trợ, nếu ứng dụng cần điều khiển truy vấn ở tầng template thay vì repository.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nối chuỗi để tạo điều kiện Cypher | Dễ lỗi cú pháp và khó quản lý đầu vào | Tạo `Condition` và dùng tham số |
| Lặp lại cùng một điều kiện ở nhiều truy vấn | Khó sửa khi nghiệp vụ thay đổi | Tách hàm hỗ trợ trả về `Condition` |
| Dùng chung alias node không phù hợp giữa các pattern | Symbolic name có thể trùng hoặc khó đọc | Tạo node theo từng statement và đặt alias rõ |
| Gắn giá trị trực tiếp vào chuỗi Cypher | Tăng nguy cơ injection | Dùng `Cypher.parameter` hoặc `Cypher.anonParameter` |
| Dùng `ConditionExecutor` khi cần projection tùy chỉnh | Executor chỉ trả domain type | Chọn `CypherdslStatementExecutor` |
| Dùng `StatementExecutor` nhưng trả thiếu node hoặc relationship cần ánh xạ | SDN không đủ dữ liệu để dựng kết quả mong muốn | Trả về các phần tử cần cho mapping/projection |
| Sắp xếp theo property không có trong domain | Có thể tạo truy vấn sai hoặc không đúng ý | Kiểm tra property và cân nhắc static metamodel |
| Phân trang qua relationship một-nhiều mà không xử lý dòng trùng | Một node gốc có thể chiếm nhiều vị trí | Xác định đơn vị phân trang và xây dựng count query tương ứng |
| Dùng imperative mixin trong reactive repository | Không khớp mô hình thực thi | Dùng reactive executor tương ứng |
| Bỏ qua giá trị trả về từ builder | Statement cuối không chứa bước vừa xây dựng | Tiếp tục từ đối tượng builder mới |

## 15. Câu hỏi tự kiểm tra

1. Cypher-DSL biểu diễn câu truy vấn bằng cấu trúc dữ liệu nào?
2. `Node`, `Relationship`, `Property` và `Condition` có vai trò gì?
3. Vì sao nên tách điều kiện thành hàm trả về `Condition`?
4. `Cypher.parameter()` khác việc nối giá trị trực tiếp vào chuỗi truy vấn như thế nào?
5. Khi nào nên dùng `CypherdslConditionExecutor`?
6. Khi nào cần `CypherdslStatementExecutor`?
7. Projection class được truyền vào overload `findAll(statement, projectionClass)` có tác dụng gì?
8. `SortItem` được tạo từ property như thế nào?
9. Overload phân trang của `CypherdslStatementExecutor` cần những thành phần nào?
10. Vì sao static metamodel hữu ích khi entity có nhiều property và truy vấn?
11. Tại sao cần tiếp tục từ giá trị trả về của mỗi bước builder?
12. Khi repository reactive, cần chọn executor nào?

## Tài liệu tham khảo

- [Spring Data Neo4j – Repository extensions và Cypher-DSL](https://docs.spring.io/spring-data/neo4j/reference/repositories/sdn-extension.html)
- [CypherdslConditionExecutor API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/CypherdslConditionExecutor.html)
- [CypherdslStatementExecutor API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/CypherdslStatementExecutor.html)
- [The Neo4j Cypher-DSL Manual](https://neo4j.github.io/cypher-dsl/2025.2.6/)

## Kết luận

Cypher-DSL giúp xây dựng truy vấn Neo4j bằng các thành phần Java có thể kết hợp và tái sử dụng. Tách node pattern, relationship, property, condition và sort item thành hàm hỗ trợ giúp giảm lặp, giữ truy vấn dễ đọc và truyền tham số an toàn.

Trong Spring Data Neo4j, `CypherdslConditionExecutor` phù hợp khi muốn bổ sung điều kiện vào truy vấn domain do SDN tạo. `CypherdslStatementExecutor` phù hợp khi cần kiểm soát toàn bộ statement, trả về projection hoặc phân trang với count query. Hãy chọn executor theo mức độ tùy biến, dùng đúng kiểu sắp xếp, trả đủ dữ liệu cho mapping và tổ chức các builder bất biến theo cách dễ kiểm tra.
