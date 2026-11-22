# FetchMode.SUBSELECT và các điều kiện cần kiểm chứng

## 1. Bài toán: tránh N+1 khi tải collection của nhiều entity cha

Trong Hibernate ORM, một entity thường có association dạng collection. Ví dụ một phòng ban có nhiều nhân viên:

```java
@Entity
public class Department {
    @Id
    private Long id;

    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private List<Employee> employees = new ArrayList<>();
}
```

Nếu ứng dụng tải 30 phòng ban rồi lần lượt truy cập `department.getEmployees()`, chiến lược SELECT thông thường có thể tạo ra:

- Một câu SELECT lấy danh sách Department.
- Một câu SELECT lấy employees cho từng Department khi collection được khởi tạo.

Tổng cộng có thể thành **1 + 30 câu SQL**. Đây là dạng vấn đề **N+1 select**.

Hibernate cung cấp chiến lược **`FetchMode.SUBSELECT`** cho collection. Khi nhiều entity cha được tải bởi cùng một truy vấn và collection của một entity trong nhóm được khởi tạo, Hibernate có thể dùng **một truy vấn phụ với subquery lấy lại tập ID của các entity cha** để tải collection tương ứng cho cả nhóm.

Ví dụ ý tưởng:

```text
Query đầu:
  SELECT departments
  WHERE active = true

Khi truy cập employees của một Department:
  SELECT employees
  WHERE department_id IN (
      SELECT id
      FROM departments
      WHERE active = true
  )

Kết quả:
  Collection employees của các Department thuộc nhóm
  được tải cùng trong một secondary SELECT.
```

`FetchMode.SUBSELECT` có thể giảm số câu SQL so với SELECT-per-collection, nhưng **không phải một công tắc bật lên là mọi tình huống đều chỉ còn hai query**. Cần hiểu nhóm owner nào được Hibernate ghi nhận, thời điểm collection được khởi tạo, phạm vi Session, kích thước tập kết quả và SQL thật được sinh ra.

Sau bài này, bạn cần phân biệt SUBSELECT với SELECT, BATCH và JOIN; hiểu điều kiện để Hibernate có thể dùng nhóm owner của một truy vấn; biết vì sao pagination, query phức tạp, collection lớn và Persistence Context có thể làm thay đổi kết quả; và biết cách kiểm chứng bằng SQL log cùng query plan.

## 2. FetchMode.SUBSELECT là gì?

`FetchMode.SUBSELECT` là chiến lược fetch **đặc thù của Hibernate**, áp dụng cho association dạng collection. Nó cho phép Hibernate tải collection của nhiều owner bằng một secondary select có điều kiện dựa trên truy vấn đã tải các owner đó.

Khai báo:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<Employee> employees = new ArrayList<>();
```

Hai annotation làm hai nhiệm vụ khác nhau:

| Khai báo | Trách nhiệm |
|---|---|
| `@OneToMany` | Mô tả quan hệ giữa Department và Employee |
| `fetch = FetchType.LAZY` | Khai báo thời điểm collection được yêu cầu khởi tạo theo ngữ nghĩa Jakarta Persistence |
| `@Fetch(FetchMode.SUBSELECT)` | Chọn chiến lược SQL Hibernate dùng khi collection được tải |

**`FetchMode.SUBSELECT` không phải một giá trị của `FetchType`.** Jakarta Persistence định nghĩa `LAZY` và `EAGER` cho fetch type, còn `SUBSELECT` là lựa chọn fetch mode của Hibernate.

### Phân biệt với @Subselect

Tên hai tính năng khá giống nhau:

- `@Fetch(FetchMode.SUBSELECT)`: chiến lược tải collection cho nhiều owner.
- `@Subselect`: annotation Hibernate dùng để ánh xạ một entity từ câu SQL SELECT được nhúng trong mapping.

Chúng giải quyết hai bài toán khác nhau. `FetchMode.SUBSELECT` không tạo read-only entity, không tạo database view và không thay thế `@Subselect`.

## 3. Ví dụ mapping hoàn chỉnh

Giả sử có hai bảng:

```sql
CREATE TABLE departments (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL
        REFERENCES departments(id),
    full_name VARCHAR(150) NOT NULL
);

CREATE INDEX ix_employees_department_id
    ON employees(department_id);
```

Entity Department:

```java
package com.example.organization;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    private Long id;

    private String name;
    private boolean active;

    @OneToMany(
        mappedBy = "department",
        fetch = FetchType.LAZY
    )
    @Fetch(FetchMode.SUBSELECT)
    private List<Employee> employees = new ArrayList<>();

    protected Department() {}

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }
}
```

Entity Employee:

```java
package com.example.organization;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    private Long id;

    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
```

Trong ví dụ, `Employee.department` là phía sở hữu foreign key; `Department.employees` là phía inverse vì có `mappedBy`. `@Fetch(FetchMode.SUBSELECT)` được đặt trên collection của Department.

`FetchMode.SUBSELECT` thường được dùng với collection mapping phù hợp, chẳng hạn `@OneToMany`, `@ManyToMany` hoặc `@ElementCollection`. Phải kiểm tra SQL và semantics của mapping cụ thể.

## 4. Cơ chế hoạt động qua một truy vấn

Ứng dụng tải những phòng ban đang hoạt động:

```java
List<Department> departments = session.createQuery(
    "from Department d where d.active = true",
    Department.class
).getResultList();
```

Lúc này collection `employees` vẫn LAZY. Chưa nhất thiết có SQL lấy nhân viên.

Khi ứng dụng truy cập:

```java
Department first = departments.get(0);
int employeeCount = first.getEmployees().size();
```

Hibernate có thể thực hiện một secondary select để lấy employees cho **nhóm Department được tải bởi truy vấn trước đó**.

SQL minh họa:

```sql
SELECT d.id, d.name, d.active
FROM departments d
WHERE d.active = true;

SELECT e.department_id, e.id, e.full_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.id
    FROM departments d
    WHERE d.active = true
);
```

SQL thật có thể khác về alias, join, tham số, cách bọc truy vấn và cú pháp tùy Hibernate version, dialect, filter, pagination và câu query ban đầu. Đây là **mô hình giải thích**, không phải chuỗi SQL cố định.

Điểm quan trọng:

- Hibernate không cần phát một query riêng cho từng Department trong nhóm.
- Điều kiện subquery đại diện cho tập owner mà truy vấn trước đã tải.
- Khi collection của một owner trong nhóm được khởi tạo, Hibernate có thể khởi tạo collection tương ứng cho các owner còn lại trong nhóm.
- Lần truy cập collection sau đó có thể dùng dữ liệu đã được khởi tạo trong Persistence Context mà không cần query collection lần nữa.

SUBSELECT là **secondary select**, không phải JOIN ngay từ query đầu. Truy vấn cha vẫn chạy trước; truy vấn collection chạy khi cần khởi tạo collection. Điều này giữ được tính LAZY và tránh nhân số hàng parent trong kết quả truy vấn đầu tiên như một số kiểu join fetch.

## 5. Điều kiện quan trọng: owner phải được tải trong một nhóm truy vấn phù hợp

SUBSELECT fetch dựa trên thông tin về truy vấn đã tải các owner. Trường hợp điển hình:

```java
List<Department> departments = session.createQuery(
    "from Department d where d.active = true",
    Department.class
).getResultList();

// Truy cập collection trong cùng Session.
departments.get(0).getEmployees().size();
```

Những điều cần kiểm chứng:

1. Các owner có thực sự được tải từ cùng một truy vấn Hibernate hay không?
2. Collection có được khởi tạo trong **cùng Session/Persistence Context** không?
3. Collection đã được khởi tạo trước đó chưa?
4. Truy vấn owner có dùng HQL/JPQL, Criteria hay một đường tải đặc biệt nào?
5. Có pagination, filter, join hoặc native SQL khiến câu subselect được tạo ra khác dự kiến không?

### Nếu tải từng owner bằng find()

```java
Department a = session.find(Department.class, 1L);
Department b = session.find(Department.class, 2L);

a.getEmployees().size();
b.getEmployees().size();
```

Không nên mặc định trường hợp này sẽ có cùng hiệu quả như tải cả nhóm bằng một query HQL. `find()` tải từng owner theo identifier, không nhất thiết tạo ra cùng một nhóm subselect fetch như truy vấn trả nhiều owner.

Trong trường hợp tải từng ID, **batch fetching** có thể là chiến lược phù hợp hơn. Hãy bật SQL log và đo số query trên đúng phiên bản Hibernate thay vì suy luận từ annotation.

### Nếu owner đến từ nhiều query khác nhau?

```java
List<Department> active = session.createQuery(
    "from Department d where d.active = true",
    Department.class
).getResultList();

List<Department> inactive = session.createQuery(
    "from Department d where d.active = false",
    Department.class
).getResultList();
```

Hai tập owner được tải bởi hai truy vấn riêng. Không nên giả định collection của cả hai tập sẽ luôn được gom vào một lần tải duy nhất. Subselect fetch gắn với **nhóm kết quả truy vấn** mà Hibernate ghi nhận; từng nhóm có thể tạo secondary select riêng.

## 6. SUBSELECT giúp tránh N+1 như thế nào?

Giả sử truy vấn lấy `N` phòng ban và ứng dụng truy cập collection của tất cả:

### SELECT fetching thông thường

```text
SELECT departments ...          1 query
SELECT employees WHERE dept=1   1 query
SELECT employees WHERE dept=2   1 query
...
SELECT employees WHERE dept=N   1 query

Tổng: 1 + N queries
```

### SUBSELECT fetching

```text
SELECT departments ...                    1 query
SELECT employees WHERE dept_id IN
    (SELECT id FROM departments ...)      1 query

Tổng điển hình: 2 queries
```

Đây là lợi ích nổi bật khi một trang hoặc use case cần collection của **nhiều owner được tải trong cùng một truy vấn**.

### Không nên hiểu “hai query” là cam kết tuyệt đối

Tổng số SQL có thể khác khi:

- Có nhiều collection role cùng được truy cập.
- Các owner đến từ nhiều truy vấn khác nhau.
- Một collection đã được khởi tạo trước.
- Entity/collection được lấy từ cache.
- Một số association khác cũng cần truy vấn riêng.
- Hibernate cần thực hiện SQL bổ sung do mapping hoặc inheritance.

SUBSELECT giảm số query cho một nhóm collection cụ thể; nó không loại bỏ toàn bộ N+1 trong cả object graph.

## 7. So sánh SELECT, SUBSELECT, BATCH và JOIN

| Chiến lược | Cách tải | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **SELECT** | Mỗi collection được tải bằng SELECT riêng khi truy cập | Đơn giản, chỉ tải collection thực sự cần | Có thể tạo N+1 |
| **SUBSELECT** | Một secondary SELECT tải collection cho nhóm owner từ query trước | Giảm số query khi cần collection của nhiều owner cùng nhóm | Có thể tải nhiều collection hơn nhu cầu |
| **BATCH** | Một SELECT tải collection của tối đa một nhóm owner bằng IN-list | Linh hoạt cho owner được tải rải rác; giới hạn kích thước nhóm | Có thể phát nhiều batch query |
| **JOIN** | Dùng SQL JOIN lấy owner và phần tử collection trong một query | Có thể tải ngay collection với một round-trip | Nhân hàng kết quả, pagination và nhiều collection có thể phức tạp |

### Ví dụ BATCH

Hibernate có annotation:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@BatchSize(size = 20)
private List<Employee> employees = new ArrayList<>();
```

Khi collection của một owner được truy cập, Hibernate có thể gom collection của các owner cùng loại đang chờ khởi tạo trong Persistence Context thành nhóm tối đa 20 owner:

```sql
SELECT e.*
FROM employees e
WHERE e.department_id IN (?, ?, ?, ...);
```

BATCH thường phù hợp khi:

- Owner được tải bằng nhiều cách, kể cả truy vấn riêng lẻ.
- Ứng dụng chỉ truy cập một phần collection trong số owner đang managed.
- Muốn giới hạn số collection được tải trong một query.

### Ví dụ JOIN fetch

```java
List<Department> departments = session.createQuery(
    "select distinct d " +
    "from Department d " +
    "left join fetch d.employees " +
    "where d.active = true",
    Department.class
).getResultList();
```

JOIN fetch có thể lấy collection ngay cùng truy vấn. Nhưng nếu mỗi Department có nhiều Employee, kết quả SQL sẽ có nhiều hàng lặp thông tin Department. Hibernate cần hợp nhất chúng thành entity/collection trong bộ nhớ.

Không nên mặc định JOIN fetch nhiều collection bag cùng lúc; một số mapping có thể gặp lỗi multiple bag fetch hoặc tạo tích Descartes rất lớn.

## 8. SUBSELECT và FetchType.LAZY

Một cách khai báo thường dùng:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<Employee> employees = new ArrayList<>();
```

`FetchType.LAZY` thể hiện collection chưa cần được nạp ngay khi tải Department. `FetchMode.SUBSELECT` lựa chọn cách Hibernate tải collection khi collection được khởi tạo.

### LAZY không có nghĩa chắc chắn sẽ không có SQL

Những thao tác như:

```java
department.getEmployees().size();
department.getEmployees().iterator().hasNext();
department.getEmployees().stream().count();
```

có thể khởi tạo collection và phát SQL, tùy loại collection và thao tác. Chỉ gọi getter để lấy wrapper/proxy có thể chưa truy vấn database; nhưng truy cập nội dung thường kích hoạt initialization.

### EAGER không phải giải pháp thay thế

Đổi sang `FetchType.EAGER` không tự giải quyết tốt N+1. Provider phải bảo đảm dữ liệu eager có sẵn theo ngữ nghĩa mapping, nhưng chiến lược SQL cụ thể có thể vẫn tạo nhiều query hoặc join. **Không đổi toàn bộ LAZY thành EAGER chỉ để tránh LazyInitializationException hoặc N+1.**

## 9. SUBSELECT chỉ áp dụng cho collection, không phải mọi association

`FetchMode.SUBSELECT` thường được dùng với association collection:

- `@OneToMany`.
- `@ManyToMany`.
- `@ElementCollection`.

Không xem nó là lựa chọn tổng quát cho mọi `@ManyToOne` hoặc `@OneToOne`. Entity-valued to-one association có các chiến lược khác như SELECT, JOIN và batch fetching theo mapping/version.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Không đặt `@Fetch(FetchMode.SUBSELECT)` lên một field to-one rồi kỳ vọng Hibernate tải nhóm Department theo cách giống collection. Khi muốn tối ưu nhiều to-one reference, xem xét batch fetching cho entity hoặc join fetch phù hợp.

## 10. Khi nào SUBSELECT có thể tải quá nhiều dữ liệu?

Giả sử một truy vấn lấy 500 Department:

```java
List<Department> departments = session.createQuery(
    "from Department d where d.region = :region",
    Department.class
)
.setParameter("region", "NORTH")
.getResultList();
```

Ứng dụng chỉ cần danh sách nhân viên của **một Department** đầu tiên:

```java
List<Employee> employees =
    departments.get(0).getEmployees();
```

Với SUBSELECT, lần khởi tạo collection có thể tải collection của cả nhóm 500 Department. Điều này có thể gây:

- Đọc nhiều hàng hơn nhu cầu.
- Tăng lượng dữ liệu truyền qua mạng.
- Tăng bộ nhớ và số entity/collection được quản lý trong Persistence Context.
- Tăng thời gian hydration và dirty checking về sau.
- Tạo một query phụ có kết quả lớn, khó kiểm soát.

### Cách quyết định

SUBSELECT phù hợp khi use case thực sự cần collection của phần lớn hoặc tất cả owner trong nhóm. Nếu chỉ thường xuyên cần collection của một vài owner, BATCH với batch size phù hợp hoặc query riêng theo ID có thể hiệu quả hơn.

Không chỉ đếm số query. Hãy đo:

- Số hàng được trả về.
- Số byte truyền.
- Thời gian database execution.
- Thời gian Hibernate hydrate entities.
- Số entity/collection managed.
- Heap và GC trong request/job.

**Hai query lớn có thể đắt hơn nhiều query nhỏ**, tùy kích thước dữ liệu và query plan.

## 11. SUBSELECT và pagination: phải kiểm chứng SQL thật

Một màn hình phân trang:

```java
List<Department> page = session.createQuery(
    "from Department d " +
    "where d.active = true " +
    "order by d.name, d.id",
    Department.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Sau đó truy cập collection:

```java
page.get(0).getEmployees().size();
```

Không được tự giả định secondary subselect sẽ luôn:

- Chỉ lấy đúng 20 owner trong page.
- Giữ nguyên mọi filter/order như query gốc theo cùng cách ở mọi version.
- Không lặp lại một phần query phức tạp.
- Được database tối ưu tốt như truy vấn lấy danh sách ID đơn giản.

Hibernate cần tái sử dụng thông tin truy vấn owner để tạo subselect; SQL thực tế có thể chứa phần truy vấn owner và chịu tác động của pagination/dialect/version.

### Các điểm cần quan sát

1. Query cha có LIMIT/OFFSET hoặc cú pháp phân trang đặc thù không?
2. Secondary select dùng tập ID của page hay thực thi subquery có hình dạng khác?
3. Query owner có join nhiều bảng hoặc DISTINCT không?
4. Database có query plan tốt cho subselect không?
5. Khi page rỗng hoặc có ít kết quả, collection fetch có tạo SQL không cần thiết không?
6. Số child thực tế của 20 owner có quá lớn không?

Nếu màn hình chỉ cần một trang nhỏ và collection có thể lớn, **DTO projection hoặc truy vấn phân trang child riêng** thường kiểm soát dữ liệu tốt hơn việc khởi tạo collection đầy đủ.

## 12. Subselect query có thể lặp lại điều kiện phức tạp

Giả sử query owner:

```java
List<Department> departments = session.createQuery(
    "select distinct d " +
    "from Department d " +
    "join d.company c " +
    "where c.country = :country " +
    "and d.active = true " +
    "and exists (" +
    "  select 1 from Employee e " +
    "  where e.department = d and e.fullName like :prefix" +
    ")",
    Department.class
)
.setParameter("country", "VN")
.setParameter("prefix", "Nguyen%")
.getResultList();
```

Khi collection được khởi tạo, secondary query có thể cần đưa tập owner vào điều kiện subselect. Vì vậy, một phần logic truy vấn phức tạp có thể xuất hiện lại trong SQL.

Tác động:

- Database có thể phải tối ưu một subquery dài.
- Join/EXISTS/filter có thể được đánh giá lại.
- Query plan của secondary select có thể khác query cha.
- Parameter binding và filter session cần được giữ đúng theo provider.

Hãy quan sát SQL log và EXPLAIN/query plan trên database thật. Nếu subquery lặp lại quá đắt, BATCH hoặc truy vấn child riêng theo danh sách ID có thể phù hợp hơn.

## 13. Session và Persistence Context phải còn phù hợp khi collection được khởi tạo

SUBSELECT là chiến lược lazy collection fetching, nên collection cần được khởi tạo khi Hibernate còn có Persistence Context và thông tin cần thiết về owner query.

Ví dụ:

```java
Department department;

try (Session session = sessionFactory.openSession()) {
    department = session.find(Department.class, 1L);
}

// Session đã đóng.
department.getEmployees().size();
```

Nếu collection chưa được khởi tạo trước khi Session đóng, truy cập sau đó có thể gây `LazyInitializationException`.

### Không giải quyết lỗi bằng cách luôn bật EAGER

Thay vì tải mọi collection ngay:

- Chọn transaction/service boundary rõ ràng.
- Tạo DTO trong transaction khi cần dữ liệu trả về.
- Dùng fetch join/entity graph cho use case cụ thể.
- Dùng SUBSELECT hoặc BATCH khi collection lazy cần được tải theo nhóm.

SUBSELECT **không cho phép lazy collection tự truy cập database sau khi Session đóng**.

## 14. Nhiều collection trên cùng entity: mỗi role là một bài toán riêng

Giả sử Department có:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<Employee> employees = new ArrayList<>();

@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<DepartmentProject> projects = new ArrayList<>();
```

Nếu ứng dụng truy cập cả `employees` và `projects`, không nên kỳ vọng một secondary query duy nhất sẽ tải cả hai collection role. Mỗi collection có bảng/quan hệ và dữ liệu khác nhau; Hibernate có thể cần một truy vấn phụ cho từng role.

Nếu mỗi Department có 50 employees và 100 projects, việc khởi tạo cả hai collection cho 100 Department có thể tải:

- 5.000 employee rows.
- 10.000 project-link rows.

Số câu SQL thấp không có nghĩa dữ liệu ít. Cân nhắc tách query/use case hoặc chỉ lấy những cột cần thiết qua projection.

### Multiple bag fetch khác SUBSELECT

Lỗi/giới hạn khi join fetch nhiều bag là vấn đề khác. SUBSELECT có thể tránh việc JOIN nhiều collection vào cùng một result set, nhưng vẫn có thể tải nhiều dữ liệu và phát nhiều secondary query. Đừng dùng nó như lý do để khởi tạo toàn bộ object graph trong mọi màn hình.

## 15. Collection đã được khởi tạo trước thì sao?

Nếu collection đã được initialize trong cùng Persistence Context:

```java
List<Employee> employees = department.getEmployees();
employees.size(); // Khởi tạo lần đầu.
employees.size(); // Dùng collection đã có.
```

Lần truy cập sau thường không cần tải lại collection bằng SUBSELECT. Hibernate quản lý trạng thái initialized trong collection wrapper.

Nếu dữ liệu child thay đổi từ Session khác sau khi collection đã khởi tạo, SUBSELECT không tự làm mới collection. Cần refresh/clear/reload phù hợp với transaction và cache; **FetchMode.SUBSELECT là chiến lược tải ban đầu, không phải cơ chế đồng bộ thời gian thực**.

Tương tự, nếu collection được lấy từ second-level cache, số SQL có thể khác kỳ vọng. Đừng chỉ nhìn annotation để kết luận database chắc chắn đã chạy secondary select.

## 16. Filter, soft delete và tenant: điều kiện owner/child phải được giữ đúng

Một ứng dụng có thể dùng:

- Hibernate filters.
- Soft-delete condition.
- Tenant discriminator hoặc schema/database per tenant.
- Restriction theo trạng thái.
- Security/visibility predicate.

Khi SUBSELECT fetch collection, cần xác nhận **cả tập owner và các child được phép nhìn thấy** vẫn đúng trong secondary query.

Ví dụ, Department chỉ được tải theo tenant:

```java
List<Department> departments = session.createQuery(
    "from Department d where d.tenantId = :tenantId",
    Department.class
)
.setParameter("tenantId", tenantId)
.getResultList();
```

Collection employees cũng phải có điều kiện tenant/ownership phù hợp. Không chỉ dựa vào subselect của owner để bảo vệ child nếu dữ liệu và mapping cho phép child tham chiếu chéo tenant.

Các filter Hibernate, `@SQLRestriction`, soft delete hoặc multi-tenancy có semantics riêng theo version. **Phải quan sát SQL secondary select và kiểm tra quyền dữ liệu trên database**, đặc biệt khi đây là ranh giới bảo mật.

## 17. @BatchSize thường là phương án thay thế đáng so sánh

SUBSELECT phù hợp khi Hibernate có một nhóm owner từ query. BATCH có cách hoạt động khác:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<Employee> employees = new ArrayList<>();
```

Khi một collection được khởi tạo, Hibernate có thể chọn các collection role cùng loại đang chờ trong Persistence Context và tải tối đa một nhóm bằng IN-list.

### So sánh theo use case

| Use case | SUBSELECT | BATCH |
|---|---|---|
| Tải 100 Department bằng một query, sau đó cần employees của gần như tất cả | Thường đáng thử | Cần nhiều batch query theo size |
| Tải 100 Department nhưng chỉ truy cập employees của 2 Department | Có thể tải quá nhiều | Có thể chỉ tải nhóm nhỏ quanh collection được yêu cầu |
| Tải owner từng cái bằng `find()` | Không nên mặc định tạo cùng nhóm subselect | Thường phù hợp hơn |
| Truy vấn owner rất phức tạp | Secondary SQL có thể lặp lại subquery phức tạp | IN-list theo ID có thể đơn giản hơn |
| Cần giới hạn số owner trong một secondary query | Không có batch-size knob tương đương trên annotation này | Có thể cấu hình batch size |

`@BatchSize` có thể đặt trên entity để batch-fetch các entity proxy hoặc trên collection role để batch-fetch collection. Cách dùng và tác động cần phân biệt theo vị trí annotation.

## 18. Khi nào nên dùng JOIN fetch thay SUBSELECT?

Nếu màn hình luôn cần employees của một Department duy nhất, JOIN fetch có thể đơn giản:

```java
Department department = session.createQuery(
    "select d from Department d " +
    "left join fetch d.employees " +
    "where d.id = :id",
    Department.class
)
.setParameter("id", departmentId)
.uniqueResult();
```

Ưu điểm:

- Một truy vấn lấy owner và collection.
- Không chờ lazy initialization.
- Không cần secondary subselect.

Nhưng nếu tải nhiều Department:

```java
select distinct d
from Department d
left join fetch d.employees
where d.active = true
```

SQL có thể trả nhiều hàng cho cùng Department. Khi có pagination trên collection fetch join, Hibernate/database có thể phải xử lý đặc biệt; một số cấu hình có thể cảnh báo và áp pagination trong bộ nhớ, gây tải dữ liệu rất lớn.

**SUBSELECT tránh nhân parent rows trong truy vấn owner ban đầu**, nhưng phải trả giá bằng một secondary query có thể tải collection của cả nhóm. Lựa chọn dựa trên số owner, số child, pagination và query plan.

## 19. SUBSELECT và EntityGraph/Fetch Profile

Jakarta Persistence EntityGraph cho phép một use case chỉ định association cần fetch:

```java
EntityGraph<Department> graph =
    entityManager.createEntityGraph(Department.class);
graph.addAttributeNodes("employees");

Department department = entityManager.find(
    Department.class,
    departmentId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
```

EntityGraph xác định **những thuộc tính cần được fetch** theo ngữ nghĩa JPA; nó không phải cú pháp portable để chỉ định chính xác `FetchMode.SUBSELECT`. Provider có thể chọn cách thực hiện SQL phù hợp.

Hibernate Fetch Profile cũng là cơ chế Hibernate-specific để chọn cách fetch cho use case. Khi dùng các công cụ này cùng annotation `@Fetch`, hãy kiểm tra **chiến lược nào thực sự được áp dụng** cho truy vấn đang chạy.

Không giả định EntityGraph yêu cầu SUBSELECT hoặc luôn ghi đè một cách đồng nhất mọi mapping fetch strategy.

## 20. Native SQL và DTO projection không phải tình huống SUBSELECT mặc định

SUBSELECT fetch dựa trên thông tin về entity owner được Hibernate quản lý và truy vấn đã tải nhóm owner.

Nếu ứng dụng chạy native query trả DTO:

```java
List<DepartmentRow> rows = session.createNativeQuery(
    "select id, name from departments where active = true",
    DepartmentRow.class
).getResultList();
```

thì `DepartmentRow` không phải entity owner với collection được quản lý theo mapping. Không có lý do để kỳ vọng `@Fetch(FetchMode.SUBSELECT)` trên Department tự được áp dụng.

Nếu native query trả entity `Department.class`, Hibernate có thể quản lý các entity được hydrate, nhưng khả năng SUBSELECT hoạt động như với một HQL entity query **phải kiểm chứng theo phiên bản, query mapping và metadata được cung cấp**. Đừng dựa vào giả định.

Với DTO/projection, nếu cần employees, có thể:

- Viết query riêng lấy employee rows cho tập department IDs.
- Dùng một DTO query có aggregate.
- Chia batch theo danh sách ID.
- Dùng native SQL/CTE khi cần query shape đặc biệt.

## 21. SQL log và query plan là bằng chứng cần kiểm tra

Khai báo annotation chưa chứng minh SUBSELECT đang có lợi. Hãy quan sát:

### 21.1. Bật SQL logging khi phát triển

Ví dụ Spring Boot/Hibernate 6:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Trong môi trường khác, cấu hình logger tương ứng. Bind parameter logging có thể chứa thông tin cá nhân; chỉ bật ở môi trường được kiểm soát.

### 21.2. Kịch bản SQL cần nhìn thấy

Với query owner:

```sql
SELECT d.id, d.name, d.active
FROM departments d
WHERE d.active = ?;
```

Sau khi truy cập collection:

```sql
SELECT e.department_id, e.id, e.full_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.id
    FROM departments d
    WHERE d.active = ?
);
```

Nếu log thực tế cho thấy:

```text
SELECT departments ...
SELECT employees WHERE department_id = ?
SELECT employees WHERE department_id = ?
SELECT employees WHERE department_id = ?
...
```

thì có thể SUBSELECT không được áp dụng cho nhóm owner như mong đợi, collection đã được tải qua đường khác hoặc mapping/fetch override khác đang chi phối.

### 21.3. Đo query plan

Trên database mục tiêu, dùng công cụ tương ứng như `EXPLAIN` hoặc `EXPLAIN ANALYZE` (cẩn trọng vì ANALYZE thực thi statement trong một số hệ quản trị).

Kiểm tra:

- Subquery owner có dùng index phù hợp không?
- Join/filter trên child có sử dụng index `department_id` không?
- Có sort, hash, materialization hoặc scan lớn không?
- Số hàng ước tính và số hàng thực tế khác nhau nhiều không?
- Query phụ có đọc lại một phần lớn bảng parent không?
- Tải toàn bộ collection có vượt nhu cầu use case không?

Đôi khi BATCH với IN-list hoặc một query child riêng có query plan tốt hơn SUBSELECT dù số query nhiều hơn.

## 22. Những điều kiện cần kiểm chứng trước khi chọn SUBSELECT

| Điều cần kiểm chứng | Câu hỏi cụ thể | Dấu hiệu không phù hợp |
|---|---|---|
| **Owner query grouping** | Owner có được tải bởi cùng một query không? | Tải từng owner qua nhiều lần find |
| **Session scope** | Collection có được initialize trong cùng Persistence Context không? | Truy cập sau khi Session đã đóng |
| **Tỷ lệ collection cần dùng** | Use case cần collection của bao nhiêu owner trong nhóm? | Chỉ cần 1/100 collection |
| **Kích thước tập owner** | Query owner trả bao nhiêu entity? | Hàng nghìn owner với collection lớn |
| **Số child mỗi owner** | Tổng số child của cả nhóm là bao nhiêu? | Kết quả secondary select quá lớn |
| **Query complexity** | Query owner có join/EXISTS/filter phức tạp không? | Subquery lặp lại tốn kém |
| **Pagination** | Secondary SQL có giới hạn đúng page không? | Tải child của owner ngoài page hoặc query plan xấu |
| **Multiple collections** | Có nhiều collection role được truy cập không? | Nhiều secondary query lớn |
| **Cache** | L2/query cache có ảnh hưởng kết quả đo không? | Kết luận sai từ số SQL trong một lần chạy |
| **Native query/fetch override** | Owner được load bằng đường nào? | Annotation không được áp dụng như dự tính |
| **Database index** | Có index trên FK/điều kiện lọc không? | Full scan child table |
| **Concurrency/consistency** | Collection có thể đổi trong khi query chạy không? | Kỳ vọng snapshot nhưng transaction không phù hợp |

Không phải tất cả điều kiện đều là yêu cầu bắt buộc của annotation; đây là những điểm cần xác minh để hiểu đúng phạm vi và hiệu quả thực tế.

## 23. Kiểm thử SUBSELECT bằng một kịch bản nhỏ

Tạo 3 Department:

```text
Department 1: 2 employees
Department 2: 3 employees
Department 3: 1 employee
```

Truy vấn tất cả Department:

```java
List<Department> departments = session.createQuery(
    "from Department order by id",
    Department.class
).getResultList();
```

Trước khi truy cập collection, xác nhận LAZY:

```java
boolean initialized = Hibernate.isInitialized(
    departments.get(0).getEmployees()
);
```

Trong test, có thể dùng `org.hibernate.Hibernate.isInitialized(...)` để quan sát trạng thái collection. Không gọi `size()` trước khi kiểm tra vì thao tác ấy có thể kích hoạt initialization.

Sau đó:

```java
int total = departments.get(0).getEmployees().size();
```

Quan sát:

- Có query riêng lấy employees không?
- Secondary query có dùng subquery tập owner không?
- Collection của các Department khác có được khởi tạo cùng không?
- Truy cập collection của Department thứ hai có phát thêm SQL không?

Có thể tiếp tục kiểm tra:

```java
for (Department department : departments) {
    System.out.println(
        department.getId() + ": " + department.getEmployees().size()
    );
}
```

Nếu collection của cả nhóm đã được initialize bởi secondary select, vòng lặp này thường không tạo một query collection cho mỗi owner.

### So sánh với SELECT và BATCH

Tạo ba phiên bản mapping/test riêng:

1. Không có `@Fetch(SUBSELECT)` và không batch size.
2. Có `@Fetch(FetchMode.SUBSELECT)`.
3. Có `@BatchSize(size = 2)`.

Chạy cùng dữ liệu, cùng query owner và cùng thao tác truy cập. Đo **số SQL, số hàng, thời gian, heap**. Không chỉ đo thời gian một lần chạy; warm-up và cache có thể làm kết quả sai lệch.

## 24. Lỗi thường gặp khi dùng SUBSELECT

### Lỗi 1: Nghĩ SUBSELECT luôn giảm xuống đúng hai query

Nếu có nhiều collection role, nhiều nhóm owner, query khác hoặc các association khác, tổng số SQL có thể cao hơn. SUBSELECT chỉ tác động collection mapping được cấu hình.

### Lỗi 2: Tải từng owner rồi mong một subselect chung

Từng `find()` không nhất thiết tạo nhóm owner giống một query trả nhiều entity. Cân nhắc BATCH nếu owner được tải rải rác.

### Lỗi 3: Chỉ truy cập một collection nhưng tải cả nhóm rất lớn

SUBSELECT có thể initialize collection cho toàn bộ nhóm owner. Đo số child rows; nếu chỉ cần một collection, dùng batch hoặc query riêng.

### Lỗi 4: Tưởng LAZY và SUBSELECT mâu thuẫn

Không. LAZY mô tả thời điểm collection được yêu cầu; SUBSELECT mô tả chiến lược SQL khi khởi tạo collection.

### Lỗi 5: Tưởng SUBSELECT là JOIN

Không. Đây là secondary select có subquery owner; nó không lấy parent và child trong cùng một result set đầu tiên.

### Lỗi 6: Dùng cho @ManyToOne hoặc @OneToOne

Không xem SUBSELECT là chiến lược chung cho mọi association. Tập trung vào collection mapping được hỗ trợ.

### Lỗi 7: Quên Session đã đóng

SUBSELECT không sửa `LazyInitializationException`. Collection lazy vẫn cần Persistence Context phù hợp để khởi tạo.

### Lỗi 8: Không đo pagination và query plan

Subquery có thể lặp lại query owner phức tạp hoặc có SQL khác dự kiến. Xem SQL log và plan thực tế.

### Lỗi 9: Cho rằng collection đã initialize sẽ tự cập nhật

Không. FetchMode chỉ ảnh hưởng quá trình tải collection; dữ liệu thay đổi sau đó cần refresh/reload theo transaction và cache.

### Lỗi 10: Chỉ đếm số query

Hai query lớn tải hàng triệu child rows có thể chậm hơn nhiều query nhỏ. Cần đo lượng dữ liệu, memory và DB work.

## 25. Hướng dẫn chọn chiến lược theo use case

| Use case | Chiến lược nên thử trước | Lý do |
|---|---|---|
| Trang hiển thị danh sách 50 Department và cần employees của hầu hết các Department | SUBSELECT | Một query phụ có thể tải collection cho nhóm owner |
| Báo cáo tải 1.000 Department nhưng chỉ hiển thị employee của 3 Department được chọn | BATCH hoặc query riêng | Tránh tải collection của cả 1.000 owner |
| Mở chi tiết một Department và luôn cần employees | JOIN fetch hoặc entity graph | Một owner, collection cần ngay |
| Owner được tải từng ID trong nhiều service call | BATCH | Không phụ thuộc một query owner chung |
| Chỉ cần tổng số employee theo Department | DTO projection với COUNT/GROUP BY | Không cần hydrate toàn bộ Employee |
| Collection có hàng chục nghìn child | Query phân trang child riêng | Không tải toàn collection |
| Nhiều collection lớn trên cùng owner | Query riêng/projection theo use case | Tránh tải object graph khổng lồ |
| Query owner có điều kiện phức tạp và subquery tốn kém | BATCH hoặc query child theo ID | Có thể có query plan đơn giản hơn |

### Không có một fetch mode tốt cho mọi màn hình

Một mapping có thể được dùng bởi nhiều use case khác nhau:

- Màn hình chi tiết cần một collection.
- Màn hình danh sách cần collection của nhiều owner.
- Báo cáo chỉ cần aggregate.
- API mobile chỉ cần vài trường.

Có thể giữ association LAZY làm mặc định rồi chọn fetch plan theo use case bằng query fetch join, EntityGraph, batch fetching hoặc SUBSELECT khi phù hợp. Nếu cần query hình dạng hoàn toàn khác, DTO projection thường rõ ràng hơn.

## 26. Bài thực hành tổng hợp

Xây dựng trang tổ chức công ty:

- Tải danh sách Department theo trạng thái hoạt động.
- Mỗi Department có một collection employees.
- Một số Department có rất nhiều nhân viên.
- Trang đầu hiển thị tên Department và số lượng nhân viên; trang chi tiết hiển thị danh sách nhân viên có phân trang.

### Phần A — SUBSELECT cho danh sách cần toàn bộ collection

1. Ánh xạ `Department.employees` LAZY.
2. Đặt `@Fetch(FetchMode.SUBSELECT)`.
3. Query 20 Department.
4. Truy cập employees của tất cả 20 Department.
5. Quan sát số câu SQL và secondary select.

### Phần B — Chỉ cần số lượng

Thay vì khởi tạo collection:

```java
List<Object[]> counts = session.createQuery(
    "select d.id, count(e.id) " +
    "from Department d " +
    "left join d.employees e " +
    "where d.active = true " +
    "group by d.id",
    Object[].class
).getResultList();
```

So sánh lượng dữ liệu và thời gian với cách tải cả collection rồi gọi `size()`. Với use case chỉ cần count, projection thường phù hợp hơn.

### Phần C — Pagination child

Tạo query riêng lấy employees của một Department:

```java
List<Employee> page = session.createQuery(
    "from Employee e " +
    "where e.department.id = :departmentId " +
    "order by e.fullName, e.id",
    Employee.class
)
.setParameter("departmentId", departmentId)
.setFirstResult(0)
.setMaxResults(25)
.getResultList();
```

Không cần khởi tạo toàn bộ `Department.employees` chỉ để hiển thị 25 dòng đầu.

### Phần D — So sánh BATCH

Đổi SUBSELECT thành `@BatchSize(size = 10)`. Tải Department theo nhiều truy vấn hoặc `find()` từng ID rồi truy cập employees. So sánh số query và tổng số rows với SUBSELECT.

### Phần E — Kiểm tra vòng đời Session

1. Query Department trong Session.
2. Đóng Session trước khi truy cập employees.
3. Quan sát lazy initialization failure.
4. Sửa bằng cách khởi tạo collection trong transaction hoặc chuyển sang DTO trước khi đóng Session.

## 27. Các câu hỏi tự kiểm tra

1. `FetchMode.SUBSELECT` khác `FetchType.LAZY` ở điểm nào?
2. Vì sao tải nhiều Department bằng một query rồi truy cập collection có thể giảm N+1?
3. Vì sao tải từng Department bằng `find()` không nên mặc định có cùng hiệu quả?
4. SUBSELECT khác BATCH ở cách xác định tập owner như thế nào?
5. Vì sao SUBSELECT có thể tải quá nhiều dữ liệu khi chỉ cần collection của một owner?
6. SUBSELECT có giúp truy cập collection sau khi Session đóng không?
7. Vì sao JOIN fetch có thể gây nhân hàng hoặc vấn đề pagination?
8. Nếu query owner có nhiều join/filter/EXISTS, cần kiểm tra gì ở secondary select?
9. Nếu collection đã initialize rồi, dữ liệu thay đổi từ Session khác có tự cập nhật không?
10. Nếu chỉ cần count employees, vì sao DTO projection có thể tốt hơn SUBSELECT?

Gợi ý: (1) LAZY là timing, SUBSELECT là SQL strategy; (2) một secondary query có thể tải collection cho cả nhóm owner; (3) không có cùng owner-query grouping; (4) SUBSELECT dùng subquery của owner query, BATCH dùng nhóm ID trong IN-list; (5) nó có thể initialize collection cho cả nhóm; (6) không; (7) mỗi child tạo hàng kết quả và pagination trên collection fetch phức tạp; (8) SQL được sinh và query plan; (9) không; (10) không cần hydrate toàn bộ child entities.

## 28. Nguyên tắc cần ghi nhớ

1. **`FetchMode.SUBSELECT` là chiến lược Hibernate-specific cho collection fetching**, thường dùng để tránh N+1 khi nhiều owner được tải từ cùng một truy vấn.
2. **LAZY và SUBSELECT giải quyết hai câu hỏi khác nhau:** khi nào collection được khởi tạo và Hibernate dùng SQL nào để tải collection.
3. **Owner query grouping là điều kiện cần hiểu rõ.** Không mặc định tải từng owner bằng `find()` có cùng hiệu quả như một query trả nhiều owner.
4. **Collection được khởi tạo cho cả nhóm owner** có thể giảm query nhưng tải nhiều dữ liệu hơn nhu cầu.
5. **SUBSELECT khác BATCH:** SUBSELECT dùng subquery của owner query; BATCH gom ID owner vào IN-list theo batch size.
6. **SUBSELECT khác JOIN fetch:** nó phát secondary select, tránh nhân parent rows trong query đầu nhưng vẫn có thể tạo result set lớn.
7. **Pagination, query phức tạp, filter, cache và native query cần kiểm chứng bằng SQL thật.** Annotation không thay thế query plan.
8. **Persistence Context phải còn phù hợp khi lazy collection được khởi tạo.** SUBSELECT không khắc phục collection truy cập sau khi Session đóng.
9. **Một fetch mode không phù hợp mọi use case.** Dùng DTO/projection cho aggregate và query phân trang cho collection lớn.
10. **Đo cả số query lẫn số hàng, thời gian, memory và DB work.** Ít query hơn không tự động đồng nghĩa nhanh hơn.

Khi cân nhắc `FetchMode.SUBSELECT`, hãy trả lời bốn câu hỏi: **“Các owner có đến từ cùng một query không?”, “Use case cần collection của bao nhiêu owner?”, “Secondary SQL có bị phình bởi pagination/filter/query phức tạp không?”, và “Query plan có thực sự tốt hơn BATCH/SELECT không?”**. Kiểm chứng được những điều này trên Hibernate và database của dự án mới cho biết SUBSELECT có phải fetch strategy phù hợp.

### Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide — Fetching strategies](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching-strategies)
- [Hibernate ORM User Guide — Batch fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching-batch)
- [Hibernate ORM User Guide — Subselect fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching-subselect)
- [Hibernate ORM Javadocs — Fetch](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/annotations/Fetch.html)
- [Hibernate ORM Javadocs — FetchMode](https://docs.jboss.org/hibernate/orm/current/javadocs/org/hibernate/annotations/FetchMode.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
