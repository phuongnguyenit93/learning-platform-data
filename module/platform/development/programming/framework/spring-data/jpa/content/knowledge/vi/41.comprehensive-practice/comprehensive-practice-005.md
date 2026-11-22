# Tái hiện N+1 và so sánh các phương án khắc phục trong Spring Data JPA

N+1 là vấn đề hiệu năng xảy ra khi một truy vấn lấy danh sách entity cha, sau đó ứng dụng phát thêm một truy vấn cho mỗi entity để tải dữ liệu liên quan. Với N entity cha, tổng số truy vấn thường là 1 + N. Dữ liệu có thể vẫn đúng, test chức năng vẫn pass, nhưng thời gian phản hồi tăng nhanh khi số bản ghi lớn hoặc database nằm qua mạng.

Bài học này tạo một ví dụ Spring Data JPA có thể tái hiện N+1 bằng Hibernate Statistics, sau đó so sánh các cách khắc phục: JPQL `JOIN FETCH`, `@EntityGraph`, DTO projection và batch fetching. Mỗi cách có ưu và nhược điểm; chọn theo dữ liệu cần đọc, phân trang và kích thước tập kết quả. Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6, JUnit 5, AssertJ và H2.

## 1. N+1 là gì?

Giả sử hệ thống có ba phòng ban, mỗi phòng ban có một danh sách nhân viên. Ứng dụng cần hiển thị tên phòng ban và số nhân viên.

Một cách viết dễ gặp:

```java
List<Department> departments = departmentRepository.findAll();

for (Department department : departments) {
    System.out.println(
        department.getName() + ": " + department.getEmployees().size()
    );
}
```

Truy vấn đầu tiên tải danh sách phòng ban. Quan hệ `employees` được khai báo LAZY, nên khi gọi `getEmployees()`, Hibernate tải collection cho từng phòng ban nếu collection đó chưa được khởi tạo.

SQL có dạng khái niệm:

```sql
-- Query 1: lấy các phòng ban
select d.id, d.name
from departments d;

-- Query 2: nhân viên của phòng ban thứ nhất
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;

-- Query 3: nhân viên của phòng ban thứ hai
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;

-- Query 4: nhân viên của phòng ban thứ ba
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;
```

Với ba phòng ban, có một truy vấn cha và ba truy vấn con: tổng cộng bốn truy vấn. Với 100 phòng ban, có thể thành 101 truy vấn. Đây là N+1.

N+1 không chỉ xảy ra với `@OneToMany`. Một quan hệ `@ManyToOne(fetch = FetchType.LAZY)` hoặc `@OneToOne(fetch = FetchType.LAZY)` cũng có thể gây ra một truy vấn phụ cho từng entity khi ứng dụng truy cập association. Quan hệ EAGER cũng không bảo đảm luôn chỉ có một câu SQL; provider có thể tải association bằng các câu truy vấn phụ.

## 2. Tạo mô hình entity để tái hiện N+1

Dùng quan hệ một phòng ban có nhiều nhân viên. `Department` là phía inverse với `mappedBy`; `Employee.department` là owning side giữ khóa ngoại.

**Department.java**

```java
package com.example.department;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "department",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<Employee> employees = new ArrayList<>();

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

    public List<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }
}
```

**Employee.java**

```java
package com.example.department;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() {
    }

    public Employee(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Department getDepartment() {
        return department;
    }

    void setDepartment(Department department) {
        this.department = department;
    }
}
```

Hai điểm quan trọng:

- `mappedBy = "department"` trỏ tới thuộc tính Java trong `Employee`, không phải tên cột `department_id`.
- Khi thêm nhân viên, helper `addEmployee()` cập nhật cả collection inverse và owning side. Chỉ thêm vào `Department.employees` mà không gán `Employee.department` có thể không ghi khóa ngoại như mong đợi.

## 3. Repository với các phương án truy vấn

Bắt đầu bằng phương thức lấy danh sách phòng ban bình thường, sau đó khai báo các biến thể tải association.

**DepartmentRepository.java**

```java
package com.example.department;

import com.example.department.dto.DepartmentSummary;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DepartmentRepository
        extends JpaRepository<Department, Long> {

    List<Department> findAllByOrderByNameAsc();

    @Query("""
        select distinct d
        from Department d
        left join fetch d.employees
        order by d.name
        """)
    List<Department> findAllWithEmployees();

    @EntityGraph(attributePaths = "employees")
    @Query("""
        select d
        from Department d
        order by d.name
        """)
    List<Department> findAllWithEmployeesGraph();

    @Query("""
        select distinct d
        from Department d
        left join fetch d.employees
        where d.id in :ids
        """)
    List<Department> findWithEmployeesByIdIn(@Param("ids") Collection<Long> ids);

    @Query("""
        select new com.example.department.dto.DepartmentSummary(
            d.id, d.name, count(e)
        )
        from Department d
        left join d.employees e
        group by d.id, d.name
        order by d.name
        """)
    List<DepartmentSummary> findDepartmentSummaries();

    @Query(
        value = "select d from Department d order by d.name",
        countQuery = "select count(d) from Department d"
    )
    Page<Department> findDepartmentPage(Pageable pageable);
}
```

Các phương thức dùng cho các tình huống khác nhau:

- `findAllByOrderByNameAsc()`: baseline để quan sát N+1.
- `findAllWithEmployees()`: dùng fetch join để tải collection trong cùng truy vấn.
- `findAllWithEmployeesGraph()`: khai báo fetch plan bằng EntityGraph.
- `findWithEmployeesByIdIn(...)`: truy vấn thứ hai theo danh sách ID, hữu ích cho chiến lược phân trang hai bước.
- `findDepartmentSummaries()`: chỉ lấy dữ liệu cần cho màn hình tổng hợp.
- `findDepartmentPage(...)`: phân trang danh sách entity cha mà không fetch collection.

## 4. Tái hiện và đo N+1 bằng Hibernate Statistics

Không nên chỉ nhìn log rồi phỏng đoán. Hibernate cung cấp `Statistics` để đếm số prepared statement. Bật thống kê trong test:

**application-test.yml**

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Integration test tạo ba phòng ban, mỗi phòng ban có hai nhân viên. Sau khi flush và clear, test xóa số liệu thống kê, truy vấn danh sách cha rồi truy cập collection.

**DepartmentNPlusOneTest.java**

```java
package com.example.department;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class DepartmentNPlusOneTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private DepartmentRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @BeforeEach
    void setUp() {
        Department engineering = new Department("Engineering");
        engineering.addEmployee(new Employee("An"));
        engineering.addEmployee(new Employee("Binh"));

        Department finance = new Department("Finance");
        finance.addEmployee(new Employee("Chi"));
        finance.addEmployee(new Employee("Dung"));

        Department sales = new Department("Sales");
        sales.addEmployee(new Employee("Giang"));
        sales.addEmployee(new Employee("Hoa"));

        entityManager.persist(engineering);
        entityManager.persist(finance);
        entityManager.persist(sales);
        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void demonstratesOnePlusNSelects() {
        Statistics statistics = entityManagerFactory
            .unwrap(SessionFactory.class)
            .getStatistics();

        statistics.clear();

        var departments = repository.findAllByOrderByNameAsc();

        // Chỉ truy vấn bảng cha ở thời điểm này.
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);

        int employeeCount = departments.stream()
            .mapToInt(department -> department.getEmployees().size())
            .sum();

        assertThat(employeeCount).isEqualTo(6);

        // 1 query lấy departments + 3 query tải 3 collections.
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(4L);
    }
}
```

Test dùng `flush()` để ghi dữ liệu fixture xuống database và `clear()` để loại entity khỏi persistence context trước khi đo. Nếu không clear, entity hoặc collection còn managed có thể đã được khởi tạo và làm số truy vấn đo được thấp hơn thực tế.

Kết quả kỳ vọng của test là:

- Sau khi lấy danh sách phòng ban: 1 prepared statement.
- Sau khi duyệt ba collection employees: 4 prepared statements tổng cộng.
- Số nhân viên đếm được: 6.

Số lượng prepared statement là bằng chứng định lượng cho trường hợp test này. Khi bật các listener, filter hoặc query khác, hãy gọi `statistics.clear()` ngay trước phần cần đo và tránh chạy đồng thời các test dùng chung SessionFactory statistics.

## 5. Cách 1 — JPQL JOIN FETCH

Fetch join yêu cầu JPA tải association trong cùng truy vấn với entity gốc:

```java
@Query("""
    select distinct d
    from Department d
    left join fetch d.employees
    order by d.name
    """)
List<Department> findAllWithEmployees();
```

- `left join fetch` giữ lại phòng ban ngay cả khi chưa có nhân viên.
- `join fetch` (inner join) chỉ trả phòng ban có association phù hợp.
- `fetch` yêu cầu provider nạp association cùng truy vấn thay vì đợi truy cập lazy.
- `distinct` diễn tả kết quả entity gốc không trùng lặp ở cấp JPQL.

Khi fetch collection, SQL vẫn có thể trả nhiều hàng cho một phòng ban — một hàng cho mỗi nhân viên. Hibernate ghép các hàng đó thành entity graph và loại trùng entity gốc trong kết quả. Vì vậy số hàng SQL và số entity Java không nhất thiết bằng nhau.

Kiểm thử biến thể fetch join:

```java
@Test
void fetchJoinLoadsDepartmentsAndEmployeesInOneStatement() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var departments = repository.findAllWithEmployees();

    int employeeCount = departments.stream()
        .mapToInt(department -> department.getEmployees().size())
        .sum();

    assertThat(departments).hasSize(3);
    assertThat(employeeCount).isEqualTo(6);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

Phương án này phù hợp khi cần entity và association cho một màn hình hoặc use case có phạm vi rõ ràng. Tránh fetch join nhiều collection lớn trong cùng một câu lệnh vì có thể tạo tích Descartes, làm số hàng trung gian tăng mạnh; với một số kiểu collection dạng bag, Hibernate còn có thể báo `MultipleBagFetchException`.

### Giới hạn khi kết hợp phân trang

Không nên phân trang trực tiếp một truy vấn fetch join collection:

```java
@Query("""
    select distinct d
    from Department d
    left join fetch d.employees
    order by d.name
    """)
Page<Department> findAllWithEmployees(Pageable pageable);
```

Database phân trang trên các hàng join, trong khi một phòng ban có thể chiếm nhiều hàng. Hibernate có thể phải áp dụng pagination trong bộ nhớ và phát cảnh báo như `HHH90003004`; điều này có thể tải quá nhiều dữ liệu.

Khi cần page, hãy phân trang entity cha trước rồi tải association cho các ID trong trang, hoặc dùng DTO projection. Không đánh đổi việc lấy toàn bộ collection chỉ để tránh thêm một truy vấn.

## 6. Cách 2 — @EntityGraph

EntityGraph khai báo association cần tải cho một query mà không phải viết fetch join trong JPQL:

```java
@EntityGraph(attributePaths = "employees")
@Query("select d from Department d order by d.name")
List<Department> findAllWithEmployeesGraph();
```

EntityGraph hữu ích khi muốn giữ query dễ đọc hoặc dùng lại fetch plan cho nhiều method. Có thể khai báo named graph trên entity hoặc dùng `attributePaths` để tạo graph động ngay trên repository method.

EntityGraph định nghĩa fetch plan mà provider phải đáp ứng theo ngữ nghĩa JPA. Provider quyết định chiến lược SQL cụ thể; Hibernate thường dùng join cho trường hợp đơn giản, nhưng cần kiểm tra SQL thực tế và số statement. Không suy luận rằng chỉ có annotation là chắc chắn hết N+1.

Ví dụ kiểm thử:

```java
@Test
void entityGraphLoadsTheRequestedAssociation() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var departments = repository.findAllWithEmployeesGraph();

    int employeeCount = departments.stream()
        .mapToInt(department -> department.getEmployees().size())
        .sum();

    assertThat(employeeCount).isEqualTo(6);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

Assertion một statement là kỳ vọng cho cấu hình Hibernate và association đơn giản của ví dụ. Nếu đổi provider, mapping hoặc graph sâu hơn, hãy kiểm tra lại SQL thay vì giữ nguyên giả định.

EntityGraph phù hợp khi fetch plan thay đổi theo use case. Ví dụ màn hình danh sách chỉ cần `employees`, trong khi màn hình khác cần thêm `manager`. Có thể định nghĩa graph riêng cho từng repository method thay vì chuyển toàn bộ association thành EAGER.

## 7. Cách 3 — DTO projection

Nếu màn hình chỉ cần tên phòng ban và số nhân viên, không cần tải entity cùng toàn bộ collection. DTO projection chỉ lấy các cột cần thiết và thực hiện phép tổng hợp trong database.

DTO:

**DepartmentSummary.java**

```java
package com.example.department.dto;

public record DepartmentSummary(
    Long id,
    String name,
    Long employeeCount
) {
}
```

Repository dùng JPQL constructor expression:

```java
@Query("""
    select new com.example.department.dto.DepartmentSummary(
        d.id, d.name, count(e)
    )
    from Department d
    left join d.employees e
    group by d.id, d.name
    order by d.name
    """)
List<DepartmentSummary> findDepartmentSummaries();
```

Kiểm thử:

```java
@Test
void projectionReturnsOnlyTheSummaryFields() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var summaries = repository.findDepartmentSummaries();

    assertThat(summaries).hasSize(3);
    assertThat(summaries)
        .extracting(DepartmentSummary::employeeCount)
        .containsExactly(2L, 2L, 2L);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

DTO projection thường là lựa chọn tốt cho read model, báo cáo, danh sách và API response chỉ cần một phần dữ liệu. Nó tránh tải entity không cần thiết và tránh việc serialize entity kéo theo lazy loading. Đổi lại, DTO không phải managed entity; không dùng DTO projection để cập nhật aggregate như thể nó đang nằm trong persistence context.

Với màn hình cần chi tiết nhân viên, có thể dùng DTO projection dạng một hàng cho mỗi cặp phòng ban/nhân viên rồi nhóm thành response ở service. Cần cân nhắc dữ liệu trùng lặp của cột phòng ban và cách biểu diễn phòng ban không có nhân viên.

## 8. Cách 4 — Batch fetching

Batch fetching giảm N+1 bằng cách gom nhiều association chưa khởi tạo vào một câu truy vấn có điều kiện `IN`. Thay vì mỗi phòng ban có một SELECT riêng, Hibernate tải collection theo nhóm.

Đặt batch size trên collection:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
@BatchSize(size = 20)
private List<Employee> employees = new ArrayList<>();
```

Hoặc đặt mặc định toàn cục:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 20
```

Với N phòng ban và batch size B, số truy vấn collection thường xấp xỉ `ceil(N / B)`; tổng số statement khoảng `1 + ceil(N / B)` cho một association collection. Đây là ước lượng; số thực tế phụ thuộc số collection chưa khởi tạo, dialect, giới hạn bind parameter, persistence context và provider.

Ví dụ với 45 phòng ban và batch size 20, thay vì 46 câu truy vấn, thường có một query cha và khoảng ba query collection. Batch fetching hữu ích khi không thể hoặc không muốn join toàn bộ collection, hoặc khi entity được tải theo các luồng khác nhau rồi mới truy cập association.

Hibernate còn có `@Fetch(FetchMode.SUBSELECT)` cho một số collection. Khi một collection được khởi tạo, provider có thể tải các collection cùng loại của tập entity cha đã truy vấn bằng một subselect. Đây là tính năng riêng của Hibernate; cần kiểm tra SQL và lượng dữ liệu được nạp trong persistence context.

Batch fetching giảm số round trip, nhưng vẫn có thể tải nhiều cột/entity hơn DTO projection. Nó cũng không bảo đảm một query duy nhất như fetch join đơn giản.

## 9. So sánh các phương án

| Phương án | Cách giảm N+1 | Ưu điểm | Giới hạn / phù hợp |
|---|---|---|---|
| JPQL `JOIN FETCH` | Tải association bằng join trong một query | Chủ động, rõ SQL, tốt cho một graph nhỏ | Trùng hàng SQL; thận trọng với pagination và nhiều collection |
| `@EntityGraph` | Khai báo fetch plan theo use case | Ít thay đổi JPQL, dễ tái sử dụng graph | SQL do provider quyết định; phải đo thực tế |
| DTO projection | Query đúng cột và phép tổng hợp cần thiết | Ít dữ liệu, không cần lazy loading, tốt cho read API | Không trả managed aggregate để cập nhật |
| Batch fetching | Gom nhiều lazy load thành các nhóm | Ít thay đổi code truy vấn, giảm round trip | Vẫn có query phụ và tải entity; phụ thuộc Hibernate |
| Two-step loading | Page root trước, fetch association theo ID sau | Giữ pagination đúng và kiểm soát tập dữ liệu | Thường cần hai query và sắp xếp lại theo thứ tự page |

Không có một cách khắc phục tối ưu cho mọi query. Hãy bắt đầu từ dữ liệu use case cần:

- Cần một aggregate với một collection nhỏ: fetch join hoặc EntityGraph.
- Cần danh sách chỉ có vài trường và số đếm: DTO projection.
- Cần giữ lazy loading nhưng giảm số round trip khi truy cập nhiều collection: batch fetching.
- Cần phân trang cha và hiển thị association: hai bước hoặc DTO projection.

## 10. Phân trang an toàn với collection

Một cách phổ biến là lấy trang ID/entity cha trước, sau đó fetch collection bằng truy vấn thứ hai.

Service:

```java
@Service
public class DepartmentQueryService {

    private final DepartmentRepository repository;

    public DepartmentQueryService(DepartmentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Department> findPageWithEmployees(Pageable pageable) {
        Page<Department> page =
            repository.findDepartmentPage(pageable);

        List<Long> ids = page.getContent().stream()
            .map(Department::getId)
            .toList();

        if (ids.isEmpty()) {
            return List.of();
        }

        List<Department> loaded =
            repository.findWithEmployeesByIdIn(ids);

        Map<Long, Department> byId = loaded.stream()
            .collect(Collectors.toMap(Department::getId, Function.identity()));

        // IN query không bảo đảm giữ thứ tự ID đầu vào; khôi phục thứ tự của page.
        return ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();
    }
}
```

Đoạn service cần các import:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
```

Hai query có ý nghĩa riêng: query đầu áp dụng LIMIT/OFFSET và count để xác định page; query thứ hai tải collection cho đúng các ID đã có. Cả hai chạy trong transaction read-only để entity được quản lý và association có thể được truy cập trong phạm vi transaction.

Với tập ID lớn, cần chú ý giới hạn số bind parameter của database. Một page nhỏ thường không gặp vấn đề. Nếu phải tải hàng nghìn ID, chia batch hoặc chuyển sang DTO query phù hợp.

## 11. N+1 có thể bị che khuất bởi transaction và Open Session in View

`@Transactional(readOnly = true)` giúp đặt transaction đọc và có thể tối ưu flush behavior, nhưng tự nó không loại bỏ N+1. Nếu service truy cập một collection lazy trong vòng lặp, các query phụ vẫn xảy ra.

Open Session in View (OSIV) có thể giữ persistence context mở tới lúc render response, làm cho lazy loading vẫn hoạt động sau khi service trả về. Điều đó đôi khi che giấu việc API đang kích hoạt query ngoài service. Không nên dựa vào OSIV để khắc phục N+1; hãy xác định fetch plan trong use case hoặc trả DTO đã được dựng trong transaction.

Không chuyển tất cả association sang `FetchType.EAGER` để chữa N+1. EAGER có thể làm tải dữ liệu không cần thiết, tạo query phụ và khiến graph ngày càng lớn. Chọn fetch plan theo từng truy vấn.

## 12. Phát hiện N+1 trong log và môi trường thật

Có thể bật SQL logging trong profile local/test:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 dùng category `org.hibernate.orm.jdbc.bind` để log bind parameter. Bind logging có thể lộ dữ liệu nhạy cảm, vì vậy không nên bật tùy tiện trong production hoặc ghi thông tin cá nhân vào log.

Các dấu hiệu cần tìm:

- Một câu SELECT lấy danh sách entity cha.
- Sau đó lặp lại cùng một mẫu SELECT theo foreign key của từng entity.
- Số câu SELECT tăng gần tuyến tính theo số entity cha.
- Thời gian DB/network chiếm phần lớn thời gian endpoint.

Trong môi trường production, kết hợp APM/tracing, slow query log và số liệu database. Hibernate Statistics hữu ích trong test hoặc môi trường quan sát được kiểm soát; không bật log bind rộng rãi chỉ để tìm N+1.

## 13. Những lỗi thường gặp khi sửa N+1

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm fetch join collection vào query Pageable | Pagination có thể diễn ra trong bộ nhớ hoặc trả page không hiệu quả | Page root trước, sau đó fetch theo ID hoặc dùng DTO |
| Fetch nhiều collection trong cùng một query | Tích Descartes, nhiều hàng trùng hoặc lỗi bag fetch | Tách query, batch fetch hoặc dùng projection |
| Chuyển toàn bộ quan hệ sang EAGER | Tải dư dữ liệu và vẫn có thể phát sinh query phụ | Giữ LAZY phù hợp, đặt fetch plan theo use case |
| Chỉ kiểm tra số entity, không đếm SQL | Test chức năng pass nhưng N+1 vẫn còn | Dùng Hibernate Statistics hoặc công cụ đếm SQL |
| Đo thống kê mà không clear persistence context | Collection đã được load trước, số query thấp giả tạo | Flush, clear, rồi clear statistics trước đoạn đo |
| Trả entity ra API và serialize association | Serialization kích hoạt lazy load hoặc lỗi ngoài transaction | Map sang DTO bên trong service |
| Dùng batch size quá lớn | Tải nhiều association và bind parameter hơn cần thiết | Đo dữ liệu thực tế, chọn batch size theo use case/database |

## 14. Checklist xử lý một N+1 trong dự án

1. Xác định endpoint hoặc use case chậm và entity cha được truy vấn.
2. Bật SQL log ở môi trường an toàn hoặc dùng APM để tìm mẫu SELECT lặp.
3. Xác định association nào bị truy cập trong vòng lặp hoặc trong mapper/serializer.
4. Viết integration test có dữ liệu nhiều entity cha và đo statement count.
5. Chọn fetch join, EntityGraph, DTO projection, batch fetching hoặc hai bước phân trang theo dữ liệu cần.
6. Chạy lại test và so sánh cả số statement, số hàng, thời gian và lượng dữ liệu truyền.
7. Kiểm tra pagination, nhiều collection, transaction boundary và các association khác để tránh chuyển N+1 thành một query khổng lồ.
8. Giữ test hồi quy để thay đổi query sau này không vô tình tái tạo N+1.

## 15. Kiểm thử với Testcontainers và regression test

H2 phù hợp để chạy test nhanh, nhưng không mô phỏng đầy đủ dialect, kiểu dữ liệu, kế hoạch truy vấn và giới hạn của database production. Nếu ứng dụng chạy PostgreSQL, nên có ít nhất một integration test dùng PostgreSQL thật qua Testcontainers để xác nhận JPQL, fetch plan và số statement trên đúng hệ quản trị.

Thêm các dependency test (phiên bản có thể được quản lý bằng Spring Boot dependency management hoặc Testcontainers BOM):

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Ví dụ cấu hình test slice dùng PostgreSQL container:

**DepartmentPostgresIT.java**

```java
package com.example.department;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers(disabledWithoutDocker = true)
@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class DepartmentPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
    }

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private DepartmentRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchJoinKeepsCollectionLoadingToOneStatementOnPostgres() {
        Department department = new Department("Engineering");
        department.addEmployee(new Employee("An"));
        department.addEmployee(new Employee("Binh"));
        entityManager.persistAndFlush(department);
        entityManager.clear();

        Statistics statistics = entityManagerFactory
            .unwrap(SessionFactory.class)
            .getStatistics();
        statistics.clear();

        var result = repository.findAllWithEmployees();
        int employeeCount = result.stream()
            .mapToInt(item -> item.getEmployees().size())
            .sum();

        assertThat(result).hasSize(1);
        assertThat(employeeCount).isEqualTo(2);
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
    }
}
```

Testcontainers cần Docker hoặc một môi trường container tương thích. `disabledWithoutDocker = true` cho phép JUnit bỏ qua test khi Docker không khả dụng; CI nên cấu hình Docker để test này thực sự chạy. Với Spring Boot, `@DynamicPropertySource` đăng ký URL và thông tin kết nối của container trước khi test context tạo DataSource. `replace = NONE` ngăn test slice thay DataSource PostgreSQL bằng database nhúng.

Regression test nên kiểm tra hành vi quan sát được thay vì chỉ kiểm tra annotation:

- Baseline lazy loading với ba phòng ban phải cho thấy một query cha và ba query collection trong fixture đơn giản.
- JOIN FETCH và DTO projection phải giữ số statement ở mức một trong ví dụ không phân trang.
- EntityGraph cần được đo trên Hibernate/provider thực tế; nếu mục tiêu là một statement, giữ assertion để phát hiện khi fetch plan thay đổi.
- Batch fetching nên kiểm tra số query bị chặn theo batch size, ví dụ khoảng `1 + ceil(N / B)`, thay vì giả định luôn chỉ một query.
- Kiểm thử hai bước cần xác nhận page chứa đúng số phòng ban, collection đã được tải và thứ tự kết quả vẫn theo page ban đầu.
- Bổ sung trường hợp phòng ban không có nhân viên, page rỗng, page cuối và dữ liệu đủ lớn để tạo nhiều batch.

Khi đếm SQL, flush và clear fixture trước khi reset statistics; reset ngay trước phần truy vấn cần đo. Không chạy song song các test cùng đọc/ghi Hibernate Statistics của một SessionFactory vì bộ đếm là trạng thái dùng chung. Tách test H2 nhanh và test Testcontainers theo profile hoặc tag để vẫn có feedback nhanh trong quá trình phát triển.

## 16. Checklist xử lý một N+1 trong dự án

1. Xác định endpoint hoặc use case chậm và entity cha được truy vấn.
2. Bật SQL log ở môi trường an toàn hoặc dùng APM để tìm mẫu SELECT lặp.
3. Xác định association nào bị truy cập trong vòng lặp hoặc trong mapper/serializer.
4. Viết integration test có dữ liệu nhiều entity cha và đo statement count.
5. Chọn fetch join, EntityGraph, DTO projection, batch fetching hoặc hai bước phân trang theo dữ liệu cần.
6. Chạy lại test và so sánh cả số statement, số hàng, thời gian và lượng dữ liệu truyền.
7. Kiểm tra pagination, nhiều collection, transaction boundary và các association khác để tránh chuyển N+1 thành một query khổng lồ.
8. Giữ regression test trên database production-compatible để thay đổi query sau này không vô tình tái tạo N+1.

N+1 là vấn đề về số lần truy cập database, không chỉ là một annotation mapping. Cách xử lý tốt bắt đầu từ việc tái hiện bằng số liệu, xác định dữ liệu thực sự cần cho use case, rồi chọn fetch plan phù hợp. Một câu SQL ít hơn không tự động đồng nghĩa với nhanh hơn; hãy so sánh số statement, số hàng trả về, kích thước dữ liệu và khả năng phân trang trước khi chốt giải pháp.