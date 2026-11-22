# Kết hợp EntityGraph với phương thức truy vấn phù hợp trong Spring Data JPA

Trong Spring Data JPA, phương thức truy vấn quyết định entity nào được chọn, còn fetch plan quyết định những association nào được tải cùng entity đó. Nếu mọi association đều để LAZY, ứng dụng có thể gặp N+1 khi đọc nhiều entity rồi truy cập quan hệ. Nếu đặt EAGER rộng khắp, những truy vấn không cần dữ liệu liên quan vẫn có thể tải quá nhiều.

EntityGraph cho phép khai báo fetch plan theo từng use case. Có thể gắn graph vào derived query method hoặc method dùng @Query trong repository. Nhờ đó, cùng một entity có thể được tải với các association khác nhau tùy màn hình hoặc thao tác.

Bài học này trình bày named entity graph, dynamic graph qua attributePaths, FETCH và LOAD semantics, nested subgraph, cách kết hợp với các loại repository method, giới hạn khi dùng projection/native query/phân trang collection, và cách kiểm thử fetch plan.

## 1. EntityGraph giải quyết vấn đề gì?

Giả sử entity Employee có quan hệ to-one tới Department và quan hệ to-many tới Assignment. Assignment lại tham chiếu Project.

Một truy vấn chỉ cần tên nhân viên có thể không cần tải Department, Assignment hoặc Project. Nhưng trang hồ sơ nhân viên có thể cần Department cùng các Assignment và Project tương ứng.

Nếu luôn tải mọi association, query đơn giản cũng có thể trở nên nặng. Nếu luôn để LAZY, code đọc hồ sơ có thể tạo thêm nhiều query.

EntityGraph mô tả những thuộc tính cần được fetch cho một truy vấn cụ thể:

- Query A: Employee cùng Department.
- Query B: Employee cùng Department, Assignments và Project của từng Assignment.
- Query C: chỉ Employee, không cần association nào thêm.

Fetch plan được chọn tại repository method hoặc khi tạo query bằng EntityManager. EntityGraph không thay đổi điều kiện WHERE, thứ tự, hay ý nghĩa nghiệp vụ của bộ lọc.

## 2. Phân biệt predicate và fetch plan

Một repository query có nhiều khía cạnh độc lập:

| Thành phần | Câu hỏi cần trả lời | Công cụ |
|---|---|---|
| Predicate | Chọn Employee nào? | Derived query, JPQL, Criteria, Specification |
| Fetch plan | Cần tải Department/Assignments/Project nào? | EntityGraph, fetch join, batch fetching |
| Projection | Cần trả những trường nào? | DTO hoặc interface projection |
| Pagination | Lấy trang nào và tổng số bao nhiêu? | Pageable, Page/Slice, count query |

Ví dụ:

~~~java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.department.name = :departmentName
       """)
List<Employee> findActiveByDepartmentName(
        @Param("departmentName") String departmentName);
~~~

Query trên chọn nhân viên đang hoạt động thuộc một phòng ban. Nếu cần tải Department cùng Employee, có thể gắn EntityGraph vào method. Predicate vẫn giữ nguyên; graph chỉ bổ sung yêu cầu tải association.

Không dùng EntityGraph như một cách viết điều kiện lọc. Graph không thể thay thế WHERE, JOIN predicate hoặc EXISTS.

## 3. Mô hình entity dùng trong bài

Các ví dụ sau dùng cùng một mô hình trong package com.example.employee. Employee có Department và danh sách Assignment; mỗi Assignment tham chiếu một Project.

Entity Department:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity Project:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "projects")
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Project() {
    }

    public Project(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity Assignment là phần tử của collection:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "assignments")
public class Assignment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "employee_id", nullable = false)
    private Employee employee;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(nullable = false, length = 80)
    private String role;

    protected Assignment() {
    }

    public Assignment(Employee employee, Project project, String role) {
        this.employee = employee;
        this.project = project;
        this.role = role;
    }

    public Long getId() {
        return id;
    }

    public Employee getEmployee() {
        return employee;
    }

    public Project getProject() {
        return project;
    }

    public String getRole() {
        return role;
    }
}
~~~

Entity Employee khai báo named graph:

~~~java
package com.example.employee;

import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "Employee.withDepartment",
        attributeNodes = @NamedAttributeNode("department")
    ),
    @NamedEntityGraph(
        name = "Employee.detail",
        attributeNodes = {
            @NamedAttributeNode("department"),
            @NamedAttributeNode(
                value = "assignments",
                subgraph = "assignment-project"
            )
        },
        subgraphs = @NamedSubgraph(
            name = "assignment-project",
            attributeNodes = @NamedAttributeNode("project")
        )
    )
})
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, unique = true, length = 200)
    private String email;

    @Column(nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @OneToMany(mappedBy = "employee", fetch = FetchType.LAZY)
    private List<Assignment> assignments = new ArrayList<>();

    protected Employee() {
    }

    public Employee(
            String name,
            String email,
            boolean active,
            Department department) {
        this.name = name;
        this.email = email;
        this.active = active;
        this.department = department;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }

    public List<Assignment> getAssignments() {
        return assignments;
    }
}
~~~

Các association được khai báo LAZY để mô tả nhu cầu tải theo từng query. EntityGraph ở Employee cung cấp hai graph đã đặt tên: graph chỉ tải Department và graph tải Department cùng Assignments/Project.

Trong ứng dụng thật, cần bổ sung phương thức quản lý hai chiều association nếu domain cần thêm/xóa Assignment. Các ví dụ đọc bên dưới chỉ cần mapping và getter đã khai báo.

Lưu ý: LAZY trên quan hệ to-one là gợi ý cho provider theo JPA; provider có thể tải sớm hơn trong một số trường hợp. Quan hệ to-many mặc định LAZY. EntityGraph giúp chỉ định dữ liệu tối thiểu cần được tải cho một thao tác, nhưng không phải cam kết rằng SQL chỉ lấy đúng các cột/association đã liệt kê.

## 4. Named EntityGraph là gì?

Named EntityGraph là fetch plan được khai báo trước bằng annotation @NamedEntityGraph trên entity hoặc bằng metadata XML.

Ví dụ graph đơn giản:

~~~java
@NamedEntityGraph(
    name = "Employee.withDepartment",
    attributeNodes = @NamedAttributeNode("department")
)
~~~

Tên graph là Employee.withDepartment. Attribute node department tham chiếu tên thuộc tính Java trong entity, không phải tên cột department_id.

Graph detail có thêm collection và nested subgraph:

~~~java
@NamedEntityGraph(
    name = "Employee.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(
            value = "assignments",
            subgraph = "assignment-project"
        )
    },
    subgraphs = @NamedSubgraph(
        name = "assignment-project",
        attributeNodes = @NamedAttributeNode("project")
    )
)
~~~

Cách đọc:

1. Tải Employee.
2. Tải Department của Employee.
3. Tải collection assignments.
4. Với mỗi Assignment, tải Project.

Subgraph cho phép khai báo sâu hơn trên association hoặc embedded attribute. Nếu cần tải thuộc tính lồng nhau nhiều cấp, có thể khai báo subgraph tiếp theo tương ứng.

Named graph được đăng ký trong persistence unit và có thể tái sử dụng ở nhiều repository method hoặc EntityManager query. Tên graph phải duy nhất trong persistence unit.

## 5. Attribute node và subgraph

Attribute node xác định thuộc tính cần fetch trực tiếp từ entity gốc. Với association to-one, node tải entity liên quan; với collection, node tải collection và phần tử theo graph.

Subgraph mô tả graph tiếp theo cho loại đích của association:

~~~java
@NamedAttributeNode(
    value = "assignments",
    subgraph = "assignment-project"
)
~~~

Tên assignment-project trỏ tới:

~~~java
@NamedSubgraph(
    name = "assignment-project",
    attributeNodes = @NamedAttributeNode("project")
)
~~~

Trong subgraph của Assignment, project là thuộc tính của Assignment. Không viết đường dẫn assignments.project bên trong @NamedSubgraph; subgraph đã xác định ngữ cảnh entity Assignment.

Các tên node phải khớp thuộc tính persistent của entity tương ứng. Sai tên thường được phát hiện khi provider khởi tạo hoặc sử dụng graph.

Không cần thêm mọi association vào graph. Graph quá rộng có thể tải nhiều collection, tạo SQL lớn, tăng bộ nhớ và gây chi phí hydrate không cần thiết.

## 6. FETCH graph và LOAD graph

JPA định nghĩa hai loại EntityGraph:

- **FETCH graph:** các thuộc tính được chỉ định trong graph được xem là EAGER cho lần tải này; các thuộc tính không được chỉ định được xem là LAZY.
- **LOAD graph:** các thuộc tính được chỉ định được xem là EAGER; các thuộc tính không được chỉ định giữ theo fetch mapping của entity.

Trong cả hai trường hợp, provider vẫn có thể tải thêm dữ liệu ngoài graph nếu cần để thực hiện query hoặc theo yêu cầu triển khai. Graph xác định những gì phải được fetch, không phải cam kết SQL chỉ tải đúng các thuộc tính được liệt kê.

Ví dụ FETCH:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<Employee> findByEmail(String email);
~~~

FETCH phù hợp khi method cần một fetch plan cụ thể cho use case, và muốn các thuộc tính khác được xem là LAZY trong lần tải đó.

Ví dụ LOAD:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.LOAD
)
Optional<Employee> findByEmail(String email);
~~~

LOAD thêm Department vào fetch plan, còn các thuộc tính khác tiếp tục theo mapping fetch type của entity. Nếu một association được mapping EAGER, LOAD graph không biến nó thành LAZY chỉ vì graph không liệt kê nó.

Trong Spring Data JPA, EntityGraphType mặc định là FETCH nếu không chỉ định type. Hãy ghi rõ type khi muốn người đọc hiểu chủ đích fetch plan.

## 7. Gắn named graph vào derived query method

Spring Data JPA cung cấp annotation org.springframework.data.jpa.repository.EntityGraph cho repository method.

Repository:

~~~java
package com.example.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findByEmail(String email);

    @EntityGraph(
        value = "Employee.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findDetailedById(Long id);

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.LOAD
    )
    List<Employee> findByActiveTrue();
}
~~~

Method findByEmail là derived query. Spring Data tạo predicate theo tên method, đồng thời áp dụng named graph Employee.withDepartment làm fetch plan.

findDetailedById dùng named graph detail. findByActiveTrue tìm các Employee có active = true và áp dụng graph Department theo LOAD semantics.

EntityGraph không thay đổi giá trị điều kiện. Nếu bỏ annotation khỏi findByEmail, query vẫn tìm cùng Employee nhưng fetch plan có thể khác.

## 8. Dùng dynamic graph qua attributePaths

Nếu chỉ cần một graph dùng tại một method, không nhất thiết khai báo named graph trên entity. Có thể dùng attributePaths:

~~~java
@EntityGraph(attributePaths = {"department"})
Optional<Employee> findByEmail(String email);
~~~

Với path lồng nhau:

~~~java
@EntityGraph(attributePaths = {
    "department",
    "assignments.project"
})
Optional<Employee> findDetailedById(Long id);
~~~

Spring Data xây dựng ad hoc entity graph từ các đường dẫn thuộc tính được khai báo. Dạng này thường được gọi là dynamic EntityGraph trong ngữ cảnh repository method.

Khi attributePaths được cung cấp, Spring Data xem đó là graph được tạo động; tên named graph trong value không còn là nguồn graph được sử dụng. Vì vậy, nên chọn một cách rõ ràng:

- Dùng value để tham chiếu named graph đã khai báo.
- Dùng attributePaths để tạo graph riêng cho method.

Không cần vừa khai báo value vừa attributePaths với kỳ vọng hai graph được cộng lại.

Đường dẫn dùng tên thuộc tính Java. Ví dụ assignments.project đi từ Employee tới collection assignments, rồi tới thuộc tính project của Assignment.

## 9. Nested attribute path và giới hạn đường dẫn

Với dynamic graph, Spring Data hỗ trợ path dạng dot notation để biểu diễn association lồng nhau:

~~~java
@EntityGraph(attributePaths = {
    "department",
    "assignments.project"
})
List<Employee> findByDepartment_Name(String departmentName);
~~~

Method này minh họa việc kết hợp predicate đi qua Department với fetch graph tải Department và Project của các Assignment.

Đường dẫn phải hợp lệ theo mô hình entity. Nếu thuộc tính là embedded object, có thể dùng path lồng nhau tương ứng. Với association collection, hãy cân nhắc kích thước collection và số tầng graph.

Một graph nhiều tầng có thể tạo nhiều SQL join hoặc nhiều truy vấn phụ tùy provider. Không giả định mỗi graph luôn tương ứng một câu SQL duy nhất.

## 10. Kết hợp EntityGraph với @Query

EntityGraph cũng có thể gắn vào repository method có @Query. JPQL chịu trách nhiệm lọc, graph chịu trách nhiệm tải association.

~~~java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.department.name = :departmentName
       """)
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.FETCH
)
List<Employee> findActiveByDepartmentName(
        @Param("departmentName") String departmentName);
~~~

JPQL không cần viết join fetch e.department vì graph đã mô tả fetch plan. Predicate vẫn có thể tham chiếu e.department.name để lọc theo phòng ban.

Nếu query cần JOIN để lọc nhưng không muốn tải association, có thể viết JOIN thông thường trong JPQL và không đưa association vào graph. Nếu cần tải, graph có thể bổ sung fetch plan.

Tránh vừa viết join fetch e.department trong JPQL vừa khai báo graph cùng association chỉ để tải lại cùng dữ liệu. Cách kết hợp dư thừa có thể khiến query khó đọc và phụ thuộc provider.

## 11. EntityGraph không thay thế JOIN hoặc EXISTS để lọc

Ví dụ graph:

~~~java
@EntityGraph(attributePaths = {"department"})
List<Employee> findByActiveTrue();
~~~

Graph không có nghĩa "chỉ lấy Employee có Department". Nó yêu cầu tải Department cho Employee được tìm thấy. Employee có department null vẫn có thể được trả về nếu predicate không loại bỏ nó.

Nếu muốn chỉ lấy Employee thuộc phòng ban có tên Engineering, phải có predicate:

~~~java
List<Employee> findByActiveTrueAndDepartment_Name(String name);
~~~

Hoặc dùng @Query với điều kiện WHERE tương ứng.

Tương tự, nếu muốn tìm Employee có ít nhất một Assignment thuộc Project cụ thể, cần predicate bằng join/exists/Specification. Đưa assignments.project vào graph chỉ tải dữ liệu liên quan, không tự lọc Employee theo Project.

## 12. EntityGraph và kiểu trả về repository

EntityGraph thường phù hợp nhất với method trả về entity hoặc collection entity:

| Kiểu trả về | Cách sử dụng |
|---|---|
| Optional<Employee> | Tải tối đa một Employee cùng association |
| Employee | Tải một Employee theo hợp đồng method |
| List<Employee> | Tải danh sách Employee cùng graph |
| Page<Employee> | Có thể dùng graph; đặc biệt cẩn thận nếu graph chứa collection |
| Slice<Employee> | Có thể dùng graph; vẫn phải xem tác động của collection fetch |
| DTO projection | Graph thường không cần thiết vì query chỉ lấy projection |
| Scalar value | EntityGraph không có association entity gốc để tải |

Với projection, chỉ chọn những trường cần dùng. Không dựa vào EntityGraph để ép tải association cho một DTO constructor expression hoặc scalar query; fetch plan có ý nghĩa rõ nhất khi kết quả là entity.

Với native query, cách áp dụng graph và mapping kết quả có thể phụ thuộc provider. Không giả định EntityGraph sẽ tự thay đổi SQL native hoặc tự hydrate collection; nếu cần native SQL, hãy kiểm tra hỗ trợ của provider và kiểm thử mapping thực tế.

## 13. EntityGraph với Page và Pageable

Có thể gắn graph vào method trả Page:

~~~java
@EntityGraph(attributePaths = {"department"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

Department là quan hệ to-one nên thường không nhân số dòng Employee nếu mapping cardinality đúng. Đây là trường hợp thường phù hợp với phân trang.

Cẩn thận khi graph chứa collection:

~~~java
@EntityGraph(attributePaths = {"assignments"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

Provider có thể tải collection bằng JOIN. Một Employee có nhiều Assignment tạo nhiều dòng SQL; giới hạn kết quả ở database có thể không còn tương ứng số Employee. Hibernate có thể phải phân trang trong bộ nhớ hoặc cảnh báo tùy phiên bản/cấu hình.

EntityGraph không bảo đảm collection pagination an toàn. Nếu cần Page Employee cùng toàn bộ Assignment, cân nhắc:

1. Phân trang ID Employee trước.
2. Tải Employee cùng Assignment cho tập ID đó bằng truy vấn riêng không Pageable.
3. Khôi phục thứ tự ID của trang.

Nếu UI chỉ cần số Assignment, dùng DTO projection với count aggregate thay vì fetch cả collection.

## 14. EntityGraph và count query

Page<T> có thể cần content query và count query. Count query chỉ cần đếm root entity phù hợp; không cần tải Department, Assignment hoặc Project.

EntityGraph là fetch plan cho việc đọc entity. Không thêm association fetch vào count query bằng cách viết JPQL fetch join trong count query. Với query phân trang có graph collection, hãy kiểm tra SQL content và count riêng biệt.

Nếu content query có filter qua collection, count query phải giữ predicate tương đương. Ví dụ tìm Employee có ít nhất một Assignment cho Project:

~~~java
@Query(
    value = """
            select e
            from Employee e
            where exists (
                select a.id
                from Assignment a
                where a.employee = e
                  and a.project.id = :projectId
            )
            """,
    countQuery = """
            select count(e)
            from Employee e
            where exists (
                select a.id
                from Assignment a
                where a.employee = e
                  and a.project.id = :projectId
            )
            """
)
Page<Employee> findPageByProject(
        @Param("projectId") Long projectId,
        Pageable pageable);
~~~

Có thể gắn graph Department vào method nếu cần tải Department cho content entity. Predicate EXISTS vẫn giữ nguyên và count query đếm Employee theo cùng điều kiện.

## 15. EntityGraph với to-one và to-many

Quan hệ to-one:

- @ManyToOne
- @OneToOne

Thông thường mỗi root entity liên kết tối đa một entity đích. Fetch graph to-one ít có nguy cơ nhân dòng root hơn.

Quan hệ to-many:

- @OneToMany
- @ManyToMany

Một root có thể có nhiều phần tử liên quan. Fetch graph collection có thể tạo nhiều dòng SQL cho một root và làm tăng dữ liệu truyền/hydrate.

Nếu graph tải nhiều collection, chi phí có thể tăng theo tích số phần tử. Hibernate còn có thể gặp MultipleBagFetchException khi fetch đồng thời nhiều bag collection trong một query.

Không thêm mọi collection vào graph detail chỉ vì có thể. Tạo graph theo nhu cầu màn hình và cân nhắc batch fetching hoặc query riêng.

## 16. EntityGraph và N+1

N+1 xảy ra khi ứng dụng tải N entity gốc rồi phát sinh thêm một query cho mỗi entity khi truy cập association LAZY.

Ví dụ:

~~~java
List<Employee> employees = repository.findByActiveTrue();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
~~~

Nếu Department chưa được tải và provider không thể gom truy vấn, vòng lặp có thể tạo thêm nhiều SQL.

Dùng EntityGraph:

~~~java
@EntityGraph(attributePaths = "department")
List<Employee> findByActiveTrue();
~~~

Graph yêu cầu Department được tải trong fetch plan của query. Provider có thể dùng join hoặc chiến lược khác, nhưng ứng dụng không còn phụ thuộc vào việc truy cập từng Department mới tải.

EntityGraph giúp kiểm soát fetch plan cho association được chỉ định; nó không bảo đảm mọi N+1 đều biến mất. Nếu vòng lặp truy cập thêm assignments.project mà graph chỉ có Department, các association còn lại vẫn có thể tạo query bổ sung.

Kiểm tra SQL thực tế và số statement để xác nhận hiệu quả.

## 17. EntityGraph so với JOIN FETCH

| Tiêu chí | EntityGraph | JOIN FETCH |
|---|---|---|
| Mục đích | Khai báo fetch plan | Khai báo fetch trong JPQL |
| Vị trí | Annotation, named graph hoặc EntityManager hint | JPQL query |
| Tách khỏi predicate | Có; graph không tự lọc dữ liệu | JOIN FETCH nằm trong query |
| Tái sử dụng | Named graph có thể dùng ở nhiều query | Thường gắn với câu JPQL cụ thể |
| Nested association | Attribute nodes và subgraph | Nhiều fetch join |
| SQL thực tế | Provider quyết định cách thực thi | Provider chuyển fetch join thành SQL join tương ứng |
| Pagination với collection | Vẫn có thể gặp row multiplication | Có rủi ro row multiplication rõ ràng |
| DTO projection | Thường không cần graph | Constructor projection có thể kết hợp join thường |

EntityGraph thường làm rõ sự tách biệt giữa predicate và fetch plan. JOIN FETCH phù hợp khi query cụ thể cần thể hiện rõ association được fetch trong JPQL.

Không có quy tắc rằng EntityGraph luôn hiệu quả hơn JOIN FETCH. Cả hai cần được kiểm tra bằng SQL và dữ liệu thật.

## 18. Named graph trong XML

Ngoài annotation, JPA cho phép khai báo named entity graph trong orm.xml. Named graph được đặt bên trong phần mapping của entity tương ứng.

Ví dụ file src/main/resources/META-INF/orm.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <entity class="com.example.employee.Employee">
        <named-entity-graph name="Employee.withDepartment">
            <named-attribute-node name="department"/>
        </named-entity-graph>
    </entity>
</entity-mappings>
~~~

Nếu cùng tên graph được khai báo cả annotation và XML, XML metadata có thể override metadata annotation theo quy tắc mapping. Chọn một nguồn định nghĩa rõ ràng cho từng graph và kiểm tra mapping file được provider nạp.

Nếu dự án dùng Jakarta Persistence 3.0, 3.1 hoặc 3.2, hãy dùng namespace và XSD version tương ứng. Dự án Spring Boot 3 thường dùng jakarta.persistence; dự án cũ dùng javax.persistence có schema/namespace cũ.

## 19. Dùng EntityGraph trực tiếp với EntityManager

JPA EntityManager hỗ trợ tạo graph động và truyền graph qua query hint.

Ví dụ:

~~~java
EntityGraph<Employee> graph =
        entityManager.createEntityGraph(Employee.class);

graph.addAttributeNodes("department");

TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.active = true",
        Employee.class
);

query.setHint("jakarta.persistence.fetchgraph", graph);

List<Employee> employees = query.getResultList();
~~~

Có thể lấy named graph đã khai báo:

~~~java
EntityGraph<?> graph =
        entityManager.getEntityGraph("Employee.detail");

TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.id = :id",
        Employee.class
);

query.setParameter("id", id);
query.setHint("jakarta.persistence.fetchgraph", graph);
~~~

Hai hint chuẩn:

- jakarta.persistence.fetchgraph: áp dụng FETCH graph semantics.
- jakarta.persistence.loadgraph: áp dụng LOAD graph semantics.

Trong JPA 2.x dùng namespace javax.persistence; với Jakarta Persistence 3.x dùng jakarta.persistence. Spring Boot 3 trở lên thường dùng Jakarta namespace. Kiểm tra phiên bản dự án trước khi sao chép code.

## 20. EntityGraph và repository method có thể kết hợp linh hoạt

Một repository có thể có nhiều method cho các use case khác nhau:

~~~java
package com.example.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findByEmail(String email);

    @EntityGraph(
        value = "Employee.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findDetailedById(Long id);

    @EntityGraph(attributePaths = {"department"})
    List<Employee> findByActiveTrue();

    @EntityGraph(attributePaths = {"department"})
    Page<Employee> findByDepartment_Name(
            String departmentName,
            Pageable pageable);

    @Query("""
           select e
           from Employee e
           where e.active = true
             and e.department.id = :departmentId
           """)
    @EntityGraph(attributePaths = {"department"})
    List<Employee> findActiveByDepartmentId(
            @Param("departmentId") Long departmentId);
}
~~~

Đây là một interface tổng hợp các method minh họa; mỗi method có predicate riêng nhưng có thể chọn named graph hoặc dynamic graph theo nhu cầu.

Lưu ý rằng nếu repository đã có method kế thừa cùng chữ ký, việc override để gắn annotation cần thực hiện có chủ đích. Không khai báo các method trùng chữ ký với mong muốn tạo fetch plan khác nhau; Java không cho overload chỉ bằng annotation.

## 21. Kiểm thử EntityGraph bằng PersistenceUnitUtil

Không nên chỉ kiểm tra giá trị association sau khi gọi repository vì truy cập getter có thể tự kích hoạt lazy loading trong transaction. Có thể dùng PersistenceUnitUtil.isLoaded() để xác nhận association đã được tải ngay sau query.

Ví dụ test:

~~~java
package com.example.employee;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnitUtil;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class EmployeeEntityGraphTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void namedGraphLoadsDepartment() {
        Department department = new Department("Engineering");
        testEntityManager.persist(department);

        Employee employee = new Employee(
                "Ada",
                "ada@example.com",
                true,
                department
        );
        testEntityManager.persist(employee);

        testEntityManager.flush();
        testEntityManager.clear();

        Employee found = repository.findByEmail("ada@example.com")
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(found, "department")).isTrue();
        assertThat(found.getDepartment().getName())
                .isEqualTo("Engineering");
    }

    @Test
    void nestedGraphLoadsAssignmentsAndProjects() {
        Department department = new Department("Engineering");
        Project project = new Project("Migration");

        testEntityManager.persist(department);
        testEntityManager.persist(project);

        Employee employee = new Employee(
                "Ada",
                "ada@example.com",
                true,
                department
        );
        testEntityManager.persist(employee);

        Assignment assignment =
                new Assignment(employee, project, "Developer");
        testEntityManager.persist(assignment);

        testEntityManager.flush();
        Long employeeId = employee.getId();
        testEntityManager.clear();

        Employee found = repository.findDetailedById(employeeId)
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(found, "assignments")).isTrue();
        Assignment loadedAssignment = found.getAssignments().get(0);
        assertThat(util.isLoaded(loadedAssignment, "project")).isTrue();
        assertThat(loadedAssignment.getProject().getName())
                .isEqualTo("Migration");
    }
}
~~~

Test đầu dùng named graph Employee.withDepartment trên findByEmail. Sau clear(), entity không còn nằm trong persistence context trước đó. isLoaded kiểm tra association đã được tải bởi query.

Test thứ hai dùng graph detail để xác nhận collection assignments và nested project được tải. Test cần chạy trong persistence context của @DataJpaTest để có thể kiểm tra trạng thái association và đọc tên Project.

Nếu muốn test SQL statement count, dùng datasource proxy hoặc Hibernate statistics để xác nhận số query, vì isLoaded chỉ kiểm tra trạng thái association chứ không chứng minh query tối ưu.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Named graph không được tìm thấy | Sai tên graph hoặc metadata không được nạp | Kiểm tra name và mapping |
| Attribute node báo lỗi | Dùng tên cột SQL thay thuộc tính Java | Dùng persistent property name |
| Nested subgraph không hoạt động | Subgraph khai báo sai entity đích hoặc sai tên path | Kiểm tra association và target type |
| EntityGraph không lọc kết quả | Graph chỉ quy định fetch plan | Thêm WHERE/JOIN/EXISTS predicate |
| N+1 vẫn xảy ra | Graph bỏ sót association được truy cập | Bổ sung path cần thiết hoặc batch fetching |
| Query tải quá nhiều dữ liệu | Graph chứa nhiều collection hoặc nhiều tầng | Thu hẹp graph theo use case |
| Page chậm với graph collection | Collection fetch nhân dòng hoặc phân trang trong bộ nhớ | Page ID trước rồi fetch riêng |
| Count query bị ảnh hưởng bởi join | Predicate JOIN to-many làm nhân root | Dùng EXISTS hoặc count distinct root |
| DTO không dùng graph như mong đợi | Projection không trả entity graph root | Chọn projection phù hợp, không dựa vào graph |
| EntityGraph và JOIN FETCH bị trùng | Cùng association được khai báo hai lần | Chọn một fetch strategy rõ ràng |
| MultipleBagFetchException | Fetch nhiều bag collection cùng query | Tách query hoặc batch fetch |
| LazyInitializationException | Truy cập association ngoài transaction | Tải trong transaction hoặc trả DTO |
| LOAD graph vẫn tải association ngoài graph | Mapping của association là EAGER | Hiểu khác biệt LOAD và FETCH |
| FETCH graph vẫn thấy thêm trường được tải | Provider có thể fetch thêm ngoài graph | Graph không phải cam kết SQL tối thiểu tuyệt đối |

## 23. Nguyên tắc thiết kế thực tế

- Đặt association LAZY làm mặc định hợp lý và chọn fetch plan theo use case.
- Dùng named graph khi một fetch plan được tái sử dụng ở nhiều repository method.
- Dùng attributePaths cho graph nhỏ, riêng một method.
- Dùng FETCH khi muốn các thuộc tính ngoài graph được xem là LAZY cho lần tải; dùng LOAD khi muốn giữ mapping fetch type cho thuộc tính không được liệt kê.
- Giữ predicate trong derived query, @Query, Specification hoặc Criteria; graph chỉ quản lý fetch plan.
- Gắn graph vào method trả entity khi thực sự cần association.
- Không thêm collection vào mọi graph detail.
- Kiểm tra SQL và N+1 thay vì giả định graph luôn tạo một JOIN.
- Cẩn thận với Page/Slice khi graph có collection.
- Tách ID pagination và fetch collection nếu cần trang root cùng collection đầy đủ.
- Dùng DTO projection nếu chỉ cần một vài trường hoặc số liệu tổng hợp.
- Tránh khai báo cùng association trong cả EntityGraph và JOIN FETCH khi không cần thiết.
- Kiểm thử association đã tải bằng PersistenceUnitUtil và đo query count.
- Kiểm tra Jakarta/Javax namespace theo phiên bản JPA của dự án.

## 24. Checklist tự đánh giá

- [ ] Giải thích được khác biệt giữa predicate và fetch plan.
- [ ] Khai báo named graph bằng @NamedEntityGraph.
- [ ] Dùng @NamedAttributeNode cho thuộc tính gốc.
- [ ] Dùng @NamedSubgraph cho association lồng nhau.
- [ ] Phân biệt FETCH graph và LOAD graph.
- [ ] Dùng @EntityGraph(value = ...) để tham chiếu named graph.
- [ ] Dùng attributePaths để tạo dynamic graph.
- [ ] Hiểu attributePaths có ưu tiên khi được khai báo và graph name không còn là nguồn graph.
- [ ] Kết hợp EntityGraph với derived query.
- [ ] Kết hợp EntityGraph với @Query.
- [ ] Hiểu graph không tự thêm predicate lọc.
- [ ] Chọn đúng graph cho to-one và to-many.
- [ ] Nhận diện rủi ro collection fetch với Page/Slice.
- [ ] Phân biệt EntityGraph và JOIN FETCH.
- [ ] Biết dùng EntityManager fetchgraph/loadgraph hint.
- [ ] Kiểm tra association bằng PersistenceUnitUtil.isLoaded().
- [ ] Đo SQL/query count để phát hiện N+1.
- [ ] Dùng DTO projection hoặc batch fetching khi phù hợp.

## 25. Kết luận

EntityGraph giúp Spring Data JPA chọn fetch plan theo từng phương thức truy vấn. Named graph phù hợp với fetch plan được tái sử dụng; attributePaths phù hợp với graph nhỏ, khai báo ngay tại repository method. FETCH và LOAD khác nhau ở cách xử lý thuộc tính không được liệt kê trong graph.

Khi kết hợp EntityGraph với derived query hoặc @Query, hãy giữ rõ vai trò: query xác định entity nào phù hợp, graph xác định association nào cần tải. Đặc biệt cẩn thận với collection trong Page/Slice vì graph không loại bỏ row multiplication hoặc in-memory pagination. Kiểm tra SQL, trạng thái association và số query trên dữ liệu thực tế để chọn fetch plan vừa đủ.
