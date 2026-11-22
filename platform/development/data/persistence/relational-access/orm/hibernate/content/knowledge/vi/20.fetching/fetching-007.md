# `@BatchSize` và cấu hình kích thước tải nhóm

Trong Hibernate ORM, `@BatchSize` là cơ chế **batch fetching** giúp giảm số lần truy vấn khi ứng dụng truy cập nhiều entity proxy hoặc collection lazy trong cùng một `Session`/`EntityManager`. Thay vì mỗi lần khởi tạo một proxy hay collection lại gửi một câu `SELECT` riêng, Hibernate có thể gom nhiều định danh đang chờ tải vào một truy vấn, thường sử dụng điều kiện `IN`.

Cơ chế này đặc biệt hữu ích khi ứng dụng đọc danh sách entity rồi lần lượt truy cập quan hệ lazy, dẫn tới vấn đề **N+1 SELECT**. Ví dụ, tải 100 `Department` rồi đọc `department.getEmployees()` có thể tạo một truy vấn lấy phòng ban và thêm 100 truy vấn lấy nhân viên. Nếu collection được cấu hình batch size 16, Hibernate có thể tải collection của nhiều phòng ban trong một lần SELECT, giảm số round trip đáng kể.

`@BatchSize` có thể được khai báo ở hai phạm vi:

- **Trên entity class:** gom các entity proxy cùng loại đang chờ khởi tạo, ví dụ nhiều `Department` được tham chiếu bởi các `Employee`.
- **Trên collection-valued association:** gom nhiều collection cùng role đang chờ khởi tạo, ví dụ collection `Department.employees` của nhiều phòng ban.

Ngoài annotation, có thể cấu hình kích thước mặc định toàn cục bằng `hibernate.default_batch_fetch_size`. Cần phân biệt batch fetching khi **đọc** với JDBC batching khi **ghi**; hai cơ chế giải quyết hai vấn đề khác nhau.

## 1. N+1 SELECT: vấn đề mà batch fetching nhắm tới

Giả sử có 100 phòng ban, mỗi phòng ban có nhiều nhân viên. Ứng dụng tải danh sách phòng ban:

```java
List<Department> departments = em.createQuery(
    "select d from Department d order by d.name",
    Department.class
).getResultList();
```

Sau đó truy cập collection lazy:

```java
for (Department department : departments) {
    System.out.println(
        department.getName() + ": " + department.getEmployees().size()
    );
}
```

Nếu `employees` được fetch theo kiểu `SELECT` và chưa được khởi tạo, một lịch truy vấn thường gặp là:

```sql
-- Truy vấn đầu tiên: lấy danh sách department
SELECT d.id, d.name
FROM departments d
ORDER BY d.name;

-- Mỗi lần truy cập một collection có thể tạo một SELECT riêng
SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id = 1;

SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id = 2;

SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id = 3;

-- ... tiếp tục cho các department còn lại
```

Nếu có 100 phòng ban, tổng số truy vấn có thể gần 101: một truy vấn lấy department và 100 truy vấn lấy collection.

Đây là vấn đề **N+1**:

- 1 truy vấn tải danh sách entity gốc.
- N truy vấn tải dữ liệu liên quan theo từng entity.

Số lượng entity không phải lúc nào cũng bằng số truy vấn: collection có thể đã được load, cache có thể đáp ứng, hoặc một số owner không có phần tử. Nhưng mô hình trên là dấu hiệu điển hình của N+1.

### 1.1. N+1 không chỉ xuất hiện ở collection

Ví dụ `Employee` tham chiếu `Department` bằng quan hệ to-one lazy:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Ứng dụng tải nhiều employee, sau đó đọc tên department:

```java
List<Employee> employees = em.createQuery(
    "select e from Employee e",
    Employee.class
).getResultList();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
```

Nếu mỗi `Department` là một proxy chưa khởi tạo, Hibernate có thể phải tải từng proxy riêng. Đây là trường hợp **entity batch fetching** mà `@BatchSize` trên class `Department` có thể giúp giảm số SELECT.

### 1.2. Vì sao N+1 ảnh hưởng hiệu năng?

Một SELECT nhỏ có thể chạy nhanh, nhưng hàng chục hoặc hàng trăm round trip cộng lại tạo ra độ trễ đáng kể:

- Mỗi truy vấn có chi phí gửi/nhận qua mạng và xử lý ở database.
- Connection có thể phải chờ thực thi nhiều statement tuần tự.
- Database phải parse/execute nhiều câu tương tự.
- Transaction có thể kéo dài hơn, giữ connection và snapshot lâu hơn.
- Khi tải cao, số query tăng làm tăng contention và chi phí monitoring.

Batch fetching giảm **số lần tải theo nhóm**, nhưng không nhất thiết giảm tổng số hàng dữ liệu phải đọc. Nếu ứng dụng thật sự cần toàn bộ 100 collection, database vẫn phải trả các employee tương ứng.

## 2. Batch fetching hoạt động như thế nào?

Hibernate duy trì thông tin về các proxy entity và persistent collection chưa được khởi tạo trong persistence context. Khi ứng dụng truy cập một proxy hoặc collection, Hibernate có thể chọn thêm các đối tượng cùng loại/role đang chờ tải và lấy chúng cùng một lần.

Hình dung:

```text
Persistence Context
  ├─ Department#1.employees  (uninitialized)
  ├─ Department#2.employees  (uninitialized)
  ├─ Department#3.employees  (uninitialized)
  ├─ Department#4.employees  (uninitialized)
  └─ Department#5.employees  (uninitialized)
                  |
                  | truy cập collection đầu tiên
                  v
        Batch fetch, size = 5
                  |
                  v
SELECT ... FROM employees
WHERE department_id IN (1, 2, 3, 4, 5)
                  |
                  v
Hibernate phân nhóm các hàng trả về
vào từng Department.employees collection
```

Với batch size 16, Hibernate có thể tải **tối đa một nhóm gồm 16 định danh đủ điều kiện** trong một lần truy vấn. Khi truy cập các đối tượng còn lại, các batch tiếp theo có thể được thực hiện.

Điều cần nhớ:

- Batch fetching là tối ưu của **lazy loading**.
- Nó không tự động biến quan hệ thành `EAGER`.
- Nó không nhất thiết tải hết mọi entity/collection ngay khi query gốc chạy.
- Nó gom các đối tượng lazy đang có trong persistence context và đủ điều kiện tải.
- Số định danh thực tế trong một câu SQL có thể ít hơn kích thước cấu hình.

Batch fetching thường được thực hiện bằng một hoặc một số SELECT có điều kiện theo nhiều khóa, ví dụ `IN (?, ?, ...)`. Hình dạng SQL chính xác phụ thuộc mapping, identifier type, database dialect và phiên bản Hibernate.

## 3. `@BatchSize` trên entity class

Dùng khi Hibernate có nhiều **entity proxy cùng loại** đang chờ khởi tạo.

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.BatchSize;

@Entity
@Table(name = "departments")
@BatchSize(size = 16)
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Department() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Và entity `Employee`:

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    private Department department;

    protected Employee() {
    }

    public Department getDepartment() {
        return department;
    }

    public String getFullName() {
        return fullName;
    }
}
```

Khi tải nhiều employee:

```java
List<Employee> employees = em.createQuery(
    "select e from Employee e",
    Employee.class
).getResultList();

for (Employee employee : employees) {
    Department department = employee.getDepartment();
    System.out.println(department.getName());
}
```

Giả sử Hibernate có 16 proxy `Department` chưa khởi tạo trong cùng persistence context. Khi ứng dụng truy cập một proxy, Hibernate có thể tải một nhóm bằng SQL tương đương:

```sql
SELECT d.id, d.name
FROM departments d
WHERE d.id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

Thay vì 16 SELECT theo từng ID, một SELECT có thể khởi tạo nhiều proxy cùng lúc.

### 3.1. Annotation nằm trên entity đích

Trong ví dụ trên, `@BatchSize` đặt trên class `Department`, vì đây là **loại entity mà Hibernate cần gom proxy để tải**.

Không nên nhầm rằng annotation phải đặt trên field `Employee.department` để batch các department proxy. Với entity batch fetching, cấu hình trên entity type là cách diễn đạt rõ ràng.

### 3.2. Chỉ những proxy đủ điều kiện mới được gom

Hibernate không thể gom tùy ý mọi entity trong database. Những proxy cần tải phải:

- Thuộc cùng entity type/role phù hợp.
- Đang tồn tại trong persistence context/session liên quan.
- Chưa được khởi tạo hoặc chưa có state cần thiết.
- Không được đáp ứng sẵn bởi trạng thái managed/cache hiện tại.
- Có identifier hợp lệ để tạo truy vấn tải nhóm.

Nếu mỗi employee tham chiếu một department khác nhau và các proxy đã được tạo khi materialize query gốc, batch fetching có cơ hội gom chúng. Nếu ứng dụng chỉ tạo một proxy rồi đóng session ngay, không có nhóm nào để tải cùng.

### 3.3. Không phải mọi association to-one đều chắc chắn tạo proxy

Batch fetching entity chỉ hữu ích khi Hibernate có lazy reference/proxy hoặc representation phù hợp để trì hoãn tải. Một quan hệ được fetch eager, đã join fetch, đã initialized hoặc được provider xử lý theo cách khác có thể không tạo ra các proxy chờ tải.

Đặc biệt, hành vi lazy của một số mapping `@OneToOne` phụ thuộc optionality, ownership và bytecode enhancement. Không nên thêm `@BatchSize` rồi giả định mọi to-one đều trở thành proxy lazy.

## 4. `@BatchSize` trên collection-valued association

Khi vấn đề là nhiều collection lazy của cùng một association role, đặt annotation trên field/property collection.

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import org.hibernate.annotations.BatchSize;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
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
}
```

Giả sử query tải 50 phòng ban. Khi truy cập:

```java
departments.get(0).getEmployees().size();
```

Hibernate có thể khởi tạo collection của một nhóm các department chưa được tải, tối đa theo batch size. SQL khái niệm:

```sql
SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id IN (?, ?, ?, ..., ?);
```

Hibernate nhận các hàng và phân chúng vào collection tương ứng dựa trên `department_id`.

Sau đó, khi code truy cập collection của một department khác đã được tải trong cùng batch, Hibernate có thể không cần SELECT mới.

### 4.1. Collection batch size là batch của owner keys

Nếu annotation nằm trên `Department.employees`, các định danh được gom là **ID của các Department sở hữu collection**, không phải ID của từng Employee.

Ví dụ:

```text
Department#10.employees
Department#11.employees
Department#12.employees
```

Một truy vấn collection batch tải employee cho nhiều `department_id` cùng lúc.

Đây là điểm khác với entity batch fetching:

| Cấu hình | Đối tượng được gom | Khóa thường xuất hiện trong điều kiện SQL |
| --- | --- | --- |
| `@BatchSize` trên entity class | Entity proxy cùng loại | Primary key của entity |
| `@BatchSize` trên collection field/property | Collection cùng role của nhiều owner | Foreign key/owner key của collection |

### 4.2. Collection role phải tương ứng

Hibernate gom các collection cùng mapping role. Hai collection có tên field giống nhau nhưng thuộc những association role khác nhau không mặc nhiên được gom chung một truy vấn.

Ví dụ `Department.employees` và `Project.tasks` là hai collection role riêng. Cấu hình batch size trên `Department.employees` không tự áp dụng cho `Project.tasks`.

## 5. Cấu hình mặc định toàn cục bằng `hibernate.default_batch_fetch_size`

Thay vì gắn annotation lên từng entity/collection, có thể thiết lập kích thước mặc định:

```properties
hibernate.default_batch_fetch_size=16
```

Setting này cung cấp batch fetch size mặc định cho những entity/collection không có cấu hình riêng. Giá trị `1` hoặc không cấu hình batch size thường có nghĩa batch fetching không được kích hoạt theo mặc định.

Ví dụ với Spring Boot:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

Hoặc cấu hình trong `persistence.xml`:

```xml
<properties>
    <property name="hibernate.default_batch_fetch_size" value="16"/>
</properties>
```

Tên property Hibernate vẫn là `hibernate.default_batch_fetch_size`; Spring Boot dùng tiền tố `spring.jpa.properties.` để chuyển property xuống provider.

### 5.1. Annotation cụ thể và global default

Có thể dùng kết hợp:

```java
@Entity
@BatchSize(size = 32)
public class Department {
    // ...
}
```

và:

```properties
hibernate.default_batch_fetch_size=16
```

Mục tiêu là đặt một mức mặc định chung, rồi chọn batch size riêng cho một entity/collection có workload đặc biệt. Cấu hình cụ thể trên mapping có thể ghi đè default tương ứng.

Không nên đặt một annotation cho mọi entity theo cùng một giá trị chỉ vì một truy vấn đang gặp N+1. Hãy xác định loại proxy/collection nào được tải nhiều và đo số query trước khi mở rộng phạm vi.

### 5.2. Khi nào nên dùng annotation, khi nào dùng global setting?

| Cách cấu hình | Phù hợp khi | Ưu điểm | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| `@BatchSize` trên entity | Một entity type thường được tham chiếu lazy từ nhiều hàng | Tập trung ngay tại mapping | Hibernate-specific annotation trong model |
| `@BatchSize` trên collection | Một collection role thường được truy cập theo từng owner | Điều chỉnh riêng từng quan hệ | Cần gắn đúng field/property |
| `hibernate.default_batch_fetch_size` | Muốn có default cho nhiều mapping lazy | Dễ cấu hình ở deployment | Có thể ảnh hưởng rộng và tải dữ liệu không cần thiết |
| Kết hợp default + annotation | Hệ thống có pattern chung nhưng vài role cần mức riêng | Linh hoạt | Phải ghi rõ lý do để tránh cấu hình khó hiểu |

### 5.3. Không có một batch size tối ưu cho mọi ứng dụng

Giá trị 16, 32 hoặc 64 chỉ là điểm bắt đầu để thử nghiệm. Batch size hợp lý phụ thuộc:

- Số proxy/collection thường xuất hiện cùng lúc trong một persistence context.
- Số lượng owner/association thực tế được truy cập.
- Kích thước row và số cột cần hydrate.
- Độ trễ mạng tới database.
- Giới hạn số bind parameters/IN expressions của DBMS và JDBC driver.
- Chi phí parse/plan query và hiệu quả cache của database.
- Bộ nhớ heap và thời gian giữ persistence context.
- Mức độ truy cập trùng ID, L2 cache hit và cardinality của quan hệ.

Một batch size quá nhỏ vẫn tạo nhiều round trip. Một batch size quá lớn có thể tải nhiều dữ liệu không cần, tạo IN list lớn, tăng số bind parameters, tăng memory footprint hoặc làm query plan kém hiệu quả.

## 6. Ví dụ đầy đủ: giảm N+1 cho collection `Department.employees`

Giả sử có 100 phòng ban. Dùng mapping:

```java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    private Long id;

    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<Employee> employees = new ArrayList<>();

    // constructor/getters...
}
```

Query:

```java
List<Department> departments = em.createQuery(
    "select d from Department d order by d.id",
    Department.class
).getResultList();

for (Department department : departments) {
    int employeeCount = department.getEmployees().size();
    System.out.println(employeeCount);
}
```

Với collection select fetching thông thường không có batch size:

```text
1 SELECT lấy 100 Department
100 SELECT lấy 100 collection employees

Tổng minh họa: 101 SELECT
```

Với batch size 16:

```text
1 SELECT lấy 100 Department
1 SELECT lấy employees cho một nhóm department
1 SELECT lấy employees cho nhóm tiếp theo
...
các nhóm còn lại cho tới khi collection cần thiết được khởi tạo

Số truy vấn collection có thể gần ceil(100 / 16) = 7
Tổng minh họa: khoảng 8 SELECT
```

Đây là **ước lượng để giải thích**, không phải cam kết chính xác. Số SELECT có thể khác do collection đã initialized, owner không có child, cache, thứ tự truy cập, dialect, cách Hibernate chọn batch và các association khác được fetch.

SQL minh họa cho một nhóm:

```sql
SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id IN (10, 11, 12, 13, 14, 15, 16, 17,
                          18, 19, 20, 21, 22, 23, 24, 25);
```

Một truy vấn có thể trả nhiều hàng cho mỗi department. Hibernate phân chúng vào từng collection; không phải tất cả nhân viên được gộp vào một collection duy nhất.

### 6.1. Vì sao batch size 16 không đảm bảo đúng 7 query?

Một số phòng ban có thể không có nhân viên; một số collection có thể đã được khởi tạo trước; một số owner có thể bị bỏ qua; L2 cache có thể đáp ứng một phần dữ liệu; và batch cuối thường không đủ 16 ID.

Vì vậy công thức:

\[
\text{Số SELECT collection} \approx
\left\lceil \frac{\text{Số collection cần khởi tạo}}{\text{Batch size}} \right\rceil
\]

chỉ là mô hình ước lượng. Đừng dùng nó làm assertion tuyệt đối cho mọi phiên bản/provider.

## 7. Ví dụ đầy đủ: batch fetching entity proxy

Xét `Employee.department` là lazy to-one:

```java
@Entity
@Table(name = "departments")
@BatchSize(size = 16)
public class Department {

    @Id
    private Long id;

    private String name;

    protected Department() {
    }

    public String getName() {
        return name;
    }
}
```

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    private Long id;

    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected Employee() {
    }

    public String getFullName() {
        return fullName;
    }

    public Department getDepartment() {
        return department;
    }
}
```

Ứng dụng tải employee:

```java
List<Employee> employees = em.createQuery(
    "select e from Employee e order by e.id",
    Employee.class
).getResultList();

for (Employee employee : employees) {
    System.out.println(
        employee.getFullName() + " / " +
        employee.getDepartment().getName()
    );
}
```

Khi hydrate các employee, Hibernate có thể tạo proxy cho các department tham chiếu. Nếu nhiều proxy `Department` đang chờ khởi tạo trong cùng session, batch fetching có thể phát:

```sql
SELECT d.id, d.name
FROM departments d
WHERE d.id IN (?, ?, ?, ?, ?, ?, ?, ?);
```

Nếu 100 employee cùng tham chiếu 5 department, số proxy **unique** cần tải chỉ là 5, không phải 100. Hibernate persistence context giữ một managed representation theo persistent identity, nên những employee cùng department có thể dùng chung proxy/instance.

### 7.1. Batch size áp dụng theo entity type, không theo số employee

Trong ví dụ, `@BatchSize` trên `Department` gom các proxy `Department`. Nếu `Employee` cũng có các association lazy tới `Manager`, đó là entity type/association khác với candidate queue riêng.

Không hiểu batch size 16 là “mỗi lần xử lý 16 Employee”. Nó là giới hạn nhóm **entity/collection lazy instances** phù hợp đang chờ tải.

## 8. Batch fetching vẫn là lazy SELECT, không phải JOIN FETCH

Khi dùng `@BatchSize`, Hibernate thường phát các SELECT bổ sung với nhiều ID/owner keys. Nó không biến truy vấn ban đầu thành một JOIN duy nhất.

So sánh:

| Cơ chế | Cách tải | Điểm mạnh | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| Lazy SELECT mặc định | Mỗi proxy/collection tải riêng khi truy cập | Đơn giản, chỉ tải khi cần | Có thể tạo N+1 |
| `@BatchSize` | Gom nhiều lazy instances vào SELECT theo nhóm | Giảm round trip, ít thay đổi query gốc | Vẫn có các query bổ sung |
| `JOIN FETCH` | Join association trong query gốc | Lấy dữ liệu cần trong một query | Có thể nhân số hàng, ảnh hưởng pagination |
| Entity Graph | Chỉ định fetch plan theo use case | Có thể tái sử dụng mapping và query | Provider quyết định SQL; cần kiểm tra |
| `@Fetch(FetchMode.SUBSELECT)` | Có thể tải collections cùng role của nhóm owner bằng subselect | Hữu ích cho collection của tập owner được query trước | Có thể tải nhiều collection hơn cần thiết |
| DTO projection | Chọn trực tiếp dữ liệu cần trả | Tránh hydrate graph entity không cần | Phải thiết kế projection/query |

Batch fetching là một lựa chọn khi ứng dụng muốn giữ lazy loading và vẫn truy cập nhiều association theo từng object.

### 8.1. Dùng `JOIN FETCH` khi biết rõ dữ liệu cần

```java
List<Department> departments = em.createQuery(
    "select distinct d " +
    "from Department d " +
    "left join fetch d.employees",
    Department.class
).getResultList();
```

Query này yêu cầu tải department cùng employees trong query. Với một trang nhỏ và collection phù hợp, JOIN FETCH có thể tốt hơn batch fetching vì chỉ cần một lần round trip.

Nhưng join collection có thể làm một department xuất hiện trên nhiều SQL rows, mỗi employee một row. `distinct` trong JPQL giúp xử lý duplicate root entities theo semantics query/provider; nó không loại bỏ chi phí truyền dữ liệu lặp của các cột department ở SQL result.

### 8.2. Pagination và fetch join collection

Không nên mặc định kết hợp pagination với `JOIN FETCH` collection lớn. Việc giới hạn row SQL có thể cắt mất child rows hoặc khiến provider phải xử lý phân trang ở bộ nhớ/cảnh báo. Hãy kiểm tra SQL và log của phiên bản Hibernate đang dùng.

Một cách thường dùng là:

1. Query trang các ID/root entity.
2. Query dữ liệu association cho nhóm ID đó bằng batch fetch hoặc truy vấn thứ hai.
3. Dùng DTO projection nếu endpoint chỉ cần một tập field cụ thể.

Batch fetching có thể phù hợp khi tải từng page entity rồi truy cập collection lazy của những entity trong page.

## 9. So sánh với `@Fetch(FetchMode.SUBSELECT)`

Hibernate có `@Fetch(FetchMode.SUBSELECT)` cho một số collection mapping:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
@org.hibernate.annotations.Fetch(
    org.hibernate.annotations.FetchMode.SUBSELECT
)
private List<Employee> employees = new ArrayList<>();
```

Khi một collection của role đó được khởi tạo, Hibernate có thể dùng một truy vấn subselect để tải collections cho những owner được lấy bởi query trước đó.

SQL minh họa có thể giống:

```sql
SELECT e.id, e.department_id, e.full_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.id
    FROM departments d
    WHERE d.active = true
);
```

Hình dạng thực tế phụ thuộc query gốc, mapping và dialect.

Phân biệt:

- `@BatchSize(size=16)` gom một **nhóm hữu hạn owner keys** vào mỗi batch.
- `FetchMode.SUBSELECT` có thể tải collection cùng role cho tập owner gắn với truy vấn trước đó bằng một subselect.

Subselect có thể rất hữu ích khi chắc chắn cần collection cho phần lớn owner trong một kết quả. Nếu chỉ truy cập một vài collection, nó có thể tải thừa. Batch fetching thường linh hoạt hơn khi ứng dụng truy cập một phần danh sách.

Không nên gắn cả hai annotation trên cùng một collection rồi giả định chúng cộng dồn. Chọn một chiến lược rõ ràng và quan sát SQL.

## 10. Batch fetching và second-level cache

L1 cache là persistence context của một session. L2 cache có thể lưu entity/collection giữa các session nếu được cấu hình.

Khi batch fetching diễn ra:

- Entity/collection đã có trong L1 không cần tải lại.
- L2 cache có thể đáp ứng một số candidate nếu mapping/cache strategy hỗ trợ.
- Những candidate còn thiếu có thể được tải qua SQL batch.
- Số ID thực tế trong SQL có thể nhỏ hơn batch size.
- Cache hit/miss và invalidation ảnh hưởng kết quả đo.

Không nên kết luận `@BatchSize` luôn tạo một câu SELECT có đủ N tham số. Hibernate có thể bỏ qua các entity/collection đã được initialized hoặc có sẵn dữ liệu từ cache.

### 10.1. L2 cache không thay thế fetch plan

L2 cache có thể giảm số lần database đọc dữ liệu, nhưng nó không tự giải quyết mọi vấn đề về:

- Truy vấn cần lấy danh sách ID theo điều kiện.
- N+1 cho những association không cacheable.
- Fetch quá nhiều cột/hàng.
- Lazy loading ngoài session.
- Kích thước object graph và memory.

Batch fetching và L2 cache có thể bổ sung nhau, nhưng phải đo trong môi trường cache có trạng thái gần production.

## 11. Kích thước batch ảnh hưởng gì?

Batch size là **giới hạn số identifier/collection keys được Hibernate cố gắng tải cùng lúc**, không phải số entity chắc chắn sẽ được trả về.

Ví dụ với 50 collection cần tải:

| Batch size | Số nhóm lý thuyết | Ý nghĩa |
| ---: | ---: | --- |
| 1 | 50 | Gần như không có batch fetching |
| 8 | 7 | Nhiều query nhỏ hơn |
| 16 | 4 | Cân bằng để bắt đầu thử |
| 32 | 2 | Ít round trip hơn, nhóm lớn hơn |
| 64 | 1 | Có thể tải toàn bộ 50 trong một batch nếu đủ điều kiện |

Bảng chỉ là phép chia lý thuyết; số query thật có thể khác.

### 11.1. Batch nhỏ

Ưu điểm:

- Ít bind parameters mỗi query.
- Không tải quá nhiều collection/entity cùng lúc.
- Có thể phù hợp DB có giới hạn hoặc association rất lớn.

Nhược điểm:

- Nhiều round trip hơn.
- N+1 được giảm nhưng chưa tối ưu trong workload có nhiều candidate.
- Tăng số lần parse/execute statement.

### 11.2. Batch lớn

Ưu điểm:

- Giảm số lần query khi có nhiều proxy/collection cùng chờ.
- Có thể tận dụng độ trễ mạng tốt hơn.
- Giảm overhead statement ở workload phù hợp.

Nhược điểm:

- IN list và số bind parameters lớn.
- Có thể tải những collection không thực sự cần.
- Collection lớn có thể làm heap tăng mạnh.
- Query plan/statement cache của database có thể chịu tác động.
- Một số dialect có giới hạn số phần tử trong IN expression hoặc số bind parameters.

### 11.3. Chọn kích thước bằng benchmark

Một quy trình hợp lý:

1. Đo baseline SQL count và latency với batch fetching tắt.
2. Chọn giá trị ban đầu vừa phải, ví dụ 16.
3. Đo lại số statement, tổng rows, thời gian query và heap.
4. Thử mức thấp hơn/cao hơn như 8, 16, 32.
5. Chạy với phân bố dữ liệu thực tế: owner có collection rỗng, nhỏ và rất lớn.
6. Kiểm tra trên đúng DBMS/driver production.
7. Chọn giá trị cân bằng, không chỉ chọn phương án có ít SELECT nhất.

Một query lớn trả hàng trăm nghìn rows không tự nhiên tốt hơn nhiều query nhỏ nếu endpoint chỉ cần một phần dữ liệu.

## 12. Giới hạn của SQL `IN` và identifier phức hợp

Batch fetching thường dùng nhiều ID trong điều kiện SQL:

```sql
WHERE id IN (?, ?, ?, ...)
```

Với database/driver có giới hạn số bind parameters hoặc số biểu thức trong `IN`, batch quá lớn có thể bị chia nhỏ hoặc chịu giới hạn theo dialect. Hibernate có thông tin dialect để tạo SQL phù hợp, nhưng không nên giả định mọi DBMS có giới hạn giống nhau.

### 12.1. Composite identifiers

Entity dùng `@EmbeddedId`/composite key có nhiều thành phần. SQL batch có thể cần tuple comparison hoặc biểu thức tương đương, tùy dialect hỗ trợ:

```sql
WHERE (tenant_id, document_no) IN (
    (?, ?),
    (?, ?),
    (?, ?)
)
```

Không phải mọi DBMS đều hỗ trợ cú pháp tuple `IN` như nhau. Hibernate có thể phải dùng một dạng SQL khác hoặc chia batch theo khả năng dialect.

Nếu hệ thống dùng composite key, test batch fetching trên **đúng database** thay vì chỉ kiểm tra H2.

### 12.2. Không chọn batch size bằng giới hạn lý thuyết

Nếu mỗi ID gồm nhiều bind parameters, batch size 64 có thể tiêu thụ nhiều tham số hơn dự kiến. Ngoài ra query còn có các parameter khác, tenant filter hoặc soft-delete condition. Hãy xem SQL thực tế và giới hạn DBMS/driver.

## 13. Tương tác với filter, tenant và soft delete

Trong hệ thống đa tenant hoặc dùng Hibernate filters, truy vấn batch phải giữ đúng điều kiện bảo vệ dữ liệu.

Ví dụ SQL có thể chứa thêm điều kiện:

```sql
SELECT d.id, d.name
FROM departments d
WHERE d.id IN (?, ?, ?, ...)
  AND d.tenant_id = ?;
```

Batch fetching chỉ là cách gom truy vấn; nó không được dùng để bỏ qua tenant isolation, soft-delete restriction hoặc filter nghiệp vụ đã được mapping cấu hình.

Những filter/parameter bổ sung có thể ảnh hưởng số bind parameters và SQL plan. Test multi-tenant nên xác nhận batch không trả entity từ tenant khác.

## 14. Lazy collection phải được truy cập khi persistence context còn mở

Batch fetching không loại bỏ yêu cầu lifecycle của lazy loading.

Ví dụ:

```java
List<Department> departments;

try (EntityManager em = emf.createEntityManager()) {
    departments = em.createQuery(
        "select d from Department d",
        Department.class
    ).getResultList();
}

// Persistence context đã đóng.
for (Department department : departments) {
    System.out.println(department.getEmployees().size());
}
```

Nếu collection chưa được khởi tạo trước khi đóng `EntityManager`, truy cập nó có thể gây `LazyInitializationException`.

`@BatchSize` không mở lại session và không tự tải dữ liệu trước khi entity rời context. Cần:

- Fetch dữ liệu cần thiết trong transaction/service.
- Dùng DTO để trả dữ liệu ra ngoài.
- Dùng JOIN FETCH/entity graph khi endpoint biết rõ dữ liệu cần.
- Hoặc chủ động khởi tạo collection trong persistence context nếu đó là yêu cầu use case.

Không dựa vào Open Session In View chỉ để che việc fetch plan chưa rõ ràng.

## 15. Batch fetching không đồng nghĩa batch insert/update

Tên gọi “batch” xuất hiện ở hai cơ chế Hibernate khác nhau.

### 15.1. Batch fetching — đọc theo nhóm

```java
@BatchSize(size = 16)
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
private List<Employee> employees;
```

Mục tiêu: giảm số SELECT khi khởi tạo nhiều proxy/collection lazy.

Cấu hình:

```properties
hibernate.default_batch_fetch_size=16
```

SQL thường có dạng:

```sql
SELECT ...
FROM employees
WHERE department_id IN (?, ?, ...);
```

### 15.2. JDBC batching — ghi theo nhóm

```properties
hibernate.jdbc.batch_size=30
hibernate.order_inserts=true
hibernate.order_updates=true
```

Mục tiêu: gom các INSERT/UPDATE/DELETE tương thích vào JDBC batch để giảm round trip khi ghi.

Ví dụ nhiều câu:

```sql
INSERT INTO employees (...);
INSERT INTO employees (...);
INSERT INTO employees (...);
```

có thể được gửi theo JDBC batch khi mapping, driver và ID generator hỗ trợ.

### 15.3. So sánh nhanh

| Tiêu chí | Batch fetching | JDBC batching |
| --- | --- | --- |
| Công việc | Đọc lazy entities/collections | Ghi DML |
| Annotation thường dùng | `@BatchSize` | Không dùng `@BatchSize` |
| Cấu hình | `hibernate.default_batch_fetch_size` | `hibernate.jdbc.batch_size` |
| SQL điển hình | SELECT với nhiều ID/owner keys | Nhiều INSERT/UPDATE/DELETE cùng batch |
| Vấn đề thường giải quyết | N+1 SELECT | Chi phí round trip khi ghi nhiều rows |
| Thời điểm | Khi lazy proxy/collection được initialize | Khi Hibernate flush DML |
| Có thay đổi fetch type? | Không, vẫn là lazy fetching | Không liên quan fetch type |

Đừng đổi `hibernate.jdbc.batch_size` để mong N+1 SELECT biến mất; cũng đừng dùng `@BatchSize` để mong insert hàng loạt nhanh hơn.

## 16. Batch fetching không tự thay đổi fetch type

Ví dụ:

```java
@OneToMany(fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<Employee> employees;
```

Association vẫn là `LAZY`. Annotation chỉ tối ưu **cách Hibernate tải khi collection được yêu cầu**.

Tương tự:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Department department;
```

Nếu entity type `Department` có batch size, proxy có thể được tải theo nhóm khi ứng dụng cần state.

Không nên đổi `LAZY` thành `EAGER` chỉ để hết N+1. EAGER có thể tải dữ liệu ngoài nhu cầu và tạo query phụ không dễ kiểm soát. Batch fetching giữ quyền trì hoãn tải nhưng giảm số truy vấn khi thật sự cần nhiều association.

## 17. Batch fetching và truy vấn phân trang

Một use case phổ biến là tải một trang department rồi đọc số nhân viên của mỗi department:

```java
List<Department> page = em.createQuery(
        "select d from Department d order by d.id",
        Department.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();

for (Department department : page) {
    System.out.println(department.getEmployees().size());
}
```

Nếu `employees` có `@BatchSize(size=16)`, Hibernate có thể tải collection cho các owner trong page theo nhóm. Đây là một cách tránh JOIN FETCH collection trực tiếp trên query phân trang.

Nhưng lưu ý:

- Mỗi page có persistence context riêng hay dùng chung ảnh hưởng số candidate.
- Nếu collection quá lớn, batch fetch vẫn có thể tải rất nhiều rows.
- Nếu chỉ cần count, có thể dùng DTO/projection query `count` theo nhóm thay vì hydrate toàn bộ Employee entities.
- Nếu endpoint chỉ cần vài field, DTO projection thường tiết kiệm hơn entity graph.
- Không mặc định batch fetching giải quyết pagination cho mọi association hoặc mọi query shape.

## 18. Batch fetching khi một số owner không có phần tử

Giả sử 16 department được gom trong một batch, nhưng chỉ 5 department có employees.

Một query có thể trả các hàng của 5 department đó; 11 collection còn lại được khởi tạo như collection rỗng theo kết quả truy vấn. Hibernate không cần phát thêm một SELECT riêng chỉ để xác nhận từng collection rỗng nếu query batch đã bao phủ các owner keys đó.

Điều này giúp batch fetching vẫn hữu ích khi dữ liệu phân bố không đồng đều. Tuy nhiên, số rows trả về phụ thuộc cardinality; 5 collection có thể chứa 500.000 employees và vẫn tạo kết quả rất lớn.

## 19. Cẩn trọng với collection rất lớn

Nếu một `Department` có hàng triệu employees, batch size 16 không có nghĩa Hibernate chỉ tải 16 employees. Nó có nghĩa tải collection của tối đa 16 owner trong một batch; mỗi collection vẫn có thể chứa rất nhiều phần tử.

Ví dụ:

```java
department.getEmployees().size();
```

có thể cần khởi tạo toàn bộ collection theo mapping. Với collection cực lớn, nên cân nhắc:

- Query phân trang trực tiếp `Employee` theo `departmentId`.
- DTO projection chỉ lấy các cột cần.
- Query `COUNT(*)` nếu chỉ cần số lượng.
- Keyset pagination hoặc streaming phù hợp.
- Không trả collection entity khổng lồ qua API.

`@BatchSize` giảm round trips, **không biến một collection lớn thành dữ liệu nhỏ**.

## 20. Tác động của persistence context và thứ tự truy cập

Batch fetching tận dụng các proxy/collection đang chờ trong cùng persistence context. Vì vậy hành vi phụ thuộc việc các candidate được tạo ra như thế nào và ứng dụng truy cập chúng ra sao.

Ví dụ:

```java
List<Department> departments = ...;

// Chỉ truy cập 3 collection đầu.
for (int i = 0; i < 3; i++) {
    departments.get(i).getEmployees().size();
}
```

Hibernate có thể tải collection của các owner khác cùng batch dù code chưa gọi trực tiếp `getEmployees()` cho từng owner. Điều này là chủ ý: một query lấy cả nhóm để giảm round trip.

Nếu ứng dụng chỉ cần một collection nhưng batch size lớn, một số collection khác có thể được tải sớm hơn dự kiến. Vì vậy batch fetching có trade-off giữa **số lần query** và **dữ liệu tải thừa**.

### 20.1. Persistence context quá ngắn

Nếu mỗi department được tải trong một `EntityManager` riêng rồi truy cập collection, các session không có candidate chung để gom. Batch size 32 không thể gom 32 collection thuộc 32 persistence contexts độc lập thành một query.

### 20.2. Persistence context quá dài

Giữ một session quá lâu có thể làm số managed entity/proxy và collection tăng lớn, khiến batch candidate queue và memory footprint phình ra. Không giữ session lâu chỉ để tạo batch lớn; giới hạn persistence context theo unit of work phù hợp.

## 21. Đo hiệu quả batch fetching

Đừng chỉ nhìn annotation và cho rằng N+1 đã được giải quyết. Cần đo SQL trong use case thật.

### 21.1. Bật Hibernate Statistics trong test

```properties
hibernate.generate_statistics=true
```

Lấy `Statistics` từ `SessionFactory`:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

try (EntityManager em = emf.createEntityManager()) {
    List<Department> departments = em.createQuery(
        "select d from Department d",
        Department.class
    ).getResultList();

    for (Department department : departments) {
        department.getEmployees().size();
    }
}

System.out.println(
    "Prepared statements: " + statistics.getPrepareStatementCount()
);
System.out.println(
    "Collection fetches: " + statistics.getCollectionFetchCount()
);
System.out.println(
    "Entity fetches: " + statistics.getEntityFetchCount()
);
```

Các counter thuộc phạm vi `SessionFactory` và có thể bị ảnh hưởng bởi test khác chạy song song, startup SQL, cache hoặc association fetch ngoài mục tiêu. Nên cô lập test và reset statistics có kiểm soát.

`getPrepareStatementCount()` đếm prepared statements được Hibernate chuẩn bị; nó không chỉ đếm SELECT collection. Nếu cần phân biệt câu SQL, có thể dùng logger `org.hibernate.SQL`, `StatementInspector`, datasource proxy hoặc công cụ tracing JDBC.

### 21.2. Bật SQL logging

Ví dụ cấu hình:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

Hoặc trong Spring Boot:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Chỉ bật trong development/test nếu phù hợp. Bind parameter logging có thể để lộ email, thông tin cá nhân, token hoặc dữ liệu nhạy cảm; không bật tùy tiện ở production.

### 21.3. Đo nhiều chỉ số

Một benchmark tốt nên ghi:

| Chỉ số | Vì sao cần |
| --- | --- |
| Số SELECT | Cho biết số round trips có giảm không |
| Tổng rows trả về | Phát hiện tải thừa |
| Thời gian query và tổng request | Đo lợi ích thực |
| Heap/GC | Batch lớn có thể hydrate nhiều object hơn |
| Lock/transaction duration | Fetch plan có thể kéo dài unit of work |
| Cache hit/miss | Phân biệt lợi ích L1/L2 với batch fetching |
| DB CPU và query plan | IN list lớn có thể đổi chi phí DB |

Ít SELECT hơn không luôn đồng nghĩa endpoint nhanh hơn nếu batch quá lớn và tải nhiều dữ liệu không dùng tới.

## 22. Integration test cho collection batch fetching

Một test cần database và mapping Hibernate thực tế. Giả sử fixture đã seed 20 departments và mỗi department có ít nhất một employee.

```java
@Test
void batchSizeReducesCollectionFetchStatements() {
    SessionFactory sessionFactory =
        emf.unwrap(SessionFactory.class);

    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    try (EntityManager em = emf.createEntityManager()) {
        List<Department> departments = em.createQuery(
            "select d from Department d order by d.id",
            Department.class
        ).getResultList();

        for (Department department : departments) {
            department.getEmployees().size();
        }
    }

    long statements = statistics.getPrepareStatementCount();

    // Không hardcode một số query tuyệt đối cho mọi provider/version.
    assertTrue(statements < 21);
}
```

Đây là **test body minh họa**, cần fixture JUnit tạo `EntityManagerFactory`, seed data và cô lập Statistics. Nếu database có SQL bootstrap hoặc association khác được fetch, assertion cần điều chỉnh. Trong dự án thực, nên đo SELECT cụ thể bằng SQL inspector và so sánh baseline với batch fetching tắt.

### 22.1. Test entity proxy batching

Tạo nhiều employee tham chiếu department, tải employees trong một context, rồi truy cập `getDepartment().getName()`. Đo số entity fetch statements với `@BatchSize` trên `Department`.

Không chỉ assert `employees.size()` vì điều đó không initialize các department proxy. Phải truy cập một thuộc tính cần proxy initialize.

### 22.2. Kiểm thử nhiều collection role

Nếu có cả `Department.employees` và `Project.tasks`, kiểm tra riêng từng role. Batch size trên một role không chứng minh role còn lại được tối ưu.

## 23. Cấu hình đề xuất theo tình huống

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Danh sách entity rồi đọc một to-one lazy cùng loại | `@BatchSize` trên entity đích |
| Danh sách owner rồi truy cập nhiều collection cùng role | `@BatchSize` trên collection |
| Nhiều mapping lazy có pattern tương tự | `hibernate.default_batch_fetch_size` làm baseline |
| Endpoint luôn cần một association nhỏ | `JOIN FETCH` hoặc Entity Graph |
| Endpoint phân trang parent và cần collection của page | Batch fetching hoặc query thứ hai theo IDs |
| Cần tất cả collection của tập owner lấy từ một query | Đánh giá `FetchMode.SUBSELECT` |
| Chỉ cần count/summary | DTO hoặc aggregate query |
| Collection cực lớn | Query child riêng có pagination |
| Chỉ ghi nhiều entity | JDBC batching, không phải `@BatchSize` |

Không có chiến lược fetch duy nhất tốt cho mọi use case. Một ứng dụng có thể dùng global default vừa phải, `@BatchSize` cho vài role hay gây N+1, và query-specific fetch join/DTO cho endpoint cần dữ liệu cố định.

## 24. Những hiểu lầm thường gặp

### “`@BatchSize` làm association thành EAGER”

Sai. Nó tối ưu việc tải những proxy/collection lazy khi chúng được truy cập; association vẫn có thể là LAZY.

### “Batch size 16 có nghĩa Hibernate luôn tải đúng 16 entity”

Sai. Đây là giới hạn nhóm tối đa theo mapping/điều kiện tải. Số candidate thực tế có thể ít hơn do cache, proxy đã khởi tạo hoặc batch cuối.

### “`@BatchSize` trên Department sẽ gom collection employees”

Không tự động. Annotation trên entity class cấu hình batch fetching entity proxy `Department`; muốn gom collection `Department.employees`, đặt annotation trên collection role hoặc dùng default global phù hợp.

### “Một batch là một JOIN FETCH”

Sai. Batch fetching thường phát SELECT bổ sung với nhiều ID/owner keys; JOIN FETCH đưa association vào query gốc.

### “`hibernate.jdbc.batch_size` giảm N+1 SELECT”

Sai. Đó là cấu hình JDBC batching cho DML ghi. Batch fetching dùng `@BatchSize` hoặc `hibernate.default_batch_fetch_size`.

### “Chỉ cần bật L2 cache là không còn N+1”

Không. L2 cache có thể giảm database hits cho entity/collection cacheable, nhưng không tự giải quyết mọi query và fetch plan.

### “Giữ session mở càng lâu thì batch fetching càng hiệu quả”

Không. Persistence context quá dài có thể tích lũy object và dữ liệu stale. Cần scope hợp lý.

### “Batch size càng lớn càng nhanh”

Không. Có thể tải thừa, tăng bind parameters, heap và thời gian xử lý kết quả.

### “Batch fetching giảm số rows database phải trả”

Không nhất thiết. Nó chủ yếu giảm số truy vấn/round trips; tổng rows phụ thuộc dữ liệu ứng dụng cần tải.

### “Một collection rất lớn sẽ được chia thành nhiều page nhờ batch size”

Không. Batch size là số collection owner keys trong nhóm, không phải số phần tử bên trong từng collection.

### “Không thấy N+1 trong unit test thì production không có”

Không. Dữ liệu production có cardinality, cache, session scope và truy cập association khác. Cần đo trên workload đại diện.

## 25. Quy trình chọn và triển khai batch size

Một quy trình thực tế:

1. **Xác định N+1:** log SQL cho thấy một query gốc và nhiều SELECT cùng dạng theo từng ID/owner key.
2. **Xác định loại candidate:** entity proxy hay collection role.
3. **Chọn scope cấu hình:** annotation trên entity/collection hay global default.
4. **Giữ lazy loading:** không đổi association thành EAGER chỉ để giảm query count.
5. **Chọn batch size ban đầu:** dùng giá trị vừa phải, ví dụ 16.
6. **Chạy với dữ liệu đại diện:** gồm nhiều owner, collection rỗng, collection nhỏ và lớn.
7. **Đo SQL và rows:** so baseline, query count, latency, heap và DB load.
8. **Điều chỉnh:** thử 8/16/32 hoặc giá trị phù hợp với giới hạn DB.
9. **Kiểm tra mọi fetch path:** L2 cache, entity graph, fetch join, filter, tenant và pagination.
10. **Ghi lại lý do:** annotation/global setting cần có rationale để tránh tăng batch size không kiểm soát trong tương lai.

## 26. Bài tập tình huống

### Bài 1 — N+1 collection

Có 40 department. Tải danh sách một lần rồi gọi `getEmployees().size()` trên mỗi department. Nếu không batch fetching, số SELECT có thể là bao nhiêu?

**Đáp án:** Có thể là 41: một SELECT department và 40 SELECT collection, nếu tất cả collection ban đầu chưa initialized và không có cache/fetch optimization.

### Bài 2 — Đặt annotation ở đâu?

Muốn batch các proxy `Department` được tham chiếu bởi nhiều `Employee`. Đặt `@BatchSize` ở đâu?

**Đáp án:** Trên entity class `Department`, vì đây là entity type cần gom proxy.

### Bài 3 — Batch collection

Muốn gom collection `Department.employees` của nhiều department. Đặt annotation ở đâu?

**Đáp án:** Trên field/property collection `employees` hoặc cấu hình global `hibernate.default_batch_fetch_size`.

### Bài 4 — Batch size 32

Có 10 collection đủ điều kiện và cấu hình size 32. Hibernate có bắt buộc tải 32 không?

**Đáp án:** Không. Nó chỉ có tối đa 10 candidate đủ điều kiện; batch size là giới hạn, không phải số phần tử bắt buộc.

### Bài 5 — JDBC batch

Ứng dụng insert 1.000 employee và muốn gom INSERT. Có nên dùng `@BatchSize`?

**Đáp án:** Không. Dùng JDBC batching qua `hibernate.jdbc.batch_size` và đánh giá ID generator/driver. `@BatchSize` phục vụ lazy read fetching.

### Bài 6 — Collection rất lớn

Một department có 500.000 employees. `@BatchSize(size=16)` có làm mỗi lần tải chỉ lấy 16 employee không?

**Đáp án:** Không. Nó có thể tải collection của tối đa 16 department owner; mỗi collection vẫn có thể chứa hàng trăm nghìn employee. Dùng query phân trang/count/projection nếu cần.

### Bài 7 — EntityManager đóng

Đã query department, đóng EntityManager rồi mới truy cập employees. Batch size có khởi tạo collection được không?

**Đáp án:** Không. Lazy collection cần persistence context phù hợp; sau khi context đóng, truy cập chưa initialized thường gây `LazyInitializationException`.

### Bài 8 — JOIN FETCH và batch size

Một endpoint luôn cần employees của 5 department. Có nên luôn dùng batch size thay JOIN FETCH?

**Đáp án:** Không có đáp án chung. JOIN FETCH có thể chỉ cần một query cho tập nhỏ; batch fetching giữ lazy loading và có ích khi truy cập một phần/nhiều owner. Đo SQL và xét pagination/cardinality.

### Bài 9 — Global default

Đặt `hibernate.default_batch_fetch_size=32`. Điều này có nghĩa mọi association được tải ngay khi query entity gốc không?

**Đáp án:** Không. Đây là default cho batch fetching lazy; proxy/collection vẫn được khởi tạo khi ứng dụng cần, theo nhóm đủ điều kiện.

### Bài 10 — Vì sao query count không đúng công thức?

Có 100 collection, batch size 16 nhưng chỉ thấy 4 SELECT thay vì 7. Có thể vì sao?

**Đáp án:** Một số collection có thể đã initialized, cache đáp ứng dữ liệu, số owner thực tế cần tải ít hơn 100 hoặc một số collection không được truy cập. Công thức ceil chỉ là ước lượng.

## 27. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Batch fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/#fetching-batch): `@BatchSize`, batch fetching entity/collection và cơ chế gom lazy fetch.
- [Hibernate ORM Javadoc — `@BatchSize`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/annotations/BatchSize.html): vị trí annotation, thuộc tính `size` và phạm vi batch.
- [Hibernate ORM User Guide — Fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/#fetching): lazy/eager fetching, SELECT, JOIN, subselect và N+1.
- [Hibernate ORM User Guide — Batch processing](https://docs.hibernate.org/stable/orm/userguide/html_single/#batch): JDBC batching và các cấu hình ghi theo nhóm; phân biệt với batch fetching.
- [Hibernate ORM Javadoc — `FetchSettings`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/cfg/FetchSettings.html): các setting liên quan fetch, gồm default batch fetch size.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): fetch type, entity graph, query và persistence context ở cấp chuẩn.
- [Jakarta Persistence 3.2 — `FetchType`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/FetchType.html): ý nghĩa LAZY và EAGER trong mapping chuẩn.

`@BatchSize` và `hibernate.default_batch_fetch_size` là tính năng/cấu hình Hibernate, không phải annotation chuẩn Jakarta Persistence. Hãy dùng User Guide/Javadoc của đúng Hibernate version đang triển khai và kiểm tra SQL trên DBMS/driver thực tế.

## Kết luận

`@BatchSize` giúp Hibernate **gom nhiều lazy entity proxy hoặc collection cùng loại/role vào một lần tải**, thường bằng SELECT với nhiều khóa trong điều kiện `IN`. Đặt annotation trên entity class để batch proxy của entity đó; đặt trên collection để batch collection role tương ứng. Có thể dùng `hibernate.default_batch_fetch_size` làm giá trị mặc định toàn cục, rồi tinh chỉnh riêng các mapping có workload khác biệt.

Batch fetching giảm round trips và thường giảm đáng kể N+1 SELECT, nhưng không biến association thành EAGER, không tự thay JOIN FETCH, không giới hạn số phần tử bên trong collection và không phải JDBC batching cho INSERT/UPDATE/DELETE. Kích thước phù hợp phụ thuộc số candidate lazy, cardinality, bind parameter limits, cache, bộ nhớ và DBMS. Hãy bắt đầu với một giá trị vừa phải, đo SQL/rows/latency trên use case thật rồi điều chỉnh.
