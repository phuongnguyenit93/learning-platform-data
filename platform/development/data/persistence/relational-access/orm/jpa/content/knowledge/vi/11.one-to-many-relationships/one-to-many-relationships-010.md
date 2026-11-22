# Kiểm thử thao tác lưu, chuyển và xóa đối tượng liên quan trong quan hệ một-nhiều JPA

Quan hệ **một-nhiều** (*one-to-many*) trong JPA không chỉ là việc khai báo `@OneToMany` và `@ManyToOne`. Trong thực tế, những thao tác như **lưu entity cha cùng các entity con**, **chuyển một entity con từ cha A sang cha B**, **gỡ liên kết**, hoặc **xóa entity con** phải được xác nhận bằng trạng thái dữ liệu thật trong cơ sở dữ liệu, không chỉ bằng việc kiểm tra collection trong bộ nhớ.

Một bài kiểm thử như sau chưa đủ mạnh:

~~~java
department.getEmployees().add(employee);
assertEquals(1, department.getEmployees().size());
~~~

Assertion chỉ cho thấy một `List` Java đã chứa phần tử. Nó **không chứng minh** cột khóa ngoại `employee.department_id` đã được cập nhật, `INSERT` đã chạy, hoặc transaction đã commit.

Để kiểm thử đúng, cần phân biệt ba tầng:

1. **Đồ thị object trong Java:** các reference và collection có nhất quán hay không?
2. **Persistence context của JPA:** entity nào đang được quản lý, thao tác nào được cascade và thời điểm nào flush?
3. **Cơ sở dữ liệu:** FK, bản ghi cha/con, ràng buộc và kết quả transaction có đúng sau khi đọc lại từ một context khác không?

Bài học sử dụng hai mô hình để thể hiện hai kiểu nghiệp vụ rất khác nhau:

- **Phòng ban – nhân viên (`Department` – `Employee`):** nhân viên có thể **chuyển phòng ban**; gỡ liên kết không đồng nghĩa với xóa nhân viên.
- **Đơn hàng – dòng hàng (`SalesOrder` – `SalesOrderLine`):** dòng hàng có vòng đời phụ thuộc đơn; gỡ dòng khỏi đơn thường đồng nghĩa với **xóa dòng** qua `orphanRemoval = true`.

Hai mô hình này không nên trộn chính sách xóa với nhau. Hiểu được sự khác biệt giúp thiết kế test đúng bản chất nghiệp vụ thay vì chỉ kiểm tra annotation.

## 1. Xác định dữ liệu và invariant trước khi viết test

Giả sử phòng ban có nhiều nhân viên:

~~~text
department                      employee
-----------------------         ---------------------------------
id (PK)      1  <----------- N id (PK)
name                             full_name
                                 department_id (FK, nullable)
~~~

Trong ví dụ này:

- Một phòng ban có thể có từ 0 đến nhiều nhân viên.
- Mỗi nhân viên ở tối đa một phòng ban tại một thời điểm.
- Nhân viên có thể tạm thời chưa thuộc phòng ban nào.
- Chuyển nhân viên từ A sang B nghĩa là **cập nhật FK** của chính bản ghi nhân viên, không phải xóa nhân viên cũ rồi tạo bản ghi mới.
- Xóa một phòng ban không mặc nhiên xóa những nhân viên từng thuộc phòng ban đó.
- Xóa nhân viên là một thao tác độc lập với việc gỡ nhân viên khỏi phòng ban.

Những invariant cần kiểm thử:

| Thao tác | Kết quả object mong muốn | Kết quả database mong muốn |
|---|---|---|
| Tạo Department kèm Employee | Cả hai phía tham chiếu đúng nhau | Có bản ghi cha/con, FK trỏ đúng cha |
| Chuyển Employee A → B | A không còn chứa employee, B chứa employee, `employee.department == B` | Vẫn **một** bản ghi Employee, cùng PK, FK đổi từ A sang B |
| Gỡ Employee khỏi Department | Employee không thuộc phòng ban nào | Employee vẫn tồn tại, `department_id = NULL` |
| Xóa Employee | Collection của cha không còn employee | Dòng employee bị `DELETE`, cha vẫn tồn tại |
| Xóa Department nhưng giữ Employee | Nhân viên được gỡ liên kết trước | Cha bị xóa, nhân viên còn tồn tại với FK `NULL` |
| Thử gán Employee cho Department chưa được lưu | Có thể tạo object reference trong Java | Phải xử lý lifecycle đúng, không lưu FK vô hiệu |

Trong mô hình này, cột FK cho phép `NULL` để hỗ trợ trạng thái “nhân viên chưa được gán phòng ban”. Nếu nghiệp vụ yêu cầu mọi nhân viên luôn phải thuộc một phòng ban, schema cần `NOT NULL`, và việc chuyển phải cập nhật trực tiếp từ A sang B mà không flush ở trạng thái trung gian không hợp lệ.

## 2. Phía sở hữu quan hệ quyết định khóa ngoại

Với liên kết hai chiều trong JPA:

~~~java
// Department (phía inverse)
@OneToMany(mappedBy = "department")
private List<Employee> employees;

// Employee (phía owning)
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
~~~

`mappedBy = "department"` trỏ tới **tên field Java** `Employee.department`, không phải tên bảng hoặc cột SQL.

Sơ đồ:

~~~text
Department.employees
    @OneToMany(mappedBy = "department")
              |
              | inverse side
              v
Employee.department
    @ManyToOne
    @JoinColumn(name = "department_id")
              |
              | owning side
              v
employee.department_id
~~~

Thay đổi `Employee.department` là thao tác chủ đạo để JPA cập nhật FK. Chỉ thêm Employee vào `Department.employees` có thể làm collection đúng trong bộ nhớ nhưng **không thay đổi quan hệ được lưu**.

Vì vậy, các test luôn cần quan sát **cột FK sau `flush()` và `clear()`** hoặc đọc lại bằng transaction khác. Chỉ assert `department.getEmployees().size()` là chưa đủ.

## 3. Mô hình thực hành: Department và Employee

Các ví dụ dùng Jakarta Persistence API (package `jakarta.persistence`), Java 17 và JUnit 5. Với ứng dụng Spring Boot, có thể dùng `@DataJpaTest` để chạy kiểm thử tầng repository/JPA. Các class Java sau đặt trong package `com.example.hr.domain`.

### 3.1. Entity Department

~~~java
package com.example.hr.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "department")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @OneToMany(
        mappedBy = "department",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE}
    )
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
        // Constructor cho JPA.
    }

    public Department(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Department name is required");
        }
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return Collections.unmodifiableList(employees);
    }

    public void addEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee");
        employee.transferTo(this);
    }

    public void removeEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee");
        if (employee.getDepartment() == this) {
            employee.transferTo(null);
        }
    }

    // Helper nội bộ, được Employee.transferTo(...) sử dụng.
    void attachEmployee(Employee employee) {
        if (!employees.contains(employee)) {
            employees.add(employee);
        }
    }

    void detachEmployee(Employee employee) {
        employees.remove(employee);
    }
}
~~~

Điểm đáng chú ý:

- `@OneToMany(mappedBy = "department")` là phía inverse.
- `cascade = {PERSIST, MERGE}` cho phép thao tác lưu/merge từ Department lan sang Employee phù hợp.
- **Không có `CascadeType.REMOVE`** vì xóa phòng ban không nên xóa nhân viên.
- **Không có `orphanRemoval = true`** vì nhân viên có thể gỡ/chuyển phòng ban mà vẫn tồn tại.
- Collection chỉ trả ra view không thể sửa trực tiếp, để người gọi dùng helper giữ cả hai phía đồng bộ.

`CascadeType.MERGE` được khai báo để minh họa một chính sách cascade có chọn lọc. Trong nhiều hệ thống, chỉ `PERSIST` có thể đủ; đừng mặc định bật `ALL` khi vòng đời con không phụ thuộc cha.

### 3.2. Entity Employee

~~~java
package com.example.hr.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "employee")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 150)
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected Employee() {
    }

    public Employee(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Employee name is required");
        }
        this.fullName = fullName;
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

    public void transferTo(Department target) {
        if (this.department == target) {
            return;
        }

        Department previous = this.department;

        // Xóa tham chiếu ở collection phía cũ.
        if (previous != null) {
            previous.detachEmployee(this);
        }

        // Sửa owning side; JPA dựa vào field này để ghi FK.
        this.department = target;

        // Đồng bộ collection ở phía mới.
        if (target != null) {
            target.attachEmployee(this);
        }
    }
}
~~~

Ở đây `department_id` cho phép `NULL`, nên việc chuyển đến `null` có nghĩa nghiệp vụ “chưa được phân phòng”, không phải xóa Employee.

`transferTo(...)` cập nhật cả ba nơi liên quan trong object graph:

1. Collection của phòng ban cũ.
2. Field `Employee.department` (owning side).
3. Collection của phòng ban mới.

Trong một persistence context nhất quán, phương thức này giúp tránh trạng thái A vẫn chứa employee trong khi Employee đã trỏ B.

**Giới hạn của ví dụ:** helper so sánh object bằng tham chiếu `==` để minh họa entity managed trong cùng persistence context. Trong hệ thống xử lý đối tượng detached, proxy hoặc nhiều persistence context, nên xác định rõ chiến lược identity và không trộn các instance của cùng bản ghi từ nhiều context trong cùng một thao tác domain.

### 3.3. SQL schema tham chiếu

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE department (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE employee (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    department_id BIGINT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES department(id)
);

CREATE INDEX idx_employee_department_id
    ON employee(department_id);
~~~

Cột `employee.department_id` biểu diễn FK. Không có bảng nối riêng trong mô hình này.

Nếu ứng dụng dùng Hibernate schema generation, ORM có thể tạo SQL tương đương dựa vào mapping; với hệ thống production, migration được kiểm soát là cách phổ biến để đảm bảo schema thực tế khớp mô hình.

## 4. Chuẩn bị môi trường kiểm thử tích hợp JPA

### 4.1. Vì sao cần integration test?

Unit test thuần gọi:

~~~java
Employee employee = new Employee("Lan");
Department department = new Department("Engineering");
department.addEmployee(employee);

assertSame(department, employee.getDepartment());
~~~

là hữu ích để kiểm tra helper và invariant trong Java. Nhưng nó **không** thực thi JPA provider, SQL, FK hay các lifecycle callback.

Để xác nhận mapping và transaction, cần kiểm thử trên môi trường có:

- JPA provider thực sự (Hibernate, EclipseLink...).
- `EntityManager`.
- Datasource/JDBC driver.
- Database/schema tương thích.
- Transaction manager phù hợp.
- Cơ chế tạo và dọn dữ liệu test.

Nếu ứng dụng chạy PostgreSQL/MySQL/SQL Server trong production, integration test với cùng họ DB hoặc Testcontainers thường phản ánh hành vi FK, identity, constraint và thứ tự SQL tốt hơn khi chỉ dùng H2. H2 vẫn hữu ích cho kiểm thử nhanh, nhưng không nên mặc định dialect và constraint giống hệt production.

### 4.2. Chọn `@DataJpaTest` trong Spring Boot

Một test đơn giản:

~~~java
package com.example.hr.persistence;

import com.example.hr.domain.Department;
import com.example.hr.domain.Employee;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
class DepartmentMappingTest {

    @Autowired
    private EntityManager entityManager;

    @Test
    void basicJpaWiringIsAvailable() {
        Department department = new Department("Engineering");
        entityManager.persist(department);
        entityManager.flush();

        assertNotNull(department.getId());
    }
}
~~~

`@DataJpaTest` là tính năng của Spring Boot Test, không phải annotation thuộc chuẩn JPA. Mặc định nhiều cấu hình `@DataJpaTest` tạo transaction cho mỗi test và **rollback khi test kết thúc**.

Điều này tốt cho cô lập dữ liệu giữa các test. Nhưng cần nhớ: **`flush()` thành công trong test rollback không phải bằng chứng dữ liệu đã được commit**. Nếu bài test cần xác minh commit thật, phải dùng một phương pháp điều khiển transaction khác ở phần sau.

Ví dụ giả định các entity nằm trong phạm vi quét của cấu hình ứng dụng và dependency JPA/JUnit đã có. Nếu package structure khác, cần cấu hình entity scanning/test bootstrap tương ứng.

### 4.3. Nguyên tắc `flush()` rồi `clear()`

Mẫu phổ biến:

~~~java
entityManager.persist(department);
entityManager.flush();
entityManager.clear();

Department reloaded =
    entityManager.find(Department.class, departmentId);
~~~

- `flush()` buộc provider đồng bộ những SQL cần thiết tại thời điểm đó.
- `clear()` tách các managed entity ra khỏi persistence context hiện tại, để lần `find` sau không đơn giản trả object cũ từ first-level cache.
- `find(...)` sau `clear()` giúp quan sát mapping qua một lần nạp lại thay vì chỉ kiểm tra trạng thái object Java.

**Lưu ý:** Sau `clear()`, những object cũ trở thành detached. Khi muốn tiếp tục sửa dữ liệu trong cùng test, hãy lấy lại entity managed bằng `find(...)`; đừng tiếp tục thao tác trên object detached rồi mong JPA tự lưu thay đổi.

`flush()` rồi `clear()` vẫn nằm trong **cùng transaction test**. Nó giúp xác nhận SQL/mapping tốt hơn, nhưng không thay thế kiểm thử commit thực tế và khả năng quan sát từ transaction độc lập.

## 5. Kiểm thử lưu Department cùng các Employee mới

### 5.1. Test cascade PERSIST

Vì `Department.employees` có `cascade = PERSIST`, lưu Department mới có thể kéo theo lưu các Employee mới được gắn đúng quan hệ.

~~~java
@Test
void persistDepartmentAlsoPersistsItsEmployees() {
    Department department = new Department("Engineering");
    Employee lan = new Employee("Lan");
    Employee minh = new Employee("Minh");

    department.addEmployee(lan);
    department.addEmployee(minh);

    // Xác nhận object graph trước persistence.
    assertSame(department, lan.getDepartment());
    assertSame(department, minh.getDepartment());
    assertEquals(2, department.getEmployees().size());

    entityManager.persist(department);
    entityManager.flush();

    Long departmentId = department.getId();
    Long lanId = lan.getId();
    Long minhId = minh.getId();

    assertNotNull(departmentId);
    assertNotNull(lanId);
    assertNotNull(minhId);

    entityManager.clear();

    Department dbDepartment =
        entityManager.find(Department.class, departmentId);

    Employee dbLan =
        entityManager.find(Employee.class, lanId);

    Employee dbMinh =
        entityManager.find(Employee.class, minhId);

    assertNotNull(dbDepartment);
    assertNotNull(dbLan);
    assertNotNull(dbMinh);

    assertEquals(departmentId, dbLan.getDepartment().getId());
    assertEquals(departmentId, dbMinh.getDepartment().getId());
    assertEquals(2, dbDepartment.getEmployees().size());
}
~~~

Test có hai loại assertion:

- **Trước lưu:** helper đã đồng bộ hai phía trong Java.
- **Sau flush/clear:** thực sự có hai Employee trong DB với FK đến Department mong muốn.

### 5.2. Vì sao chỉ `persist(department)` có thể đủ?

Ở ví dụ trên, cascade PERSIST truyền thao tác từ Department qua collection đến những Employee mới. Nếu bỏ cascade này, lời gọi `persist(department)` không mặc nhiên lưu nhân viên; test có thể thấy parent được lưu nhưng child không tồn tại hoặc provider báo lỗi tùy trường hợp.

Một giải pháp khác, không cần cascade, là lưu tường minh:

~~~java
entityManager.persist(department);
entityManager.persist(lan);
entityManager.persist(minh);
~~~

Khi quyết định cascade, hãy nhìn **quy tắc vòng đời**. Trong mô hình nhân viên có thể chuyển phòng ban, việc cascade PERSIST từ Department tới Employee không nhất thiết sai, nhưng nhiều hệ thống nhân sự tạo Employee qua service riêng và chỉ dùng quan hệ tham chiếu; lúc đó không cần cascade PERSIST.

### 5.3. Test dữ liệu thực bằng truy vấn JPQL

Không chỉ đếm collection:

~~~java
Long count = entityManager.createQuery(
    "SELECT COUNT(e) FROM Employee e " +
    "WHERE e.department.id = :departmentId",
    Long.class
)
.setParameter("departmentId", departmentId)
.getSingleResult();

assertEquals(2L, count);
~~~

JPQL truy vấn theo property `Employee.department`. Provider chuyển thành SQL dựa trên FK `employee.department_id`.

Nếu tên bảng/cột và annotation lệch nhau, flush hoặc query sẽ giúp bộc lộ lỗi mà unit test List không thể phát hiện.

## 6. Kiểm thử chuyển Employee từ Department A sang B

Đây là phần quan trọng nhất khi nghiệp vụ cho phép “chuyển đối tượng liên quan”.

### 6.1. Mục tiêu của thao tác chuyển

Ban đầu:

~~~text
Department A (id=10)         Department B (id=20)
    |                             |
    v                             |
Employee E (id=100)               |
department_id = 10                |
~~~

Sau chuyển:

~~~text
Department A (id=10)         Department B (id=20)
                                  |
                                  v
                             Employee E (id=100)
                             department_id = 20
~~~

Invariant:

1. Employee **giữ nguyên ID** 100.
2. Không sinh bản ghi Employee mới.
3. FK `department_id` đổi từ 10 sang 20.
4. Collection phía A không còn Employee.
5. Collection phía B chứa Employee.
6. Đối tượng Employee có `department` trỏ tới B.
7. Nếu transaction rollback, FK không phải giữ kết quả chuyển như một giao dịch đã commit.

### 6.2. Test chuyển bằng managed entity

~~~java
@Test
void transferEmployeeUpdatesOwningSideAndBothCollections() {
    Department from = new Department("Engineering");
    Department to = new Department("Product");
    Employee employee = new Employee("Lan");

    from.addEmployee(employee);

    entityManager.persist(from);
    entityManager.persist(to);
    entityManager.flush();

    Long employeeId = employee.getId();
    Long fromId = from.getId();
    Long toId = to.getId();

    entityManager.clear();

    // Lấy các entity managed mới, tránh sửa object detached.
    Department managedFrom =
        entityManager.find(Department.class, fromId);

    Department managedTo =
        entityManager.find(Department.class, toId);

    Employee managedEmployee =
        entityManager.find(Employee.class, employeeId);

    managedTo.addEmployee(managedEmployee);

    // Test object graph trong persistence context.
    assertSame(managedTo, managedEmployee.getDepartment());
    assertFalse(managedFrom.getEmployees().contains(managedEmployee));
    assertTrue(managedTo.getEmployees().contains(managedEmployee));

    entityManager.flush();
    entityManager.clear();

    Employee reloaded =
        entityManager.find(Employee.class, employeeId);

    assertNotNull(reloaded);
    assertEquals(employeeId, reloaded.getId());
    assertEquals(toId, reloaded.getDepartment().getId());

    // Đọc lại collection từ DB.
    Department dbFrom =
        entityManager.find(Department.class, fromId);

    Department dbTo =
        entityManager.find(Department.class, toId);

    assertTrue(dbFrom.getEmployees().isEmpty());
    assertEquals(1, dbTo.getEmployees().size());
    assertEquals(
        employeeId,
        dbTo.getEmployees().get(0).getId()
    );
}
~~~

Nhờ `@ManyToOne` là owning side, thay đổi `managedEmployee.department` được JPA chuyển thành việc cập nhật khóa ngoại khi flush.

SQL có thể tương tự:

~~~sql
UPDATE employee
SET department_id = 20
WHERE id = 100;
~~~

Đây là **UPDATE một dòng** về mặt nghiệp vụ, không phải “DELETE E khỏi A rồi INSERT một Employee mới vào B”.

### 6.3. Kiểm thử cùng ID sau khi chuyển

Việc xác nhận ID không đổi quan trọng, bởi nếu code chọn cách “tạo Employee mới trong phòng B, xóa Employee cũ ở A”, hệ thống có thể vô tình làm mất lịch sử tham chiếu đến employee ID cũ.

Có thể kiểm tra thêm:

~~~java
Long count = entityManager.createQuery(
    "SELECT COUNT(e) FROM Employee e WHERE e.id = :id",
    Long.class
)
.setParameter("id", employeeId)
.getSingleResult();

assertEquals(1L, count);
~~~

Cũng nên khẳng định số employee thuộc A bằng 0 và thuộc B bằng 1 bằng các truy vấn độc lập nếu use case yêu cầu.

## 7. Lỗi điển hình: Chỉ sửa collection inverse

Giả sử một entity có setter công khai cho collection:

~~~java
Department a = entityManager.find(Department.class, aId);
Department b = entityManager.find(Department.class, bId);
Employee e = entityManager.find(Employee.class, employeeId);

// Chỉ sửa các collection phía @OneToMany:
a.getMutableEmployees().remove(e);
b.getMutableEmployees().add(e);

// e.department vẫn là a!
entityManager.flush();
~~~

`getMutableEmployees()` trong đoạn giả định trên chỉ để minh họa anti-pattern; **entity của bài đã chủ động không cung cấp** API này.

Vì `Department.employees` là inverse side, sửa collection nhưng không cập nhật `Employee.department` khiến object graph mâu thuẫn. SQL FK có thể không đổi sang B.

Cách đúng là dùng helper đặt quan hệ ở owning side:

~~~java
b.addEmployee(e);
// hoặc:
e.transferTo(b);
~~~

Một integration test nên tái hiện lỗi bằng việc đọc **FK từ database sau flush/clear** thay vì chỉ assert size của hai collection.

### 7.1. `mappedBy` không phải tên cột SQL

Sai:

~~~java
@OneToMany(mappedBy = "department_id")
private List<Employee> employees;
~~~

Đúng:

~~~java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
~~~

Tên `department` là property Java trong Employee; cột SQL tương ứng đặt tại `@JoinColumn(name = "department_id")`.

## 8. Test gỡ liên kết nhưng không xóa Employee

Trong mô hình nhân sự, một nhân viên có thể chưa thuộc phòng ban. Gỡ khỏi Department nghĩa là `employee.department_id = NULL`, không có `DELETE`.

### 8.1. Test unlink

~~~java
@Test
void unlinkEmployeeKeepsEmployeeRow() {
    Department department = new Department("Support");
    Employee employee = new Employee("Minh");
    department.addEmployee(employee);

    entityManager.persist(department);
    entityManager.flush();

    Long departmentId = department.getId();
    Long employeeId = employee.getId();

    department.removeEmployee(employee);

    assertNull(employee.getDepartment());
    assertFalse(department.getEmployees().contains(employee));

    entityManager.flush();
    entityManager.clear();

    Employee reloaded =
        entityManager.find(Employee.class, employeeId);

    Department reloadedDepartment =
        entityManager.find(Department.class, departmentId);

    assertNotNull(reloaded); // Employee không bị xóa.
    assertNull(reloaded.getDepartment());
    assertTrue(reloadedDepartment.getEmployees().isEmpty());
}
~~~

Vì `Employee.department` cho phép `null`, JPA có thể cập nhật:

~~~sql
UPDATE employee
SET department_id = NULL
WHERE id = ?;
~~~

Nếu schema dùng `department_id NOT NULL`, thao tác này không hợp lệ. Khi đó nghiệp vụ phải **chuyển trực tiếp sang phòng ban mới** hoặc xóa employee theo chính sách, không để một khoảng trạng thái “không phòng ban” được flush.

### 8.2. Phân biệt ba hành động

| Hành động | FK Employee | Bản ghi Employee |
|---|---|---|
| Chuyển A sang B | Từ `A.id` sang `B.id` | Giữ nguyên |
| Gỡ khỏi mọi phòng ban | Thành `NULL` nếu được phép | Giữ nguyên |
| Xóa Employee | Dòng không còn | Bị DELETE |

Tránh đặt tên method như `removeEmployee` mà không xác định rõ nghĩa “remove khỏi collection” hay “xóa bản ghi”. Trong model ở đây, `Department.removeEmployee` là **unlink**, không phải xóa nhân viên khỏi DB.

## 9. Test xóa Employee nhưng vẫn giữ Department

Để xóa vĩnh viễn một employee, cần thao tác remove trên **managed entity** hoặc thực hiện delete query/repository operation thích hợp. Việc gỡ khỏi collection không tự xóa vì model này **không dùng orphanRemoval**.

### 9.1. Test xóa tường minh

~~~java
@Test
void deletingEmployeeDoesNotDeleteDepartment() {
    Department department = new Department("Operations");
    Employee employee = new Employee("Hà");
    department.addEmployee(employee);

    entityManager.persist(department);
    entityManager.flush();

    Long departmentId = department.getId();
    Long employeeId = employee.getId();

    // Giữ object graph nhất quán trước khi xóa.
    department.removeEmployee(employee);

    // Xóa một entity đang managed.
    entityManager.remove(employee);

    entityManager.flush();
    entityManager.clear();

    assertNull(entityManager.find(Employee.class, employeeId));

    Department remaining =
        entityManager.find(Department.class, departmentId);

    assertNotNull(remaining);
    assertTrue(remaining.getEmployees().isEmpty());
}
~~~

Tùy cách provider tổ chức SQL, việc chuyển FK về null trước khi xóa có thể được tối ưu hoặc không cần thiết, nhưng với mô hình FK nullable, thao tác cuối cùng vẫn là Employee bị xóa và Department còn tồn tại.

**Không bật `cascade = REMOVE` từ Employee sang Department.** Nhiều employee có thể tham chiếu cùng department; xóa một nhân viên không được xóa phòng ban dùng chung.

### 9.2. Vì sao `remove` khác sửa collection?

~~~java
department.removeEmployee(employee);
~~~

Đây là thay đổi association; vì `orphanRemoval = false`, bản ghi Employee vẫn tồn tại.

~~~java
entityManager.remove(employee);
~~~

Đây mới là yêu cầu JPA xóa một entity cụ thể. Test cần xác nhận bằng `find` sau `flush/clear` hoặc truy vấn độc lập.

### 9.3. `remove` trên detached entity

Nếu đã gọi `entityManager.clear()`, object `employee` trước đó trở thành detached. Gọi `entityManager.remove(employee)` trực tiếp trên detached entity không phải cách sử dụng hợp lệ chung. Hãy tìm lại entity managed:

~~~java
Employee managed =
    entityManager.find(Employee.class, employeeId);

if (managed != null) {
    entityManager.remove(managed);
}
~~~

Hoặc dùng repository delete theo ID theo hợp đồng thực tế của framework. Đừng trông đợi một object cũ tự động trở lại managed.

## 10. Test xóa Department nhưng giữ các Employee

Mô hình nhân sự chọn chính sách: xóa phòng ban thì giữ nhân viên, đồng thời gỡ FK của từng người về `NULL`.

Nếu xóa Department khi vẫn còn employee tham chiếu, database FK có thể ngăn xóa vì các bản ghi con còn chỉ vào Department. Vì không bật cascade REMOVE và không cấu hình DB `ON DELETE SET NULL`, service phải xử lý liên kết trước.

### 10.1. Service minh họa

~~~java
@Transactional
public void deleteDepartmentButKeepEmployees(Long departmentId) {
    Department department =
        entityManager.find(Department.class, departmentId);

    if (department == null) {
        return;
    }

    // Lấy bản sao để tránh sửa List trong lúc đang duyệt.
    List<Employee> employees =
        new ArrayList<>(department.getEmployees());

    for (Employee employee : employees) {
        department.removeEmployee(employee);
    }

    entityManager.remove(department);
}
~~~

`@Transactional` ở đây là annotation của Spring, không phải một phần của JPA thuần. Cần import `java.util.ArrayList` và `java.util.List` cùng những dependency của service. Trong một transaction, JPA có thể flush những cập nhật FK và thao tác xóa ở thứ tự thích hợp; việc giữ FK nullable và SQL transaction giúp mô hình này khả thi.

Nếu nghiệp vụ yêu cầu **không được xóa phòng ban đang có nhân viên**, policy lại khác: kiểm tra số nhân viên và từ chối operation, đồng thời dùng FK restrict/NO ACTION ở DB. Không có một chính sách xóa đúng cho mọi domain.

### 10.2. Test kết quả

~~~java
@Test
void deletingDepartmentKeepsEmployeesUnassigned() {
    Department department = new Department("Temporary");
    Employee employee = new Employee("Linh");
    department.addEmployee(employee);

    entityManager.persist(department);
    entityManager.flush();

    Long departmentId = department.getId();
    Long employeeId = employee.getId();

    department.removeEmployee(employee);
    entityManager.remove(department);

    entityManager.flush();
    entityManager.clear();

    assertNull(entityManager.find(Department.class, departmentId));

    Employee remaining =
        entityManager.find(Employee.class, employeeId);

    assertNotNull(remaining);
    assertNull(remaining.getDepartment());
}
~~~

Kiểm tra cả **cha đã xóa** lẫn **con vẫn tồn tại** mới thể hiện đầy đủ chính sách.

## 11. Trường hợp khác: Aggregate cha sở hữu vòng đời con

Không phải mọi quan hệ one-to-many cho phép chuyển con hoặc gỡ mà vẫn giữ con. Với **SalesOrder – SalesOrderLine**:

- Một đơn hàng sở hữu các dòng hàng.
- Mỗi dòng hàng chỉ có nghĩa khi thuộc một đơn.
- Nếu người dùng xóa dòng khỏi đơn đang chỉnh sửa, dòng đó nên bị xóa khỏi database.
- Dòng của đơn A không được tự ý chuyển sang đơn B sau khi đã persisted, theo chính sách nghiệp vụ ví dụ này.

Trong trường hợp đó, `orphanRemoval = true` phù hợp hơn.

### 11.1. Sơ đồ

~~~text
sales_order                      sales_order_line
-----------------------          -------------------------------
id (PK)          1 <-------- N  id (PK)
code                              order_id (FK, NOT NULL)
                                  sku
                                  quantity
~~~

Khác với Employee, SalesOrderLine không được tồn tại khi `order_id` là `NULL`.

### 11.2. SalesOrder dùng cascade và orphanRemoval

~~~java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<SalesOrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public SalesOrder(String orderCode) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("Order code is required");
        }
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }

    public List<SalesOrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(String sku, int quantity) {
        SalesOrderLine line = new SalesOrderLine(this, sku, quantity);
        lines.add(line);
    }

    public void removeLine(SalesOrderLine line) {
        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }
}
~~~

### 11.3. SalesOrderLine bắt buộc có cha

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "sales_order_line")
public class SalesOrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "sku", nullable = false, length = 50)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected SalesOrderLine() {
    }

    SalesOrderLine(SalesOrder order, String sku, int quantity) {
        if (order == null || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid order line");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        this.order = order;
        this.sku = sku;
        this.quantity = quantity;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

`detachFromOrder()` chỉ được gọi khi dòng bị **loại khỏi collection chứa nó**, và mapping `orphanRemoval = true` sẽ yêu cầu xóa entity orphan trong quá trình flush. Dòng không được phép tồn tại độc lập trong DB. Đây không phải API cho phép reparent một line đã persisted.

### 11.4. Schema ràng buộc

~~~sql
CREATE TABLE sales_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE sales_order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES sales_order(id),
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Ở đây FK là `NOT NULL`, phù hợp với ý nghĩa “dòng hàng không tồn tại độc lập”.

## 12. Test `orphanRemoval = true` khi xóa dòng khỏi đơn

### 12.1. Tạo trước hai dòng

~~~java
SalesOrder order = new SalesOrder("ORD-1001");
order.addLine("BOOK-01", 2);
order.addLine("PEN-02", 5);

entityManager.persist(order);
entityManager.flush();

Long orderId = order.getId();
Long removedLineId = order.getLines().get(0).getId();
Long keptLineId = order.getLines().get(1).getId();
~~~

Do `cascade = ALL` bao gồm PERSIST, hai line được lưu cùng order. `SalesOrderLine.order` trỏ đúng `SalesOrder` ngay từ constructor.

### 12.2. Xóa một dòng và đọc lại DB

~~~java
@Test
void removingLineFromOrderDeletesOrphanedRow() {
    SalesOrder order = new SalesOrder("ORD-1002");
    order.addLine("BOOK-01", 2);
    order.addLine("PEN-02", 5);

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long removedLineId = order.getLines().get(0).getId();
    Long keptLineId = order.getLines().get(1).getId();

    // Chỉ bỏ dòng đầu khỏi aggregate.
    SalesOrderLine removed = order.getLines().get(0);
    order.removeLine(removed);

    assertEquals(1, order.getLines().size());

    entityManager.flush();
    entityManager.clear();

    SalesOrder reloaded =
        entityManager.find(SalesOrder.class, orderId);

    assertNotNull(reloaded);
    assertEquals(1, reloaded.getLines().size());
    assertEquals(
        keptLineId,
        reloaded.getLines().get(0).getId()
    );

    // Dòng đã orphaned bị xóa, không chỉ bỏ FK.
    assertNull(
        entityManager.find(SalesOrderLine.class, removedLineId)
    );

    // Dòng còn lại không bị xóa.
    assertNotNull(
        entityManager.find(SalesOrderLine.class, keptLineId)
    );
}
~~~

Test này đánh giá đủ ba điểm:

1. Collection trong bộ nhớ đã giảm số phần tử.
2. Dòng bị remove **không còn trong DB** sau flush/clear.
3. Dòng còn lại và order chính vẫn tồn tại.

Nếu chỉ assert `order.getLines().size() == 1`, có thể bỏ sót lỗi mapping orphanRemoval khiến row chưa bị xóa.

### 12.3. `orphanRemoval` khác `CascadeType.REMOVE`

| Cơ chế | Trigger thường gặp | Ví dụ |
|---|---|---|
| `orphanRemoval = true` | Entity con bị tách khỏi quan hệ chứa nó | `order.removeLine(line)` |
| `CascadeType.REMOVE` | Entity cha bị remove | `entityManager.remove(order)` kéo theo remove line |
| Không có orphanRemoval | Gỡ con thường chỉ thay đổi association | `department.removeEmployee(employee)` để Employee còn sống |
| Xóa tường minh | Gọi remove trên entity con managed | `entityManager.remove(employee)` |

`CascadeType.ALL` bao gồm `REMOVE`, nhưng hai cơ chế vẫn có ngữ nghĩa khác nhau. Trong quan hệ cha sở hữu hoàn toàn con, thường có thể dùng cả cascade và orphanRemoval; trong quan hệ cha/con độc lập có thể chuyển cha, **không nên bật orphanRemoval chỉ vì collection có nhiều phần tử**.

## 13. Vì sao chuyển con khi có `orphanRemoval = true` là nguy hiểm?

Một số người viết logic:

~~~java
orderA.getLines().remove(line);
orderB.getLines().add(line);
line.setOrder(orderB);
~~~

và nghĩ JPA sẽ luôn hiểu đó là “chuyển line từ A sang B”. Nhưng trong mô hình có `orphanRemoval = true`:

- Tháo line khỏi collection của A có thể đánh dấu line là **orphan** và lên lịch xóa.
- Gắn lại line sang B **không bảo đảm** hủy lệnh xóa đã lên lịch theo cách di động giữa provider.
- JPA không định nghĩa việc “chuyển parent” của entity orphan như một thao tác an toàn chung.
- Có thể phát sinh lỗi “deleted entity re-saved”, exception trạng thái entity hoặc SQL trái mong đợi.

Nếu nghiệp vụ **cho phép chuyển Employee giữa Department**, dùng mô hình không orphanRemoval, cập nhật owning FK và giữ identity của employee.

Nếu nghiệp vụ quy định SalesOrderLine là thành phần không được chuyển từ order này sang order khác, hãy **từ chối reparent** trong domain. Nếu cần nhân bản nội dung sang order mới, thường tạo **line mới với identity mới**, đồng thời thực hiện quy tắc xóa/sửa line cũ theo nghiệp vụ.

### 13.1. Test quy tắc không cho chuyển

Thay vì tạo một bài test mong ORM tự sửa tình trạng orphan, định nghĩa API domain không cho thay đổi trường `SalesOrderLine.order` tùy ý:

~~~java
// Không cung cấp:
public void setOrder(SalesOrder anotherOrder);

// Chỉ cho phép:
order.removeLine(line); // line bị xóa theo orphanRemoval
otherOrder.addLine(sku, quantity); // line mới
~~~

Kiểm thử nên xác nhận code nghiệp vụ **không có đường chuyển line đã persisted** nếu đây là invariant của mô hình. Chỉ chọn một mô hình reparent nếu yêu cầu nghiệp vụ thật sự cần và mapping được thiết kế phù hợp.

## 14. Test xóa cha khi cascade REMOVE được bật

Trong mô hình `SalesOrder`:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<SalesOrderLine> lines;
~~~

Xóa order được kỳ vọng xóa cả line phụ thuộc.

~~~java
@Test
void deletingOrderAlsoDeletesItsLines() {
    SalesOrder order = new SalesOrder("ORD-1003");
    order.addLine("BOOK-01", 1);
    order.addLine("PEN-02", 3);

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long firstLineId = order.getLines().get(0).getId();
    Long secondLineId = order.getLines().get(1).getId();

    entityManager.remove(order);
    entityManager.flush();
    entityManager.clear();

    assertNull(entityManager.find(SalesOrder.class, orderId));

    assertNull(
        entityManager.find(SalesOrderLine.class, firstLineId)
    );

    assertNull(
        entityManager.find(SalesOrderLine.class, secondLineId)
    );
}
~~~

Khi có FK `sales_order_line.order_id` bắt buộc tham chiếu order, provider cần xử lý xóa các child trước khi xóa parent theo cách phù hợp constraint.

Nếu dùng database `ON DELETE CASCADE` thay cho cascade ORM, SQL và entity callbacks có thể khác. Không mặc định rằng DB-level cascade và JPA cascade là cùng một cơ chế.

## 15. Test rollback: Flush thành công vẫn có thể mất toàn bộ thay đổi

Một test có thể gọi:

~~~java
entityManager.persist(order);
entityManager.flush();

assertNotNull(order.getId());
~~~

Điều này chỉ cho thấy thao tác đã được đồng bộ trong **transaction hiện tại**, không chứng minh đã commit.

### 15.1. `@DataJpaTest` thường rollback mặc định

Với Spring Boot Test, các test transaction thường rollback sau test, nên dữ liệu không tồn tại ở trạng thái committed sau khi test kết thúc. Test vẫn có thể đọc lại sau `clear()` trong cùng transaction và thấy bản ghi.

Điều cần phân biệt:

~~~text
persist -> flush -> clear -> find (cùng transaction)
    |
    +-- xác nhận mapping/SQL trong giao dịch
    |
    +-- KHÔNG chứng minh COMMIT

persist -> flush -> commit thành công
    |
    +-- context/transaction mới -> find
        |
        +-- xác nhận dữ liệu đã tồn tại sau COMMIT
~~~

### 15.2. Kiểm thử commit thật bằng TransactionTemplate

Khi cần kiểm tra dữ liệu đã commit (ví dụ lỗi deferred constraint hoặc kết quả đọc ở transaction mới), có thể tạo integration test không bọc `@Transactional` ở method test và điều phối transaction tường minh.

~~~java
@SpringBootTest
class DepartmentCommitIntegrationTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private EntityManager entityManager;

    @Test
    void employeeExistsAfterCommittedTransaction() {
        TransactionTemplate template =
            new TransactionTemplate(transactionManager);

        Long employeeId = template.execute(status -> {
            Department department = new Department("Finance");
            Employee employee = new Employee("Linh");

            department.addEmployee(employee);
            entityManager.persist(department);
            entityManager.flush();

            return employee.getId();
        });
        // template.execute(...) đã kết thúc transaction
        // (commit thành công nếu không có lỗi).

        assertNotNull(employeeId);

        Boolean exists = template.execute(status ->
            entityManager.find(Employee.class, employeeId) != null
        );

        assertEquals(Boolean.TRUE, exists);
    }
}
~~~

Ví dụ giả định có import Spring và JPA tương ứng, và test không chạy trong một transaction bên ngoài. Với `@SpringBootTest` thông thường, `EntityManager` được inject thường là proxy gắn với transaction hiện tại. Các callback của `TransactionTemplate` sử dụng transaction manager để tạo ranh giới hợp lệ.

Nếu framework/test setup đã mở một transaction khác, cần xem propagation và cấu hình thật, thay vì ngầm coi callback luôn tạo commit độc lập.

### 15.3. Kiểm thử rollback đúng nghĩa

Một hướng là dùng `TransactionTemplate` và chủ động đánh dấu rollback-only:

~~~java
TransactionTemplate template =
    new TransactionTemplate(transactionManager);

Long attemptedId = template.execute(status -> {
    Department department = new Department("Rollback Team");
    entityManager.persist(department);
    entityManager.flush();

    Long id = department.getId();
    status.setRollbackOnly();
    return id;
});

// Transaction thứ nhất đã rollback khi template trả về.
Boolean exists = template.execute(status ->
    entityManager.find(Department.class, attemptedId) != null
);

assertEquals(Boolean.FALSE, exists);
~~~

Bài test này minh họa ID có thể được cấp dù dòng không được commit. Hãy dùng DB test cô lập; không suy luận rằng sequence hoặc auto-increment sẽ hoàn lại giá trị đã cấp sau rollback.

## 16. Kiểm tra khóa ngoại ở tầng DB thay vì chỉ ở JPA object graph

Với liên kết `Employee.department`, một native SQL query có thể giúp xác nhận FK thực tế:

~~~java
Object fk = entityManager.createNativeQuery(
    "SELECT department_id FROM employee WHERE id = :id"
)
.setParameter("id", employeeId)
.getSingleResult();
~~~

Giá trị số được JDBC/provider trả về có thể là kiểu Java khác nhau giữa database/driver. Nếu cần so sánh nhất quán, dùng một phép chuyển có kiểm soát, chẳng hạn với `Number`:

~~~java
Long actualDepartmentId =
    fk == null ? null : ((Number) fk).longValue();

assertEquals(expectedDepartmentId, actualDepartmentId);
~~~

Phương pháp này phù hợp nếu test thực sự cần khẳng định tên cột/DB vật lý. Với bài test tính di động, JPQL:

~~~java
Long count = entityManager.createQuery(
    "SELECT COUNT(e) FROM Employee e " +
    "WHERE e.department.id = :departmentId",
    Long.class
)
.setParameter("departmentId", expectedDepartmentId)
.getSingleResult();
~~~

thường đủ để quan sát mapping.

Nếu dùng native query trong cùng persistence context, cần `flush()` trước để dữ liệu SQL nhất quán với thay đổi đang chờ. Đọc lại sau `clear()` giúp tránh nhầm với managed object cũ; một transaction mới còn là bước cần thiết khi mục tiêu là xác minh commit/visibility.

## 17. Cạnh tranh và kiểm thử nhiều transaction

### 17.1. Hai request đồng thời chuyển một Employee

Giả sử Employee E đang ở phòng A. Hai request:

~~~text
Transaction T1                      Transaction T2
-------------------------------     -------------------------------
Đọc E.department = A               Đọc E.department = A
Chuyển E sang B                     Chuyển E sang C
Commit                              Commit
~~~

Nếu không có biện pháp xử lý concurrency, kết quả có thể là **last writer wins**, hoặc một transaction gặp xung đột tùy isolation/locking. Test một transaction đơn lẻ không phát hiện được những rủi ro này.

Khi cần ngăn cập nhật mất (*lost update*), có thể thêm optimistic locking:

~~~java
@Version
@Column(name = "version", nullable = false)
private long version;
~~~

Đặt `@Version` ở Employee và tạo cột version tương ứng, sau đó kiểm thử hai persistence context/transaction đồng thời sửa cùng Employee. Một transaction có thể gặp `OptimisticLockException` khi flush/commit nếu version đã thay đổi.

Không chỉ thêm `@Version` vào code mà không cập nhật schema và xử lý exception. Hãy quyết định có retry hay báo xung đột cho người dùng theo nghiệp vụ.

### 17.2. Test race condition không được dựa vào sleep tùy ý

Kiểm thử đồng thời cần ranh giới transaction xác định và cơ chế điều phối luồng phù hợp; dùng latch/barrier hoặc công cụ test chuyên biệt để đảm bảo hai transaction cùng đọc trước khi một bên commit. Kết quả còn phụ thuộc mức cô lập, khả năng khóa và phiên bản DB.

Đừng chỉ `Thread.sleep(...)` rồi coi đó là phép kiểm chứng chắc chắn không xảy ra lost update. Với production DB, test concurrency cần quan sát exception/SQL và khả năng commit.

### 17.3. FK và transaction đồng thời

Một request xóa Department trong khi request khác chuyển Employee vào đó có thể gây tranh chấp. DB foreign key và transaction isolation là lớp bảo vệ cuối. Nếu nghiệp vụ cần “phòng ban đang đóng không nhận nhân viên mới”, đó là invariant bổ sung cần được kiểm tra với trạng thái Department và cơ chế locking/concurrency phù hợp, chứ chỉ `@ManyToOne` chưa đủ.

## 18. Các lỗi khi test collection và dirty checking

### 18.1. Test thành công giả do first-level cache

Ví dụ:

~~~java
department.addEmployee(employee);
assertTrue(department.getEmployees().contains(employee));
~~~

Chỉ là bộ nhớ Java. Kể cả `entityManager.find(Employee.class, employee.getId())` cũng có thể trả chính managed entity từ first-level cache mà không chạy SQL.

Cách quan sát rõ hơn:

~~~java
entityManager.flush();
Long id = employee.getId();
entityManager.clear();

Employee reloaded =
    entityManager.find(Employee.class, id);

assertEquals(
    expectedDepartmentId,
    reloaded.getDepartment().getId()
);
~~~

### 18.2. Quên đồng bộ owning side

Sai về mặt thiết kế hai chiều:

~~~java
department.getEmployees().add(employee);
~~~

Nếu owning field `Employee.department` không được đặt, FK có thể không đúng. Để ngăn lỗi, chỉ cung cấp helper `department.addEmployee(employee)` và collection read-only.

### 18.3. Mở flush ở trạng thái FK bất hợp lệ

Nếu `department_id NOT NULL` nhưng code:

~~~java
employee.transferTo(null);
entityManager.flush(); // Có thể lỗi NOT NULL.
employee.transferTo(otherDepartment);
~~~

thì trạng thái trung gian bất hợp lệ đã được gửi xuống DB. Khi chuyển nhân viên giữa hai phòng ban bắt buộc, gán trực tiếp `employee.transferTo(otherDepartment)` và không flush giữa bước tạm gỡ và bước gán mới.

### 18.4. Dùng `orphanRemoval = true` cho mô hình cần chuyển con

Nếu Department.employees có orphanRemoval true, gỡ Employee khỏi A có thể đánh dấu xóa Employee; gắn nó vào B không đảm bảo sẽ hủy việc xóa đó. Test cần bắt đầu bằng việc xác nhận **chính sách vòng đời**. Với nhân viên chuyển được, không bật orphanRemoval; với dòng hàng thuộc đơn, thường bật.

### 18.5. Entity mới và detached entity bị nhầm

Khi test gọi `clear()`, tất cả entity đang managed trong context đó trở thành detached. Nếu sau `clear`:

~~~java
department.addEmployee(new Employee("Lan"));
entityManager.flush();
~~~

thì việc sửa `department` detached không tự được đồng bộ. Cần lấy lại managed Department rồi thao tác và persist entity mới theo cascade hoặc tường minh. Không gọi `merge` chỉ để “cho qua test” nếu chưa hiểu semantics của merge và instance trả về.

### 18.6. Collection đang được Hibernate quản lý bị thay bằng List mới

Ví dụ:

~~~java
this.employees = new ArrayList<>(newEmployees);
~~~

Nếu entity managed, provider có thể dùng persistent collection wrapper để theo dõi thay đổi, đặc biệt khi có orphanRemoval. Thay toàn bộ reference collection có thể dẫn tới cập nhật/xóa bất ngờ hoặc lỗi ORM.

Ưu tiên thao tác qua helper như `addEmployee`, `removeEmployee`, `addLine`, `removeLine`; không chỉ gán lại field collection.

### 18.7. `equals()/hashCode()` làm collection hoạt động sai

Một entity dùng ID tự sinh có thể chưa có ID trước persist. Nếu `hashCode()` dựa trên ID mutable và entity đang nằm trong `HashSet`, sau khi được cấp ID thì hash code thay đổi, khiến thao tác remove/contains khó dự đoán.

Các ví dụ dùng `List` và identity Java theo mặc định để tập trung vào mapping. Trong ứng dụng thật, lựa chọn equality phải phù hợp lifecycle entity, generated ID, proxy và collection semantics. Không tự động sinh `equals()/hashCode()` trên toàn bộ association hai chiều vì dễ gây recursion và lazy loading không mong muốn.

## 19. Kiểm thử lỗi ràng buộc và chính sách xóa

### 19.1. Xóa Department còn Employee tham chiếu

Nếu chưa gỡ FK, thao tác:

~~~java
entityManager.remove(department);
entityManager.flush();
~~~

có thể bị database từ chối vì FK `employee.department_id` vẫn trỏ tới Department. Đó thường là hành vi đúng của constraint nếu không có `ON DELETE SET NULL` hoặc cascade DB.

Kiểm thử policy nên xác định kỳ vọng:

- **Restrict:** phòng ban đang có nhân viên không được xóa; service trả lỗi nghiệp vụ và DB bảo vệ FK.
- **Unassign:** gỡ các nhân viên ra khỏi phòng ban trước khi xóa; Employee vẫn sống.
- **Cascade delete:** xóa nhân viên cùng phòng ban — ít khi đúng với nhân sự, nhưng có thể hợp lệ với aggregate phụ thuộc hoàn toàn khác.

Không viết assertion phụ thuộc vào chuỗi message DB cụ thể nếu test có thể chạy trên nhiều dialect. Kiểm tra loại lỗi phù hợp và cuối cùng kiểm tra dữ liệu sau transaction rollback theo chính sách mong muốn.

### 19.2. Lỗi FK không phải lúc nào cũng xuất hiện tại `persist()`

Provider có thể trì hoãn SQL đến flush/commit. Vì vậy:

~~~java
entityManager.persist(employee);
// Chưa chắc đã kiểm tra FK ở đây.
entityManager.flush();
// SQL và constraint thường được kiểm tra ở đây.
~~~

Một số DB hỗ trợ deferred constraint kiểm tra lúc commit. Nếu kiểm thử “ghi FK sai phải thất bại”, test cần biết thời điểm constraint được thực thi trong cấu hình DB thực tế.

### 19.3. Không tận dụng lỗi constraint để kiểm thử trên transaction hỏng

Khi flush thất bại do FK/UNIQUE, transaction có thể bị đánh dấu rollback-only hoặc context không còn đáng tin cậy. Không tiếp tục sử dụng cùng transaction để chạy một loạt assert như thể nó vẫn bình thường.

Một test chuyên kiểm tra lỗi nên kết thúc/rollback transaction đúng cách, sau đó đọc lại bằng context mới nếu cần. Trong Spring Test, có thể tổ chức test riêng để expected exception không làm ảnh hưởng các kiểm thử kế tiếp.

## 20. Tạo bộ test có ý nghĩa từ các use case

Thay vì viết hàng chục test lặp, có thể xem coverage như một ma trận hành vi:

| Nhóm test | Dữ liệu ban đầu | Thao tác | Assert tối thiểu |
|---|---|---|---|
| Persist cha + con | Department mới, 2 Employee mới | add helper + persist parent | 2 row Employee, cùng FK Department |
| Persist con tham chiếu cha có sẵn | Department persisted | add Employee mới + persist Employee | FK hợp lệ, ID child có |
| Transfer | Employee thuộc A, B tồn tại | `transferTo(B)` | ID giữ nguyên, FK đổi, hai collection đúng |
| Unlink | Employee thuộc A | `transferTo(null)` | Row Employee còn, FK NULL |
| Delete child | Employee thuộc A | unlink + `remove(employee)` | Employee biến mất, Department còn |
| Delete parent/keep child | A có Employee | unlink tất cả + remove A | A mất, Employee còn |
| Cascade delete aggregate | Order có 2 line | remove Order | Order + lines đều biến mất |
| Orphan removal | Order có 2 line | remove 1 line | Chỉ 1 line bị DELETE |
| Rollback | Tạo A và Employee | flush rồi rollback | Không có row committed |
| Concurrency | 2 transaction đọc cùng Employee | cùng transfer sang B/C | Xung đột/lock theo policy dự kiến |
| Invalid reference | Child trỏ parent không hợp lệ | persist/flush/commit | FK bảo vệ dữ liệu |
| Read visibility | Writer chưa commit | đọc từ transaction khác | Phù hợp isolation đã chọn |

**Mỗi test nên có một lý do nghiệp vụ rõ ràng.** Các biến thể về annotation, provider và transaction nên được dùng khi chúng giúp phát hiện một failure mode thực tế.

## 21. Cách đặt test data để dễ đọc và ít phụ thuộc thứ tự

Một bài test tốt cần tự tạo dữ liệu:

~~~java
Department sales = new Department("Sales");
Department support = new Department("Support");
Employee employee = new Employee("An");

sales.addEmployee(employee);

entityManager.persist(sales);
entityManager.persist(support);
entityManager.flush();
~~~

Không dùng ID cố định như `1L`, `2L` vì database sequence/identity có thể tăng qua nhiều lần test và rollback. Lấy ID thực:

~~~java
Long salesId = sales.getId();
Long supportId = support.getId();
Long employeeId = employee.getId();
~~~

Sau đó `clear` và `find` theo chính các ID này.

Nếu kiểm thử trên database dùng chung giữa các test, cần transaction rollback/cleanup thích hợp. Test thay đổi trạng thái schema hoặc commit thật phải dọn dữ liệu theo thứ tự FK và không giả định thứ tự thực thi các test method.

### 21.1. Tránh đoán số dòng toàn bảng

Nếu test có thể chia sẻ DB, assertion:

~~~java
assertEquals(1L,
    entityManager.createQuery(
        "SELECT COUNT(e) FROM Employee e", Long.class
    ).getSingleResult()
);
~~~

có thể thất bại vì dữ liệu do test khác hoặc fixture tạo. Thay vào đó, đếm theo ID Department hoặc khóa nghiệp vụ riêng của test:

~~~java
Long count = entityManager.createQuery(
    "SELECT COUNT(e) FROM Employee e WHERE e.department.id = :id",
    Long.class
).setParameter("id", targetDepartmentId)
 .getSingleResult();
~~~

Khi test yêu cầu toàn bảng sạch, phải đảm bảo database/schema được cô lập và khởi tạo deterministic.

## 22. Đọc SQL và trạng thái JPA khi test thất bại

Khi assertion FK sai, trình tự điều tra hữu ích là:

1. **Xác nhận object graph:** `employee.getDepartment()` trỏ ai? Collection A/B chứa gì?
2. **Kiểm tra owning side:** `Employee.department` có được cập nhật không?
3. **Kiểm tra managed state:** object đã bị `clear`/detach chưa? Có dùng đúng EntityManager không?
4. **Kiểm tra cascade:** Employee mới có được persist do cascade hoặc explicit persist không?
5. **Kiểm tra transaction:** transaction đã begin chưa, có bị đánh dấu rollback-only không?
6. **Kiểm tra flush:** SQL có thực sự được phát trước khi assert không?
7. **Kiểm tra DDL:** FK nullable/NOT NULL, constraint và column name có đúng không?
8. **Đọc lại sau clear:** lần đọc mới có còn gặp lỗi không?
9. **Quan sát commit:** test mặc định rollback hay có transaction commit thật?
10. **Kiểm tra provider/version:** hành vi orphanRemoval, lazy loading, batching và SQL ordering có phù hợp cấu hình không?

Trong môi trường Spring Boot/Hibernate, có thể bật logging SQL và bind parameters trong **môi trường test** theo cấu hình/version phù hợp. Không nên log dữ liệu nhạy cảm ở production chỉ để xem câu SQL.

Những đoạn test ở đây nêu **ý đồ và kỳ vọng hành vi**. Tên SQL, số lượng câu lệnh và thời điểm thực thi cụ thể có thể khác giữa Hibernate/EclipseLink, version, dialect, batching và flush mode; không nên khóa test vào đúng thứ tự chuỗi SQL khi business invariant có thể được kiểm tra ổn định hơn bằng dữ liệu sau flush/clear.

## 23. Bài tập thực hành

### Bài 1: Phát hiện test yếu

Cho code:

~~~java
Department department = new Department("Marketing");
Employee employee = new Employee("Huy");

department.addEmployee(employee);

assertEquals(1, department.getEmployees().size());
~~~

**Câu hỏi:** Test đã chứng minh Department và Employee được lưu đúng trong database chưa?

**Đáp án:** Chưa. Chỉ kiểm tra collection Java. Cần persist trong transaction, flush/clear rồi đọc lại Employee và xác nhận FK trỏ đúng Department. Nếu cần xác nhận commit, tổ chức transaction commit thật và đọc lại ở transaction khác.

### Bài 2: Chuyển nhân viên

Ban đầu `Employee(id=50)` thuộc Department A. Ứng dụng gọi `employee.transferTo(B)` trong transaction với A và B managed.

**Câu hỏi:** Sau flush/clear nên khẳng định điều gì?

**Đáp án:** Employee ID vẫn bằng 50, `department_id` bằng B.id, collection A không có employee, collection B có employee. Không nên kỳ vọng DELETE Employee cũ và INSERT Employee mới.

### Bài 3: Gỡ nhân viên khỏi phòng ban

`Department.removeEmployee(e)` được gọi trong model không orphanRemoval và FK nullable.

**Câu hỏi:** Employee có bị xóa khỏi DB không?

**Đáp án:** Không. Đây là thao tác unlink, thường cập nhật `department_id = NULL`. Muốn xóa Employee, phải thực hiện `entityManager.remove(e)` hoặc thao tác repository delete đúng cách.

### Bài 4: Xóa dòng hàng khỏi đơn

`SalesOrder.lines` có `orphanRemoval = true` và `cascade = ALL`. Service gọi `order.removeLine(line)`.

**Câu hỏi:** Assertion nào tốt hơn `order.getLines().size() == 1`?

**Đáp án:** Sau `flush` và `clear`, `entityManager.find(SalesOrderLine.class, removedLineId) == null`; đồng thời order và các line còn lại vẫn tồn tại.

### Bài 5: Chuyển một dòng hàng có orphanRemoval

Ứng dụng xóa line khỏi Order A rồi gắn cùng instance line vào Order B trong cùng transaction.

**Câu hỏi:** Có thể coi đây là thao tác reparent an toàn theo JPA chuẩn không?

**Đáp án:** Không. Line có thể đã bị coi là orphan và được lên lịch xóa. Nếu nghiệp vụ cần chuyển con, thiết kế association không orphanRemoval và update owning side. Nếu dòng hàng không được chuyển, tạo line mới hoặc cập nhật nội dung theo quy tắc domain.

### Bài 6: Test chạy xanh nhưng không có dữ liệu sau test

Một `@DataJpaTest` gọi `persist`, `flush`, `clear` rồi `find` và tất cả assertion đều pass. Sau khi test kết thúc, bảng lại trống.

**Câu hỏi:** Có phải lỗi JPA không?

**Đáp án:** Không nhất thiết. `@DataJpaTest` mặc định thường rollback transaction sau test. Kiểm tra mapping trong transaction và kiểm tra commit là hai loại bài test khác nhau.

### Bài 7: Hai chiều không đồng bộ

Một lập trình viên sửa collection `Department.employees` nhưng quên `Employee.department`.

**Câu hỏi:** Tại sao tình trạng này khó phát hiện bằng unit test mà dễ lộ trong integration test?

**Đáp án:** Collection trong Java có thể chứa đúng employee, nhưng owning side chưa đổi nên FK tại DB có thể không được cập nhật. Sau `flush/clear` và đọc lại, khác biệt sẽ lộ rõ.

### Bài 8: Xóa Department còn nhân viên

Business rule: “Được xóa phòng ban nhưng không xóa nhân viên.”

**Câu hỏi:** Có nên bật `cascade = REMOVE` trên `Department.employees` không?

**Đáp án:** Không. Cần chuyển/gỡ nhân viên phù hợp rồi xóa Department, với FK/transaction hỗ trợ; hoặc thiết lập policy DB phù hợp. Cascade REMOVE sẽ có nguy cơ xóa dữ liệu nhân viên trái yêu cầu.

## 24. Tổng kết: Kiểm thử phải quan sát cả quan hệ và vòng đời

~~~text
QUY TẮC NGHIỆP VỤ
        |
        v
Chọn loại quan hệ một-nhiều
        |
        +-- Con có thể chuyển cha?
        |        |
        |        +-- Có: không orphanRemoval;
        |        |        update owning FK, giữ ID
        |        |
        |        +-- Không, vòng đời phụ thuộc:
        |                 có thể dùng orphanRemoval
        |
        v
Thiết kế helper đồng bộ hai phía
        |
        v
Persist / transfer / unlink / remove
        |
        v
Flush (đồng bộ SQL)
        |
        v
Clear (tránh first-level cache)
        |
        v
Find / JPQL / native SQL
        |
        v
Assert ID, FK, số dòng, sự tồn tại
        |
        v
Nếu cần: kiểm chứng commit/rollback
~~~

Những nguyên tắc quan trọng nhất:

1. **`@ManyToOne` thường là owning side** trong liên kết hai chiều một-nhiều; `@OneToMany(mappedBy = "...")` là phía inverse.
2. **Chỉ sửa collection không đủ**: helper phải đồng bộ `Employee.department` và collection của cả cha cũ/cha mới.
3. **Kiểm thử persist** cần xác nhận con thực sự được lưu và FK đúng, không chỉ `id != null` hoặc collection có phần tử.
4. **Kiểm thử chuyển** cần xác nhận con giữ ID, FK đổi sang cha mới và không phát sinh bản ghi trùng.
5. **Unlink và delete khác nhau**: không có orphanRemoval thì gỡ liên kết không mặc nhiên xóa entity con.
6. **`orphanRemoval = true` thích hợp khi con phụ thuộc vòng đời vào cha**; không nên dùng nó với quan hệ mà con được chuyển qua nhiều cha.
7. **`CascadeType.REMOVE` xóa theo vòng đời**, phải lựa chọn theo nghiệp vụ, không bật chỉ vì có `@OneToMany`.
8. **`flush()` rồi `clear()` giúp kiểm tra dữ liệu lưu**, vì tránh nhầm object graph/first-level cache với DB; nhưng chúng không thay thế commit.
9. **Integration test cần database và constraint thực tế** để phát hiện lỗi FK, SQL, transaction và sự khác biệt giữa provider.
10. **Test rollback, concurrency và commit riêng khi cần**, thay vì suy diễn từ kết quả của một test `@DataJpaTest` rollback mặc định.

Kiểm thử tốt một quan hệ một-nhiều không dừng ở câu hỏi “collection có bao nhiêu phần tử?”. Nó phải trả lời chính xác: **entity nào còn tồn tại, khóa ngoại đang trỏ tới ai, định danh có được giữ lại, bản ghi nào phải bị xóa, và kết quả đó thuộc transaction nào**.
