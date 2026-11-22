# Ánh xạ nhiều-một bằng @ManyToOne và @JoinColumn

## Mục tiêu

Trong mô hình quan hệ, một bản ghi ở bảng này có thể tham chiếu tới một bản ghi ở bảng khác. Quan hệ nhiều-một (many-to-one) mô tả trường hợp nhiều entity nguồn cùng tham chiếu tới một entity đích. Ví dụ, nhiều nhân viên thuộc cùng một phòng ban, nhiều đơn hàng thuộc cùng một khách hàng hoặc nhiều bình luận thuộc cùng một bài viết.

Trong JPA, ta dùng `@ManyToOne` để khai báo quan hệ và `@JoinColumn` để mô tả cột khóa ngoại ở bảng chứa entity sở hữu quan hệ.

Sau bài này, bạn có thể:

- Hiểu ý nghĩa của many-to-one và vị trí khóa ngoại.
- Ánh xạ quan hệ bằng `@ManyToOne` và `@JoinColumn`.
- Phân biệt quan hệ một chiều và hai chiều, owning side và inverse side.
- Chọn giá trị phù hợp cho `fetch`, `optional`, `nullable` và cascade.
- Tải quan hệ hiệu quả, tránh N+1 và lỗi lazy loading.
- Kiểm thử mapping và xử lý các lỗi thường gặp.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Quan hệ nhiều-một là gì?

Giả sử một phòng ban có nhiều nhân viên, nhưng mỗi nhân viên thuộc về một phòng ban:

- Một `Department` có thể liên kết với nhiều `Employee`.
- Mỗi `Employee` tham chiếu tới một `Department`.

Trong database, khóa ngoại thường được đặt ở bảng phía nhiều:

| departments | |
|---|---|
| id (PK) | name |
| 10 | Engineering |
| 20 | Finance |

| employees | | |
|---|---|---:|
| id (PK) | full_name | department_id (FK) |
| 101 | An | 10 |
| 102 | Bình | 10 |
| 103 | Chi | 20 |
| 104 | Dũng | 10 |

Ba nhân viên An, Bình và Dũng cùng tham chiếu phòng ban có ID 10. Đây là quan hệ nhiều-một nhìn từ phía Employee.

Trong JPA, quan hệ được khai báo ở entity phía nhiều. Mỗi Employee có một thuộc tính Department; database lưu ID của Department trong cột khóa ngoại thuộc bảng employees.

### 1.1. Vì sao khóa ngoại nằm ở phía nhiều?

Một cột của bảng employees có thể lưu một department ID cho mỗi hàng. Nhiều hàng employees có thể cùng lưu giá trị 10, nhưng mỗi hàng chỉ có một giá trị department_id.

Ngược lại, nếu đặt danh sách employee ID trong một cột của departments thì sẽ khó bảo đảm tính nguyên tử và toàn vẹn tham chiếu của quan hệ. Mô hình quan hệ chuẩn lưu khóa ngoại ở phía nhiều.

Quan hệ many-to-one không tự tạo ra một collection ở phía Department. Nếu nghiệp vụ cần truy cập danh sách nhân viên từ phòng ban, có thể bổ sung chiều ngược lại bằng `@OneToMany`.

## 2. @ManyToOne và @JoinColumn

Hai annotation có trách nhiệm khác nhau:

- `@ManyToOne`: khai báo thuộc tính entity tham chiếu tới một entity khác theo quan hệ nhiều-một.
- `@JoinColumn`: mô tả cột join, thường là cột khóa ngoại trên bảng của entity sở hữu quan hệ.

Ví dụ:

```java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

Ở đây:

- `Employee` là entity nguồn, phía nhiều.
- `Department` là entity được tham chiếu, phía một.
- `department` là thuộc tính quan hệ trong Java.
- `department_id` là tên cột khóa ngoại trong bảng employees.

Tên thuộc tính Java và tên cột database có thể khác nhau. Trong code Java, ta dùng `employee.getDepartment()`; trong SQL, database lưu khóa ngoại ở `employees.department_id`.

### 2.1. Các thuộc tính của @ManyToOne

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| `targetEntity` | Suy ra từ kiểu thuộc tính | Chỉ định entity đích khi kiểu không thể được suy ra |
| `cascade` | Không cascade | Các thao tác nào được truyền tới entity đích |
| `fetch` | `EAGER` | Chiến lược tải quan hệ |
| `optional` | `true` | Quan hệ có được phép không có entity đích hay không |

`@ManyToOne` mặc định fetch `EAGER`. Điều này có nghĩa provider phải bảo đảm quan hệ được tải khi entity nguồn được truy cập theo hợp đồng JPA; provider có thể thực hiện join hoặc truy vấn bổ sung.

Với ứng dụng thường cần kiểm soát việc tải quan hệ, nhiều trường hợp nên khai báo rõ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

`LAZY` yêu cầu provider trì hoãn tải entity đích cho đến khi cần. Tuy nhiên, với `@ManyToOne`, `LAZY` là một gợi ý fetch của JPA; provider có thể không thực hiện được trì hoãn trong mọi trường hợp. Hibernate thường hỗ trợ proxy/lazy loading khi mapping và class phù hợp.

### 2.2. Các thuộc tính của @JoinColumn

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên cột join/foreign key ở bảng entity sở hữu quan hệ |
| `referencedColumnName` | Tên cột ở bảng entity được tham chiếu; mặc định là cột primary key |
| `nullable` | Cho biết cột có cho phép null trong schema được sinh hay không |
| `unique` | Yêu cầu cột có unique constraint khi tạo schema |
| `insertable` | Cột có tham gia câu INSERT do provider tạo hay không |
| `updatable` | Cột có tham gia câu UPDATE do provider tạo hay không |
| `foreignKey` | Cho phép chỉ định tên và thuộc tính của foreign key constraint |

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "department_id",
    referencedColumnName = "id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

Trong ví dụ:

- `name = "department_id"`: cột khóa ngoại trong bảng employees.
- `referencedColumnName = "id"`: tham chiếu cột ID của departments.
- `nullable = false`: cột không được null trong schema được sinh.
- `optional = false`: về mặt object model, Employee bắt buộc có Department.
- `foreignKey`: đặt tên constraint để schema dễ đọc và quản lý.

`referencedColumnName` thường được bỏ qua vì mặc định tham chiếu primary key. Nếu tham chiếu một cột khác, cột đó cần có tính duy nhất phù hợp để làm đích foreign key và phải được database hỗ trợ. Ưu tiên tham chiếu primary key nếu không có yêu cầu cụ thể.

Không khai báo `@Column` trên cùng thuộc tính đã ánh xạ bằng `@ManyToOne`; các thuộc tính của join column được cấu hình bằng `@JoinColumn`.

### 2.3. Tên cột và schema

Nếu không chỉ định `@JoinColumn(name = ...)`, JPA provider áp dụng quy tắc đặt tên mặc định dựa trên tên thuộc tính và khóa được tham chiếu. Quy tắc naming strategy của Hibernate/Spring Boot cũng có thể chuyển camelCase thành snake_case.

Để tránh bất ngờ khi làm việc với schema có sẵn hoặc migration, nên khai báo tên cột rõ ràng:

```java
@JoinColumn(name = "department_id")
```

Nếu schema được quản lý bằng Flyway hoặc Liquibase, tên cột, nullability và foreign key trong migration phải khớp với mapping JPA.

## 3. Ví dụ hoàn chỉnh: Employee và Department

### 3.1. Entity Department

```java
package com.example.demo.department;

import jakarta.persistence.*;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
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

    public void setName(String name) {
        this.name = name;
    }
}
```

### 3.2. Entity Employee có quan hệ many-to-one

```java
package com.example.demo.employee;

import com.example.demo.department.Department;
import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "department_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_employee_department")
    )
    private Department department;

    protected Employee() {
    }

    public Employee(String fullName, Department department) {
        this.fullName = fullName;
        this.department = department;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Department getDepartment() {
        return department;
    }

    public void setDepartment(Department department) {
        this.department = department;
    }
}
```

Entity Employee sở hữu quan hệ. Hibernate ánh xạ giá trị ID của `department` vào cột `department_id` của bảng employees.

### 3.3. Repository

```java
package com.example.demo.department;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DepartmentRepository
        extends JpaRepository<Department, Long> {
}
```

```java
package com.example.demo.employee;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    List<Employee> findByDepartmentId(Long departmentId);
}
```

Spring Data phân tích `findByDepartmentId` thành đường dẫn thuộc tính `department.id`. Tên cột database không tham gia vào tên derived query; method dùng tên thuộc tính Java của entity.

### 3.4. Lưu dữ liệu trong service

```java
package com.example.demo.employee;

import com.example.demo.department.Department;
import com.example.demo.department.DepartmentRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeService {

    private final DepartmentRepository departmentRepository;
    private final EmployeeRepository employeeRepository;

    public EmployeeService(
            DepartmentRepository departmentRepository,
            EmployeeRepository employeeRepository
    ) {
        this.departmentRepository = departmentRepository;
        this.employeeRepository = employeeRepository;
    }

    @Transactional
    public Employee addEmployee(Long departmentId, String fullName) {
        Department department = departmentRepository.findById(departmentId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Department not found")
                );

        Employee employee = new Employee(fullName, department);
        return employeeRepository.save(employee);
    }
}
```

Service tải Department hiện có rồi gán vào Employee. Đây là cách rõ ràng khi Department đã tồn tại. Trong transaction, entity Department được quản lý bởi persistence context; Hibernate có thể dùng khóa ngoại của nó khi insert Employee.

Không cần cascade persist từ Employee sang Department trong trường hợp này. Department đã tồn tại và được tải từ repository.

## 4. Quan hệ một chiều và hai chiều

### 4.1. Many-to-one một chiều

Ở ví dụ trước, chỉ Employee có thuộc tính Department. Từ Employee có thể truy cập phòng ban:

```java
Employee employee = employeeRepository.findById(101L).orElseThrow();
String departmentName = employee.getDepartment().getName();
```

Từ Department không có danh sách Employee. Đây là quan hệ một chiều.

Ưu điểm:

- Mapping đơn giản.
- Ít rủi ro vòng lặp khi tuần tự hóa JSON.
- Không cần duy trì collection hai chiều.
- Phù hợp khi nghiệp vụ chủ yếu đi từ entity phía nhiều tới entity phía một.

Nếu không cần truy cập nhân viên từ Department, một chiều thường là đủ.

### 4.2. Many-to-one hai chiều

Nếu cần lấy danh sách nhân viên từ Department, có thể thêm `@OneToMany` ở phía Department:

```java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public List<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }

    public void removeEmployee(Employee employee) {
        employees.remove(employee);
        employee.setDepartment(null);
    }
}
```

Trong quan hệ hai chiều:

- `Employee.department` là owning side, vì nó chứa `@JoinColumn` và điều khiển giá trị khóa ngoại.
- `Department.employees` là inverse side, được khai báo bằng `mappedBy = "department"`.
- `mappedBy` phải trỏ tới tên thuộc tính Java ở entity sở hữu quan hệ, không phải tên cột database.

Khi thêm nhân viên, phải cập nhật owning side:

```java
department.addEmployee(employee);
```

Chỉ thêm vào collection `department.getEmployees()` mà không cập nhật `employee.setDepartment(department)` sẽ không đảm bảo khóa ngoại được ghi đúng. JPA dựa vào owning side để đồng bộ quan hệ xuống database.

### 4.3. Helper methods duy trì hai phía

Với quan hệ hai chiều, nên đóng gói thao tác thêm/xóa trong helper method để giữ object graph nhất quán.

Nếu một Employee được chuyển từ phòng ban cũ sang phòng ban mới, helper có thể cập nhật cả hai collection:

```java
public void addEmployee(Employee employee) {
    if (employee.getDepartment() != null) {
        employee.getDepartment().getEmployees().remove(employee);
    }

    employees.add(employee);
    employee.setDepartment(this);
}
```

Đoạn mã này minh họa ý tưởng đồng bộ hai phía; trong ứng dụng thực tế nên bảo đảm collection không chứa trùng lặp, xử lý null và thống nhất cách so sánh entity (ID, equals/hashCode). Không triển khai equals/hashCode dựa trên field mutable hoặc quan hệ hai chiều vì có thể gây vòng lặp và làm hỏng collection.

Nếu Department cũ không được tải hoặc collection chưa được khởi tạo, hãy thiết kế phương thức chuyển quan hệ phù hợp với trạng thái entity và persistence context. Có thể dùng service để tải hai phía và thực hiện thao tác trong transaction.

## 5. optional, nullable và ràng buộc database

Hai thuộc tính thường được dùng cùng nhau:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

Chúng liên quan nhưng không hoàn toàn đồng nghĩa:

- `optional = false` mô tả quan hệ trong mô hình JPA: Employee bắt buộc có Department.
- `nullable = false` mô tả nullability của cột join khi provider tạo schema.

Nếu quan hệ là bắt buộc, nên thể hiện nhất quán ở cả mapping và database. Database cần NOT NULL và foreign key để bảo vệ dữ liệu trước cả các thao tác ngoài ứng dụng.

Nếu quan hệ được phép bỏ trống:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
```

Có thể bỏ các thuộc tính vì đây là mặc định, nhưng khai báo rõ giúp người đọc hiểu quy tắc. Nếu department null, cột `department_id` trong employee có thể null.

`optional = false` không tự tạo ra một đối tượng Department. Khi tạo Employee, ứng dụng phải gán một Department hợp lệ. Database foreign key vẫn cần được cấu hình để ngăn ID không tồn tại.

## 6. Cascade: có nên cascade từ Employee sang Department?

Mặc định, `@ManyToOne` không cascade thao tác nào. Điều đó có nghĩa lưu Employee không tự động persist Department mới nếu không khai báo cascade.

Có thể khai báo:

```java
@ManyToOne(cascade = CascadeType.PERSIST)
@JoinColumn(name = "department_id")
private Department department;
```

Nhưng cần cân nhắc kỹ. Một Department có thể được nhiều Employee dùng chung. Cascade từ Employee sang Department có thể khiến một thao tác lưu Employee kéo theo việc lưu Department, dù Department thuộc vòng đời riêng.

Đặc biệt, tránh `CascadeType.REMOVE` hoặc `CascadeType.ALL` một cách máy móc trên `@ManyToOne`. Xóa một Employee không nên vô tình xóa Department vẫn đang được nhân viên khác tham chiếu.

Quy tắc thực hành:

- Department đã tồn tại: tải Department và gán vào Employee; không cần cascade persist.
- Department được tạo riêng: lưu Department trước, sau đó gán cho Employee.
- Chỉ cascade khi entity đích thực sự thuộc vòng đời của entity nguồn và hành vi đó phù hợp nghiệp vụ.
- Cascade không thay thế foreign key, transaction hoặc kiểm tra quyền nghiệp vụ.

Ở mô hình Department có nhiều Employee, nếu cần xóa Employee khi gỡ khỏi collection, `orphanRemoval` có thể được cân nhắc trên quan hệ `@OneToMany` phía Department. Đây là quy tắc vòng đời child; không phải thuộc tính của `@ManyToOne` và chỉ nên dùng khi Employee thực sự thuộc sở hữu vòng đời của Department.

## 7. Fetch strategy và vấn đề N+1

`@ManyToOne` mặc định có `FetchType.EAGER`. Quan hệ EAGER phải được tải khi entity nguồn được truy cập theo hợp đồng JPA; provider có thể dùng JOIN hoặc truy vấn riêng. Vì vậy, EAGER không đảm bảo chỉ có một SQL query.

`FetchType.LAZY` cho phép trì hoãn tải quan hệ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Trong Hibernate, LAZY thường được thực hiện bằng proxy. Khi code truy cập `employee.getDepartment().getName()`, Hibernate có thể phát sinh query để tải Department.

### 7.1. N+1 query

Ví dụ:

```java
List<Employee> employees = employeeRepository.findAll();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
```

Nếu danh sách có N nhân viên và mỗi Department chưa được tải, việc truy cập quan hệ có thể tạo thêm nhiều query. Kết quả có thể là một query tải employees cộng với các query tải departments. Số query thực tế phụ thuộc cache, provider, batching và cách dữ liệu được truy cập.

### 7.2. Dùng JOIN FETCH

Khi biết một use case cần Department, có thể tải quan hệ trong cùng truy vấn:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.id = :id
       """)
Optional<Employee> findByIdWithDepartment(@Param("id") Long id);
```

Đây là JPQL; `Employee` và `department` là tên entity/property Java. `join fetch` tải association trong cùng query.

### 7.3. Dùng EntityGraph

Có thể chỉ định association cần tải bằng `@EntityGraph`:

```java
@EntityGraph(attributePaths = "department")
Optional<Employee> findByFullName(String fullName);
```

EntityGraph cho phép chọn fetch plan theo từng phương thức truy vấn mà không phải đổi fetch type mặc định của mapping.

Không nên chuyển mọi quan hệ sang EAGER để né lazy loading. Điều đó có thể khiến các query không cần association vẫn tải dữ liệu thừa. Hãy xác định dữ liệu cần cho từng use case và dùng fetch join/entity graph/DTO phù hợp.

## 8. Lazy loading, transaction và DTO

Khi quan hệ LAZY chưa được tải, việc truy cập nó sau khi persistence context đã đóng có thể gây `LazyInitializationException` trong Hibernate.

Ví dụ rủi ro:

```java
public Employee getEmployee(Long id) {
    return employeeRepository.findById(id).orElseThrow();
}

// Ở nơi khác, session đã đóng:
String name = employee.getDepartment().getName();
```

Cách xử lý tốt hơn là tải dữ liệu cần thiết trong transaction và ánh xạ sang DTO trước khi trả khỏi service:

```java
public record EmployeeResponse(
        Long id,
        String fullName,
        String departmentName
) {
}
```

```java
@Transactional(readOnly = true)
public EmployeeResponse getEmployee(Long id) {
    Employee employee = employeeRepository.findByIdWithDepartment(id)
            .orElseThrow();

    return new EmployeeResponse(
            employee.getId(),
            employee.getFullName(),
            employee.getDepartment().getName()
    );
}
```

DTO chứa đúng dữ liệu mà use case cần và không phụ thuộc proxy Hibernate. Cách này cũng tránh vô tình serialize toàn bộ entity graph.

Nếu trả entity trực tiếp qua REST, quan hệ hai chiều có thể tạo vòng lặp JSON: Employee chứa Department, Department lại chứa Employees, mỗi Employee lại tham chiếu Department. DTO là cách rõ ràng để kiểm soát payload.

## 9. Truy vấn theo quan hệ

Spring Data JPA có thể tạo derived query từ đường dẫn thuộc tính:

```java
List<Employee> findByDepartmentId(Long departmentId);

List<Employee> findByDepartmentNameIgnoreCase(String name);
```

Các tên method dùng thuộc tính Java `department.id` và `department.name`, không dùng tên cột SQL `department_id`.

Khi query phức tạp hoặc cần chọn rõ dữ liệu liên quan, có thể dùng `@Query`:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.department.id = :departmentId
       order by e.fullName
       """)
List<Employee> findAllByDepartmentWithDepartment(
        @Param("departmentId") Long departmentId
);
```

Với query phân trang có collection fetch join, cần cẩn thận vì join collection có thể nhân bản hàng và làm sai phân trang. Quan hệ many-to-one thường không nhân bản một employee theo nhiều department, nhưng vẫn cần xem xét query và dữ liệu thực tế.

## 10. Kiểm thử quan hệ Many-to-One

Nên kiểm thử cả mapping và hành vi database:

- Lưu Department.
- Lưu Employee với Department đã tồn tại.
- Flush và clear persistence context để chắc chắn dữ liệu được đọc lại từ database.
- Tải Employee và xác nhận Department đúng.
- Kiểm tra trường hợp Department null nếu quan hệ optional.
- Kiểm tra NOT NULL/foreign key nếu quan hệ bắt buộc.
- Kiểm tra query fetch join/entity graph khi use case cần Department.

Ví dụ với `@DataJpaTest`:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository employeeRepository;

    @Autowired
    private DepartmentRepository departmentRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void storesManyToOneForeignKey() {
        Department department =
                departmentRepository.save(new Department("Engineering"));

        Employee employee =
                employeeRepository.save(new Employee("An", department));

        entityManager.flush();
        entityManager.clear();

        Employee loaded =
                employeeRepository.findByIdWithDepartment(employee.getId())
                        .orElseThrow();

        assertThat(loaded.getDepartment().getName())
                .isEqualTo("Engineering");
    }
}
```

Test giả định có các import JUnit 5, AssertJ, Spring Boot Test và các entity/repository tương ứng. `TestEntityManager` có sẵn trong test slice JPA của Spring Boot. `flush()` đẩy thay đổi xuống database; `clear()` làm rỗng persistence context để lần đọc tiếp theo không chỉ lấy entity đang managed trong bộ nhớ.

Nếu dùng PostgreSQL-specific behavior hoặc cần xác nhận constraint đúng database production, hãy chạy integration test với PostgreSQL/Testcontainers. Embedded database có thể khác về kiểu dữ liệu và hành vi constraint.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Entity bắt buộc Department nhưng department null | Không gán association trước khi lưu | Tải Department và gán vào Employee |
| Foreign key constraint violation | department_id tham chiếu ID không tồn tại | Kiểm tra ID, transaction và thứ tự lưu |
| Cột department_id không được tạo đúng tên | @JoinColumn thiếu/sai name hoặc naming strategy khác dự kiến | Khai báo name rõ và kiểm tra migration/schema |
| LazyInitializationException | Truy cập quan hệ lazy ngoài persistence context | Tải trong transaction, dùng fetch join/entity graph và DTO |
| N+1 query | Truy cập quan hệ lazy trong vòng lặp | Chọn fetch plan phù hợp với use case |
| Xóa Employee làm mất Department | Cascade REMOVE/ALL đặt không phù hợp | Bỏ cascade remove từ phía many-to-one |
| Collection Department không phản ánh Employee mới | Chỉ cập nhật inverse side | Cập nhật owning side Employee.department |
| JSON lặp vô hạn | Serialize quan hệ hai chiều trực tiếp | Trả DTO với cấu trúc rõ ràng |
| Không thể tạo schema do FK | Entity/table/column mapping hoặc migration chưa đồng bộ | Kiểm tra tên bảng, join column và thứ tự migration |

## 12. Checklist thiết kế @ManyToOne

- [ ] Xác định entity phía nhiều và entity phía một.
- [ ] Đặt `@ManyToOne` trên entity phía nhiều.
- [ ] Đặt `@JoinColumn` để mô tả khóa ngoại ở bảng phía nhiều.
- [ ] Chọn `optional` và `nullable` nhất quán với nghiệp vụ và schema.
- [ ] Cân nhắc khai báo `fetch = FetchType.LAZY` và tải association theo use case.
- [ ] Không cascade REMOVE từ child sang parent dùng chung.
- [ ] Nếu quan hệ hai chiều, cập nhật owning side và đồng bộ hai phía bằng helper method.
- [ ] Kiểm tra N+1, lazy loading và serialize entity.
- [ ] Dùng DTO để kiểm soát dữ liệu trả về API.
- [ ] Kiểm thử foreign key, nullability, fetch query và transaction.

## Kết luận

`@ManyToOne` mô tả quan hệ từ entity phía nhiều tới entity phía một; `@JoinColumn` chỉ ra cột khóa ngoại trong bảng entity sở hữu quan hệ. Trong mô hình hai chiều, thuộc tính `@ManyToOne` là owning side và quyết định giá trị foreign key được ghi xuống database.

Thiết kế tốt bắt đầu từ việc đặt đúng khóa ngoại, chọn fetch strategy phù hợp, kiểm soát cascade và duy trì owning side. Hãy tải dữ liệu theo nhu cầu từng use case, dùng transaction và DTO hợp lý, đồng thời kiểm thử mapping với database phù hợp. Những nguyên tắc này giúp quan hệ entity rõ ràng, hiệu quả và ít lỗi khi ứng dụng phát triển.
