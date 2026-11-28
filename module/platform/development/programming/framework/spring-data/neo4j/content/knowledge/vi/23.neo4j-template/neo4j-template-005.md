# saveAs và fluent save để giới hạn dữ liệu được ghi

Trong Spring Data Neo4j (SDN), lệnh **save(entity)** lưu entity cùng các entity liên quan theo mapping. Cách này phù hợp khi ứng dụng muốn đồng bộ toàn bộ phần graph mà entity đại diện. Nhưng có những thao tác chỉ cần ghi một vài thuộc tính hoặc một nhánh quan hệ. Nếu vẫn dùng **save(entity)** với một object chỉ chứa một phần dữ liệu, ứng dụng có thể vô tình ghi một trạng thái graph không đầy đủ.

**Neo4jTemplate** cung cấp hai cách giới hạn phạm vi ghi: **saveAs(...)** dùng projection tĩnh hoặc predicate động để chọn property và relationship; fluent save bắt đầu bằng **save(DomainType.class)** rồi nhận một entity hoặc projection qua **one(...)** hay **all(...)**. Các API này giúp mô tả rõ phần graph được ghi trong từng use case.

## Mô hình ví dụ

Giả sử ứng dụng quản lý nhân viên. Một người có mã định danh, họ tên, email, trạng thái, phòng ban và danh sách kỹ năng:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;
    private String email;
    private Boolean active;

    @Relationship(type = "WORKS_IN")
    private Department department;

    @Relationship(type = "HAS_SKILL")
    private Set<Skill> skills = new LinkedHashSet<>();

    protected Person() {
    }

    public Person(String employeeCode, String fullName, String email) {
        this.employeeCode = employeeCode;
        this.fullName = fullName;
        this.email = email;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public Boolean getActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }

    public Set<Skill> getSkills() {
        return skills;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }

    public void setDepartment(Department department) {
        this.department = department;
    }

    public void setSkills(Set<Skill> skills) {
        this.skills = skills;
    }
}
~~~

Hai entity được tham chiếu:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Department")
public class Department {

    @Id
    private String code;

    private String name;

    protected Department() {
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Skill")
public class Skill {

    @Id
    private String code;

    private String name;

    protected Skill() {
    }
}
~~~

Với entity này, **neo4jTemplate.save(person)** có thể lưu các property của Person và các entity liên quan qua **department** và **skills**. Nếu use case chỉ đổi email, việc ghi cả graph có thể không cần thiết. Nếu use case chỉ cập nhật Person và Department, danh sách Skill có thể nằm ngoài phạm vi thay đổi.

## save(entity) và saveAs(entity, projectionType)

**save(entity)** lưu một instance cùng các entity liên quan được mapping. API này thể hiện ý định lưu entity graph theo mô hình đầy đủ:

~~~java
Person saved = neo4jTemplate.save(person);
~~~

**saveAs(entity, projectionType)** nhận entity nguồn và một kiểu projection. Projection xác định các property và relationship được SDN đưa vào thao tác lưu. Ví dụ projection chỉ gồm mã, họ tên và email:

~~~java
public record PersonContactProjection(
    String employeeCode,
    String fullName,
    String email
) {
}
~~~

Gọi **saveAs**:

~~~java
PersonContactProjection savedProjection =
    neo4jTemplate.saveAs(person, PersonContactProjection.class);
~~~

Các tên thuộc tính trong projection phải khớp với property của entity nguồn. Trong ví dụ, projection bao gồm **employeeCode**, **fullName** và **email**; các property **active**, **department** và **skills** không thuộc projection này. Vì vậy, thao tác được giới hạn theo phần dữ liệu đã khai báo trong projection.

Projection có thể là interface hoặc DTO. Interface projection khai báo getter cho property cần đưa vào:

~~~java
public interface PersonContactView {

    String getEmployeeCode();

    String getFullName();

    String getEmail();
}
~~~

Sau đó dùng chính kiểu interface làm projection:

~~~java
PersonContactView savedView =
    neo4jTemplate.saveAs(person, PersonContactView.class);
~~~

Với class-based projection, DTO hoặc record cần khai báo các property có tên tương ứng với entity. Với interface projection, tên getter phải ánh xạ đúng property nguồn. Không thêm property tổng hợp không tồn tại trong entity nếu mục đích là dùng projection làm khuôn ghi.

## Projection nhiều cấp để ghi relationship

Projection không chỉ chọn property ở node gốc. Nó có thể mô tả các relationship và property của node liên quan. Giả sử thao tác cần cập nhật Person cùng phòng ban, nhưng không cần ghi danh sách Skill:

~~~java
public interface PersonWithDepartmentProjection {

    String getEmployeeCode();

    String getFullName();

    DepartmentProjection getDepartment();

    interface DepartmentProjection {
        String getCode();
        String getName();
    }
}
~~~

Dùng projection này khi lưu:

~~~java
PersonWithDepartmentProjection saved =
    neo4jTemplate.saveAs(
        person,
        PersonWithDepartmentProjection.class
    );
~~~

Projection có **department** nên SDN có thể xử lý relationship **WORKS_IN** và các property **code**, **name** của Department theo mapping. **skills** không xuất hiện trong projection nên nằm ngoài phạm vi cập nhật của thao tác này.

Nếu muốn cập nhật property của một entity liên quan, phải đưa relationship property đó vào projection. Chỉ đưa các trường của Person mà không có getter **getDepartment()** thì không mô tả nhánh Department cần lưu. Với relationship có **@RelationshipProperties**, cần tính cả entity relationship-properties vào cấu trúc projection nếu muốn ghi các property của chính relationship.

Projection nhiều cấp cũng có thể biểu diễn collection:

~~~java
import java.util.Set;

public interface PersonWithSkillsProjection {

    String getEmployeeCode();

    Set<SkillProjection> getSkills();

    interface SkillProjection {
        String getCode();
        String getName();
    }
}
~~~

Projection trên mô tả Person và nhánh **skills**. Khi dùng nó, hãy bảo đảm object nguồn chứa đầy đủ danh sách Skill cần giữ. Nếu collection mới chỉ được tải một phần, việc đồng bộ nhánh đó có thể làm mất các relationship không có trong object. Projection giới hạn phạm vi ghi, nhưng không tự biết dữ liệu nào bị bỏ sót trong collection mà bạn đã chọn đưa vào projection.

## saveAs với predicate động

Khi các field cần ghi thay đổi theo từng use case, có thể dùng overload **saveAs(entity, includeProperty)**. Tham số thứ hai là predicate nhận **PropertyPath** và **Neo4jPersistentProperty**; predicate quyết định property path nào được đưa vào graph được lưu. Cách này hoạt động như một dynamic projection.

Ví dụ chỉ ghi mã nhân viên, họ tên và email:

~~~java
import java.util.Set;

Set<String> allowedPaths = Set.of(
    "employeeCode",
    "fullName",
    "email"
);

Person saved = neo4jTemplate.saveAs(
    person,
    (path, property) -> allowedPaths.contains(path.toDotPath())
);
~~~

**path.toDotPath()** biểu diễn đường dẫn property theo dạng có dấu chấm. Vì vậy có thể chọn cả property lồng nhau:

~~~java
import java.util.Set;

Set<String> allowedPaths = Set.of(
    "employeeCode",
    "fullName",
    "department",
    "department.code",
    "department.name"
);

Person saved = neo4jTemplate.saveAs(
    person,
    (path, property) -> allowedPaths.contains(path.toDotPath())
);
~~~

Trong ví dụ thứ hai, predicate đưa vào property gốc **department** và các property của Department. Khi muốn ghi association, phải cho phép cả association property, không chỉ các property nằm bên trong node liên quan. Điều này giúp SDN biết nhánh quan hệ nào thuộc phạm vi ghi.

Có thể kiểm tra theo metadata thay vì chỉ dùng chuỗi:

~~~java
import java.util.Set;

Person saved = neo4jTemplate.saveAs(
    person,
    (path, property) ->
        property.isIdProperty()
            || Set.of("fullName", "email").contains(property.getName())
);
~~~

Ví dụ này luôn đưa ID vào phạm vi xử lý và chọn thêm hai property **fullName**, **email**. Khi dùng predicate theo tên property, cần chú ý các entity lồng nhau có thể có property trùng tên. Nếu cần phân biệt đường dẫn, kiểm tra **path.toDotPath()** thay vì chỉ **property.getName()**.

**saveAs** với predicate động phù hợp khi quy tắc chọn property phụ thuộc loại thao tác hoặc quyền cập nhật. Tuy nhiên, whitelist cần được quản lý tập trung và có test. Một predicate quá rộng có thể đưa trở lại những relationship mà use case muốn bỏ qua.

## Fluent save với domain type và projection

Fluent save API cho phép chỉ rõ domain type trước, sau đó thực thi việc lưu một projection hoặc một entity:

~~~java
PersonContactProjection contact = new PersonContactProjection(
    "E-01",
    "Lan Nguyen",
    "lan@example.test"
);

PersonContactProjection saved =
    neo4jTemplate.save(Person.class).one(contact);
~~~

**save(Person.class)** xác định kiểu domain mà projection thuộc về. **one(contact)** lưu đúng một instance. Kiểu projection cần có quan hệ hợp lệ với domain type, tức là projection của Person hoặc chính Person; truyền một kiểu không liên quan có thể tạo kết quả không xác định.

Fluent save cũng hỗ trợ lưu một tập instance:

~~~java
import java.util.List;

List<PersonContactProjection> contacts = List.of(
    new PersonContactProjection("E-01", "Lan Nguyen", "lan@example.test"),
    new PersonContactProjection("E-02", "Minh Tran", "minh@example.test")
);

List<PersonContactProjection> savedContacts =
    neo4jTemplate.save(Person.class).all(contacts);
~~~

Trong cả hai ví dụ, projection chứa ba property nên thao tác lưu theo projection đó. Fluent save không tự suy ra danh sách field cần giới hạn nếu bạn truyền entity đầy đủ. Muốn giới hạn dữ liệu ghi, hãy truyền projection phù hợp.

Lưu ý rằng kết quả **one(...)** hoặc **all(...)** có thể là object mới được tạo trong quá trình mapping. Hãy sử dụng instance được trả về sau khi lưu, đặc biệt khi SDN cập nhật ID được sinh hoặc tạo projection kết quả.

## Chọn giữa saveAs và fluent save

| Nhu cầu | API phù hợp | Ý nghĩa |
|---|---|---|
| Lưu entity cùng graph được mapping đầy đủ | **save(entity)** | Dùng toàn bộ entity graph |
| Lưu entity theo projection tĩnh | **saveAs(entity, Projection.class)** | Projection định nghĩa property và relationship |
| Chọn property bằng điều kiện động | **saveAs(entity, predicate)** | Predicate quyết định property path được đưa vào |
| Lưu một projection cho domain type đã biết | **save(Domain.class).one(projection)** | Fluent save cho một instance |
| Lưu nhiều projection cùng domain type | **save(Domain.class).all(projections)** | Fluent save theo lô |
| Lưu nhiều entity theo projection tĩnh | **saveAllAs(entities, Projection.class)** | Lưu tập entity theo projection |
| Lưu nhiều entity theo predicate động | **saveAllAs(entities, predicate)** | Lưu tập entity với cùng quy tắc chọn property |

Các overload **saveAs** và fluent save cùng sử dụng projection để định hình graph được ghi, nhưng điểm vào API khác nhau. **saveAs** nhận entity nguồn rồi chọn kiểu projection hoặc predicate. Fluent save bắt đầu bằng domain type rồi nhận projection/entity thông qua **one** hoặc **all**.

## Giới hạn dữ liệu tải và nguy cơ xóa relationship

Projection giới hạn các property và relationship được đưa vào thao tác ghi. Tuy nhiên, nó không thay thế việc quản lý đầy đủ dữ liệu của những nhánh mà bạn chọn cập nhật.

Giả sử database đang có:

~~~text
(Person E-01)
  ├──[:HAS_SKILL]──> (Java)
  ├──[:HAS_SKILL]──> (Cypher)
  └──[:HAS_SKILL]──> (Spring Data Neo4j)
~~~

Ứng dụng chỉ tải Person và hai trong ba Skill, nhưng lại dùng projection có **getSkills()** để lưu. SDN nhận collection trong projection như trạng thái của nhánh được quản lý. Relationship tới Skill chưa được tải có thể bị loại khỏi graph sau khi thao tác đồng bộ.

Vì vậy, cần tuân theo các nguyên tắc:

1. Chỉ đưa relationship vào projection khi use case thực sự muốn quản lý nhánh đó.
2. Nếu projection có collection relationship, tải đủ các phần tử cần được giữ trước khi lưu.
3. Nếu chỉ thay đổi một property ở node gốc, chọn projection không có relationship hoặc dùng predicate chỉ cho phép property đó.
4. Nếu cần cập nhật một node liên quan, đưa association và các property cần ghi vào projection.
5. Không dùng object projection đã bị giới hạn làm entity đầy đủ cho một lần **save()** tiếp theo.

Projection trả về thường không được hydrate đầy đủ như entity gốc. Đừng giữ một object projection rồi dùng nó như nguồn dữ liệu hoàn chỉnh cho thao tác ghi khác. Nếu nghiệp vụ cần chuyển sang một thao tác ghi rộng hơn, hãy đọc lại aggregate với đầy đủ relationship cần thiết hoặc xây dựng object nguồn từ dữ liệu đầy đủ.

## Transaction và ranh giới cập nhật

**Neo4jTemplate** tham gia transaction do Spring quản lý khi được gọi trong một phương thức **@Transactional** phù hợp. Có thể kết hợp nhiều thao tác có liên quan trong một transaction:

~~~java
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonUpdateService {

    private final Neo4jTemplate neo4jTemplate;

    public PersonUpdateService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    @Transactional
    public PersonContactProjection updateContact(Person person) {
        return neo4jTemplate.saveAs(
            person,
            PersonContactProjection.class
        );
    }
}
~~~

Transaction giúp các câu lệnh thuộc cùng transaction commit hoặc rollback cùng nhau. Nó không tự xác định property nào cần ghi và cũng không tự nạp các relationship còn thiếu. Việc chọn projection và bảo đảm dữ liệu nguồn đủ đầy vẫn là trách nhiệm của use case.

Với các thay đổi đồng thời, projection hẹp có thể giúp giảm phạm vi dữ liệu bị tác động, nhưng không thay thế cơ chế xử lý xung đột. Nếu nhiều request cập nhật cùng một node hoặc relationship, hãy cân nhắc optimistic locking, kiểm tra version hoặc quy tắc đồng bộ phù hợp với mô hình.

## Phiên bản API cần biết

Các API projection-based save được bổ sung qua nhiều phiên bản SDN:

| API | Phiên bản bắt đầu |
|---|---|
| **saveAs(entity, Projection.class)** | SDN 6.1 |
| Fluent save **save(Domain.class).one(...)** và **.all(...)** | SDN 6.1.3 |
| **saveAllAs(entities, Projection.class)** | SDN 6.1 |
| **saveAs(entity, predicate)** | SDN 6.3 |
| **saveAllAs(entities, predicate)** | SDN 6.3 |

Khi dự án dùng phiên bản cũ hơn, kiểm tra API của **Neo4jTemplate** và **Neo4jOperations** đã resolve trước khi sử dụng các overload này. Không tự nâng riêng một module Spring Data nếu chưa xác nhận tương thích với Spring Boot và các module Spring Data khác.

Tài liệu API chính thức:

- [Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Neo4jOperations API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jOperations.html)
- [Spring Data Neo4j Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi **save(entity)** khi chỉ muốn ghi vài property | Toàn bộ graph được mapping có thể tham gia đồng bộ | Dùng **saveAs** hoặc fluent save với projection hẹp |
| Projection dùng tên getter không khớp property entity | SDN không ánh xạ được property mong muốn | Đặt tên getter theo đúng property nguồn |
| Muốn ghi Department nhưng projection chỉ có property Person | Relationship và node liên quan không thuộc phạm vi projection | Thêm getter association và projection lồng nhau |
| Predicate chỉ cho phép property con mà bỏ association gốc | Nhánh relationship không được đưa vào phạm vi ghi như dự định | Cho phép cả association property |
| Dùng collection relationship đã tải một phần trong projection ghi | Có thể làm mất các liên kết chưa được tải | Tải đủ nhánh trước khi lưu hoặc loại nhánh khỏi projection |
| Dùng projection trả về như entity đầy đủ | Lần save sau có thể ghi thiếu dữ liệu | Đọc lại aggregate đầy đủ trước thao tác ghi rộng |
| Fluent save truyền kiểu không thuộc domain | Kết quả mapping có thể không xác định | Dùng domain type và projection có quan hệ đúng |
| Không dùng object trả về từ save | Bỏ qua ID hoặc dữ liệu được SDN cập nhật trong kết quả | Tiếp tục với instance được trả về |
| Dùng predicate quá rộng | Nhiều property/relationship ngoài dự định bị ghi | Dùng whitelist path và kiểm thử từng use case |

## Bài tập thực hành

Với entity Person có **employeeCode**, **fullName**, **email**, **department** và **skills**, hãy thực hiện:

1. Lưu một Person đầy đủ bằng **neo4jTemplate.save(person)** và xác định các node, relationship được ghi.
2. Tạo projection chỉ có **employeeCode**, **fullName**, **email**.
3. Dùng **saveAs(person, PersonContactProjection.class)** và giải thích phần graph thuộc phạm vi projection.
4. Tạo projection nhiều cấp gồm **department.code** và **department.name**.
5. Dùng predicate động để chỉ cho phép **employeeCode**, **fullName** và **email**.
6. Dùng fluent save với **neo4jTemplate.save(Person.class).one(projection)**.
7. Lưu một collection projection bằng **.all(...)** và so sánh với **saveAllAs(...)**.
8. Tạo một Person có ba Skill nhưng chỉ tải hai Skill; thử lưu projection có **skills** trên database kiểm thử và quan sát tác động.
9. Viết test xác nhận projection không chứa **skills** không đưa nhánh đó vào thao tác ghi.
10. Viết test xác nhận projection có **skills** phải nhận đầy đủ các liên kết cần giữ.

**saveAs** và fluent save giúp định nghĩa ranh giới graph được ghi bằng projection tĩnh hoặc predicate động. Hãy chọn property và relationship theo đúng use case, bảo đảm tải đủ dữ liệu cho mọi nhánh được đưa vào projection và dùng object trả về sau khi lưu. Cách làm này giúp thao tác ghi có phạm vi rõ ràng, giảm việc truyền và đồng bộ những phần graph không cần thiết.

