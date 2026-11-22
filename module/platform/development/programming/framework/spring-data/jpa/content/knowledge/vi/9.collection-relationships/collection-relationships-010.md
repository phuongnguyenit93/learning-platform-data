# Thêm, xóa và thay thế phần tử mà vẫn giữ nhất quán hai phía

## Mục tiêu

Với quan hệ hai chiều trong Spring Data JPA, một entity có thể giữ tham chiếu tới entity liên quan, đồng thời entity kia giữ collection chứa nó. Ví dụ `Department.employees` là danh sách nhân viên, còn `Employee.department` là phòng ban của từng nhân viên.

Database chỉ có một mapping quan hệ được điều khiển bởi owning side. Vì vậy, thao tác thêm, xóa, chuyển hoặc thay thế phần tử phải cập nhật đúng owning-side reference để khóa ngoại được ghi chính xác. Đồng thời, code nên đồng bộ collection inverse side để object graph trong bộ nhớ phản ánh cùng một trạng thái.

Bài này trình bày cách thiết kế helper methods cho `add`, `remove`, `transfer` và `replace`, cách chọn cascade/orphan removal, cùng ví dụ Java 17+ chạy được với Spring Boot và H2.

## 1. Hai phía của quan hệ hai chiều

Xét quan hệ một phòng ban có nhiều nhân viên:

```java
@Entity
public class Department {
    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();
}

@Entity
public class Employee {
    @ManyToOne
    @JoinColumn(name = "department_id")
    private Department department;
}
```

- `Employee.department` là **owning side** vì nó khai báo `@JoinColumn` và điều khiển cột khóa ngoại `department_id`.
- `Department.employees` là **inverse side** vì `mappedBy = "department"` trỏ tới thuộc tính owning side.

Khi flush, JPA provider dựa vào `Employee.department` để quyết định giá trị `employee.department_id`. Collection `Department.employees` không tự ghi khóa ngoại chỉ vì nó chứa một phần tử.

## 2. Vì sao cần cập nhật cả hai phía?

Giả sử code thêm nhân viên bằng:

```java
department.getEmployees().add(employee);
```

Collection trong bộ nhớ có thể chứa nhân viên, nhưng `employee.getDepartment()` vẫn là `null`. Vì collection là inverse side, JPA không dùng thay đổi này để cập nhật FK. Database có thể vẫn lưu `department_id = NULL` hoặc vi phạm constraint nếu cột không cho null.

Trường hợp ngược lại, nếu chỉ gọi:

```java
employee.setDepartment(department);
```

owning side đã có thông tin để ghi FK, nhưng `department.getEmployees()` có thể vẫn không chứa nhân viên. Các đoạn code tiếp theo đọc collection có thể thấy trạng thái cũ.

Do đó, mỗi thao tác quan hệ nên thực hiện hai việc:

1. Cập nhật owning side để JPA ghi đúng database.
2. Cập nhật inverse side để object graph trong bộ nhớ nhất quán.

## 3. Thiết kế helper methods cho add và remove

Nên đóng gói logic đồng bộ hai phía trong entity hoặc một domain method phù hợp, thay vì rải các lệnh `collection.add()` và `setDepartment()` khắp Service.

Ví dụ trên `Department`:

```java
public void addEmployee(Employee employee) {
    Objects.requireNonNull(employee, "employee must not be null");

    Department previous = employee.getDepartment();
    if (previous != null && previous != this) {
        previous.detachEmployee(employee);
    }

    if (!employees.contains(employee)) {
        employees.add(employee);
    }
    employee.setDepartment(this);
}

private void detachEmployee(Employee employee) {
    employees.remove(employee);
}

public boolean removeEmployee(Employee employee) {
    Objects.requireNonNull(employee, "employee must not be null");
    boolean removed = employees.remove(employee);

    if (employee.getDepartment() == this) {
        employee.setDepartment(null);
    }
    return removed;
}
```

`addEmployee` cũng xử lý trường hợp chuyển nhân viên từ phòng ban khác: nó gỡ nhân viên khỏi collection cũ, thêm vào collection mới và cập nhật owning side. `removeEmployee` gỡ khỏi collection và đặt owning reference thành null.

Ví dụ này dùng `List` và không override `equals()`/`hashCode()` trên entity, nên `contains` và `remove` sử dụng identity mặc định của object. Nếu entity có custom equality dựa trên ID hoặc thuộc tính mutable, cần thiết kế cẩn thận để tránh collection không tìm được phần tử sau khi ID thay đổi hoặc entity chưa được persist.

### Giữ collection không bị thay trực tiếp

Có thể trả về view không sửa được từ getter:

```java
public List<Employee> getEmployees() {
    return Collections.unmodifiableList(employees);
}
```

Nhờ vậy, code gọi không thể tùy tiện thêm/xóa phần tử mà bỏ qua helper method. Hibernate vẫn quản lý collection nội bộ; không nên thay collection persistent bằng một `new ArrayList` qua setter sau khi entity đã được managed.

## 4. Chuyển một phần tử giữa hai parent

Chuyển nhân viên từ `Engineering` sang `Support` cần cập nhật ba điểm:

1. Gỡ nhân viên khỏi `Engineering.employees`.
2. Thêm nhân viên vào `Support.employees`.
3. Đặt `Employee.department = Support`.

Helper `Support.addEmployee(employee)` ở trên thực hiện cả ba bước: đọc phòng ban cũ, gọi `detachEmployee` ở phòng ban cũ, rồi đặt owning side về phòng ban mới.

Không cần gọi `removeEmployee` trên phòng ban cũ trước khi `addEmployee` nếu helper đã xử lý việc chuyển. Gọi remove trước có thể đặt `employee.department` thành null; trong mô hình có orphan removal, điều này còn có thể đánh dấu entity là orphan để xóa.

### Ranh giới của orphanRemoval

Nếu quan hệ thể hiện vòng đời sở hữu chặt chẽ, có thể khai báo:

```java
@OneToMany(mappedBy = "department",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<Employee> employees = new ArrayList<>();
```

Khi một employee bị loại khỏi collection, JPA sẽ xóa entity orphan theo quy tắc orphan removal. Đây phù hợp khi employee chỉ tồn tại như một phần của department và không được chuyển sang parent khác.

Nếu nghiệp vụ cho phép chuyển employee giữa các department, không nên kết hợp quy trình chuyển với việc biến employee thành orphan. Hãy cân nhắc không dùng orphan removal hoặc thiết kế thao tác chuyển theo mô hình vòng đời phù hợp. Jakarta Persistence không bảo đảm hành vi di chuyển một entity đã bị đánh dấu orphan sang parent khác trong cùng transaction.

## 5. Thay thế toàn bộ collection

Thay thế collection có nghĩa là biến tập phần tử hiện tại thành một tập mới. Cách làm an toàn là tính chênh lệch rồi dùng helper methods:

- Phần tử đang có và vẫn xuất hiện trong tập mới: giữ nguyên.
- Phần tử đang có nhưng không còn trong tập mới: gọi `removeEmployee`.
- Phần tử mới: gọi `addEmployee`.
- Phần tử thuộc parent khác: `addEmployee` chuyển nó khỏi collection cũ và gắn với parent hiện tại.

Ví dụ:

```java
public void replaceEmployees(Collection<Employee> replacement) {
    Objects.requireNonNull(replacement, "replacement must not be null");
    List<Employee> requested = new ArrayList<>(replacement);

    Set<Employee> seen = Collections.newSetFromMap(new IdentityHashMap<>());
    for (Employee employee : requested) {
        Objects.requireNonNull(employee, "replacement contains null");
        if (!seen.add(employee)) {
            throw new IllegalArgumentException("Duplicate employee instance");
        }
    }

    for (Employee current : new ArrayList<>(employees)) {
        if (!seen.contains(current)) {
            removeEmployee(current);
        }
    }

    for (Employee employee : requested) {
        addEmployee(employee);
    }
}
```

`IdentityHashMap` làm tập kiểm tra trùng dựa trên cùng object instance, tránh phụ thuộc vào `equals()` tùy chỉnh của entity. Nếu ứng dụng cần nhận danh sách ID từ API, Service nên tải các entity theo ID, kiểm tra quyền và tính hợp lệ, rồi mới gọi domain method; không nên tạo entity giả chỉ chứa ID và gán trực tiếp vào collection.

### Vì sao không gán collection mới thẳng vào field?

Không nên làm như sau với entity đã managed:

```java
department.setEmployees(new ArrayList<>(replacement));
```

Việc thay collection có thể làm mất wrapper collection mà Hibernate đang dùng để theo dõi thay đổi, làm khó kiểm soát orphan removal và không cập nhật owning side trên từng employee. Cách diff + helper methods giữ collection được quản lý và đồng bộ cả hai phía.

## 6. Cascade và orphanRemoval khác với đồng bộ hai phía

`cascade` quyết định thao tác JPA có được lan truyền từ entity này sang entity liên quan hay không:

- `PERSIST`: persist các entity liên quan khi persist parent.
- `MERGE`: merge các entity liên quan khi merge parent.
- `REMOVE`: propagate thao tác remove.
- `ALL`: bao gồm các loại cascade trên.

`orphanRemoval = true` biểu thị entity con bị xóa khi không còn được liên kết với parent theo quan hệ đó. Đây là quy tắc vòng đời, không phải quy tắc ownership.

Dù dùng cascade nào, `mappedBy` vẫn xác định inverse side và owning side vẫn điều khiển FK. Cascade không làm cho `Department.employees` trở thành owning side.

## 7. Lưu ý về List, Set và equals/hashCode

Collection type ảnh hưởng tới cách Java phát hiện phần tử trùng và cách Hibernate quản lý thứ tự:

- `List` cho phép giữ thứ tự và phần tử trùng. Nếu thứ tự có ý nghĩa trong database, cần mapping thứ tự rõ ràng, ví dụ `@OrderColumn` hoặc sắp xếp theo thuộc tính.
- `Set` ngăn phần tử trùng theo `equals()`/`hashCode()`. Entity có ID được sinh sau persist cần chiến lược equality nhất quán trước và sau khi có ID.
- Không đưa thuộc tính mutable vào `hashCode()` nếu thuộc tính có thể đổi trong khi entity đang nằm trong `HashSet`.
- Helper methods vẫn cần cập nhật owning side bất kể dùng List hay Set.

Với collection có thứ tự, `@OrderBy` sắp xếp theo thuộc tính khi đọc; `@OrderColumn` lưu vị trí trong database. Hai annotation này có ý nghĩa khác nhau và có chi phí cập nhật khác nhau.

## 8. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ này minh họa thêm, chuyển, xóa và thay thế nhân viên trong hai phòng ban. Quan hệ cho phép nhân viên tạm thời chưa thuộc phòng ban nào, vì vậy `department_id` có thể null. Không dùng orphan removal để hỗ trợ chuyển employee giữa các parent.

### Cấu trúc dự án

```text
collection-sync/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/collectionsync/
        │   ├── CollectionSyncApplication.java
        │   ├── Department.java
        │   ├── Employee.java
        │   ├── DepartmentRepository.java
        │   ├── EmployeeRepository.java
        │   └── DepartmentService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>collection-sync</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:collectiondb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Department.java`

```java
package com.example.collectionsync;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "departments")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "department",
               cascade = {CascadeType.PERSIST, CascadeType.MERGE})
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public void addEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee must not be null");

        Department previous = employee.getDepartment();
        if (previous != null && previous != this) {
            previous.detachEmployee(employee);
        }

        if (!employees.contains(employee)) {
            employees.add(employee);
        }
        employee.setDepartment(this);
    }

    private void detachEmployee(Employee employee) {
        employees.remove(employee);
    }

    public boolean removeEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee must not be null");
        boolean removed = employees.remove(employee);
        if (employee.getDepartment() == this) {
            employee.setDepartment(null);
        }
        return removed;
    }

    public void replaceEmployees(Collection<Employee> replacement) {
        Objects.requireNonNull(replacement, "replacement must not be null");
        List<Employee> requested = new ArrayList<>(replacement);
        Set<Employee> seen = Collections.newSetFromMap(new IdentityHashMap<>());

        for (Employee employee : requested) {
            Objects.requireNonNull(employee, "replacement contains null");
            if (!seen.add(employee)) {
                throw new IllegalArgumentException("Duplicate employee instance");
            }
        }

        for (Employee current : new ArrayList<>(employees)) {
            if (!seen.contains(current)) {
                removeEmployee(current);
            }
        }

        for (Employee employee : requested) {
            addEmployee(employee);
        }
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
}
```

### `Employee.java`

```java
package com.example.collectionsync;

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

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected Employee() {
    }

    public Employee(String name) {
        this.name = name;
    }

    Department getDepartment() {
        return department;
    }

    void setDepartment(Department department) {
        this.department = department;
    }

    public String getName() {
        return name;
    }
}
```

### `DepartmentRepository.java`

```java
package com.example.collectionsync;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DepartmentRepository extends JpaRepository<Department, Long> {
}
```

### `EmployeeRepository.java`

```java
package com.example.collectionsync;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository extends JpaRepository<Employee, Long> {
    long countByDepartmentIsNull();
}
```

### `DepartmentService.java`

```java
package com.example.collectionsync;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DepartmentService {
    private final DepartmentRepository departmentRepository;
    private final EmployeeRepository employeeRepository;

    @PersistenceContext
    private EntityManager entityManager;

    public DepartmentService(DepartmentRepository departmentRepository,
                             EmployeeRepository employeeRepository) {
        this.departmentRepository = departmentRepository;
        this.employeeRepository = employeeRepository;
    }

    @Transactional
    public String demonstrateCollectionChanges() {
        Department engineering = new Department("Engineering");
        Department support = new Department("Support");
        Employee an = new Employee("An");
        Employee binh = new Employee("Binh");

        engineering.addEmployee(an);
        engineering.addEmployee(binh);
        departmentRepository.save(engineering);
        departmentRepository.save(support);

        // Transfer Binh: detach from Engineering and attach to Support.
        support.addEmployee(binh);

        // Remove An from the department; the employee row remains unassigned.
        engineering.removeEmployee(an);

        // Replace Engineering's remaining members with a new collection.
        engineering.replaceEmployees(List.of(new Employee("Cuong")));

        entityManager.flush();
        Long engineeringId = engineering.getId();
        Long supportId = support.getId();
        entityManager.clear();

        Department loadedEngineering = departmentRepository.findById(engineeringId)
                .orElseThrow();
        Department loadedSupport = departmentRepository.findById(supportId)
                .orElseThrow();

        String engineeringNames = loadedEngineering.getEmployees().stream()
                .map(Employee::getName)
                .sorted()
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String supportNames = loadedSupport.getEmployees().stream()
                .map(Employee::getName)
                .sorted()
                .reduce((left, right) -> left + ", " + right)
                .orElse("");

        long unassigned = employeeRepository.countByDepartmentIsNull();
        return loadedEngineering.getName() + ": " + engineeringNames
                + "\n" + loadedSupport.getName() + ": " + supportNames
                + "\nUnassigned employees: " + unassigned;
    }
}
```

Trong ví dụ này, `Department.employees` dùng cascade PERSIST/MERGE để lưu nhân viên mới được thêm vào parent đã managed. Không bật cascade REMOVE hoặc orphan removal vì nghiệp vụ cho phép chuyển nhân viên giữa các phòng ban và giữ nhân viên đã bỏ khỏi phòng ban dưới trạng thái chưa phân công.

### `CollectionSyncApplication.java`

```java
package com.example.collectionsync;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CollectionSyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(CollectionSyncApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DepartmentService service) {
        return args -> System.out.println(service.demonstrateCollectionChanges());
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Engineering: Cuong
Support: Binh
Unassigned employees: 1
```

Kết quả cho thấy `Binh` được chuyển sang Support, `An` được gỡ khỏi Engineering nhưng vẫn còn bản ghi employee, và Engineering được thay danh sách bằng `Cuong`. Các thay đổi được kiểm tra sau `flush()` và `clear()` trong cùng transaction.

## 9. Cách hiểu SQL khi thêm, xóa và chuyển phần tử

Với owning side là `Employee.department`, thao tác có thể sinh SQL tương ứng:

- Thêm nhân viên vào Engineering: INSERT employee với `department_id` bằng ID Engineering.
- Chuyển Binh sang Support: UPDATE employee đặt `department_id` thành ID Support.
- Gỡ An khỏi Engineering: UPDATE employee đặt `department_id` thành NULL trong mô hình ví dụ.
- Thay collection Engineering và thêm Cuong: INSERT employee mới với `department_id` Engineering.

SQL thực tế phụ thuộc chiến lược sinh ID, flush order và Hibernate version. Các câu trên mô tả tác động dữ liệu, không cam kết thứ tự câu lệnh cụ thể.

Nếu `department_id` có `NOT NULL`, thao tác remove đặt null sẽ thất bại. Khi đó domain phải quyết định rõ: cấm remove, yêu cầu gán sang parent khác, hoặc xóa employee theo quy tắc vòng đời.

## 10. Khi nào nên dùng orphanRemoval?

`orphanRemoval = true` phù hợp khi entity con thuộc sở hữu vòng đời của parent. Ví dụ một dòng hóa đơn chỉ tồn tại như một phần của hóa đơn; bỏ dòng khỏi hóa đơn có nghĩa là xóa dòng đó.

```java
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
```

Khi loại một `OrderLine` khỏi collection, provider sẽ xóa orphan khi đồng bộ persistence context. Không dùng orphan removal cho quan hệ mà child có thể chuyển giữa nhiều parent; Jakarta Persistence không bảo đảm việc tái gắn một entity đã bị đánh dấu orphan trong cùng transaction.

## 11. Kiểm thử và nguyên tắc thực hành

- Kiểm thử thêm phần tử và xác nhận FK được ghi đúng.
- Kiểm thử remove và xác nhận hành vi đúng với nullability hoặc orphan removal.
- Kiểm thử chuyển phần tử giữa hai parent và xác nhận cả collection lẫn owning reference.
- Kiểm thử replace với collection rỗng, phần tử giữ lại, phần tử mới và phần tử thuộc parent khác.
- Dùng integration test có `flush()` và `clear()` trước khi đọc lại để tránh chỉ kiểm tra dữ liệu đang nằm trong persistence context.
- Không thay collection Hibernate đang quản lý bằng một instance mới qua setter.
- Chọn cascade theo vòng đời entity; cascade không thay thế việc cập nhật owning side.
- Thiết kế `equals()`/`hashCode()` cẩn thận khi entity được giữ trong `Set` hoặc khi ID chỉ được sinh lúc persist.

Điểm cốt lõi: **Mọi thao tác quan hệ hai chiều cần cập nhật owning side để database ghi đúng khóa ngoại và inverse side để object graph nhất quán. Với `mappedBy`, collection chỉ là góc nhìn ngược; helper methods là nơi tập trung logic thêm, xóa, chuyển và thay thế phần tử.**