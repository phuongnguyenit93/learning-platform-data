# Constructor expression để trả về DTO trong JPQL và Spring Data JPA

JPQL constructor expression cho phép truy vấn tạo trực tiếp một đối tượng DTO từ các giá trị lấy trong database. Thay vì tải toàn bộ entity rồi chuyển từng trường sang DTO trong Java, câu truy vấn chọn đúng các thuộc tính cần thiết và gọi constructor của lớp kết quả.

Cú pháp trung tâm là `SELECT NEW ten.package.Dto(arg1, arg2, ...)`. Tên lớp phải là tên đầy đủ gồm package; thứ tự và kiểu của các đối số phải khớp với constructor. Cách này phù hợp với màn hình danh sách, báo cáo, API chỉ đọc và truy vấn tổng hợp.

## 1. Constructor expression là gì?

Một truy vấn JPQL thông thường có thể trả về entity:

~~~java
select e
from Employee e
where e.active = true
~~~

Kết quả là các entity `Employee` được JPA quản lý trong persistence context. Nếu màn hình chỉ cần ID, tên nhân viên và tên phòng ban, tải toàn bộ entity có thể lấy nhiều dữ liệu hơn mức cần thiết.

Constructor expression tạo DTO ngay trong kết quả truy vấn:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name
)
from Employee e
join e.department d
where e.active = true
~~~

Mỗi hàng kết quả sẽ được chuyển thành một đối tượng `EmployeeSummary`. Provider lấy giá trị các biểu thức trong SELECT rồi gọi constructor tương ứng.

Lợi ích chính:

- Chỉ chọn các cột cần cho use case.
- Tránh trả entity hoặc proxy trực tiếp ra API.
- Không cần lặp lại thao tác ánh xạ thủ công trong service.
- Có thể kết hợp join, điều kiện lọc, biểu thức và aggregate.
- DTO kết quả phù hợp với truy vấn chỉ đọc và báo cáo.

Constructor expression là cú pháp JPQL. Nó không phải cú pháp SQL thuần; tên entity và thuộc tính trong query là tên Java được ánh xạ, không nhất thiết là tên bảng/cột vật lý.

## 2. Cú pháp và các quy tắc bắt buộc

Dạng tổng quát:

~~~sql
SELECT NEW fully.qualified.DtoClass(expression1, expression2, ...)
FROM EntityName alias
...
~~~

Các quy tắc cần nhớ:

1. Từ khóa `NEW` phải có trước tên lớp DTO.
2. Tên lớp phải là fully qualified class name, ví dụ `com.example.report.EmployeeSummary`.
3. Thứ tự đối số trong constructor expression phải khớp thứ tự tham số constructor.
4. Kiểu Java của mỗi biểu thức phải tương thích với kiểu tham số tương ứng.
5. DTO cần constructor phù hợp; ví dụ dưới dùng public constructor để dễ tương thích.
6. Không đặt alias kiểu `e.name AS employeeName` bên trong danh sách đối số của constructor expression. Tên biến tham số trong DTO do constructor quyết định.
7. JPQL dùng entity name và thuộc tính Java, ví dụ `Employee e`, `e.name`, `e.department`; không dùng trực tiếp tên bảng/cột SQL như `employees` hay `employee_name` trừ khi đó chính là tên entity/attribute được ánh xạ.
8. Cú pháp `NEW` phải trỏ đến lớp có thể được provider khởi tạo bằng constructor tương ứng.

Ví dụ đúng:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name,
    e.salary
)
from Employee e
join e.department d
~~~

Ví dụ sai nếu DTO không có constructor theo đúng thứ tự và kiểu:

~~~java
select new com.example.report.EmployeeSummary(
    e.name,
    e.id,
    e.salary,
    d.name
)
from Employee e
join e.department d
~~~

Tên tham số trong Java không cần giống tên thuộc tính entity. Điều quyết định là thứ tự và kiểu của giá trị truyền vào constructor.

## 3. Ví dụ đầy đủ: trả DTO nhân viên và phòng ban

Giả sử mô hình có hai entity:

- `Employee`: `id` kiểu `Long`, `name` kiểu `String`, `salary` kiểu `BigDecimal` và quan hệ `department`.
- `Department`: `id` kiểu `Long` và `name` kiểu `String`.

Quan hệ từ nhân viên đến phòng ban là `@ManyToOne`. Ta cần một DTO hiển thị thông tin nhân viên mà không trả toàn bộ entity.

### 3.1. Tạo DTO

Tạo file `src/main/java/com/example/report/EmployeeSummary.java`:

~~~java
package com.example.report;

import java.math.BigDecimal;

public class EmployeeSummary {

    private final Long employeeId;
    private final String employeeName;
    private final String departmentName;
    private final BigDecimal salary;

    public EmployeeSummary(
            Long employeeId,
            String employeeName,
            String departmentName,
            BigDecimal salary) {
        this.employeeId = employeeId;
        this.employeeName = employeeName;
        this.departmentName = departmentName;
        this.salary = salary;
    }

    public Long getEmployeeId() {
        return employeeId;
    }

    public String getEmployeeName() {
        return employeeName;
    }

    public String getDepartmentName() {
        return departmentName;
    }

    public BigDecimal getSalary() {
        return salary;
    }
}
~~~

DTO chỉ chứa dữ liệu mà use case cần. Nó không cần annotation `@Entity`, `@Table` hoặc `@Id` vì không đại diện cho một entity được lưu trong database.

Các trường được khai báo `final` để thể hiện đối tượng kết quả không thay đổi sau khi tạo. Constructor nhận bốn giá trị theo đúng thứ tự mà JPQL sẽ truyền vào.

### 3.2. Khai báo repository với @Query

Tạo hoặc bổ sung phương thức trong `EmployeeRepository.java`:

~~~java
package com.example.repository;

import com.example.report.EmployeeSummary;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select new com.example.report.EmployeeSummary(
               e.id,
               e.name,
               d.name,
               e.salary
           )
           from Employee e
           join e.department d
           where d.id = :departmentId
             and e.active = true
           order by e.name
           """)
    List<EmployeeSummary> findActiveSummariesByDepartment(
            @Param("departmentId") Long departmentId);
}
~~~

Đoạn code giả định entity `Employee` có các thuộc tính `id`, `name`, `salary`, `active` và `department`; entity `Department` có `id` và `name`.

Giải thích truy vấn:

- `e.id` truyền vào tham số thứ nhất kiểu `Long`.
- `e.name` truyền vào tham số thứ hai kiểu `String`.
- `d.name` truyền vào tham số thứ ba kiểu `String`.
- `e.salary` truyền vào tham số thứ tư kiểu `BigDecimal`.
- `join e.department d` nối quan hệ được khai báo trong entity.
- `:departmentId` là named parameter được gắn với `@Param`.
- `order by e.name` sắp xếp theo thuộc tính entity.

Khi gọi:

~~~java
List<EmployeeSummary> summaries =
        employeeRepository.findActiveSummariesByDepartment(5L);
~~~

Spring Data JPA thực thi JPQL, provider tạo từng đối tượng `EmployeeSummary` và trả danh sách DTO cho caller.

### 3.3. Vì sao phải ghi tên lớp đầy đủ?

Trong JPQL, tên lớp ở constructor expression được phân giải như tên lớp Java. Query không tự suy ra package từ repository hoặc DTO import.

Nếu DTO có package:

~~~java
package com.example.report;
~~~

thì query phải dùng:

~~~java
select new com.example.report.EmployeeSummary(...)
~~~

Không thể chỉ viết `new EmployeeSummary(...)` rồi kỳ vọng JPQL tự dùng import của file repository. Import Java chỉ có tác dụng trong mã Java, không áp dụng cho chuỗi JPQL.

## 4. Kiểu dữ liệu của constructor và biểu thức JPQL

Một lỗi thường gặp là constructor có tên lớp đúng nhưng kiểu tham số không khớp với kiểu biểu thức trong SELECT.

Ví dụ entity:

~~~java
@Id
private Long id;

@Column(nullable = false)
private BigDecimal salary;

private String name;
~~~

Constructor DTO cần tương thích:

~~~java
public EmployeeSummary(
        Long id,
        String name,
        BigDecimal salary) {
    // ...
}
~~~

Không nên đổi `Long` thành `Integer` hoặc `BigDecimal` thành `Double` chỉ vì dữ liệu mẫu trông có vẻ phù hợp. Provider xác định kiểu biểu thức dựa trên mapping và quy tắc JPQL, không dựa trên giá trị tình cờ của một hàng.

### 4.1. Kiểu kết quả aggregate

Một số hàm tổng hợp có kiểu trả về được quy định:

| Biểu thức JPQL | Kiểu kết quả thường theo đặc tả |
|---|---|
| `COUNT(...)` | `Long` |
| `AVG(...)` | `Double` |
| `SUM(...)` với kiểu số nguyên | `Long` |
| `SUM(...)` với `BigInteger` | `BigInteger` |
| `SUM(...)` với `BigDecimal` | `BigDecimal` |
| `MIN(...)` / `MAX(...)` | Kiểu của biểu thức đầu vào |

Khi dùng aggregate trong constructor expression, hãy khai báo constructor theo kiểu kết quả của hàm, không chỉ theo kiểu trường entity.

Ví dụ `COUNT(e)` trả về `Long`:

~~~java
public DepartmentStats(
        Long departmentId,
        String departmentName,
        Long employeeCount) {
    // ...
}
~~~

Nếu constructor nhận `Integer employeeCount`, provider có thể không tìm được constructor phù hợp.

### 4.2. Giá trị null và LEFT JOIN

Với `LEFT JOIN`, thuộc tính của phía không có bản ghi có thể là `null`. Constructor DTO phải chấp nhận giá trị null nếu query cho phép điều đó.

Ví dụ:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name,
    e.salary
)
from Employee e
left join e.department d
~~~

Nếu nhân viên chưa được gán phòng ban, `d.name` có thể null. Trường `departmentName` trong DTO phải cho phép null hoặc query phải dùng `COALESCE` để cung cấp giá trị thay thế:

~~~java
coalesce(d.name, 'Chưa phân loại')
~~~

Không dùng kiểu primitive như `long` hoặc `double` cho tham số có thể nhận null. Dùng wrapper `Long`, `Double` hoặc kiểu tham chiếu phù hợp.

### 4.3. BigDecimal và giá trị tiền

Nếu entity dùng `BigDecimal` cho tiền lương, DTO cũng nên nhận `BigDecimal`. Không chuyển sang `double` chỉ để hiển thị vì có thể phát sinh sai số dấu phẩy động.

Khi so sánh trong test, dùng `isEqualByComparingTo` hoặc `compareTo` để tránh nhầm khác biệt về scale, ví dụ `100.0` và `100.00`.

## 5. Constructor expression với GROUP BY và hàm tổng hợp

DTO rất phù hợp với báo cáo tổng hợp. Ví dụ cần số nhân viên và tổng lương theo từng phòng ban.

### 5.1. DTO DepartmentPayroll

Tạo `DepartmentPayroll.java`:

~~~java
package com.example.report;

import java.math.BigDecimal;

public class DepartmentPayroll {

    private final Long departmentId;
    private final String departmentName;
    private final Long employeeCount;
    private final BigDecimal totalSalary;

    public DepartmentPayroll(
            Long departmentId,
            String departmentName,
            Long employeeCount,
            BigDecimal totalSalary) {
        this.departmentId = departmentId;
        this.departmentName = departmentName;
        this.employeeCount = employeeCount;
        this.totalSalary = totalSalary;
    }

    public Long getDepartmentId() {
        return departmentId;
    }

    public String getDepartmentName() {
        return departmentName;
    }

    public Long getEmployeeCount() {
        return employeeCount;
    }

    public BigDecimal getTotalSalary() {
        return totalSalary;
    }
}
~~~

### 5.2. JPQL aggregate query

Giả sử `Department` có collection `employees` được ánh xạ bằng `@OneToMany(mappedBy = "department")`:

~~~java
@Query("""
       select new com.example.report.DepartmentPayroll(
           d.id,
           d.name,
           count(e),
           sum(e.salary)
       )
       from Department d
       left join d.employees e
       group by d.id, d.name
       order by d.name
       """)
List<DepartmentPayroll> summarizePayroll();
~~~

Truy vấn:

- Bắt đầu từ `Department` để vẫn lấy phòng ban chưa có nhân viên.
- Dùng `LEFT JOIN` để giữ phòng ban không có nhân viên.
- `count(e)` đếm số nhân viên; với phòng ban rỗng, kết quả là 0.
- `sum(e.salary)` cộng lương; với nhóm không có giá trị, kết quả có thể là null.
- `group by d.id, d.name` tạo một nhóm cho mỗi phòng ban.
- `order by d.name` sắp xếp kết quả.

Vì `totalSalary` có thể null với phòng ban chưa có nhân viên, DTO cần chấp nhận null hoặc chuẩn hóa trong constructor:

~~~java
this.totalSalary = totalSalary == null
        ? BigDecimal.ZERO
        : totalSalary;
~~~

Không thay kiểu tham số constructor thành `Double` khi biểu thức `SUM` nhận `BigDecimal`.

### 5.3. HAVING để lọc nhóm

Có thể lọc các phòng ban có ít nhất một số nhân viên nhất định:

~~~java
@Query("""
       select new com.example.report.DepartmentPayroll(
           d.id,
           d.name,
           count(e),
           sum(e.salary)
       )
       from Department d
       left join d.employees e
       group by d.id, d.name
       having count(e) >= :minimumEmployees
       """)
List<DepartmentPayroll> summarizePayroll(
        @Param("minimumEmployees") long minimumEmployees);
~~~

`WHERE` lọc các hàng trước khi nhóm; `HAVING` lọc các nhóm sau `GROUP BY`. Khi dùng aggregate trong điều kiện nhóm, thường đặt điều kiện ở `HAVING`.

## 6. Phân trang kết quả DTO

Spring Data JPA có thể trả `Page<DTO>` cho constructor expression. Ví dụ:

~~~java
@Query(
    value = """
            select new com.example.report.EmployeeSummary(
                e.id,
                e.name,
                d.name,
                e.salary
            )
            from Employee e
            join e.department d
            where d.id = :departmentId
            """,
    countQuery = """
                 select count(e)
                 from Employee e
                 join e.department d
                 where d.id = :departmentId
                 """
)
Page<EmployeeSummary> findSummaries(
        @Param("departmentId") Long departmentId,
        Pageable pageable);
~~~

`value` là truy vấn lấy nội dung trang. `countQuery` đếm tổng số entity phù hợp để tạo metadata của `Page`.

Các điểm cần chú ý:

- Query đếm phải giữ cùng điều kiện lọc với query nội dung.
- Nếu query nội dung có join làm nhân bản entity, cân nhắc `count(distinct e.id)` và `select distinct new ...` theo đúng ngữ nghĩa.
- Với query có `GROUP BY`, truy vấn count có thể phức tạp hơn; cần viết count query riêng và kiểm thử kết quả tổng số nhóm.
- Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, cân nhắc `Slice<DTO>` để tránh yêu cầu tổng số kết quả.
- `Pageable` giới hạn và sắp xếp kết quả; hãy kiểm tra SQL do provider sinh ra với query thực tế.

Ví dụ gọi:

~~~java
Page<EmployeeSummary> page =
        employeeRepository.findSummaries(
                5L,
                PageRequest.of(0, 20)
        );

List<EmployeeSummary> content = page.getContent();
long total = page.getTotalElements();
int pages = page.getTotalPages();
~~~

## 7. So sánh constructor expression với các kiểu projection khác

Spring Data JPA hỗ trợ nhiều cách trả dữ liệu. Chọn cách phù hợp với độ phức tạp và mục đích của query.

| Cách | Khai báo | Điểm phù hợp |
|---|---|---|
| Entity result | `select e from Employee e` | Cần entity managed để thực hiện nghiệp vụ hoặc cập nhật |
| Constructor expression | `select new package.Dto(...)` | Muốn DTO rõ ràng, nhiều trường hoặc kết quả tổng hợp |
| Interface projection | Interface getter và alias trong SELECT | DTO đọc đơn giản, muốn Spring Data ánh xạ theo tên thuộc tính |
| Native query mapping | SQL thuần kết hợp result set mapping hoặc cơ chế projection phù hợp | Cần SQL đặc thù database |

Ví dụ interface projection:

~~~java
public interface EmployeeNameView {
    Long getEmployeeId();
    String getEmployeeName();
}
~~~

~~~java
@Query("""
       select e.id as employeeId,
              e.name as employeeName
       from Employee e
       where e.active = true
       """)
List<EmployeeNameView> findActiveNames();
~~~

Với interface projection, alias trong SELECT cần khớp tên getter theo quy tắc ánh xạ của Spring Data. Với constructor expression, thứ tự và kiểu đối số quyết định constructor được gọi; alias không thay thế thứ tự tham số.

Constructor expression thường dễ kiểm soát hơn khi DTO có constructor rõ ràng hoặc khi query chứa aggregate. Interface projection có thể gọn hơn với các kết quả phẳng và ít trường.

## 8. Những giới hạn và lỗi thường gặp

### 8.1. Quên fully qualified class name

Sai:

~~~java
select new EmployeeSummary(e.id, e.name)
from Employee e
~~~

Đúng:

~~~java
select new com.example.report.EmployeeSummary(e.id, e.name)
from Employee e
~~~

JPQL không sử dụng import của repository để tìm lớp DTO.

### 8.2. Constructor không khớp thứ tự hoặc kiểu

Nếu query truyền `(Long, String, BigDecimal)` thì DTO phải có constructor nhận các kiểu tương ứng theo đúng thứ tự. Kiểm tra cả kiểu trả về của aggregate và kiểu nullable.

### 8.3. DTO thiếu constructor phù hợp

Một DTO chỉ có constructor mặc định hoặc chỉ có setter không đủ cho constructor expression đang truyền đối số. Tạo constructor công khai với đúng signature.

Nếu dùng Lombok, annotation sinh constructor phải tạo đúng thứ tự và kiểu tham số mà query yêu cầu. Không dựa vào việc IDE hiển thị constructor nếu build thực tế không sinh constructor đó.

### 8.4. Dùng alias bên trong constructor expression

Không viết:

~~~java
select new com.example.report.EmployeeSummary(
    e.id as employeeId,
    e.name as employeeName
)
from Employee e
~~~

Hãy bỏ alias:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name
)
from Employee e
~~~

Alias phù hợp với interface projection hoặc các biểu thức SELECT thông thường. Constructor expression truyền giá trị theo vị trí.

### 8.5. Nhầm tên entity với tên bảng

Nếu entity được khai báo `@Entity(name = "Employee")`, JPQL dùng `Employee`. Tên bảng vật lý có thể là `employees` nhưng không dùng thay cho entity name trong JPQL.

Tương tự, `e.department.name` là đường dẫn thuộc tính Java. Nếu cột vật lý là `department_name`, query vẫn dùng thuộc tính được ánh xạ trong entity.

### 8.6. Dùng constructor expression trong native SQL

Cú pháp `SELECT NEW` là JPQL, không phải SQL. Với native query, dùng result set mapping như `@SqlResultSetMapping`/`@ConstructorResult` hoặc cơ chế projection được Spring Data hỗ trợ cho kiểu kết quả đó.

### 8.7. LEFT JOIN trả null

Khi quan hệ tùy chọn, trường từ phía phải có thể null. DTO phải dùng kiểu tham chiếu và xử lý null phù hợp. Với aggregate, `SUM` có thể trả null trong nhóm không có giá trị.

### 8.8. Dùng fetch join không cần thiết

Constructor expression chỉ lấy giá trị để tạo DTO. Nếu đã chọn `d.name` hoặc `e.salary` trong SELECT, không cần `JOIN FETCH` để tải entity graph. Dùng join thông thường để kết hợp và lọc dữ liệu.

### 8.9. Nhầm DTO với entity managed

DTO được tạo bằng constructor expression là object kết quả của truy vấn, không được persistence context quản lý như entity `Employee`. Thay đổi DTO không làm database tự cập nhật. Muốn ghi dữ liệu, tải entity managed trong transaction và cập nhật entity đó.

### 8.10. Query trả về nhiều hàng nhưng method khai báo Optional

Nếu query có thể trả nhiều kết quả, khai báo `List<DTO>` hoặc `Page<DTO>`. Chỉ dùng `Optional<DTO>` khi điều kiện query bảo đảm tối đa một hàng, chẳng hạn lọc theo khóa duy nhất. Nếu query trả nhiều hàng cho method đơn, provider có thể báo lỗi non-unique result.

## 9. Kiểm thử constructor expression

Một kiểm thử repository nên xác nhận cả dữ liệu trả về lẫn việc constructor được gọi với đúng trường.

Ví dụ minh họa với `@DataJpaTest`:

~~~java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EmployeeRepository employees;

    @Test
    void returnsEmployeeSummaryDto() {
        Department department = new Department("Engineering");
        entityManager.persist(department);

        Employee employee = new Employee(
                "An",
                new BigDecimal("1250.00"),
                true,
                department
        );
        entityManager.persist(employee);
        entityManager.flush();
        entityManager.clear();

        List<EmployeeSummary> result =
                employees.findActiveSummariesByDepartment(
                        department.getId());

        assertThat(result).hasSize(1);

        EmployeeSummary summary = result.get(0);
        assertThat(summary.getEmployeeId()).isEqualTo(employee.getId());
        assertThat(summary.getEmployeeName()).isEqualTo("An");
        assertThat(summary.getDepartmentName()).isEqualTo("Engineering");
        assertThat(summary.getSalary())
                .isEqualByComparingTo("1250.00");
    }
}
~~~

Đoạn test giả định entity `Department` có constructor nhận tên và entity `Employee` có constructor nhận tên, lương, trạng thái và phòng ban. Hãy điều chỉnh constructor theo mô hình entity của dự án.

`flush()` gửi dữ liệu setup xuống database trước khi truy vấn; `clear()` xóa persistence context để test không vô tình dùng entity instance còn được quản lý. Query DTO sau đó được thực thi như một truy vấn database bình thường.

Khi kiểm thử aggregate, nên thêm trường hợp nhóm rỗng nếu query dùng LEFT JOIN và xác nhận cách DTO xử lý `SUM` null. Với phân trang, kiểm tra cả `getContent()`, `getTotalElements()` và điều kiện count query.

## 10. Khi nào nên dùng constructor expression?

Nên dùng khi:

- Kết quả chỉ phục vụ đọc và không cần cập nhật entity.
- API hoặc màn hình chỉ cần một tập trường cụ thể.
- Cần kết hợp dữ liệu từ nhiều entity.
- Cần trả báo cáo có `COUNT`, `SUM`, `AVG` hoặc nhóm dữ liệu.
- Muốn đặt logic đóng gói dữ liệu vào một DTO có constructor rõ ràng.
- Muốn tránh trả entity/proxy ra khỏi tầng service.

Cân nhắc entity result khi cần thay đổi entity managed trong transaction. Cân nhắc interface projection khi kết quả phẳng và ít trường. Với native SQL hoặc truy vấn đặc thù database, chọn result set mapping hoặc projection phù hợp.

## 11. Checklist trước khi chạy query

- [ ] DTO có package rõ ràng và query dùng tên lớp đầy đủ.
- [ ] DTO có constructor phù hợp với số lượng đối số.
- [ ] Thứ tự tham số constructor khớp thứ tự biểu thức trong SELECT.
- [ ] Kiểu Java tương thích với kiểu biểu thức JPQL và aggregate.
- [ ] Đã xử lý giá trị null từ LEFT JOIN hoặc SUM.
- [ ] Dùng tên entity và thuộc tính Java trong JPQL.
- [ ] Không đặt alias bên trong danh sách đối số của constructor expression.
- [ ] Không dùng SELECT NEW trong native SQL.
- [ ] Chọn List, Optional, Page hoặc Slice đúng với số lượng kết quả.
- [ ] Có countQuery đúng nếu dùng Page và query phức tạp.
- [ ] Test repository xác nhận nội dung DTO và các trường hợp biên.

## 12. Tài liệu tham khảo

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — ngữ pháp JPQL, constructor expression, aggregate và kiểu kết quả.
- [Spring Data JPA Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/) — khai báo query, DTO projection, interface projection và phân trang.
- [Spring Data JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — sử dụng `@Query` và truy vấn khai báo.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — thực thi JPQL/HQL và projection.

Constructor expression giúp JPQL trả về đúng hình dạng dữ liệu mà caller cần. Hãy giữ DTO độc lập với entity, dùng tên lớp đầy đủ, bảo đảm thứ tự và kiểu constructor khớp với SELECT, rồi kiểm thử cả null, aggregate và phân trang. Khi làm đúng các quy tắc này, repository có thể cung cấp kết quả đọc rõ ràng mà không cần tải entity graph lớn hoặc viết bước ánh xạ thủ công sau truy vấn.
