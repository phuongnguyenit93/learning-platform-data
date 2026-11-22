# Phân biệt bỏ liên kết, xóa phần tử con và xóa thực thể cha

## 1. Ba thao tác nhìn giống nhau nhưng có ý nghĩa khác nhau

Trong Hibernate ORM/Jakarta Persistence (JPA), một association giữa hai entity có thể được lưu bằng khóa ngoại hoặc bảng nối. Khi người dùng bỏ một phần tử khỏi collection, xóa một entity hoặc xóa entity cha, database có thể nhận những câu SQL rất khác nhau.

Xét quan hệ phòng ban và nhân viên:

~~~text
Department (phòng ban)
    |
    +--- Employee A
    +--- Employee B
    +--- Employee C
~~~

Có ba yêu cầu nghiệp vụ thường bị nhầm:

1. **Bỏ liên kết (unlink/dissociate):** nhân viên vẫn tồn tại, phòng ban vẫn tồn tại, chỉ thay đổi quan hệ giữa chúng. Ví dụ Employee B chuyển sang trạng thái chưa phân công hoặc sang phòng ban khác.
2. **Xóa phần tử con (delete child):** xóa hẳn bản ghi Employee B khỏi hệ thống. Employee không còn tồn tại sau khi transaction commit thành công.
3. **Xóa thực thể cha (delete parent):** xóa Department. Những Employee đang tham chiếu đến phòng ban phải được xử lý theo quy tắc nghiệp vụ và ràng buộc database.

Ba thao tác không thể thay thế cho nhau. Nếu chỉ muốn bỏ một nhân viên khỏi danh sách đang hiển thị, không nên vô tình xóa nhân viên khỏi database. Nếu nghiệp vụ yêu cầu xóa phòng ban, không nên để lại những khóa ngoại mồ côi hoặc xóa luôn nhân viên dùng chung mà chưa có quyết định rõ ràng.

Bài học tập trung vào các khái niệm:

- Owning side và inverse side của association.
- `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`.
- Bỏ liên kết bằng cách cập nhật foreign key hoặc xóa hàng trong join table.
- `CascadeType.REMOVE` và `CascadeType.ALL`.
- `orphanRemoval = true`.
- FK `NULL`, `NOT NULL`, `RESTRICT`, `ON DELETE SET NULL`, `ON DELETE CASCADE`.
- Khác biệt giữa cascade do JPA/Hibernate điều khiển và cascade do database thực hiện.
- Cách giữ hai phía của quan hệ nhất quán trong Java.
- Tác động của transaction, flush, bulk delete và soft delete.

## 2. Một ví dụ dữ liệu để phân biệt ba ý nghĩa

Giả sử database có hai bảng:

~~~sql
CREATE TABLE departments (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    department_id BIGINT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
);
~~~

Dữ liệu ban đầu:

| departments.id | departments.name |
|---:|---|
| 10 | Engineering |
| 20 | Operations |

| employees.id | full_name | department_id |
|---:|---|---:|
| 101 | An | 10 |
| 102 | Bình | 10 |
| 103 | Chi | 20 |

`employees.department_id` là foreign key. Với schema này, `department_id` cho phép `NULL`, nên một nhân viên có thể chưa được phân công phòng ban.

### 2.1. Bỏ liên kết

Muốn nhân viên Bình vẫn tồn tại nhưng không còn thuộc Engineering:

~~~sql
UPDATE employees
SET department_id = NULL
WHERE id = 102;
~~~

Kết quả:

| employees.id | full_name | department_id |
|---:|---|---:|
| 101 | An | 10 |
| 102 | Bình | NULL |
| 103 | Chi | 20 |

Bản ghi `employees.id = 102` vẫn còn. Chỉ cột FK đổi giá trị.

Nếu Bình chuyển sang Operations, câu lệnh có thể là:

~~~sql
UPDATE employees
SET department_id = 20
WHERE id = 102;
~~~

Đây cũng là thay đổi liên kết, nhưng liên kết mới được thiết lập ngay trong cùng thao tác.

### 2.2. Xóa phần tử con

Muốn xóa hẳn nhân viên Bình:

~~~sql
DELETE FROM employees
WHERE id = 102;
~~~

Kết quả không còn hàng Employee 102. Đây là xóa entity con, không phải chỉ xóa liên kết.

### 2.3. Xóa thực thể cha

Muốn xóa Engineering:

~~~sql
DELETE FROM departments
WHERE id = 10;
~~~

Với schema FK ở trên và không có hành động cascade/set-null, database thường từ chối câu lệnh vì Employee 101 vẫn tham chiếu Department 10. Phải chọn một chính sách:

- Chuyển các nhân viên sang phòng ban khác.
- Cho phép `department_id = NULL` rồi bỏ liên kết.
- Xóa các nhân viên theo nghiệp vụ.
- Thiết lập hành động xóa phù hợp ở FK hoặc cấu hình cascade trong ORM.

**Xóa parent không tự nói lên điều gì phải xảy ra với child.** Đó là quyết định nghiệp vụ được biểu diễn bằng mapping, transaction và constraint.

## 3. Owning side: phía nào điều khiển khóa ngoại?

Trong JPA, owning side là phía có mapping quản lý liên kết trong database. Với quan hệ nhiều-một/một-nhiều phổ biến, `@ManyToOne` thường là owning side vì nó chứa `@JoinColumn`.

~~~java
@Entity
@Table(name = "employees")
public class Employee {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;
}
~~~

Ở phía Department:

~~~java
@Entity
@Table(name = "departments")
public class Department {
    @Id
    private Long id;

    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();
}
~~~

Sơ đồ:

~~~text
Employee.department
    @ManyToOne
    @JoinColumn(name = "department_id")
          |
          | owning side: điều khiển FK
          v
    employees.department_id
          ^
          |
Department.employees
    @OneToMany(mappedBy = "department")
    inverse side: đường điều hướng ngược
~~~

`mappedBy = "department"` là tên thuộc tính Java `Employee.department`, không phải tên cột SQL `department_id`.

### 3.1. Chỉ sửa inverse collection có thể không cập nhật FK

~~~java
Department department = em.find(Department.class, 10L);
Employee employee = em.find(Employee.class, 102L);

// Chỉ thay đổi collection ở inverse side:
department.getEmployees().remove(employee);
~~~

Nếu `Employee.department` vẫn trỏ đến Department 10, owning side chưa thay đổi. Hibernate dựa vào owning side để đồng bộ khóa ngoại. Chỉ sửa collection inverse không phải cách đáng tin cậy để bỏ liên kết khỏi database.

Cần cập nhật cả hai phía trong object graph:

~~~java
employee.setDepartment(null);
department.removeEmployeeInternal(employee);
~~~

Ví dụ này chỉ hợp lệ khi nghiệp vụ cho phép nhân viên không có phòng ban và FK nullable. Nếu quan hệ bắt buộc, phải chuyển sang phòng ban khác hoặc xử lý child theo một quy tắc khác.

### 3.2. Helper method giữ hai phía nhất quán

Một mẫu entity có thể cung cấp helper:

~~~java
@Entity
@Table(name = "departments")
public class Department {
    @Id
    private Long id;

    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();

    public List<Employee> getEmployees() {
        return Collections.unmodifiableList(employees);
    }

    public void addEmployee(Employee employee) {
        if (employee == null) {
            throw new IllegalArgumentException("employee is required");
        }
        employee.changeDepartment(this);
    }

    public void removeEmployee(Employee employee) {
        if (employee != null && employees.contains(employee)) {
            employee.changeDepartment(null);
        }
    }

    void addEmployeeInternal(Employee employee) {
        if (!employees.contains(employee)) {
            employees.add(employee);
        }
    }

    void removeEmployeeInternal(Employee employee) {
        employees.remove(employee);
    }
}
~~~

Phía Employee:

~~~java
@Entity
@Table(name = "employees")
public class Employee {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id", nullable = true)
    private Department department;

    public Department getDepartment() {
        return department;
    }

    public void changeDepartment(Department next) {
        if (department == next) {
            return;
        }

        Department previous = department;
        if (previous != null) {
            previous.removeEmployeeInternal(this);
        }

        department = next;

        if (next != null) {
            next.addEmployeeInternal(this);
        }
    }
}
~~~

Helper này giả định FK có thể null. Nó cập nhật owning reference và collection trong bộ nhớ. Khi Employee là managed, Hibernate có thể phát UPDATE `employees.department_id` lúc flush.

Nếu `department_id` là `NOT NULL`, method `changeDepartment(null)` phải bị cấm hoặc thay bằng thao tác chuyển sang một Department hợp lệ. Không nên để helper cho phép trạng thái Java mà database không thể lưu.

### 3.3. Không cần có hai chiều mới bỏ được liên kết

Với mapping một chiều:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
~~~

Chỉ cần cập nhật owning field:

~~~java
employee.changeDepartment(null);
~~~

Không có `Department.employees` để đồng bộ. JPA vẫn có thể ghi `department_id = NULL` nếu cột nullable. Một chiều/hai chiều là lựa chọn điều hướng Java, còn unlink là thay đổi association ở owning side.

## 4. Bỏ liên kết trong @OneToMany / @ManyToOne

Đây là tình huống thường gặp nhất khi một entity con thuộc một entity cha.

### 4.1. FK nullable: child được phép tồn tại độc lập

Mapping:

~~~java
// Employee là owning side.
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;

// Department là inverse side.
@OneToMany(mappedBy = "department")
private List<Employee> employees = new ArrayList<>();
~~~

Khi bỏ liên kết:

~~~java
@Transactional
public void unassignEmployee(Long employeeId) {
    Employee employee = em.find(Employee.class, employeeId);
    if (employee == null) {
        throw new IllegalArgumentException("Employee not found");
    }

    employee.changeDepartment(null);
}
~~~

Nếu helper đồng bộ collection như ví dụ trước, trạng thái hai phía trong bộ nhớ được giữ nhất quán. SQL khái niệm:

~~~sql
UPDATE employees
SET department_id = NULL
WHERE id = ?;
~~~

Employee vẫn tồn tại, chỉ không thuộc Department nào.

### 4.2. FK NOT NULL: không thể unlink thành null

Nếu mapping/schema:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
~~~

và DB thực sự có `NOT NULL`, thao tác:

~~~java
employee.changeDepartment(null);
~~~

không thể được lưu thành công. Khi flush, DB có thể từ chối UPDATE vì `department_id` không được null. `optional = false`/`nullable = false` mô tả mapping và schema generation; constraint thực tế phải tồn tại trong DB.

Các lựa chọn nghiệp vụ:

1. Chuyển Employee sang Department khác.
2. Xóa Employee nếu đó là quyết định nghiệp vụ.
3. Thay đổi schema và mapping để cho phép chưa phân công.
4. Dùng một Department đặc biệt như “Unassigned” nếu đó là khái niệm thật trong domain và được quản lý rõ ràng.

Không nên xử lý lỗi bằng cách tắt constraint tùy tiện; phải quyết định trạng thái dữ liệu hợp lệ.

### 4.3. Chuyển child sang parent khác

~~~java
@Transactional
public void transferEmployee(Long employeeId, Long targetDepartmentId) {
    Employee employee = em.find(Employee.class, employeeId);
    Department target = em.find(Department.class, targetDepartmentId);

    if (employee == null || target == null) {
        throw new IllegalArgumentException("Unknown employee or department");
    }

    employee.changeDepartment(target);
}
~~~

Khi owning side thay đổi, Hibernate có thể phát:

~~~sql
UPDATE employees
SET department_id = ?
WHERE id = ?;
~~~

Không cần xóa Employee khỏi database rồi tạo lại. ID, lịch sử và các quan hệ khác của Employee vẫn được giữ.

## 5. Xóa child entity: DELETE bản ghi con

Khi nghiệp vụ yêu cầu Employee không còn tồn tại, phải xóa entity. Trong JPA, `remove()` thông thường yêu cầu một managed entity:

~~~java
@Transactional
public void deleteEmployee(Long employeeId) {
    Employee employee = em.find(Employee.class, employeeId);
    if (employee == null) {
        return;
    }

    em.remove(employee);
}
~~~

Hibernate đánh dấu Employee là removed; SQL DELETE được đồng bộ khi flush/commit theo transaction:

~~~sql
DELETE FROM employees
WHERE id = ?;
~~~

Không nhầm thao tác này với:

~~~java
employee.changeDepartment(null);
~~~

Lệnh thứ hai chỉ unlink và có thể phát UPDATE, không xóa row.

### 5.1. Xóa child khi có inverse collection đã được nạp

Nếu Department đang giữ một collection Employee trong memory, xóa trực tiếp Employee có thể khiến collection trong bộ nhớ vẫn chứa reference tới entity đã bị đánh dấu removed. Để object graph không gây nhầm lẫn trong phần còn lại của transaction, có thể cập nhật collection:

~~~java
@Transactional
public void deleteEmployee(Long employeeId) {
    Employee employee = em.find(Employee.class, employeeId);
    if (employee == null) {
        return;
    }

    Department department = employee.getDepartment();
    if (department != null) {
        department.removeEmployeeInternal(employee);
    }

    em.remove(employee);
}
~~~

Trong ví dụ này, ta chỉ bỏ reference khỏi collection inverse và remove chính entity con. Không cần gán FK null trước khi xóa nếu entity sẽ bị xóa trong cùng transaction; điều đó có thể tạo một UPDATE thừa hoặc xung đột với `NOT NULL`, tùy mapping/provider và flush ordering.

Nếu ứng dụng cần một helper domain duy nhất, hãy thiết kế rõ method theo ý nghĩa: `unassignEmployee()` để bỏ liên kết; `deleteEmployee()` để xóa entity. Không đặt một method `removeEmployee()` mơ hồ làm cả hai hành vi mà caller không biết.

### 5.2. FK có thể ngăn xóa child không?

Nếu child còn được entity khác tham chiếu bằng FK, DB có thể từ chối DELETE child. Ví dụ một bảng `timesheets` tham chiếu `employees`:

~~~sql
FOREIGN KEY (employee_id) REFERENCES employees(id)
~~~

Trước khi xóa Employee, cần quyết định xử lý Timesheet: giữ lịch sử bằng cách ngăn xóa, chuyển tham chiếu, xóa theo quy tắc, hoặc dùng soft delete. `CascadeType.REMOVE` không tự giải quyết mọi quan hệ phụ thuộc và không nên lan xóa sang dữ liệu lịch sử dùng chung.

## 6. Xóa parent entity: phải quyết định số phận của child

Giả sử xóa Department 10 khi vẫn có Employee 101 và 102.

Nếu không có cascade và FK còn được tham chiếu, DB sẽ từ chối:

~~~sql
DELETE FROM departments WHERE id = 10;
-- Có thể lỗi FK: employees.department_id vẫn tham chiếu departments.id = 10.
~~~

Có bốn chính sách phổ biến.

### 6.1. RESTRICT/NO ACTION: không cho xóa parent còn child

Đây là lựa chọn an toàn khi Department không thể bị xóa nếu còn Employee:

~~~sql
FOREIGN KEY (department_id)
REFERENCES departments(id)
ON DELETE RESTRICT
~~~

Tên và semantics cụ thể của `RESTRICT`/`NO ACTION` khác nhau giữa DB. Một số database dùng `NO ACTION` mặc định; có DB kiểm tra ngay, có DB cho phép deferred constraint nếu được khai báo phù hợp.

Ứng dụng có thể kiểm tra trước để đưa thông báo thân thiện, nhưng FK vẫn là lớp bảo vệ cuối cùng vì một transaction khác có thể thêm Employee sau bước kiểm tra:

~~~java
if (!department.getEmployees().isEmpty()) {
    throw new IllegalStateException(
        "Cannot delete a department that still has employees"
    );
}
~~~

Kiểm tra collection có thể tải nhiều dữ liệu và không tự bảo vệ concurrency. Constraint DB mới đảm bảo thao tác xóa không vi phạm tham chiếu.

### 6.2. ON DELETE SET NULL: giữ child, bỏ liên kết

Nếu Employee có thể không thuộc phòng ban, schema có thể dùng:

~~~sql
FOREIGN KEY (department_id)
REFERENCES departments(id)
ON DELETE SET NULL
~~~

Khi Department bị xóa, database đặt `department_id = NULL` trên các hàng Employee tham chiếu nó. Employee vẫn tồn tại.

Đây là **unlink hàng loạt do database thực hiện**, không phải cascade remove child.

Điều kiện: cột phải cho phép null và DB phải hỗ trợ hành động đó. Nếu `department_id NOT NULL`, `SET NULL` không thể thực hiện thành công.

### 6.3. Xóa child trước rồi xóa parent

Nếu nghiệp vụ quy định nhân viên của một phòng ban phải bị xóa cùng phòng ban, service có thể xóa tường minh:

~~~java
@Transactional
public void deleteDepartmentAndEmployees(Long departmentId) {
    Department department = em.find(Department.class, departmentId);
    if (department == null) {
        return;
    }

    List<Employee> employees = em.createQuery(
            "select e from Employee e where e.department.id = :id",
            Employee.class)
        .setParameter("id", departmentId)
        .getResultList();

    for (Employee employee : employees) {
        em.remove(employee);
    }

    em.remove(department);
}
~~~

Mọi thao tác ở đây nằm trong một transaction. Nếu một DELETE thất bại, transaction có thể rollback các thay đổi chưa commit. Với collection rất lớn, tải tất cả Employee vào context có thể không phù hợp; cân nhắc batch/chunk hoặc database-level cascade theo đúng semantics.

Nếu có entity khác tham chiếu Employee, việc xóa child vẫn có thể bị FK chặn. Phải xử lý toàn bộ quan hệ phụ thuộc theo domain.

### 6.4. Cascade REMOVE từ parent sang child

Mapping:

~~~java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.REMOVE
)
private List<Employee> employees = new ArrayList<>();
~~~

Khi gọi:

~~~java
Department department = em.find(Department.class, departmentId);
em.remove(department);
~~~

JPA cascade REMOVE lan thao tác remove từ Department sang các Employee liên quan theo association mapping. Hibernate thực hiện các thao tác xóa phù hợp trong transaction.

**Ý nghĩa:** xóa parent sẽ kéo theo xóa child. Đây không phải unlink. Không dùng cấu hình này nếu Employee có thể tồn tại độc lập hoặc được chia sẻ theo nghiệp vụ.

`CascadeType.ALL` cũng bao gồm REMOVE, nên cần cân nhắc tương tự:

~~~java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.ALL
)
private List<Employee> employees = new ArrayList<>();
~~~

Không nên dùng `ALL` chỉ vì muốn persist child khi tạo parent: có thể chỉ cần `PERSIST`/`MERGE`, không cần `REMOVE`.

## 7. CascadeType.REMOVE và orphanRemoval khác nhau

Hai cơ chế thường bị nhầm vì đều có thể dẫn đến DELETE child, nhưng **thời điểm kích hoạt và ý nghĩa nghiệp vụ khác nhau**.

### 7.1. CascadeType.REMOVE: xóa parent thì lan remove sang child

~~~java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.REMOVE
)
private List<Employee> employees = new ArrayList<>();
~~~

Khi gọi `em.remove(department)`, remove được lan tới Employee liên quan.

Nếu chỉ gọi:

~~~java
department.removeEmployee(employee);
~~~

và không xóa Department, `CascadeType.REMOVE` **không tự có nghĩa** Employee sẽ bị xóa chỉ vì phần tử rời collection. Nếu owning side được đặt null và FK nullable, đó là unlink; nếu FK NOT NULL, thao tác không hợp lệ cho đến khi có hành động phù hợp.

### 7.2. orphanRemoval = true: bỏ child khỏi quan hệ riêng thì xóa child

~~~java
@OneToMany(
    mappedBy = "department",
    orphanRemoval = true
)
private List<Employee> employees = new ArrayList<>();
~~~

Với association thể hiện child có vòng đời phụ thuộc/riêng tư thuộc parent, bỏ child khỏi quan hệ có thể khiến JPA áp dụng remove cho orphan khi flush:

~~~java
department.removeEmployee(employee);
~~~

Nếu helper cập nhật cả collection và owning reference, Hibernate có thể phát DELETE cho Employee khi flush thay vì chỉ UPDATE FK thành NULL. Mục tiêu của orphan removal là: **child không còn được parent sở hữu theo quan hệ đó thì child không nên tiếp tục tồn tại**.

Orphan removal được thiết kế cho quan hệ `@OneToOne` và `@OneToMany` với child có vòng đời phụ thuộc. Không dùng nó cho đối tượng có thể được nhiều parent hoặc nhiều phần nghiệp vụ dùng chung.

### 7.3. So sánh trực tiếp

| Thao tác | `cascade = REMOVE` | `orphanRemoval = true` |
|---|---|---|
| Gọi `remove(parent)` | Lan remove tới child theo mapping | Khi parent bị remove, remove cũng được lan tới child theo semantics orphan removal |
| Chỉ bỏ child khỏi collection, parent vẫn còn | Không tự xóa child chỉ vì rời collection | Child bị xem là orphan và được remove theo quy tắc JPA |
| Mục đích | Lan thao tác xóa từ parent | Quản lý vòng đời child phụ thuộc association |
| Dùng với child được chia sẻ | Thường nguy hiểm | Không phù hợp |
| Association được hỗ trợ | Cascade REMOVE trên association thích hợp | `@OneToOne`, `@OneToMany` |
| Có tương đương ON DELETE CASCADE của DB? | Không | Không |

Khi `orphanRemoval = true`, JPA có semantics remove child khi source entity bị xóa; không nhất thiết phải khai báo thêm `cascade = REMOVE` chỉ để có hiệu ứng đó. Dù vậy, cascade PERSIST/MERGE là các lựa chọn độc lập, tùy cách ứng dụng tạo và cập nhật graph.

### 7.4. Orphan removal không phải “xóa mọi thứ trong collection”

Một collection có thể đại diện entity con được sở hữu riêng, hoặc chỉ là cách truy cập tới dữ liệu được chia sẻ. Ví dụ:

- `Order` — `OrderLine`: OrderLine thường không tồn tại độc lập nếu không có Order; orphan removal có thể phù hợp.
- `Department` — `Employee`: nhân viên có thể chuyển phòng ban và có hồ sơ độc lập; orphan removal thường không phù hợp nếu “bỏ khỏi phòng ban” chỉ là đổi nơi làm việc.
- `User` — `Role`: Role được chia sẻ giữa nhiều User; orphan removal không phù hợp.
- `Post` — `Tag`: Tag thường là dữ liệu dùng chung; xóa association không có nghĩa xóa Tag.

Quyết định dựa trên vòng đời domain, không dựa vào việc collection có tên `children`.

### 7.5. Không thay parent của orphan một cách tùy tiện trong cùng lúc

Khi chuyển một child từ parent A sang parent B, nếu mapping A có orphan removal, việc tách child khỏi A có thể mang semantics xóa child. JPA không thiết kế orphan removal để coi mọi lần chuyển owner là một thao tác move an toàn, portable trong mọi thứ tự flush.

Nếu child được phép chuyển giữa parent, thường không bật orphanRemoval hoặc thiết kế thao tác chuyển/transaction theo đúng semantics provider và schema. Không nên vừa remove khỏi collection A vừa add vào B rồi giả định mọi provider/version đều hiểu là “chuyển child, không xóa”.

## 8. ON DELETE CASCADE của database khác cascade REMOVE của JPA

Database có thể khai báo:

~~~sql
FOREIGN KEY (department_id)
REFERENCES departments(id)
ON DELETE CASCADE
~~~

Khi chạy trực tiếp:

~~~sql
DELETE FROM departments WHERE id = 10;
~~~

database tự xóa những Employee có `department_id = 10` theo FK action.

Đây là **database-level referential action**. Nó không đồng nghĩa với JPA `CascadeType.REMOVE`.

| Tiêu chí | JPA `CascadeType.REMOVE` | DB `ON DELETE CASCADE` |
|---|---|---|
| Ai điều khiển? | EntityManager/Hibernate theo mapping và entity lifecycle | Database theo FK DDL |
| Kích hoạt khi nào? | Ứng dụng gọi remove trên parent managed | SQL DELETE parent được thực thi |
| Có áp dụng khi SQL ngoài ORM xóa parent? | Không tự chạy vì SQL ngoài ORM bypass JPA cascade | Có, nếu FK có ON DELETE CASCADE |
| Lifecycle callback entity con | Có thể chạy theo JPA/provider khi remove được áp dụng | Không gọi callback JPA cho từng row bị DB cascade |
| Dirty checking/persistence context | Provider quản lý các entity tham gia cascade | Database không cập nhật Java objects đang managed |
| Cache invalidation | Provider có thể quản lý state/cache theo thao tác ORM | External/native delete có thể làm context/cache stale |
| Tính portable | Chuẩn JPA | DDL phụ thuộc database |
| Có thể dùng cùng nhau? | Có, nếu thiết kế cẩn thận | Có, nhưng phải tránh hiểu nhầm và kiểm tra SQL/ordering |

### 8.1. Vì sao DB cascade có thể làm Hibernate context stale?

Giả sử EntityManager đã nạp Department 10 và Employee 101:

~~~java
Department d = em.find(Department.class, 10L);
Employee e = em.find(Employee.class, 101L);
~~~

Một câu native SQL/JDBC khác xóa Department 10 và DB `ON DELETE CASCADE` xóa Employee 101. Các Java objects `d` và `e` trong persistence context hiện tại không tự biến mất hoặc tự cập nhật toàn bộ field. Context có thể vẫn giữ chúng như thể dữ liệu cũ còn tồn tại.

Nếu tiếp tục dùng context, có thể đọc state stale hoặc phát sinh lỗi khi flush. Cần có ranh giới context/transaction rõ ràng, hoặc refresh/clear theo cách phù hợp; không tiếp tục dùng graph cũ như thể database cascade đã đồng bộ RAM.

### 8.2. Hibernate có @OnDelete không?

Hibernate cung cấp extension như `@OnDelete` ở một số mapping/version để mô tả hành vi `ON DELETE` ở database schema. Đây là API riêng của Hibernate, không phải annotation JPA portable. Cần xem đúng User Guide của Hibernate version đang dùng và kiểm tra DDL thật được tạo hoặc migration đã áp dụng.

Không nên nhầm `@OnDelete` với `CascadeType.REMOVE`: một cái liên quan FK action ở database, một cái là lifecycle cascade của ORM.

### 8.3. Chọn một hay cả hai?

- Nếu mọi thao tác xóa đi qua JPA và cần lifecycle callback/cascade semantics, JPA cascade có thể phù hợp.
- Nếu cần DB bảo vệ khi nhiều ứng dụng/script cùng xóa parent bằng SQL, FK action có thể phù hợp.
- Nếu dùng cả hai, cần kiểm tra thứ tự SQL, việc provider có cố xóa child trước khi DB cascade hay không, và trạng thái first-level/second-level cache.
- Với dữ liệu lịch sử, thường không nên cascade delete; có thể ngăn xóa, archive hoặc soft delete.

Không thêm `ON DELETE CASCADE` chỉ để “sửa lỗi FK” mà chưa hiểu tác động lên dữ liệu con.

## 9. @OneToOne: unlink, orphan và xóa parent

Ví dụ một Account có tối đa một Profile:

~~~java
@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private AccountProfile profile;

    public AccountProfile getProfile() {
        return profile;
    }

    public void attachProfile(AccountProfile profile) {
        if (profile != null && profile.getAccount() != null
                && profile.getAccount() != this) {
            throw new IllegalStateException("Profile belongs to another account");
        }
        this.profile = profile;
        if (profile != null) {
            profile.assignAccount(this);
        }
    }

    public void detachProfile() {
        if (profile != null) {
            AccountProfile old = profile;
            profile = null;
            old.assignAccount(null);
        }
    }
}
~~~

Entity Profile là owning side:

~~~java
@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;

    public Account getAccount() {
        return account;
    }

    void assignAccount(Account account) {
        this.account = account;
    }
}
~~~

Mapping trên minh họa profile có vòng đời phụ thuộc account và không được tồn tại riêng khi bị tách. Khi `Account.detachProfile()` được gọi, orphan removal có thể xóa Profile khi flush. Vì FK `account_id` là NOT NULL, không nên diễn giải thao tác đó thành một trạng thái DB “profile còn sống nhưng account_id null”; mục đích là xóa orphan.

Nếu nghiệp vụ chỉ muốn unlink và giữ Profile để tái gắn sau, hãy chọn schema/mapping cho phép FK nullable hoặc thiết kế association/lifecycle phù hợp, và **không bật orphanRemoval**. Nếu profile bắt buộc luôn có account, việc gỡ liên kết độc lập không phải trạng thái hợp lệ.

### 9.1. Xóa Account

Nếu Account bị remove, orphan removal có semantics remove Profile thuộc association. Nếu không dùng orphanRemoval, có thể khai báo `cascade = REMOVE` khi Profile thực sự phụ thuộc vòng đời Account. Nếu Profile độc lập, phải xử lý FK trước khi xóa Account.

Không cascade remove từ Profile sang Account một cách tùy tiện; một Account thường là đối tượng gốc có thể có nhiều dữ liệu khác và vòng đời riêng.

## 10. @ManyToMany: xóa liên kết không phải xóa entity được chia sẻ

Quan hệ nhiều-nhiều giữa Student và Course thường lưu bằng bảng nối:

~~~sql
CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE courses (
    id BIGINT PRIMARY KEY,
    title VARCHAR(150) NOT NULL
);

CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
~~~

Một student đăng ký nhiều course; một course có nhiều student.

~~~java
@Entity
public class Student {
    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
~~~

~~~java
@Entity
public class Course {
    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
~~~

### 10.1. Bỏ một đăng ký

Muốn Student 1 không còn học Course 5:

~~~java
student.removeCourse(course);
~~~

Nếu helper cập nhật hai collection, Hibernate có thể xóa **hàng trong bảng nối**:

~~~sql
DELETE FROM student_courses
WHERE student_id = 1 AND course_id = 5;
~~~

Hai entity `Student` và `Course` vẫn tồn tại. Đây là unlink association.

### 10.2. Xóa Course

Muốn xóa Course 5 khỏi hệ thống, phải xử lý các hàng trong join table trước hoặc dùng FK action phù hợp, rồi xóa Course. Nhưng không có nghĩa xóa tất cả Student đăng ký Course đó.

### 10.3. Vì sao cascade REMOVE nguy hiểm trong ManyToMany?

Một Course có thể được hàng trăm Student đăng ký. Nếu Student mapping:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses = new HashSet<>();
~~~

thì xóa một Student có thể lan REMOVE tới Course dùng chung. Provider có thể cố xóa các Course được tham chiếu ở nơi khác, dẫn đến xóa dữ liệu không mong muốn hoặc lỗi FK.

Với `@ManyToMany`, thông thường cascade REMOVE không phù hợp cho entity đích được chia sẻ. Xóa association thường chỉ nên xóa row trong join table.

### 10.4. Khi join table có thuộc tính nghiệp vụ, dùng association entity

Nếu `student_courses` cần `enrolled_at`, `grade`, `status`, `attempt_number`, bảng nối không còn chỉ là một liên kết thuần. Hãy mô hình hóa thành entity `Enrollment`:

~~~text
Student 1 ---- * Enrollment * ---- 1 Course
~~~

Khi đó:
- Xóa Enrollment là xóa một lần đăng ký.
- Bỏ Enrollment khỏi Student có thể là orphan removal nếu Enrollment thuộc riêng Student.
- Xóa Student có thể cascade remove Enrollment nếu vòng đời phụ thuộc.
- Course vẫn là entity dùng chung, không nên bị cascade remove từ Student/Enrollment.

Đây là cách biểu diễn rõ hơn để tránh nhầm “xóa liên kết” với “xóa Course”.

## 11. Association entity: phân biệt xóa bản ghi quan hệ với xóa hai đầu

Ví dụ Employee tham gia Project qua `ProjectAssignment`, có role và ngày bắt đầu:

~~~sql
CREATE TABLE project_assignments (
    id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    role_name VARCHAR(80) NOT NULL,
    started_at DATE NOT NULL,
    UNIQUE (employee_id, project_id),
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
~~~

Entity trung gian:

~~~java
@Entity
@Table(name = "project_assignments")
public class ProjectAssignment {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "employee_id", nullable = false)
    private Employee employee;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(name = "role_name", nullable = false, length = 80)
    private String roleName;

    @Column(name = "started_at", nullable = false)
    private LocalDate startedAt;
}
~~~

Bỏ Employee khỏi Project nghĩa là xóa `ProjectAssignment`, không xóa Employee hoặc Project. Xóa Employee hay Project là một nghiệp vụ khác và cần xử lý tất cả assignment liên quan.

Association entity làm cho ba hành vi rõ ràng:

| Hành động | Dữ liệu bị xóa/cập nhật |
|---|---|
| Bỏ assignment | Xóa `project_assignments` row |
| Xóa Employee | Xóa hoặc xử lý các assignment theo chính sách; Project vẫn tồn tại |
| Xóa Project | Xóa hoặc xử lý các assignment; Employee vẫn tồn tại |

Nếu assignment chỉ có vòng đời phụ thuộc Employee, có thể dùng cascade/orphanRemoval từ Employee đến assignment. Không cascade REMOVE từ assignment đến Project hay Employee vì hai entity đó được tham chiếu và có vòng đời riêng.

## 12. SQL và JPA mapping: nhìn vào thao tác thực tế

Bảng sau giúp dự đoán hành vi:

| Ý định nghiệp vụ | Thao tác Java/JPA | SQL khái niệm | Row nào còn? |
|---|---|---|---|
| Bỏ liên kết nullable FK | Đặt owning reference thành null | `UPDATE child SET parent_id = NULL` | Parent và child |
| Chuyển child sang parent khác | Đổi owning reference | `UPDATE child SET parent_id = ?` | Parent cũ, parent mới, child |
| Xóa child | `em.remove(managedChild)` | `DELETE FROM child ...` | Parent |
| Xóa parent, giữ child không liên kết | DB `ON DELETE SET NULL` hoặc unlink trước | `UPDATE child SET parent_id = NULL`, `DELETE parent` | Child |
| Xóa parent và child qua JPA cascade | `em.remove(parent)` với cascade REMOVE | DELETE child rồi parent theo provider/constraints | Không còn parent/child |
| Xóa parent bằng DB cascade | SQL DELETE parent với FK `ON DELETE CASCADE` | DB xóa row con liên quan | Không còn parent/child |
| Bỏ quan hệ ManyToMany | Remove khỏi collection owning side | `DELETE FROM join_table ...` | Cả hai entity |
| Xóa entity ManyToMany đích | `em.remove(managedTarget)` sau xử lý join rows | DELETE join rows, DELETE target | Entity đầu còn nếu hợp lệ |

SQL cụ thể phụ thuộc Hibernate version, mapping, flush order, JDBC batching, dialect và ràng buộc thực tế. Bảng chỉ thể hiện ý nghĩa dữ liệu, không cam kết provider luôn phát đúng một câu SQL theo thứ tự minh họa.

## 13. Cascade không phải một lệnh SQL và không thay thế FK

### 13.1. Cascade PERSIST/MERGE không đồng nghĩa REMOVE

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = { CascadeType.PERSIST, CascadeType.MERGE }
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Cấu hình này cho phép persist/merge lan tới OrderLine, nhưng không tự xóa child khi Order bị remove. Nếu muốn xóa child cùng parent, phải có quy tắc REMOVE hoặc DB FK action phù hợp.

### 13.2. CascadeType.ALL bao gồm những gì?

`CascadeType.ALL` bao gồm các thao tác cascade chuẩn:
- `PERSIST`
- `MERGE`
- `REMOVE`
- `REFRESH`
- `DETACH`

Vì có REMOVE, `ALL` là lựa chọn mạnh. Không dùng chỉ để “tiện” khi tạo graph nếu đối tượng liên quan được chia sẻ hoặc có vòng đời độc lập.

### 13.3. Cascade lan theo hướng association được khai báo

Ví dụ:

~~~java
@ManyToOne(cascade = CascadeType.REMOVE)
private Department department;
~~~

Cascade từ Employee sang Department. Khi remove Employee, thao tác remove có thể lan tới Department — thường là sai nếu nhiều Employee cùng dùng một Department.

Ngược lại:

~~~java
@OneToMany(mappedBy = "department", cascade = CascadeType.REMOVE)
private List<Employee> employees;
~~~

Cascade từ Department sang Employee. Đây là hướng thường được cân nhắc nếu Employee thực sự phụ thuộc vòng đời Department.

**Hướng FK và hướng cascade không bắt buộc phải giống nhau.** Hãy đọc cascade từ nơi khai báo association tới entity đích.

### 13.4. FK vẫn bảo vệ dữ liệu khi ORM không biết

Ngay cả khi entity mapping không khai báo cascade, FK DB vẫn ngăn xóa parent nếu còn child và không có hành động FK khác. Ngược lại, khai báo cascade REMOVE trong Java nhưng schema có constraint/trigger khác cũng có thể khiến delete thất bại.

ORM mapping là một phần hợp đồng; database schema thực tế vẫn là nơi thực thi referential integrity cho mọi nguồn ghi.

## 14. Thao tác xóa qua transaction và thời điểm flush

JPA `remove()` đánh dấu managed entity là removed. SQL DELETE có thể chưa chạy ngay tại dòng gọi.

~~~java
em.getTransaction().begin();

Department department = em.find(Department.class, departmentId);
em.remove(department);

// Tại đây entity đã được đánh dấu removed.
// SQL DELETE có thể chưa chạy.

em.flush();
// Provider gửi các SQL pending; FK constraint có thể được kiểm tra.

em.getTransaction().commit();
// Chỉ khi commit thành công thì việc xóa mới được xác nhận bền vững.
~~~

### 14.1. Flush lỗi không thể bỏ qua rồi tiếp tục như bình thường

Nếu FK constraint từ chối xóa parent, `flush()` có thể ném `PersistenceException`/exception cụ thể của Hibernate. Transaction có thể bị đánh dấu rollback-only hoặc DB đặt transaction vào trạng thái lỗi. Không nên bắt exception, bỏ qua rồi tiếp tục dùng cùng EntityManager để xóa entity khác.

Thông thường cần rollback và xử lý lại trong transaction/context mới sau khi giải quyết nguyên nhân.

### 14.2. Xóa parent với JPA cascade

~~~java
@OneToMany(mappedBy = "department", cascade = CascadeType.REMOVE)
private List<Employee> employees;
~~~

Khi `em.remove(department)` được gọi, Hibernate áp dụng cascade theo association. Thứ tự SQL thực tế phải đáp ứng FK constraints; provider có thể cần tải child, dùng batching hoặc tối ưu theo mapping. Không suy luận rằng một câu DELETE parent duy nhất sẽ luôn chạy khi dùng JPA cascade.

### 14.3. DB ON DELETE CASCADE có thể dùng một câu DELETE parent

Nếu FK đã được tạo với `ON DELETE CASCADE`, DB có thể xóa child khi xử lý DELETE parent. Nhưng context của Hibernate có thể không biết từng child row bị xóa bởi DB. Nếu các child đang managed, state trong memory/cache có thể stale.

Khi chọn DB cascade, hãy quyết định rõ:
- Những entity con nào đang có thể được managed trong context?
- Có second-level cache/collection cache không?
- Xóa đi qua JPA hay native SQL?
- Có callback/audit nào cần chạy cho từng child?
- Có các bảng phụ thuộc khác cũng cần xóa hoặc archive không?

## 15. Bulk DELETE: không tương đương gọi remove trên từng entity

JPQL bulk delete:

~~~java
int deleted = em.createQuery(
    "delete from Employee e where e.department.id = :departmentId"
)
.setParameter("departmentId", departmentId)
.executeUpdate();
~~~

Bulk DML thao tác trực tiếp trên database, không tải từng Employee và không áp dụng đầy đủ lifecycle cascade/orphanRemoval/callback như khi gọi `em.remove(employee)` cho từng managed entity.

Các điểm cần nhớ:

- Cascade REMOVE JPA không tự được chạy cho từng entity bị xóa bởi bulk JPQL DML.
- Entity Employee đã managed trong context có thể vẫn còn trong memory sau khi row bị xóa.
- Collection `Department.employees` đã được nạp có thể không phản ánh kết quả bulk delete.
- `@PreRemove`/`@PostRemove` không được gọi cho từng entity như remove entity-by-entity.
- Cần kiểm tra FK constraint, vì bulk delete có thể bị DB chặn.
- Sau bulk operation, cân nhắc context mới hoặc `clear()`/refresh có chủ đích; đừng clear nếu còn pending changes cần giữ.

Nếu muốn áp dụng cascade/lifecycle semantics, hãy nạp hoặc truy vấn từng entity và gọi remove trong transaction phù hợp, hoặc thiết kế DB-level cascade có chủ đích. Bulk DML phù hợp khi chấp nhận semantics trực tiếp của câu SQL.

## 16. Xóa mềm (soft delete) và ý nghĩa “xóa”

Trong nhiều domain, xóa một Employee hoặc Department không có nghĩa xóa vật lý row. Ứng dụng có thể đánh dấu:

~~~java
@Column(name = "deleted_at")
private Instant deletedAt;
~~~

hoặc:

~~~java
@Column(name = "active", nullable = false)
private boolean active = true;
~~~

Khi đó thao tác nghiệp vụ có thể là:
- Deactivate Employee.
- Archive Department.
- Ẩn association khỏi màn hình.
- Đánh dấu một assignment đã kết thúc.

Đây là **soft delete/archival**, khác với JPA `remove()` mặc định và khác với FK `ON DELETE CASCADE`. Nếu parent soft-delete, DB FK không tự xóa child vì row parent vẫn còn. Ứng dụng phải xác định child có bị ẩn theo parent, có được chuyển sang parent khác hay vẫn còn hiệu lực.

Hibernate có extension soft-delete theo phiên bản; các cơ chế filter/where cũng có thể thay đổi cách truy vấn. Cần xác định rõ việc soft-deleted row có còn tham gia unique constraint/FK hay không, và cách khôi phục.

## 17. Những lỗi thường gặp và cách hiểu đúng

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bỏ child khỏi collection nhưng FK vẫn giữ parent | Chỉ sửa inverse side | Cập nhật owning side |
| Gán FK null nhưng flush lỗi | Cột FK thực tế `NOT NULL` | Chuyển parent hoặc đổi nghiệp vụ/schema |
| Xóa parent báo FK violation | Còn child tham chiếu, không có cascade/set-null | Chọn chính sách xử lý child |
| Bỏ một OrderLine nhưng row vẫn còn | Không bật orphanRemoval và không gọi remove | Xóa child tường minh hoặc orphanRemoval nếu đúng domain |
| Bỏ Employee khỏi Department làm Employee bị xóa | orphanRemoval bật dù Employee có vòng đời riêng | Bỏ orphanRemoval, dùng unlink/transfer |
| Xóa Student làm mất Course | Cascade REMOVE/ALL sang entity dùng chung | Không cascade remove sang Course |
| Xóa parent qua SQL nhưng Java child vẫn còn trong context | DB ON DELETE CASCADE không cập nhật object graph | Clear/refresh/context mới |
| Bulk JPQL delete không chạy callbacks | Bulk DML bỏ qua entity lifecycle callbacks | Dùng remove từng entity nếu cần callback |
| `CascadeType.ALL` gây xóa dữ liệu bất ngờ | ALL bao gồm REMOVE | Chỉ cấu hình cascade cần thiết |
| Xóa child bị chặn bởi FK khác | Bảng khác còn tham chiếu child | Xử lý quan hệ phụ thuộc/lịch sử |
| Xóa parent bằng JPA cascade nhưng vẫn lỗi | Child có quan hệ phụ thuộc khác hoặc schema khác mapping | Kiểm tra toàn bộ FK/trigger/DDL |
| Chuyển child sang parent mới rồi child bị xóa | orphanRemoval trên quan hệ cũ | Thiết kế lại ownership/lifecycle và transaction |
| Collection Java vẫn chứa child đã remove | Chỉ gọi em.remove(child) mà không đồng bộ graph | Cập nhật collection hoặc reload context |
| DB row đã bị xóa nhưng second-level cache còn dữ liệu | Native/DB cascade bypass invalidation | Cache strategy/invalidation phù hợp |

## 18. Cách chọn hành vi đúng theo câu hỏi nghiệp vụ

Trước khi viết code, hãy diễn đạt ý định bằng câu rõ ràng:

| Câu hỏi nghiệp vụ | Hành động |
|---|---|
| “Nhân viên không còn thuộc phòng ban này, nhưng vẫn làm việc trong công ty.” | Unlink hoặc chuyển sang phòng ban khác |
| “Nhân viên nghỉ việc và không còn là bản ghi hoạt động.” | Soft delete/deactivate hoặc delete theo chính sách lưu trữ |
| “Xóa hẳn nhân viên khỏi hệ thống.” | Remove child, sau khi xử lý các FK phụ thuộc |
| “Phòng ban không còn nhân viên và có thể bị xóa.” | Remove parent |
| “Xóa phòng ban, giữ nhân viên ở trạng thái chưa phân công.” | Set FK null hoặc DB ON DELETE SET NULL |
| “Xóa phòng ban thì xóa luôn nhân viên chỉ thuộc phòng ban đó.” | Cascade REMOVE/orphan lifecycle hoặc xóa tường minh |
| “Người dùng bỏ đăng ký một khóa học.” | Xóa association row, giữ Student và Course |
| “Xóa khóa học khỏi catalog.” | Xử lý join rows/registration history rồi xóa/archive Course |
| “Xóa một assignment giữa nhân viên và dự án.” | Xóa association entity, giữ Employee và Project |

### 18.1. Khi child có thể sống độc lập

Ví dụ Employee có thể chuyển phòng ban, nghỉ việc hoặc được giữ hồ sơ lịch sử. Thường:
- FK có thể nullable hoặc có quy tắc transfer.
- Không bật orphanRemoval cho việc bỏ khỏi collection.
- Không cascade REMOVE từ Department sang Employee nếu không có chính sách xóa đồng bộ.
- Xóa Department phải được kiểm tra hoặc xử lý riêng.

### 18.2. Khi child không có ý nghĩa nếu thiếu parent

Ví dụ OrderLine chỉ tồn tại như một phần của Order. Thường:
- `OrderLine.order` là owning `@ManyToOne`, FK `NOT NULL`.
- `Order.lines` là inverse `@OneToMany(mappedBy = "order")`.
- `orphanRemoval = true` có thể phù hợp.
- Cascade PERSIST/MERGE có thể phù hợp để lưu graph.
- Xóa Order có thể xóa lines qua orphan-removal semantics hoặc cascade REMOVE.
- Không cascade remove sang Product được tham chiếu bởi OrderLine vì Product là entity dùng chung.

### 18.3. Khi entity đích được chia sẻ

Ví dụ User và Role, Student và Course, Product và Category:
- Bỏ liên kết chỉ xóa join row.
- Không xóa entity đích chỉ vì một collection không còn tham chiếu.
- Cascade REMOVE thường không phù hợp.
- Nếu join có thuộc tính nghiệp vụ, dùng association entity để quản lý vòng đời liên kết.

## 19. Bài tập tự luyện

### Bài 1 — Unlink hay delete?

`Employee.department_id` nullable. Người dùng bỏ Bình khỏi Engineering vì Bình chuyển sang trạng thái chưa phân công.

**Câu hỏi:** nên dùng UPDATE hay DELETE?

**Định hướng:** UPDATE `department_id = NULL`; Employee vẫn tồn tại.

### Bài 2 — FK NOT NULL

`Employee.department_id` có constraint NOT NULL. Người dùng yêu cầu bỏ Employee khỏi phòng ban mà không chỉ định phòng ban mới.

**Câu hỏi:** có thể gọi `employee.setDepartment(null)` rồi commit không?

**Đáp án:** Không thể lưu thành công với schema đó. Cần thay đổi nghiệp vụ/schema hoặc chuyển sang parent hợp lệ.

### Bài 3 — Chỉ sửa inverse side

`Department.employees` dùng `@OneToMany(mappedBy = "department")`; code chỉ gọi `department.getEmployees().remove(employee)`.

**Câu hỏi:** FK chắc chắn đổi không?

**Đáp án:** Không. `Employee.department` là owning side; phải cập nhật owning reference.

### Bài 4 — Cascade REMOVE

`Department.employees` có `cascade = REMOVE`. Gọi `em.remove(department)`.

**Câu hỏi:** điều gì xảy ra với Employee liên quan?

**Định hướng:** REMOVE được cascade tới child theo mapping. Chỉ dùng nếu nghiệp vụ thật sự muốn xóa các Employee đó.

### Bài 5 — Orphan removal

`Order.lines` có `orphanRemoval = true`. Người dùng bỏ một OrderLine khỏi Order nhưng Order vẫn tồn tại.

**Câu hỏi:** line có được xóa không?

**Định hướng:** Có thể bị remove theo orphan-removal semantics khi flush. Đây là xóa child do bị tách khỏi association, khác với chỉ unlink FK thông thường.

### Bài 6 — Entity dùng chung

Một Course được 100 Student đăng ký. Student A bỏ Course.

**Câu hỏi:** có xóa Course không?

**Đáp án:** Không. Chỉ xóa association row `student_courses`; Student và Course vẫn tồn tại.

### Bài 7 — DB ON DELETE SET NULL

FK `employees.department_id` dùng ON DELETE SET NULL. Xóa Department.

**Câu hỏi:** Employee bị xóa không?

**Đáp án:** Không. Database cập nhật FK của Employee thành NULL và giữ các row Employee.

### Bài 8 — DB ON DELETE CASCADE

FK dùng ON DELETE CASCADE. Một script SQL ngoài Hibernate xóa Department.

**Câu hỏi:** callback `@PreRemove` của từng Employee có chạy không?

**Đáp án:** Không. DB tự xóa row con; không đi qua lifecycle remove của JPA.

### Bài 9 — Bulk JPQL delete

Chạy `delete from Employee e where e.department.id = :id`.

**Câu hỏi:** có cascade và callback như gọi `em.remove()` từng Employee không?

**Đáp án:** Không. Bulk DML trực tiếp tác động database và bỏ qua entity lifecycle semantics thông thường.

### Bài 10 — Chuyển child giữa hai parent

`OrderLine` có orphanRemoval trên `Order.lines`. Code remove line khỏi Order A rồi add vào Order B.

**Câu hỏi:** có nên giả định line luôn được chuyển mà không bị xóa?

**Định hướng:** Không. Orphan removal biểu diễn vòng đời phụ thuộc và việc tách có thể dẫn đến remove. Thiết kế chuyển parent riêng, xem lại ownership/orphan policy và SQL flush order.

## 20. Tổng kết

Ba hành động phải được phân biệt rõ:

- **Bỏ liên kết:** thay đổi FK hoặc xóa row join table. Hai entity đầu/cuối vẫn tồn tại.
- **Xóa child:** gọi remove trên child managed hoặc để orphan removal xử lý child bị tách khỏi association có vòng đời phụ thuộc.
- **Xóa parent:** xóa parent và quyết định rõ child sẽ bị chặn, được unlink, được cascade remove hay được xử lý theo DB FK action.

Các annotation không thể thay thế quyết định nghiệp vụ:

- `mappedBy` xác định inverse side; owning side điều khiển FK.
- `CascadeType.REMOVE` lan thao tác xóa từ source sang target.
- `orphanRemoval = true` xóa child khi child bị tách khỏi quan hệ riêng theo semantics JPA.
- `ON DELETE CASCADE`/`SET NULL` là hành động của database, có thể áp dụng cả khi SQL không đi qua ORM.
- `CascadeType.ALL` bao gồm REMOVE và có thể xóa dữ liệu dùng chung nếu đặt sai hướng.
- `@ManyToMany` thường chỉ cần xóa join row khi bỏ association; không xóa entity đầu kia.
- Bulk JPQL/SQL không có cùng entity lifecycle callbacks, cascade và first-level state synchronization như thao tác từng managed entity.

Trước khi viết method xóa, hãy xác định: **entity nào phải còn tồn tại sau thao tác, association nào phải còn, và bản ghi nào thực sự phải biến mất khỏi database?** Khi trả lời được ba câu hỏi đó, việc chọn unlink, `remove`, `orphanRemoval`, cascade và FK action sẽ rõ ràng hơn.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — entity lifecycle, relationship mappings, cascade operations và orphan removal.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/) — `EntityManager.remove`, `CascadeType`, `OneToMany`, `OneToOne` và các annotation liên quan.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — association mappings, cascading, orphan removal, flushing và bulk operations theo phiên bản.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — ví dụ cụ thể về entity associations và delete behavior.
- [PostgreSQL Foreign Key Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — `ON DELETE RESTRICT`, `CASCADE`, `SET NULL` và các hành động tham chiếu.
- [PostgreSQL DELETE](https://www.postgresql.org/docs/current/sql-delete.html) — semantics của câu lệnh DELETE.

> DDL và SQL minh họa dùng cú pháp quan hệ phổ biến; cú pháp FK action và hành vi constraint phụ thuộc hệ quản trị. Hibernate version, dialect và mapping thực tế quyết định SQL cụ thể. Trong production, xác nhận schema/migration và kiểm thử transaction trên database mục tiêu.
