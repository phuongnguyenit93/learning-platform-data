# Quan hệ một-một, một-nhiều và nhiều-nhiều trong ví dụ JPA

JPA ánh xạ quan hệ giữa các entity Java thành khóa ngoại hoặc bảng nối trong cơ sở dữ liệu quan hệ. Ba kiểu thường gặp là một-một (`@OneToOne`), một-nhiều (`@OneToMany` kết hợp `@ManyToOne`) và nhiều-nhiều (`@ManyToMany`).

Khi dùng Spring Data REST, các quan hệ này còn được công bố thành association links trên tài nguyên HAL. Vì vậy cần hiểu cả hai lớp: JPA quyết định quan hệ được lưu trong database như thế nào; Spring Data REST cho client đọc và thay đổi liên kết giữa các resource qua HTTP ra sao.

Ví dụ dưới đây dùng Java 17+, Spring Boot với Spring Data JPA và Spring Data REST. Các import dùng `jakarta.persistence.*`, phù hợp với Spring Boot 3 trở lên. Hãy giữ phiên bản Spring Boot hiện có của dự án và để parent/BOM quản lý phiên bản tương thích của Spring Data.

## 1. Mô hình miền dùng trong ví dụ

Xét một hệ thống quản lý nhân viên:

- Một `Employee` có tối đa một `EmployeeProfile`; một profile thuộc về tối đa một nhân viên.
- Một `Department` có nhiều `Employee`; mỗi nhân viên thuộc tối đa một phòng ban.
- Một `Employee` có nhiều `Skill`; một kỹ năng có thể được nhiều nhân viên cùng sở hữu.

Sơ đồ quan hệ:

~~~mermaid
erDiagram
    EMPLOYEE ||--o| EMPLOYEE_PROFILE : has
    DEPARTMENT ||--o{ EMPLOYEE : contains
    EMPLOYEE }o--o{ SKILL : has
    EMPLOYEE {
        bigint id PK
        string name
        bigint profile_id FK
        bigint department_id FK
    }
    EMPLOYEE_PROFILE {
        bigint id PK
        string biography
    }
    DEPARTMENT {
        bigint id PK
        string name
    }
    SKILL {
        bigint id PK
        string name
    }
    EMPLOYEE_SKILL {
        bigint employee_id FK
        bigint skill_id FK
    }
~~~

Bảng `employee` giữ khóa ngoại đến profile và department. Bảng `employee_skill` là bảng nối chứa cặp khóa ngoại của nhân viên và kỹ năng. Ràng buộc duy nhất trên `employee.profile_id` bảo đảm một profile không bị gán cho nhiều nhân viên.

| Kiểu quan hệ | Mapping thường dùng | Vị trí lưu liên kết |
| --- | --- | --- |
| Một-một | `@OneToOne` | Một khóa ngoại có ràng buộc UNIQUE, hoặc shared primary key/bảng nối |
| Một-nhiều | `@OneToMany` và `@ManyToOne` | Khóa ngoại nằm ở bảng phía nhiều |
| Nhiều-nhiều | `@ManyToMany` | Bảng nối gồm khóa ngoại của hai entity |

Cardinality mô tả số lượng đối tượng có thể liên kết. Nó chưa cho biết bên nào ghi quan hệ vào database. Trong quan hệ hai chiều, JPA còn phân biệt **owning side** (bên sở hữu) và **inverse side** (bên nghịch).

## 2. Quy tắc owning side và `mappedBy`

Mỗi quan hệ hai chiều có một bên sở hữu. Thay đổi ở owning side quyết định liên kết được ghi vào database. Bên inverse dùng `mappedBy` để trỏ đến tên thuộc tính quan hệ ở owning side.

- `@JoinColumn` khai báo cột khóa ngoại ở phía sở hữu của quan hệ dùng foreign key.
- `@JoinTable` khai báo bảng nối cho quan hệ nhiều-nhiều (hoặc một số kiểu mapping khác).
- `mappedBy` nhận **tên thuộc tính Java** của bên sở hữu, không phải tên cột database và không phải tên bảng.
- Không khai báo `@JoinColumn` hoặc `@JoinTable` ở inverse side của một quan hệ hai chiều thông thường.

Trong mô hình này, chọn các bên sở hữu như sau:

| Quan hệ | Owning side | Inverse side |
| --- | --- | --- |
| Employee — EmployeeProfile | `Employee.profile` có `@JoinColumn` | `EmployeeProfile.employee` có `mappedBy = "profile"` |
| Department — Employee | `Employee.department` có `@JoinColumn` và `@ManyToOne` | `Department.employees` có `mappedBy = "department"` |
| Employee — Skill | `Employee.skills` có `@JoinTable` | `Skill.employees` có `mappedBy = "skills"` |

Đặc biệt với một-nhiều hai chiều, phía nhiều (`@ManyToOne`) là owning side. Chỉ thêm một nhân viên vào collection `Department.employees` mà không cập nhật `Employee.department` có thể khiến thay đổi không được lưu. Với nhiều-nhiều, hai phía có thể chọn bên sở hữu, nhưng chỉ một phía khai báo bảng nối; phía còn lại tham chiếu bằng `mappedBy`.

## 3. Khai báo entity

Đặt các lớp dưới đây trong cùng package, ví dụ `com.example.demo.domain`. Mỗi entity có constructor không tham số cho JPA và getter/setter cần thiết. Ví dụ cố ý không dùng Lombok `@Data`, vì equals/hashCode và toString tự sinh trên quan hệ hai chiều dễ gây vòng lặp hoặc tải dữ liệu ngoài ý muốn.

### 3.1. Employee và quan hệ một-một với EmployeeProfile

`Employee` là owning side. Khóa ngoại `profile_id` nằm trong bảng `employee`; `unique = true` bảo đảm mỗi profile chỉ được tham chiếu bởi một nhân viên.

**Employee.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", unique = true)
    private EmployeeProfile profile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "employee_skill",
        joinColumns = @JoinColumn(name = "employee_id"),
        inverseJoinColumns = @JoinColumn(name = "skill_id")
    )
    private Set<Skill> skills = new LinkedHashSet<>();

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

    public void setName(String name) {
        this.name = name;
    }

    public EmployeeProfile getProfile() {
        return profile;
    }

    public void setProfile(EmployeeProfile profile) {
        if (this.profile == profile) {
            return;
        }

        EmployeeProfile previous = this.profile;
        this.profile = profile;

        if (previous != null) {
            previous.setEmployeeReference(null);
        }
        if (profile != null) {
            profile.setEmployeeReference(this);
        }
    }

    public Department getDepartment() {
        return department;
    }

    public void setDepartment(Department department) {
        if (this.department == department) {
            return;
        }

        Department previous = this.department;
        this.department = department;

        if (previous != null) {
            previous.removeEmployeeReference(this);
        }
        if (department != null) {
            department.addEmployeeReference(this);
        }
    }

    public Set<Skill> getSkills() {
        return skills;
    }

    public void addSkill(Skill skill) {
        if (skills.add(skill)) {
            skill.addEmployeeReference(this);
        }
    }

    public void removeSkill(Skill skill) {
        if (skills.remove(skill)) {
            skill.removeEmployeeReference(this);
        }
    }
}
~~~

**EmployeeProfile.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "employee_profiles")
public class EmployeeProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 1000)
    private String biography;

    @OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
    private Employee employee;

    protected EmployeeProfile() {
    }

    public EmployeeProfile(String biography) {
        this.biography = biography;
    }

    public Long getId() {
        return id;
    }

    public String getBiography() {
        return biography;
    }

    public void setBiography(String biography) {
        this.biography = biography;
    }

    public Employee getEmployee() {
        return employee;
    }

    void setEmployeeReference(Employee employee) {
        this.employee = employee;
    }
}
~~~

`mappedBy = "profile"` trỏ đến trường `profile` trong `Employee`. Không đặt `@JoinColumn` ở `EmployeeProfile.employee`, vì đó là inverse side.

### 3.2. Department và quan hệ một-nhiều với Employee

Một phòng ban có thể có nhiều nhân viên. Mỗi nhân viên giữ khóa ngoại `department_id`, nên `Employee.department` là owning side. Collection `Department.employees` là inverse side.

**Department.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private Set<Employee> employees = new LinkedHashSet<>();

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

    public Set<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employee.setDepartment(this);
    }

    public void removeEmployee(Employee employee) {
        if (employee.getDepartment() == this) {
            employee.setDepartment(null);
        }
    }

    void addEmployeeReference(Employee employee) {
        employees.add(employee);
    }

    void removeEmployeeReference(Employee employee) {
        employees.remove(employee);
    }
}
~~~

Trong `Employee.setDepartment`, owning side được cập nhật trước; sau đó collection ở hai phòng ban liên quan được đồng bộ trong bộ nhớ. Các phương thức `addEmployee` và `removeEmployee` gọi setter này để tránh chỉ sửa một phía của quan hệ.

Nếu một nhân viên bắt buộc phải thuộc phòng ban, hãy cân nhắc `@ManyToOne(optional = false)` và `@JoinColumn(nullable = false)`, đồng thời không cho phép gỡ liên kết bằng API. Ví dụ hiện tại để quan hệ tùy chọn nhằm minh họa việc chuyển hoặc gỡ một nhân viên khỏi phòng ban.

### 3.3. Skill và quan hệ nhiều-nhiều với Employee

Một nhân viên có nhiều kỹ năng và một kỹ năng có thể thuộc về nhiều nhân viên. Database cần bảng nối `employee_skill` thay vì đặt một cột chứa danh sách ID trong bảng `employee` hoặc `skill`.

**Skill.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "skills")
public class Skill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @ManyToMany(mappedBy = "skills", fetch = FetchType.LAZY)
    private Set<Employee> employees = new LinkedHashSet<>();

    protected Skill() {
    }

    public Skill(String name) {
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

    public Set<Employee> getEmployees() {
        return employees;
    }

    void addEmployeeReference(Employee employee) {
        employees.add(employee);
    }

    void removeEmployeeReference(Employee employee) {
        employees.remove(employee);
    }
}
~~~

`Employee.skills` là owning side vì nó khai báo `@JoinTable`. `Skill.employees` dùng `mappedBy = "skills"`. Hai collection được đồng bộ bởi `addSkill` và `removeSkill` trên Employee. Không thêm `CascadeType.REMOVE` từ Employee sang Skill: kỹ năng là dữ liệu dùng chung, xóa một nhân viên không nên xóa kỹ năng của các nhân viên khác.

### 3.4. Repository để xuất các entity

Mỗi repository dưới đây được Spring Data REST xuất thành collection resource. Đặt các interface cùng package hoặc package con được ứng dụng Spring Boot scan.

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Employee;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "employees")
public interface EmployeeRepository extends JpaRepository<Employee, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Department;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "departments")
public interface DepartmentRepository extends JpaRepository<Department, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.EmployeeProfile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "profiles")
public interface EmployeeProfileRepository
        extends JpaRepository<EmployeeProfile, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Skill;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "skills")
public interface SkillRepository extends JpaRepository<Skill, Long> {
}
~~~

Dependency tối thiểu cho ví dụ là Spring Data REST, Spring Data JPA và một JDBC driver. Với H2 để chạy thử:

**Maven**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**Gradle**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
~~~

Các phiên bản dependency được quản lý bởi Spring Boot parent/BOM. Không tự gán version riêng cho từng starter khi BOM đã quản lý chúng.

Cấu hình database trong `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:people;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
~~~

`create-drop` chỉ phù hợp với ví dụ dùng database trong bộ nhớ. Ứng dụng thật nên dùng migration như Flyway hoặc Liquibase và chính sách schema phù hợp với môi trường triển khai.

## 4. Quan sát schema và dữ liệu

Với mapping trên, cấu trúc quan hệ chính có dạng:

~~~text
employees
  id
  name
  profile_id     -> employee_profiles.id (UNIQUE)
  department_id  -> departments.id

employee_profiles
  id
  biography

departments
  id
  name

skills
  id
  name

employee_skill
  employee_id -> employees.id
  skill_id    -> skills.id
  PRIMARY KEY (employee_id, skill_id)
~~~

- Một-một dùng khóa ngoại ở `employees.profile_id`; ràng buộc UNIQUE biến quan hệ khóa ngoại thành một-một.
- Một-nhiều dùng `employees.department_id`; nhiều hàng employee có thể trỏ đến cùng một department.
- Nhiều-nhiều dùng hai khóa ngoại trong `employee_skill`; mỗi cặp employee/skill biểu diễn một liên kết.

Tên cột, tên bảng và kiểu ID có thể thay đổi theo naming strategy hoặc cấu hình của dự án. Điều quan trọng là hiểu nơi lưu khóa ngoại và bảng nối.

## 5. Spring Data REST công bố association links

Khi truy cập một item resource, Spring Data REST thêm link cho các thuộc tính quan hệ. Tên link mặc định theo tên thuộc tính Java; có thể tùy chỉnh bằng `@RestResource` trên thuộc tính quan hệ.

Với `spring.data.rest.base-path=/api`, các resource chính có dạng:

| Resource | Ý nghĩa |
| --- | --- |
| `/api/employees/{id}` | Một nhân viên |
| `/api/employees/{id}/profile` | Association một-một tới profile |
| `/api/employees/{id}/department` | Association nhiều-một tới phòng ban |
| `/api/employees/{id}/skills` | Association nhiều-nhiều tới các kỹ năng |
| `/api/departments/{id}/employees` | Collection nhân viên của phòng ban |
| `/api/skills/{id}/employees` | Collection nhân viên có kỹ năng |

Các association resource được phát hiện từ quan hệ entity. Chúng hỗ trợ `GET`, `PUT`, `POST` và `DELETE` theo loại quan hệ. Dữ liệu HAL thường biểu diễn quan hệ bằng link trong `_links`; client nên khám phá link từ response thay vì tự ghép URL trong ứng dụng thực.

### 5.1. Đọc một quan hệ

Lấy nhân viên:

~~~bash
curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1
~~~

Response HAL có thể chứa các liên kết tương tự:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees/1"
    },
    "profile": {
      "href": "http://localhost:8080/api/employees/1/profile"
    },
    "department": {
      "href": "http://localhost:8080/api/employees/1/department"
    },
    "skills": {
      "href": "http://localhost:8080/api/employees/1/skills"
    }
  }
}
~~~

Các giá trị ID và liên kết cụ thể phụ thuộc dữ liệu được tạo và cấu hình. Đọc profile hoặc danh sách kỹ năng qua association link:

~~~bash
curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1/profile

curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1/skills

curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/departments/1/employees
~~~

### 5.2. Gán quan hệ một-một

Trước hết tạo profile và employee bằng collection resource tương ứng, hoặc lấy URI của hai resource đã tồn tại. Sau đó gửi URI profile vào association resource của Employee:

~~~bash
curl -i -X PUT   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/profiles/10"   http://localhost:8080/api/employees/1/profile
~~~

`PUT` gắn resource được chỉ ra bởi URI vào association. Với quan hệ to-one, chỉ gửi một URI; gửi nhiều URI sẽ bị từ chối. Vì `Employee.profile` là owning side, đây là association cần cập nhật để JPA ghi khóa ngoại `profile_id`.

Để gỡ liên kết, có thể gửi `DELETE` đến association resource nếu quan hệ là tùy chọn. Nếu association được khai báo không optional, Spring Data REST có thể từ chối thao tác gỡ.

### 5.3. Gán quan hệ một-nhiều

Trong JPA, `Employee.department` là owning side của quan hệ Department–Employee. Vì thế, thao tác ghi được thực hiện trên association của employee:

~~~bash
curl -i -X PUT   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/departments/3"   http://localhost:8080/api/employees/1/department
~~~

Sau khi liên kết được cập nhật, đọc `/api/departments/3/employees` để xem collection nhân viên của phòng ban. Đừng chỉ thay collection `Department.employees` trong code rồi bỏ qua trường `Employee.department`; thay đổi inverse side một mình không bảo đảm khóa ngoại được cập nhật.

Để chuyển nhân viên sang phòng ban khác, gửi `PUT` với URI phòng ban mới vào association `/employees/{id}/department`. Nếu nghiệp vụ cần một nhân viên luôn có phòng ban, hãy ràng buộc điều đó ở cả mapping, validation và API.

### 5.4. Thêm quan hệ nhiều-nhiều

Với association collection, Spring Data REST hỗ trợ `POST` để thêm một phần tử. Gửi URI của skill đến association resource trên owning side Employee:

~~~bash
curl -i -X POST   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/skills/5"   http://localhost:8080/api/employees/1/skills
~~~

Có thể POST thêm nhiều URI trong nội dung `text/uri-list`, mỗi URI trên một dòng. Spring Data REST thêm các phần tử đó vào collection association. `GET /api/employees/1/skills` để xác nhận liên kết đã xuất hiện.

`DELETE` trên association resource gỡ association. Với collection, thao tác này tác động đến liên kết của collection đó; hãy kiểm tra đúng endpoint và nghiệp vụ trước khi dùng. Không dùng DELETE association như cách xóa entity Skill khỏi database: gỡ quan hệ và xóa entity là hai thao tác khác nhau.

## 6. Cascade, orphan removal và vòng đời entity

Các annotation quan hệ mô tả cardinality và cách ánh xạ. Cascade và orphan removal điều khiển vòng đời entity, không phải là cách định nghĩa cardinality.

- **Không cascade mặc định:** Ví dụ không khai báo cascade; tạo Profile, Department, Skill và Employee qua repository riêng rồi liên kết bằng association URI. Cách này làm rõ mỗi resource có vòng đời riêng.
- **Cascade PERSIST/MERGE:** Chỉ dùng khi lưu một entity cha thì việc lưu entity liên quan thực sự thuộc cùng một thao tác nghiệp vụ.
- **Cascade REMOVE:** Cẩn trọng với entity dùng chung. Không cascade remove từ Employee sang Skill vì nhiều nhân viên có thể cùng dùng một Skill.
- **orphanRemoval:** Phù hợp khi entity con thuộc độc quyền về cha và việc bỏ liên kết có nghĩa xóa con. Không bật tùy tiện cho Profile, Department hoặc Skill dùng chung; việc gỡ association không nhất thiết đồng nghĩa xóa entity đích.

Nếu một quan hệ có dữ liệu nghiệp vụ riêng, ví dụ kỹ năng của nhân viên có cấp độ, ngày chứng nhận hoặc ngày bắt đầu sử dụng, hãy thay `@ManyToMany` bằng entity liên kết như `EmployeeSkill`. Entity này có hai quan hệ `@ManyToOne` tới Employee và Skill, cùng các thuộc tính riêng. Cách đó giúp kiểm soát vòng đời, audit và validation của liên kết.

## 7. Fetching, serialization và hiệu năng

- `@OneToOne` và `@ManyToOne` mặc định là EAGER; `@OneToMany` và `@ManyToMany` mặc định là LAZY. Ví dụ đặt `fetch = FetchType.LAZY` rõ ràng cho các quan hệ. Với quan hệ to-one, LAZY là một yêu cầu/hint mà provider cần hỗ trợ; hãy kiểm tra hành vi thực tế của provider.
- Không truy cập collection LAZY sau khi persistence context đã đóng nếu chưa tải dữ liệu cần thiết. Lỗi thường gặp là `LazyInitializationException` ở Hibernate.
- Tải nhiều association cùng lúc có thể gây N+1 query hoặc nhân bản hàng trong kết quả join. Dùng query phù hợp, projection, pagination hoặc `@EntityGraph` khi có nhu cầu cụ thể.
- Không tự động serialize toàn bộ object graph hai chiều bằng cách gọi getter lồng nhau. Employee → Department → Employees → Employee có thể tạo vòng lặp. Spring Data REST mặc định công bố association dưới dạng link HAL; nếu cần payload tùy chỉnh, hãy dùng projection hoặc DTO phù hợp.
- Tránh Lombok `@Data` trên entity có quan hệ hai chiều. equals/hashCode và toString tự sinh có thể đệ quy qua association hoặc làm collection hoạt động không ổn định. Nếu cần equals/hashCode, chọn chiến lược dựa trên identity ổn định và kiểm tra với entity transient/proxy.
- Với `Set`, cần hiểu cách equals/hashCode của entity ảnh hưởng đến loại bỏ trùng lặp. Nếu quan hệ có thuộc tính riêng hoặc cần thứ tự, cân nhắc entity liên kết hay collection có thứ tự phù hợp.

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thêm phần tử vào collection nhưng database không đổi | Chỉ sửa inverse side có `mappedBy` | Cập nhật owning side; dùng helper method đồng bộ cả hai phía |
| `mappedBy` không được nhận diện | Giá trị là tên cột hoặc tên bảng thay vì tên thuộc tính Java | Dùng đúng tên trường ở owning side, ví dụ `mappedBy = "department"` |
| Một-một vẫn có nhiều dòng trỏ cùng profile | Thiếu ràng buộc UNIQUE trên khóa ngoại hoặc mapping không phản ánh cardinality | Dùng `@OneToOne` và unique foreign key phù hợp |
| Không thấy association link trong HAL | Repository không được export, thuộc tính quan hệ không được nhận diện hoặc serialization/configuration đã tùy chỉnh | Kiểm tra repository, entity mapping và response HAL |
| PUT association trả 400 | Gửi nhiều URI cho quan hệ to-one | Chỉ gửi một URI đích |
| POST association không thêm được liên kết | Dùng POST cho to-one, URI sai hoặc Content-Type không phải `text/uri-list` | Dùng PUT cho to-one; POST cho collection và gửi URI hợp lệ |
| Xóa một Skill làm mất dữ liệu dùng chung | Cascade REMOVE trên quan hệ nhiều-nhiều | Bỏ cascade remove; chỉ gỡ association |
| JSON bị lặp hoặc response quá lớn | Tuần tự hóa object graph hai chiều hoặc tải association không giới hạn | Dùng HAL links, projection/DTO và giới hạn dữ liệu |

## 9. Checklist thiết kế quan hệ

- [ ] Cardinality trong domain phản ánh đúng quy tắc nghiệp vụ.
- [ ] Đã xác định owning side cho mỗi quan hệ hai chiều.
- [ ] `mappedBy` trỏ đúng tên thuộc tính Java ở owning side.
- [ ] Foreign key, UNIQUE constraint và join table phản ánh đúng cardinality.
- [ ] Helper methods đồng bộ cả owning side và inverse side trong bộ nhớ.
- [ ] Cascade và orphan removal được chọn theo quyền sở hữu vòng đời entity.
- [ ] Quan hệ nhiều-nhiều có thuộc tính riêng đã được mô hình hóa thành entity liên kết.
- [ ] Các repository được xuất qua Spring Data REST đã được xem xét về bảo mật và phạm vi dữ liệu.
- [ ] Đã kiểm tra association links và các thao tác GET/PUT/POST/DELETE bằng HTTP.
- [ ] Đã xem xét lazy loading, N+1, vòng lặp serialization và pagination.

## Tài liệu chính thức

- [Spring Data REST — Repository Resources and Association Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Jakarta Persistence — Entity Relationships](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2)
- [Jakarta Persistence API — OneToOne](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToOne.html)
- [Jakarta Persistence API — OneToMany](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToMany.html)
- [Jakarta Persistence API — ManyToMany](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ManyToMany.html)
- [Jakarta Persistence API — JoinTable](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/JoinTable.html)
