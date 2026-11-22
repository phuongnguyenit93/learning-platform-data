# Quan hệ một chiều, hai chiều và ý nghĩa của `mappedBy`

## 1. Quan hệ giữa các entity có bao nhiêu hướng?

Trong cơ sở dữ liệu quan hệ, một **foreign key** cho biết bản ghi của bảng này tham chiếu bản ghi của bảng khác. Trong Java Persistence (Jakarta Persistence/JPA), ta thể hiện liên kết bằng một thuộc tính tham chiếu đến entity khác. Hibernate ORM đọc annotation và đồng bộ quan hệ đó với database.

Ví dụ một nhân viên thuộc phòng ban:

~~~sql
CREATE TABLE departments (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    department_id BIGINT NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id) REFERENCES departments(id)
);
~~~

Một hàng của `employees` chứa `department_id`. Nhưng ở mô hình Java, có ít nhất hai cách thiết kế.

**Quan hệ một chiều (unidirectional):**

~~~text
Employee ── getDepartment() ──> Department

Employee có tham chiếu department.
Department không có thuộc tính employees.
~~~

**Quan hệ hai chiều (bidirectional):**

~~~text
Employee ── getDepartment() ──> Department
Employee <── getEmployees() ─── Department

Vẫn chỉ có một FK: employees.department_id.
~~~

Hướng là đặc tính của **object model**, không nhất thiết là số lượng khóa ngoại. Một chiều không ngăn ứng dụng viết SQL hoặc JPQL để truy vấn theo chiều ngược lại; nó chỉ không có thuộc tính điều hướng trực tiếp trong object.

Bài học thuộc chủ đề **Quan hệ đơn trị**, tập trung vào `@ManyToOne` và `@OneToOne`. Để thấy rõ `mappedBy`, ta cũng cần nhìn phía ngược của `@ManyToOne` là một collection `@OneToMany`.

Sau khi học, bạn nên làm được các việc sau: đọc mapping và xác định chiều điều hướng; nhận biết **owning side** và **inverse side**; dùng `mappedBy` đúng tên thuộc tính Java; thiết kế `@OneToOne`/`@ManyToOne` một chiều và hai chiều; đồng bộ hai phía của quan hệ trong bộ nhớ; tránh lỗi cascade, fetch và foreign key phổ biến.

## 2. Phân biệt hướng điều hướng, owning side và inverse side

Ba khái niệm này liên quan nhưng **không đồng nghĩa**.

### Hướng điều hướng

Một chiều nghĩa là chỉ một class có thuộc tính tham chiếu đến class kia. Hai chiều nghĩa là cả hai class có thuộc tính cho phép đi tới đối tượng ở phía còn lại.

Ví dụ `Employee.department` cho phép nhân viên biết phòng ban. Nếu thêm `Department.employees`, phòng ban có thể biết danh sách nhân viên.

### Owning side (phía sở hữu quan hệ)

Trong JPA, **owning side** là phía mà mapping quyết định thay đổi liên kết trong database. Với quan hệ qua khóa ngoại, đây thường là phía định nghĩa `@JoinColumn` chứa foreign key.

~~~java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
~~~

Thuộc tính `Employee.department` là owning side. Hibernate dựa vào phía này để ghi `employees.department_id` khi quan hệ thay đổi.

**Owning side không đồng nghĩa chủ sở hữu nghiệp vụ, aggregate root, quyền xóa hay hướng cascade.** Những vấn đề đó cần quyết định riêng.

### Inverse side (phía nghịch đảo)

Trong một quan hệ hai chiều, phía nghịch đảo khai báo `mappedBy` để nói rằng ánh xạ liên kết do thuộc tính **ở entity bên kia** sở hữu.

~~~java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
~~~

Chuỗi `"department"` là **tên thuộc tính Java** trong entity `Employee`, không phải tên cột SQL `department_id`, tên bảng hay tên entity.

~~~text
Employee.department
   @ManyToOne
   @JoinColumn(name = "department_id")
                  |
                  | owns employees.department_id
                  v
            DATABASE FOREIGN KEY
                  ^
                  |
Department.employees
   @OneToMany(mappedBy = "department")
   inverse: khai báo đường điều hướng ngược
~~~

Quy tắc: trong mapping hai chiều, hãy tìm phía có `mappedBy`; đó là **inverse side**. Thuộc tính mà chuỗi `mappedBy` trỏ đến phải là owning side tương ứng.

## 3. @ManyToOne một chiều: nhân viên biết phòng ban

Đây thường là dạng quan hệ đơn trị đơn giản nhất.

Class `Department`:

~~~java
package demo.hr;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "departments")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Department() {}

    public Department(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
~~~

Class `Employee`:

~~~java
package demo.hr;

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
@Table(name = "employees")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() {}

    public Employee(String fullName, Department department) {
        this.fullName = fullName;
        this.department = department;
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public Department getDepartment() { return department; }

    public void changeDepartment(Department department) {
        this.department = department;
    }
}
~~~

Ý nghĩa:

- `@ManyToOne`: nhiều nhân viên có thể trỏ tới cùng phòng ban.
- `@JoinColumn(name = "department_id")`: cột FK trong bảng `employees`. Nếu bỏ `name`, provider sử dụng quy tắc đặt tên mặc định và naming strategy.
- `optional = false`: về mặt mô hình JPA, quan hệ nhân viên–phòng ban là bắt buộc.
- `nullable = false`: mô tả ý định DDL có `NOT NULL`, còn constraint thực tế phải có trong database.
- `fetch = FetchType.LAZY`: yêu cầu trì hoãn tải phòng ban, hành vi cụ thể phụ thuộc Hibernate và persistence context.
- Không có trường `Department.employees`, nên đây là **một chiều**.

Vì `Employee.department` là owning side nên khi một nhân viên được quản lý và đổi phòng ban, Hibernate có thể cập nhật foreign key:

~~~java
em.getTransaction().begin();

Employee employee = em.find(Employee.class, employeeId);
Department destination =
    em.getReference(Department.class, destinationDepartmentId);

employee.changeDepartment(destination);

em.getTransaction().commit();
~~~

SQL quan hệ dự kiến có dạng:

~~~sql
UPDATE employees
SET department_id = ?
WHERE id = ?;
~~~

Thời điểm và SQL cụ thể tùy flush, transaction, ID strategy và Hibernate version. `getReference` không đảm bảo id tồn tại; vi phạm constraint hoặc truy cập proxy không tồn tại có thể gây lỗi sau đó.

### Không có điều hướng ngược vẫn truy vấn ngược được

Mặc dù `Department` không giữ collection, ta vẫn có thể truy vấn nhân viên theo phòng ban:

~~~java
List<Employee> members = em.createQuery(
        "select e from Employee e where e.department.id = :departmentId",
        Employee.class)
    .setParameter("departmentId", departmentId)
    .getResultList();
~~~

Đây là điểm quan trọng khi lựa chọn thiết kế: **chỉ thêm quan hệ hai chiều nếu object model thực sự cần điều hướng ngược**, không phải vì database cho phép truy vấn ngược.

### Lưu mới hai entity

~~~java
em.getTransaction().begin();

Department department = new Department("Engineering");
em.persist(department);

Employee an = new Employee("An", department);
Employee binh = new Employee("Bình", department);
em.persist(an);
em.persist(binh);

em.getTransaction().commit();
~~~

Ví dụ không gắn cascade ở `@ManyToOne`, vì thế gọi `persist` cho phòng ban trước. Một phòng ban thường được chia sẻ bởi nhiều nhân viên; dùng `CascadeType.ALL` hoặc `REMOVE` từ nhân viên sang phòng ban có thể làm xóa dữ liệu dùng chung ngoài ý định.

## 4. @ManyToOne / @OneToMany hai chiều

Nếu nghiệp vụ thường gọi `department.getEmployees()`, thêm collection ở `Department`:

~~~java
import jakarta.persistence.OneToMany;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Thêm vào entity Department ở phần trên:
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

void addEmployeeInternal(Employee employee) {
    if (!employees.contains(employee)) {
        employees.add(employee);
    }
}

void removeEmployeeInternal(Employee employee) {
    employees.remove(employee);
}
~~~

Đồng thời thay method `changeDepartment` ở `Employee` để đồng bộ hai phía:

~~~java
public void changeDepartment(Department newDepartment) {
    if (newDepartment == null) {
        throw new IllegalArgumentException("department is required");
    }
    if (department == newDepartment) {
        return;
    }

    Department previous = department;
    if (previous != null) {
        previous.removeEmployeeInternal(this);
    }

    department = newDepartment;
    newDepartment.addEmployeeInternal(this);
}
~~~

Đây là một mẫu helper để đồng bộ object graph, không phải cú pháp bắt buộc của JPA. Phần triển khai thực tế cần cân nhắc equality, detached entities, nullability và quy tắc chuyển nhân viên giữa các phòng ban. Các method internal ở ví dụ cần được đặt cùng package hoặc thay quyền truy cập phù hợp.

### Vì sao mappedBy = "department"?

Collection thuộc `Department` nhưng chứa entity `Employee`. Hibernate nhìn vào `Employee` và tìm một field/property đúng tên `department`:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
~~~

Chính field này là owning side. `mappedBy` dùng **tên thuộc tính Java**, nên các cách dưới đây sai:

~~~java
// SAI: department_id là tên cột trong database.
@OneToMany(mappedBy = "department_id")
private List<Employee> employees;

// SAI: Department là tên class.
@OneToMany(mappedBy = "Department")
private List<Employee> employees;

// SAI: employees là tên collection ở phía hiện tại.
@OneToMany(mappedBy = "employees")
private List<Employee> employees;
~~~

Nếu đổi field `Employee.department` thành `team`, phải cập nhật `mappedBy = "team"` dù tên cột vẫn là `department_id`. Ngược lại, đổi tên cột từ `department_id` sang `dept_id` không đòi đổi `mappedBy` nếu field vẫn tên `department`.

### Chỉ sửa inverse collection có đủ không?

Không. Ví dụ này chỉ thay danh sách trong bộ nhớ mà không đổi owning side:

~~~java
// Ví dụ phương pháp sai, giả sử collection có thể sửa trực tiếp:
Department destination = em.find(Department.class, newDepartmentId);
Employee employee = em.find(Employee.class, employeeId);

destination.getEmployees().add(employee); // chỉ sửa inverse side
~~~

Ngay cả nếu collection cho phép `add`, `employee.department` vẫn trỏ về phòng ban cũ. Hibernate dựa vào owning side để cập nhật FK, vì vậy trạng thái hai phía có thể mâu thuẫn và database không được cập nhật như mong đợi.

Cách đúng là dùng helper:

~~~java
Department destination = em.find(Department.class, newDepartmentId);
Employee employee = em.find(Employee.class, employeeId);

destination.addEmployee(employee);
// Cập nhật Employee.department và collection liên quan.
~~~

**Đồng bộ object graph** là trách nhiệm của mã Java. **Đồng bộ khóa ngoại** do Hibernate quyết định dựa trên owning side.

### mappedBy không phải cascade

~~~java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
~~~

khác với:

~~~java
@OneToMany(mappedBy = "department", cascade = CascadeType.PERSIST)
private List<Employee> employees;
~~~

Cả hai vẫn có inverse side là `Department.employees`. Dạng thứ hai bổ sung cascade persist; nó **không chuyển quyền sở hữu FK**. Cascade là quy tắc lan truyền thao tác vòng đời, còn `mappedBy` chỉ định quan hệ được ánh xạ ở đâu.

### So sánh một chiều và hai chiều

| Tiêu chí | Employee → Department | Employee ↔ Department |
|---|---|---|
| Thuộc tính ở Employee | `department` | `department` |
| Thuộc tính ở Department | Không có | `employees` |
| FK | `employees.department_id` | Vẫn là một FK đó |
| Owning side | Employee.department | Employee.department |
| Inverse side | Không có | Department.employees |
| `mappedBy` | Không dùng | `"department"` |
| Đường điều hướng ngược | Cần truy vấn | Có collection Java |
| Độ phức tạp đồng bộ trong bộ nhớ | Thấp hơn | Cần giữ hai phía nhất quán |

Chọn quan hệ hai chiều khi thực sự cần biểu diễn đường điều hướng ngược. Không nên thêm mọi collection chỉ để “đủ hai chiều”, vì chúng làm tăng độ phức tạp object graph, lazy loading và serialization.
## 5. @OneToOne một chiều: hồ sơ tham chiếu tài khoản

Quan hệ `@OneToOne` diễn tả một entity nguồn tham chiếu tối đa một entity đích. Khác với `@ManyToOne`, thiết kế một-một thường cần **ràng buộc UNIQUE trên cột khóa ngoại** để database ngăn hai bản ghi cùng tham chiếu một đích.

Ví dụ hệ thống có bảng tài khoản và bảng hồ sơ:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE account_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES accounts(id)
);
~~~

Phía `AccountProfile` giữ khóa ngoại:

~~~java
@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;

    protected AccountProfile() {}

    public AccountProfile(Account account, String displayName) {
        this.account = account;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public Account getAccount() { return account; }
    public String getDisplayName() { return displayName; }
}
~~~

Entity `Account` chưa chứa đường tham chiếu đến profile:

~~~java
@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 150)
    private String email;

    protected Account() {}

    public Account(String email) {
        this.email = email;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
}
~~~

Đoạn code rút gọn phần import: sử dụng các annotation tương ứng từ `jakarta.persistence`, gồm `Entity`, `Table`, `Id`, `GeneratedValue`, `GenerationType`, `Column`, `OneToOne`, `JoinColumn` và `FetchType`.

Sơ đồ:

~~~text
AccountProfile ── account: Account ──> Account
       |
       +── account_profiles.account_id (FK + UNIQUE)
~~~

Đây là quan hệ **một chiều** từ profile sang account. `AccountProfile.account` là owning side và `Account` chưa có inverse side.

`optional = false` và `nullable = false` mô tả profile phải trỏ đến account. Chúng **không bảo đảm mỗi account phải có profile**; account có thể tồn tại mà chưa có bản ghi `account_profiles`. Ràng buộc `UNIQUE` ở database mới bảo vệ điều kiện không có hai profile trỏ đến một account.

Lưu dữ liệu:

~~~java
em.getTransaction().begin();

Account account = new Account("an@example.test");
em.persist(account);

AccountProfile profile = new AccountProfile(account, "An");
em.persist(profile);

em.getTransaction().commit();
~~~

Vì ví dụ chưa cấu hình cascade, hai entity được `persist` tường minh. Hibernate có thể ghi account trước, rồi profile với FK đến account. Thứ tự SQL và thời điểm flush phụ thuộc provider/ID strategy.

## 6. @OneToOne hai chiều: mappedBy đặt ở đâu?

Bây giờ cần cả hai đường điều hướng:

~~~java
AccountProfile profile = account.getProfile();
Account owner = profile.getAccount();
~~~

Ta giữ một foreign key ở bảng `account_profiles`; entity `AccountProfile` vẫn là owning side:

~~~java
@OneToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private Account account;
~~~

Thêm inverse side vào `Account`:

~~~java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
~~~

`mappedBy = "account"` trỏ đến **tên thuộc tính `AccountProfile.account`**. Nó không trỏ đến cột `account_id`.

~~~text
Account ───── profile: AccountProfile ───────▶ AccountProfile
   ▲                 inverse                        |
   |                                                |
   └───────────── account: Account ◀────────────────┘
                    owning
                       |
            account_profiles.account_id (FK)
~~~

Vì đây là hai hướng của **cùng một quan hệ**, database chỉ cần FK đã có.

### 6.1. Helper method đồng bộ hai phía

Một cách thiết kế là không cho người dùng API chỉnh hai tham chiếu độc lập. Ví dụ, `Account` chỉ cho gắn một profile khi chưa có:

~~~java
// Thêm vào Account, cùng với import OneToOne, FetchType, CascadeType:
@OneToOne(
    mappedBy = "account",
    fetch = FetchType.LAZY,
    cascade = CascadeType.PERSIST
)
private AccountProfile profile;

public AccountProfile getProfile() {
    return profile;
}

public void attachProfile(AccountProfile newProfile) {
    if (newProfile == null) {
        throw new IllegalArgumentException("profile is required");
    }
    if (profile != null && profile != newProfile) {
        throw new IllegalStateException("account already has a profile");
    }
    if (newProfile.getAccount() != null &&
        newProfile.getAccount() != this) {
        throw new IllegalStateException("profile belongs to another account");
    }

    profile = newProfile;
    newProfile.assignAccount(this);
}
~~~

Và `AccountProfile` của biến thể hai chiều có method nội bộ:

~~~java
// Biến thể constructor dành cho phương án attachProfile:
public AccountProfile(String displayName) {
    this.displayName = displayName;
}

void assignAccount(Account owner) {
    this.account = owner;
}
~~~

Dùng:

~~~java
em.getTransaction().begin();

Account account = new Account("binh@example.test");
AccountProfile profile = new AccountProfile("Bình");

account.attachProfile(profile);
em.persist(account); // Cascade PERSIST sang profile.

em.getTransaction().commit();
~~~

Helper làm cho `account.profile` và `profile.account` khớp nhau. Hibernate dùng `profile.account` (owning side) để ghi FK. Việc cascade persist từ account sang profile là **một quy tắc vòng đời độc lập** với `mappedBy`.

Ví dụ này thiết kế cho thao tác gắn profile một lần; gỡ hoặc thay profile cần quy tắc riêng cho `NOT NULL`, unique constraint và thời điểm xóa. Nếu chỉ đặt `account.profile = profile` ở phía inverse mà để `profile.account` là null, Hibernate không có giá trị FK đúng để lưu quan hệ.

### 6.2. Owning side có luôn nằm trên Profile không?

Không. Với `@OneToOne`, có thể chọn bảng nào giữ FK. Hai thiết kế khác nhau:

~~~text
Thiết kế A:
account_profiles.account_id -> accounts.id

AccountProfile.account       @JoinColumn(name = "account_id")
Account.profile              @OneToOne(mappedBy = "account")

Thiết kế B:
accounts.profile_id -> account_profiles.id

Account.profile              @JoinColumn(name = "profile_id")
AccountProfile.account       @OneToOne(mappedBy = "profile")
~~~

Ở thiết kế A, owning side là `AccountProfile.account`. Ở thiết kế B, owning side là `Account.profile`. Chọn theo schema, ràng buộc vòng đời và nhu cầu nghiệp vụ. Đổi thiết kế cần migration, không chỉ di chuyển annotation.

Trái lại, với cặp `@ManyToOne` và `@OneToMany` hai chiều, phía `@ManyToOne` là owning side trong mapping chuẩn này.

### 6.3. Tại sao không viết @JoinColumn trên cả hai phía?

Nếu khai báo:

~~~java
// Account:
@OneToOne
@JoinColumn(name = "profile_id")
private AccountProfile profile;

// AccountProfile:
@OneToOne
@JoinColumn(name = "account_id")
private Account account;
~~~

Hibernate có thể hiểu đây là **hai quan hệ sở hữu độc lập**, chứ không phải hai hướng của một association. DB có thể sinh hai cột FK, mã Java có hai giá trị không nhất quán, và việc cập nhật một phía không quản lý phía còn lại như mong đợi.

Nếu cần một quan hệ hai chiều với một FK, hãy có một owning side và một inverse side dùng `mappedBy`. Ngược lại, cũng không đặt `mappedBy` ở cả hai phía vì như vậy không còn owning side hợp lệ.
## 7. Shared primary key OneToOne với @MapsId

Ngoài cách dùng một cột FK riêng và `UNIQUE`, quan hệ một-một có thể sử dụng **khóa chính dùng chung (shared primary key)**: ID của hồ sơ chính là ID của tài khoản.

Schema minh họa:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    email VARCHAR(150) NOT NULL
);

CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_profile_account
        FOREIGN KEY (id) REFERENCES accounts(id)
);
~~~

Ở đây `account_profiles.id` đồng thời là PK và FK đến `accounts.id`; không cần một cột `account_id` thứ hai.

JPA hỗ trợ ánh xạ bằng `@MapsId`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "id")
    private Account account;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected AccountProfile() {}

    public AccountProfile(Account account, String displayName) {
        this.account = account;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public Account getAccount() { return account; }
}
~~~

`@MapsId` cho biết định danh của profile được lấy từ định danh của account được tham chiếu. Vì ID phụ thuộc account nên **không khai báo `@GeneratedValue` độc lập** cho `AccountProfile.id` trong mapping này. Khi lưu, account phải có định danh hợp lệ theo cơ chế tạo khóa của dự án.

Nếu cần hai chiều, ở `Account` thêm:

~~~java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
~~~

`AccountProfile.account` vẫn là owning side, còn `Account.profile` là inverse side. Giá trị `mappedBy` vẫn là tên thuộc tính Java `account`, **không phải cột SQL `id`**.

Lợi ích: sơ đồ dữ liệu gọn, mỗi profile có duy nhất một account theo PK, liên kết và định danh cùng một khóa. Hạn chế: vòng đời và cách tạo khóa phụ thuộc chặt vào account; việc tách/move profile sang account khác không phải cập nhật FK đơn giản.

### Còn @PrimaryKeyJoinColumn?

`@PrimaryKeyJoinColumn` xuất hiện trong một số thiết kế dùng chung khóa chính và trong những dạng mapping khác. Tuy nhiên, đối với quan hệ một-một có ID dẫn xuất, `@MapsId` thường diễn đạt ý định rõ ràng hơn: ID của entity phụ thuộc ID của association. Không nên sao chép máy móc ví dụ `@PrimaryKeyJoinColumn` cũ rồi bỏ qua cách Hibernate/JPA đồng bộ định danh.

## 8. mappedBy có thể xuất hiện ở đâu?

| Association | Phía sở hữu thường gặp | Phía inverse dùng `mappedBy` |
|---|---|---|
| `@ManyToOne` một chiều | Thuộc tính `@ManyToOne` | Không có |
| `@ManyToOne` / `@OneToMany` hai chiều | `@ManyToOne` | `@OneToMany(mappedBy = "...")` |
| `@OneToOne` một chiều | Thuộc tính tham chiếu có FK/mapping | Không có |
| `@OneToOne` hai chiều | Bên có `@JoinColumn` hoặc mapping sở hữu | Bên còn lại dùng `@OneToOne(mappedBy = "...")` |
| `@ManyToMany` hai chiều | Bên quản lý join table | Bên còn lại dùng `@ManyToMany(mappedBy = "...")` |

`@ManyToOne` **không có phần tử `mappedBy`**. Với cặp nhiều-một/một-nhiều, khai báo `mappedBy` nằm trên collection phía `@OneToMany`.

Một `@OneToMany` một chiều không dùng `mappedBy` vì không có `@ManyToOne` ở entity con để tham chiếu ngược. Tùy mapping, JPA/provider có thể dùng join table mặc định hoặc cấu hình FK qua `@JoinColumn`. Đó là mô hình khác với quan hệ hai chiều `@ManyToOne`/`@OneToMany(mappedBy)`.

Trong một association hai chiều chuẩn chỉ có **một phía sở hữu**. Nếu cả hai phía cùng mang `mappedBy` mà không có owner hợp lệ, ánh xạ có thể bị từ chối khi khởi tạo Hibernate. Nếu cả hai cùng khai báo join column độc lập, đó có thể trở thành hai association khác nhau.

### Ví dụ đổi tên thuộc tính và cột

~~~java
// Entity Employee:
@ManyToOne
@JoinColumn(name = "department_fk")
private Department team;
~~~

Nếu entity `Department` có collection:

~~~java
@OneToMany(mappedBy = "team")
private List<Employee> members;
~~~

Giá trị đúng là `mappedBy = "team"`, bất kể cột SQL được đặt tên là `department_fk`. Nếu đổi cột SQL, cần cập nhật `@JoinColumn` và migration, không phải `mappedBy`. Nếu đổi field Java `team` thành `department`, cần sửa `mappedBy` tương ứng.

## 9. Sự khác nhau giữa mappedBy, JoinColumn và JoinTable

Các annotation này thường xuất hiện gần nhau nhưng có ý nghĩa khác nhau.

### JoinColumn: cột tạo liên kết

~~~java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
~~~

`@JoinColumn` mô tả cột FK (hoặc join column phù hợp) và các thuộc tính như `nullable`, `unique`, `referencedColumnName`. Với đơn vị PK thông thường, `referencedColumnName` có thể bỏ vì provider dùng PK của entity đích theo quy tắc ánh xạ.

Ví dụ khai báo tường minh:

~~~java
@ManyToOne
@JoinColumn(
    name = "department_id",
    referencedColumnName = "id",
    nullable = false
)
private Department department;
~~~

`name` là cột trên bảng chứa FK, còn `referencedColumnName` là cột ở bảng được tham chiếu. Không đảo hai tên này.

### mappedBy: ánh xạ đang do phía khác quản lý

~~~java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
~~~

`mappedBy` **không tạo hay đặt tên FK**. Nó liên kết hai thuộc tính Java thành hai hướng của cùng một association. Phía inverse không cần một `@JoinColumn` riêng để viết lại cùng FK.

### JoinTable: bảng nối

Một association có thể được lưu bằng bảng trung gian:

~~~text
account              account_profile_link           profile
id PK  <── account_id      profile_id ──>           id PK
             UNIQUE             UNIQUE
~~~

`@JoinTable` mô tả bảng trung gian và các join columns. Với `@OneToOne` dùng join table, uniqueness trên hai phía có thể cần thiết để bảo vệ đúng cardinality. Đây là một lựa chọn cấu trúc schema khi không muốn/không thể đặt FK trực tiếp ở một bảng.

Trong đa số bài toán `@ManyToOne` hoặc `@OneToOne` thông thường có FK trực tiếp, `@JoinColumn` dễ hiểu và ít phức tạp hơn. Không nên suy luận một quan hệ hai chiều phải có join table: **hai chiều nói về object navigation, không phải số bảng**.

## 10. FetchType: có quan hệ hai chiều không có nghĩa đã tải sẵn

Quan hệ Java là đường truy cập; việc dữ liệu đích đã được nạp hay chưa là câu chuyện riêng.

Theo mặc định của Jakarta Persistence:

| Mapping | Mặc định `fetch` |
|---|---|
| `@ManyToOne` | `EAGER` |
| `@OneToOne` | `EAGER` |
| `@OneToMany` | `LAZY` |
| `@ManyToMany` | `LAZY` |

Đây là mặc định của **đặc tả**, không phải lời khuyên luôn giữ nguyên. `EAGER` là yêu cầu dữ liệu liên quan được nạp theo ngữ nghĩa fetch, nhưng không bảo đảm mọi entity đều nạp chỉ bằng một SQL join. Với quan hệ to-one, nhiều dự án chọn `fetch = FetchType.LAZY` có chủ đích và kiểm tra câu SQL thực tế.

### 10.1. LAZY là hint, không phải lời hứa cố định

Jakarta Persistence cho phép provider xử lý yêu cầu `LAZY` như gợi ý trong một số trường hợp. Hibernate thường sử dụng proxy hoặc cơ chế enhancement phù hợp để tải chậm. Với **inverse side của `@OneToOne`**, Hibernate có thể phải kiểm tra sự tồn tại của entity liên quan trước khi quyết định giá trị là null hay một tham chiếu; trong một số cấu hình/version, điều này gây thêm truy vấn hoặc cần bytecode enhancement để đạt hành vi lazy mong đợi.

Ví dụ:

~~~java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
~~~

không tự bảo đảm `profile` chưa bị truy vấn ở mọi phiên bản Hibernate. Khi yêu cầu tối ưu fetching nghiêm ngặt, hãy xác định SQL được thực thi trên provider/version đang dùng.

### 10.2. Lỗi LazyInitializationException

Giả sử service trả ra một `Employee` sau khi đóng persistence context, rồi controller mới gọi:

~~~java
employee.getDepartment().getName();
~~~

Nếu department chưa được khởi tạo, Hibernate có thể ném `LazyInitializationException`. Quan hệ hai chiều và `mappedBy` không giải quyết vấn đề này. Những cách phù hợp thường là thiết kế transaction bao trùm use case đọc, dùng truy vấn fetch đúng phạm vi hoặc tạo DTO trong khi persistence context còn hợp lệ.

### 10.3. Fetch join khi cần dữ liệu liên quan

Ví dụ lấy nhân viên cùng phòng ban:

~~~java
List<Employee> employees = em.createQuery(
        "select e from Employee e join fetch e.department " +
        "where e.id in :ids",
        Employee.class)
    .setParameter("ids", employeeIds)
    .getResultList();
~~~

Khi chỉ cần số ít trường, DTO projection có thể phù hợp hơn việc mang theo toàn bộ object graph. `EntityGraph` là lựa chọn chuẩn JPA khác để mô tả tập thuộc tính cần nạp.

### 10.4. N+1 query

Ví dụ lấy 100 nhân viên rồi với từng nhân viên đọc `employee.department.name` có thể khiến provider phát sinh nhiều SQL tùy persistence context, batch fetching và fetch plan. `EAGER` cũng không tự loại trừ N+1. Quan hệ hai chiều có thể tạo thêm đường truy cập và làm lộ vấn đề, nhưng nguyên nhân trực tiếp là **cách tải dữ liệu**, không phải sự hiện diện của `mappedBy`.

Tối ưu bằng cách xem SQL thực tế, truy vấn theo nhu cầu màn hình, fetch join/entity graph, batch fetching hoặc projection phù hợp. Không đổi mọi quan hệ thành `EAGER` để xử lý một lỗi lazy cụ thể.

## 11. Cascade và orphanRemoval không phải mappedBy

Khi có hai hướng, việc đặt cascade ở đâu là một **quyết định vòng đời**. Nó không quyết định bên nào ghi FK.

### 11.1. CascadeType.PERSIST

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.PERSIST
)
private AccountProfile profile;
~~~

Khi persist account, thao tác persist có thể được lan sang profile nếu object graph đã liên kết đúng. Owner của FK vẫn là `AccountProfile.account`.

### 11.2. CascadeType.REMOVE

Với entity con thuộc riêng entity cha, có thể muốn xóa con khi xóa cha:

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = { CascadeType.PERSIST, CascadeType.REMOVE }
)
private AccountProfile profile;
~~~

Tính năng này có thể phù hợp nếu profile không có vòng đời độc lập. Nhưng không nên tự động dùng `CascadeType.REMOVE` từ `Employee` sang `Department`: phòng ban được nhiều nhân viên dùng chung, xóa một nhân viên mà lan thao tác xóa phòng ban sẽ sai nghiệp vụ và có thể gây vi phạm FK.

### 11.3. OrphanRemoval

`orphanRemoval = true` được hỗ trợ trên `@OneToOne` và `@OneToMany`. Nó liên quan đến việc **xóa entity con không còn thuộc quan hệ sở hữu riêng**, chẳng hạn profile không còn gắn với account.

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private AccountProfile profile;
~~~

Không được nhầm:

- `CascadeType.REMOVE`: lan thao tác remove khi parent bị remove.
- `orphanRemoval = true`: xử lý child bị tách ra khỏi quan hệ, theo các điều kiện và ngữ nghĩa JPA áp dụng.

Với profile giữ FK `NOT NULL`, thao tác thay hoặc gỡ profile phải được thiết kế theo transaction, thứ tự SQL và unique constraint. Việc gán null tùy tiện rồi lập tức attach entity khác có thể gặp giới hạn uniqueness tùy thứ tự flush; không nên coi `orphanRemoval` là một giải pháp thay thế logic vòng đời đầy đủ.

**Không áp dụng orphan removal cho đối tượng dùng chung.** Chẳng hạn, việc chuyển một nhân viên từ phòng ban A sang B thường là `UPDATE employees.department_id`, không phải xóa nhân viên vì đã rời collection của A.

### 11.4. @Version và concurrency

`mappedBy` cũng không tự đảm bảo an toàn khi hai transaction đồng thời đổi cùng liên kết. Với entity cần kiểm soát lost update, hãy cân nhắc `@Version` và transaction isolation phù hợp. Việc owner/inverse được đồng bộ trong một persistence context không ngăn một transaction khác đồng thời sửa dữ liệu.
## 12. Transaction và sự nhất quán hai phía

### 12.1. Object graph có thể lệch nhau dù foreign key đúng

Trong quan hệ hai chiều, JPA/Hibernate không tự buộc mọi lệnh gán reference Java phải đồng thời sửa thuộc tính ngược. Ví dụ:

~~~java
Employee employee = em.find(Employee.class, employeeId);
Department destination = em.find(Department.class, destinationId);

// Chỉ sửa owning side:
employee.changeDepartment(destination);
~~~

Nếu `changeDepartment` là setter đơn giản, Hibernate có thể cập nhật FK đúng khi flush, nhưng collection `employees` của hai phòng ban đã được nạp trong cùng persistence context có thể tiếp tục phản ánh trạng thái cũ. Nếu chỉ sửa collection inverse, FK lại có thể không thay đổi.

Vì vậy cần tách bốn khái niệm:

1. **Nhất quán trong Java:** hai thuộc tính cùng mô tả đúng một liên kết.
2. **Đồng bộ persistence:** Hibernate dùng owning side, dirty checking và flush để ghi DB.
3. **Toàn vẹn dữ liệu tại DB:** FK, `UNIQUE`, `NOT NULL` và ràng buộc khác thực sự tồn tại.
4. **Đồng thời:** transaction isolation và optimistic locking kiểm soát tương tác giữa request khác nhau.

Helper đồng bộ hai phía giải quyết vấn đề (1), còn ba vấn đề kia cần những cơ chế tương ứng. Việc gọi getter ở inverse side không làm Hibernate “tự sửa” owning side.

### 12.2. Dùng service transaction

Với môi trường tích hợp hỗ trợ `@Transactional`:

~~~java
@Transactional
public void transferEmployee(long employeeId, long destinationId) {
    Employee employee = em.find(Employee.class, employeeId);
    Department destination = em.find(Department.class, destinationId);

    if (employee == null || destination == null) {
        throw new IllegalArgumentException(
            "Unknown employee or department"
        );
    }

    employee.changeDepartment(destination);
}
~~~

Ví dụ này giả định `Employee.changeDepartment` là helper đã đồng bộ hai phía ở phần trước. `@Transactional` thuộc cơ chế transaction của framework hoặc Jakarta Transactions được môi trường tích hợp hỗ trợ; trong Java SE với resource-local transaction, phải `begin`, `commit` và `rollback` tường minh.

Không nên giữ một `EntityManager` hoặc Hibernate `Session` sống qua nhiều request chỉ để sử dụng lazy association. Cần định nghĩa rõ phạm vi transaction và dữ liệu trả về từ service.

### 12.3. Khi FK không được phép null

Mapping:

~~~java
@ManyToOne(optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
~~~

không phù hợp với thao tác “gỡ nhân viên khỏi phòng ban mà chưa chuyển sang nơi khác” nếu database có `NOT NULL`. Nghiệp vụ phải quyết định nhân viên được xóa, chuyển phòng ban hoặc cho phép trạng thái chưa phân công và cập nhật schema tương ứng.

Tương tự, profile có FK đến account `NOT NULL` thì thao tác `profile.account = null` không tự xóa profile hay biến FK thành nullable. Nếu muốn xóa profile, cần thực hiện remove/orphanRemoval và giữ object graph nhất quán theo quy tắc vòng đời đã chọn.

## 13. Chọn mô hình dựa trên use case

### Tình huống A — Đơn hàng chỉ cần biết khách hàng

Nếu code thường đi từ `Order` sang `Customer`, nhưng màn hình danh sách đơn dùng query phân trang, có thể giữ một chiều:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

Query ngược không đòi `Customer.orders`:

~~~java
List<Order> orders = em.createQuery(
        "select o from Order o where o.customer.id = :customerId",
        Order.class)
    .setParameter("customerId", customerId)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Collection chứa toàn bộ đơn hàng của khách hàng có thể rất lớn. Không nhất thiết mô hình hóa nó trên entity chỉ để đọc một trang kết quả.

### Tình huống B — Team và Member được thao tác trong cùng nghiệp vụ

Khi một hành động thường vừa xem team vừa điều chỉnh member, hai chiều có thể giúp object model dễ dùng:

~~~java
// Member:
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "team_id", nullable = false)
private Team team;

// Team:
@OneToMany(mappedBy = "team")
private List<Member> members = new ArrayList<>();
~~~

Cần helper cập nhật `member.team` và collection thích hợp. `mappedBy` không quyết định nên cascade persist hay xóa member khi team bị xóa.

### Tình huống C — Tài khoản và hồ sơ mở rộng

Khi cần điều hướng từ cả account đến profile và ngược lại:

~~~java
// AccountProfile, owning side:
@OneToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private Account account;

// Account, inverse side:
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
~~~

Một FK ở bảng profile là đủ. Nếu account chỉ có thể có tối đa một profile, hãy bảo đảm database có `UNIQUE(account_id)` thực tế. Nếu profile có vòng đời độc lập, không tự động dùng `orphanRemoval`; nếu profile hoàn toàn phụ thuộc account, có thể cân nhắc cascade/orphan removal theo nghiệp vụ.

### Tình huống D — Yêu cầu one-to-one phải đúng cả với SQL bên ngoài ORM

Nếu bảng `account_profiles` đã có dữ liệu trùng `account_id`, khai báo `@OneToOne` mới trong Java chưa xóa được dữ liệu vi phạm. Cần kiểm tra và xử lý dữ liệu, rồi dùng migration tạo ràng buộc độc lập với Hibernate:

~~~sql
ALTER TABLE account_profiles
ADD CONSTRAINT uk_account_profile_account UNIQUE (account_id);
~~~

Cú pháp, naming và chiến lược index có thể khác tùy database. Nếu còn bản ghi trùng, migration sẽ thất bại; nếu hệ thống khác ghi trực tiếp, constraint ở DB tiếp tục bảo vệ cardinality.

## 14. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Cách hiểu đúng |
|---|---|
| `mappedBy` là tên cột SQL | Nó là tên **field/property Java** ở owning side |
| Có hai chiều Java nghĩa là hai FK | Thường vẫn là **một FK** |
| Phía có `mappedBy` sẽ ghi FK | Phía có `mappedBy` là inverse; owner điều khiển mapping liên kết |
| `mappedBy` quyết định cascade | Cascade là quy tắc vòng đời riêng |
| Sửa collection inverse đủ để chuyển child | Cần sửa owning reference và đồng bộ object graph |
| Đặt `@JoinColumn` ở cả hai phía luôn an toàn | Có thể tạo hai association độc lập |
| `@OneToOne` tự bảo đảm unique ở mọi DB | Cần unique constraint có thật trong schema |
| `fetch = LAZY` luôn tránh SQL | Phụ thuộc provider/version, đặc biệt inverse one-to-one |
| EAGER chắc chắn không N+1 | EAGER vẫn có thể tạo truy vấn phụ |
| Không có collection ngược thì không truy vấn ngược được | Có thể dùng JPQL/SQL/repository |
| Owning side nghĩa là có quyền xóa parent | Owning side chỉ là khái niệm mapping |
| Xóa phần tử collection luôn xóa row | Còn phụ thuộc owner, cascade, orphanRemoval và transaction |

### 14.1. Sai tên mappedBy khi bootstrap

~~~java
// Employee:
private Department department;

// Department:
@OneToMany(mappedBy = "dept")
private List<Employee> employees;
~~~

Vì `Employee` không có thuộc tính `dept`, Hibernate có thể báo lỗi mapping ngay khi khởi tạo. Sửa thành `mappedBy = "department"` hoặc đổi tên thuộc tính Java phía Employee cho phù hợp. Không sửa bằng tên cột SQL.

### 14.2. Chỉ thêm vào inverse collection rồi persist

Nếu child không trỏ tới parent ở owning side, FK có thể null hoặc không đúng. Helper có thể gọi từ parent nhưng phải cập nhật thuộc tính ở child. Điều này đặc biệt quan trọng khi `@JoinColumn(nullable = false)`: database sẽ từ chối insert nếu thiếu FK.

### 14.3. Equals, hashCode và toString bị vòng lặp

Trong hai chiều:

~~~text
Department.toString()
  -> Employee.toString()
     -> Department.toString()
        -> ...
~~~

Nếu `equals`, `hashCode` hoặc `toString` tự duyệt toàn bộ relation, có thể xuất hiện `StackOverflowError`, truy vấn lazy ngoài ý muốn hoặc lỗi với `Set` khi identity thay đổi. Khi dùng Lombok, cần kiểm soát trường nào được đưa vào các method này, không tự sinh trên toàn bộ association.

### 14.4. Vòng lặp JSON khi trả entity trực tiếp

Serializer có thể đi theo:

~~~text
employee.department.employees[0].department.employees...
~~~

Đây là vấn đề API serialization của object graph. DTO phù hợp với response thường dễ kiểm soát hơn việc trả trực tiếp entity ORM; ngoài vòng lặp còn phải chú ý lazy loading, dữ liệu nhạy cảm và kích thước response.

### 14.5. Truy vấn chậm khi thêm chiều ngược

Thêm `Department.employees` không có nghĩa nó luôn được nạp, nhưng mở thêm khả năng code truy cập collection lớn. Nếu collection được duyệt trong nhiều vòng lặp, N+1 có thể xuất hiện. Chọn truy vấn có phân trang hoặc projection khi chỉ cần một danh sách/filter, thay vì nạp toàn bộ graph.

## 15. Đọc SQL để củng cố ý nghĩa của owner

### Đổi phòng ban

Java:

~~~java
employee.changeDepartment(destination);
~~~

SQL khái niệm:

~~~sql
UPDATE employees
SET department_id = ?
WHERE id = ?;
~~~

Không có cột `employees` trên bảng `departments`. `Department.employees` chỉ là inverse navigation tới cùng FK.

### Tạo profile

Java:

~~~java
account.attachProfile(profile);
~~~

SQL khái niệm:

~~~sql
INSERT INTO account_profiles (account_id, display_name)
VALUES (?, ?);
~~~

Không cần một cột `profile` trên bảng `accounts` khi owning FK đã nằm ở bảng profile.

### Query cả hai phía

Tải employee cùng department:

~~~sql
-- SQL minh họa, không phải JPQL
SELECT e.*, d.*
FROM employees e
JOIN departments d ON d.id = e.department_id;
~~~

Tương ứng JPQL:

~~~java
"select e from Employee e join fetch e.department"
~~~

Tải department cùng employees:

~~~java
"select distinct d from Department d left join fetch d.employees"
~~~

Fetch join collection có thể nhân số dòng SQL, gây dữ liệu trùng trong tập kết quả trung gian và ảnh hưởng pagination. Không nên dùng nó cho mọi use case chỉ vì có quan hệ hai chiều.

## 16. Bài tập tự luyện

**Bài 1 — Xác định owner**

~~~java
@Entity
class Invoice {
    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;
}

@Entity
class Customer {
    @OneToMany(mappedBy = "customer")
    private List<Invoice> invoices;
}
~~~

Hỏi: bảng nào giữ FK? Phía nào là owner? Nếu chỉ thay `Customer.invoices`, có chắc `customer_id` thay đổi?

*Định hướng:* `invoices.customer_id` là FK, `Invoice.customer` là owning side, `Customer.invoices` inverse. Sửa collection đơn lẻ không đủ.

**Bài 2 — Sửa tên mappedBy**

~~~java
@Entity
class Book {
    @ManyToOne
    @JoinColumn(name = "publisher_id")
    private Publisher publishingHouse;
}

@Entity
class Publisher {
    @OneToMany(mappedBy = "publisher_id")
    private List<Book> books;
}
~~~

Hỏi: sửa `mappedBy` thành gì?

*Đáp án:* `mappedBy = "publishingHouse"`; `publisher_id` là tên cột SQL.

**Bài 3 — Một-một và unique**

Entity `UserSettings` dùng `@OneToOne` đến `User`, nhưng cột FK không có unique constraint trong database. Một script SQL ngoài ứng dụng thêm hai settings cùng user. Mapping JPA có ngăn được không?

*Định hướng:* Không đảm bảo. Phải tạo và duy trì constraint DB thực tế và xử lý dữ liệu trùng trước migration.

**Bài 4 — Thêm chiều ngược OneToOne**

~~~java
// UserProfile:
@OneToOne
@JoinColumn(name = "user_id", unique = true)
private User user;
~~~

Hỏi: muốn gọi `user.getProfile()`, nên thêm annotation gì ở `User`?

*Đáp án:* `@OneToOne(mappedBy = "user") private UserProfile profile;`. Không cần cột FK mới ở bảng user.

**Bài 5 — Không nên xóa dữ liệu dùng chung**

Một phòng ban bị xóa không có nghĩa toàn bộ nhân viên phải bị xóa. Có nên dùng `cascade = CascadeType.ALL` trên `Department.employees`?

*Định hướng:* Không mặc định. Cần quy định chuyển phòng ban hoặc ngăn xóa; kiểm tra tác động `REMOVE` và `orphanRemoval` trước khi sử dụng.

**Bài 6 — Lazy inverse OneToOne**

`Account.profile` có `@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)` nhưng vẫn xuất hiện SQL kiểm tra profile. Có thể kết luận `mappedBy` sai không?

*Định hướng:* Chưa chắc. Phía inverse có thể phải biết quan hệ có tồn tại hay không; hành vi tải lười phụ thuộc Hibernate version, proxy và enhancement.

**Bài 7 — Câu hỏi thiết kế**

Một ứng dụng luôn lấy đơn hàng theo khách bằng query phân trang. Có bắt buộc tạo `Customer.orders` không?

*Định hướng:* Không. `Order.customer` một chiều cùng repository query đã đủ nếu không cần điều hướng collection ngược trong object model.

## 17. Ghi nhớ

**Quan hệ một chiều** có một đường điều hướng từ entity này sang entity kia. **Quan hệ hai chiều** có hai đường điều hướng Java của cùng association và vẫn có thể chỉ có một khóa ngoại.

**Owning side** quyết định mapping liên kết được ghi xuống database. Với `@ManyToOne` hai chiều, thuộc tính nhiều-một có `@JoinColumn` là owner. Với `@OneToOne` hai chiều, hãy nhìn vị trí FK/mapping sở hữu để xác định owner.

**`mappedBy`** chỉ xuất hiện ở inverse side và trỏ tới **tên thuộc tính Java phía owning**, không phải tên bảng/cột. Nó không điều khiển cascade, không đồng bộ reference trong bộ nhớ, không bảo đảm fetch lazy và không thay thế ràng buộc FK/unique.

Mỗi khi đọc một association Hibernate, hãy hỏi: **Java điều hướng hướng nào, FK nằm ở đâu, ai là owning side, và trạng thái sẽ được nạp/ghi trong transaction nào?** Bốn câu hỏi này giúp tránh phần lớn nhầm lẫn về một chiều, hai chiều và `mappedBy`.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — `@ManyToOne`, `@OneToMany`, `@OneToOne`, `mappedBy`, cascade và derived identities.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — association mappings, bidirectional navigation, fetch và persistence context theo từng version.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — các ví dụ chi tiết về association và fetch.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/) — chú thích chuẩn và chữ ký các phần tử annotation.

> Ví dụ SQL minh họa ý nghĩa mapping; SQL thực tế còn phụ thuộc dialect, naming strategy và cấu hình Hibernate. Trong môi trường production cần kiểm soát schema bằng migration.



