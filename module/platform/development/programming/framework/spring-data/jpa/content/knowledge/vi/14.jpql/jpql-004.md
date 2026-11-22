# INNER JOIN, LEFT JOIN và điều kiện ON

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách JPQL nối entity thông qua association đã được mapping.
- Phân biệt kết quả của `INNER JOIN` và `LEFT JOIN`.
- Dùng `ON` để đặt điều kiện ngay trong phép nối và hiểu khác biệt với `WHERE`.
- Dự đoán khi nào một bản ghi phía trái được giữ lại dù không có bản ghi phía phải phù hợp.
- Xử lý kết quả trùng do join collection bằng `DISTINCT` hoặc projection phù hợp.
- Phân biệt join để lọc/truy vấn với `JOIN FETCH` dùng để tải association.
- Viết repository query và integration test xác nhận semantics của phép nối.

## 1. JOIN trong JPQL là gì?

JPQL truy vấn trên entity và thuộc tính Java, không truy vấn trực tiếp trên tên bảng và cột SQL. Khi một entity có association như `@ManyToOne`, `@OneToMany`, `@OneToOne` hoặc `@ManyToMany`, JPQL có thể nối qua đường dẫn association đó.

Ví dụ domain:

- Một Department có nhiều Employee.
- Mỗi Employee thuộc về một Department.
- Department có thuộc tính `enabled`.
- Employee có thuộc tính `active`.

Trong Java, quan hệ có thể được ánh xạ như sau:

~~~java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean enabled;

    @OneToMany(mappedBy = "department", cascade = CascadeType.PERSIST)
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name, boolean enabled) {
        this.name = name;
        this.enabled = enabled;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }

    public Long getId() {
        return id;
    }
}
~~~

~~~java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Employee() {
    }

    public Employee(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    void setDepartment(Department department) {
        this.department = department;
    }
}
~~~

Trong mapping này, `Employee.department` là owning side và chứa foreign key `department_id`. `Department.employees` là inverse side với `mappedBy = "department"`.

Một JPQL join đi qua tên thuộc tính Java:

~~~jpql
select d
from Department d
join d.employees e
~~~

- `Department` là entity name.
- `d` là identification variable (alias) của Department.
- `d.employees` là association path.
- `e` là alias cho mỗi Employee được nối.

Tên bảng `departments` và tên cột `department_id` không xuất hiện trong JPQL. Provider dựa vào mapping để sinh SQL phù hợp.

## 2. INNER JOIN

`INNER JOIN` chỉ trả về những dòng có bản ghi phù hợp ở cả hai phía.

~~~jpql
select d, e
from Department d
inner join d.employees e
~~~

Câu truy vấn trên chỉ trả về Department có ít nhất một Employee. Department không có Employee sẽ bị loại khỏi kết quả.

Có thể viết ngắn gọn:

~~~jpql
select d, e
from Department d
join d.employees e
~~~

Trong JPQL, `JOIN` không có từ `LEFT` được hiểu là inner join.

### Ví dụ dữ liệu

Giả sử có dữ liệu:

**departments**

| id | name |
|---:|---|
| 1 | Engineering |
| 2 | Finance |
| 3 | Legal |

**employees**

| id | department_id | name | active |
|---:|---:|---|---|
| 10 | 1 | An | true |
| 11 | 1 | Bình | false |
| 12 | 2 | Chi | true |

Truy vấn:

~~~jpql
select d.name, e.name
from Department d
inner join d.employees e
~~~

Kết quả có các cặp:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Engineering | Bình |
| Finance | Chi |

Legal không xuất hiện vì không có Employee liên kết.

### Khi nào dùng INNER JOIN?

Dùng inner join khi nghiệp vụ chỉ quan tâm đến entity phía trái có association phù hợp. Ví dụ:

- Tìm đơn hàng có ít nhất một dòng hàng.
- Tìm khách hàng có ít nhất một giao dịch.
- Tìm phòng ban có nhân viên.
- Lọc bài viết có tác giả hợp lệ.

Nếu association là nullable hoặc collection có thể rỗng, inner join sẽ loại các entity không có quan hệ tương ứng.

## 3. LEFT JOIN

`LEFT JOIN` giữ lại tất cả dòng phía trái. Nếu không có bản ghi phía phải phù hợp, các thuộc tính phía phải có giá trị null trong kết quả.

~~~jpql
select d, e
from Department d
left join d.employees e
~~~

Với dữ liệu ví dụ, kết quả có:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Engineering | Bình |
| Finance | Chi |
| Legal | null |

Legal vẫn xuất hiện dù không có Employee.

Có thể viết `LEFT OUTER JOIN`; từ `OUTER` là tùy chọn:

~~~jpql
select d
from Department d
left outer join d.employees e
~~~

### LEFT JOIN với association đơn

LEFT JOIN cũng hữu ích khi nối một association đơn có thể null.

Ví dụ, mỗi PurchaseOrder có thể có Customer:

~~~jpql
select o, c
from PurchaseOrder o
left join o.customer c
~~~

Đơn hàng vẫn được trả về khi chưa có Customer liên kết; alias `c` sẽ null ở kết quả tương ứng.

### Khi nào dùng LEFT JOIN?

Dùng left join khi cần giữ toàn bộ entity gốc, kể cả khi association không tồn tại hoặc không có bản ghi thỏa điều kiện. Các ví dụ thường gặp:

- Danh sách tất cả phòng ban, kể cả phòng chưa có nhân viên.
- Danh sách tất cả khách hàng, kể cả khách chưa phát sinh đơn hàng.
- Báo cáo tất cả sản phẩm và doanh số, kể cả sản phẩm chưa bán.
- Tìm bản ghi cha cùng thông tin con nếu có, nhưng không loại cha khi con không tồn tại.

## 4. Điều kiện ON đặt ở đâu?

Từ Jakarta Persistence 2.1, JPQL hỗ trợ `ON` để bổ sung điều kiện cho phép nối. Điều kiện này được đánh giá trong quá trình ghép bản ghi phía phải với phía trái.

Ví dụ, chỉ nối Employee đang active:

~~~jpql
select d, e
from Department d
left join d.employees e on e.active = true
~~~

Với dữ liệu ví dụ:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |
| Legal | null |

Employee Bình bị loại khỏi phần ghép vì `active = false`. Department Engineering vẫn xuất hiện vì LEFT JOIN giữ bản ghi phía trái. Legal cũng vẫn xuất hiện dù không có Employee.

### ON bổ sung điều kiện quan hệ

Khi join qua association như `d.employees`, mapping đã xác định cách hai entity liên hệ với nhau. Điều kiện `ON` bổ sung tiêu chí lọc cho bản ghi phía phải; nó không thay thế foreign key mapping.

Với ví dụ Department/Employee, quan hệ gốc vẫn là:

~~~text
Employee.department_id = Department.id
~~~

Điều kiện bổ sung là:

~~~text
Employee.active = true
~~~

Provider kết hợp hai điều kiện khi tạo SQL join.

Có thể dùng tham số:

~~~java
@Query("""
    select d
    from Department d
    left join d.employees e on e.active = :active
    where d.enabled = true
    """)
List<Department> findEnabledDepartmentsWithEmployeeState(
    @Param("active") boolean active
);
~~~

Tên tham số JPQL phải khớp với `@Param`. Điều kiện ON có thể tham chiếu thuộc tính của alias join, thuộc tính phía trái và tham số truy vấn.

## 5. ON khác WHERE như thế nào?

Đây là điểm quan trọng nhất khi dùng LEFT JOIN.

- `ON` quyết định bản ghi phía phải nào được ghép với bản ghi phía trái.
- `WHERE` lọc các dòng kết quả sau khi phép nối đã được thực hiện.

So sánh hai truy vấn:

**Truy vấn A — điều kiện nằm trong ON**

~~~jpql
select d.name, e.name
from Department d
left join d.employees e on e.active = true
~~~

Kết quả:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |
| Legal | null |

Engineering vẫn xuất hiện dù có Employee không active, nhưng chỉ Employee active được ghép. Legal xuất hiện với employeeName null.

**Truy vấn B — điều kiện nằm trong WHERE**

~~~jpql
select d.name, e.name
from Department d
left join d.employees e
where e.active = true
~~~

Kết quả:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |

Legal bị loại vì `e.active` là null trên dòng do LEFT JOIN tạo ra, và điều kiện `e.active = true` không đúng. Engineering chỉ còn dòng của An.

Điều kiện WHERE trên phía phải thường làm LEFT JOIN có hành vi giống INNER JOIN đối với điều kiện đó. Nếu muốn giữ cha khi không có con thỏa điều kiện, đặt điều kiện của phía phải trong ON.

### Điều kiện phía trái vẫn có thể nằm trong WHERE

Ví dụ chỉ lấy Department đang enabled, nhưng vẫn giữ phòng ban đó khi không có Employee active:

~~~jpql
select d, e
from Department d
left join d.employees e on e.active = true
where d.enabled = true
~~~

Điều kiện `d.enabled` lọc entity phía trái. Điều kiện `e.active` kiểm soát việc ghép phía phải.

Không phải mọi điều kiện đều nên đưa vào ON. Hãy phân loại theo ý nghĩa nghiệp vụ: điều kiện xác định bản ghi quan hệ nào được ghép thì đặt trong ON; điều kiện xác định kết quả cuối cùng nào được giữ thì đặt trong WHERE.

## 6. Kết quả trùng khi join collection

Một Department có thể có nhiều Employee. Khi join collection, một Department có thể xuất hiện trên nhiều dòng kết quả.

Ví dụ:

~~~jpql
select d
from Department d
join d.employees e
~~~

Nếu Engineering có ba nhân viên phù hợp, truy vấn quan hệ có ba dòng cho Engineering. Kết quả JPQL có thể chứa cùng entity Department nhiều lần.

Nếu mục tiêu là danh sách Department duy nhất, dùng:

~~~jpql
select distinct d
from Department d
join d.employees e
~~~

Nếu mục tiêu là lấy từng cặp Department/Employee, không dùng DISTINCT để làm mất các dòng chi tiết.

Với truy vấn đếm, hãy xác định cần đếm dòng quan hệ hay entity cha:

~~~jpql
select count(e)
from Department d
join d.employees e
~~~

Đếm số Employee được nối.

~~~jpql
select count(distinct d.id)
from Department d
join d.employees e
~~~

Đếm số Department có ít nhất một Employee phù hợp.

Khi dùng `Page<T>` với join collection, count query cần được thiết kế để đếm đúng đối tượng gốc, thường cần `count(distinct d.id)`. Không dùng count mặc định nếu join làm nhân bản dòng và kết quả trang sai.

## 7. JOIN để lọc khác JOIN FETCH để tải association

JOIN thông thường giúp truy vấn và lọc theo association. Nó không đồng nghĩa với việc collection của entity được khởi tạo trong persistence context.

Ví dụ:

~~~jpql
select d
from Department d
join d.employees e
where e.active = true
~~~

Truy vấn dùng Employee để xác định Department nào phù hợp. Nó không yêu cầu JPA tải toàn bộ `d.employees` vào collection.

Nếu cần tải association cùng entity, có thể dùng fetch join:

~~~jpql
select distinct d
from Department d
left join fetch d.employees
where d.enabled = true
~~~

`LEFT JOIN FETCH` tải collection cùng Department, kể cả Department không có Employee. Đây là một mục đích khác với join projection hoặc join chỉ để lọc.

Lưu ý:

- Fetch join dùng để khởi tạo association của entity được chọn; không dùng như một phép join projection thông thường.
- JPQL portable fetch join không có alias và không có điều kiện ON như association join thông thường.
- Fetch join collection kết hợp phân trang có thể làm nhân bản dòng và khiến provider phải xử lý pagination trong bộ nhớ hoặc phát cảnh báo.
- Không fetch nhiều collection lớn cùng lúc nếu có nguy cơ tạo tích Descartes hoặc nhân số dòng quá lớn.

Nếu cần lọc collection con nhưng vẫn tải entity, cân nhắc tách truy vấn, dùng EntityGraph phù hợp hoặc DTO projection. Tránh để một truy vấn fetch join làm collection trong bộ nhớ chỉ chứa một phần dữ liệu rồi code khác tưởng rằng đó là toàn bộ collection.

## 8. Projection khi cần dữ liệu từ cả hai phía

Nếu màn hình chỉ cần tên Department và tên Employee, không nhất thiết tải toàn bộ entity graph. Spring Data JPA hỗ trợ interface projection với alias trong JPQL.

Projection:

~~~java
public interface DepartmentEmployeeRow {
    Long getDepartmentId();
    String getDepartmentName();
    String getEmployeeName();
}
~~~

Repository:

~~~java
public interface DepartmentRepository
        extends JpaRepository<Department, Long> {

    @Query("""
        select
            d.id as departmentId,
            d.name as departmentName,
            e.name as employeeName
        from Department d
        left join d.employees e on e.active = true
        where d.enabled = true
        order by d.id, e.name
        """)
    List<DepartmentEmployeeRow> findEnabledDepartmentEmployeeRows();
}
~~~

Kết quả projection có thể gồm:

| departmentId | departmentName | employeeName |
|---:|---|---|
| 1 | Engineering | An |
| 2 | Finance | Chi |
| 3 | Legal | null |

`employeeName` có thể null vì LEFT JOIN giữ Department dù không có Employee active. Một Department có nhiều Employee active sẽ tạo nhiều projection row.

Projection giảm dữ liệu cần tải và làm rõ contract cho báo cáo. Nếu cần trả một object lồng nhau hoặc aggregation phức tạp, có thể dùng DTO constructor expression, interface projection hoặc native query tùy nhu cầu.

## 9. JOIN qua nhiều association

JPQL có thể nối qua nhiều đường dẫn association:

~~~jpql
select o, c, a
from PurchaseOrder o
join o.customer c
left join c.address a
where o.status = :status
~~~

Trong ví dụ:

- Order phải có Customer vì dùng inner join.
- Address có thể không tồn tại nên dùng left join.
- `o.status` là điều kiện lọc entity gốc.

Mỗi alias đại diện cho một phần trong query. Hãy đặt alias ngắn nhưng có nghĩa, ví dụ `o`, `c`, `a`, `line`, `product`.

Khi nối nhiều collection, số dòng có thể tăng theo tích số phần tử. Ví dụ một Order có 4 lines và 3 payments; nối đồng thời hai collection có thể tạo tới 12 dòng cho cùng Order. Điều này ảnh hưởng hiệu năng, kết quả đếm và phân trang.

Nếu chỉ cần kiểm tra tồn tại một association, subquery với EXISTS đôi khi phù hợp hơn join collection:

~~~jpql
select d
from Department d
where exists (
    select e.id
    from Employee e
    where e.department = d
      and e.active = true
)
~~~

EXISTS kiểm tra có ít nhất một Employee active mà không buộc kết quả ngoài phải chứa một dòng cho mỗi Employee. Hãy chọn JOIN hoặc EXISTS theo kết quả cần trả về và kế hoạch thực thi database.

## 10. Ví dụ integration test

Test sau xác nhận LEFT JOIN ON giữ Department không có Employee active và chỉ ghép Employee active.

~~~java
package com.example.department;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class DepartmentRepositoryTest {

    @Autowired
    DepartmentRepository repository;

    @Test
    void leftJoinOnKeepsDepartmentWithoutActiveEmployee() {
        Department engineering = new Department("Engineering", true);
        engineering.addEmployee(new Employee("An", true));
        engineering.addEmployee(new Employee("Binh", false));

        Department legal = new Department("Legal", true);

        repository.saveAll(List.of(engineering, legal));
        repository.flush();

        List<DepartmentEmployeeRow> rows =
                repository.findEnabledDepartmentEmployeeRows();

        assertEquals(2, rows.size());

        assertEquals("Engineering", rows.get(0).getDepartmentName());
        assertEquals("An", rows.get(0).getEmployeeName());

        assertEquals("Legal", rows.get(1).getDepartmentName());
        assertNull(rows.get(1).getEmployeeName());
    }
}
~~~

Test giả định hai entity và projection/repository đã được khai báo như các ví dụ trước, `Department.employees` có cascade PERSIST và repository method sắp xếp theo department ID. Database test phải hỗ trợ mapping được sử dụng.

Có thể viết test đối chiếu với điều kiện WHERE:

~~~jpql
select d.name, e.name
from Department d
left join d.employees e
where e.active = true
~~~

Khi đó Legal sẽ không xuất hiện. Test đối chiếu giúp phát hiện lỗi chuyển điều kiện từ ON sang WHERE trong quá trình refactor query.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Parent không xuất hiện nếu không có child | Dùng INNER JOIN hoặc implicit join | Dùng LEFT JOIN khi cần giữ parent |
| LEFT JOIN vẫn loại parent không có child | Đặt điều kiện phía phải trong WHERE | Đưa điều kiện ghép phía phải vào ON |
| Parent xuất hiện nhiều lần | Join collection tạo nhiều dòng | Dùng DISTINCT nếu chỉ cần entity cha duy nhất |
| Count của Page lớn hơn số parent | Count query đếm dòng join thay vì parent | Dùng count distinct ID |
| Join không tải collection | JOIN thường chỉ tham gia query | Dùng fetch join hoặc EntityGraph nếu thật sự cần tải |
| Phân trang sai hoặc cảnh báo khi fetch collection | Collection fetch join nhân dòng | Phân trang ID trước rồi tải association theo batch/query thứ hai |
| JPQL không nhận tên bảng/cột | JPQL dùng entity name và Java property | Viết entity name và property path |
| ON không được hỗ trợ ở runtime cũ | JPA/provider trước hỗ trợ ON | Dùng phiên bản JPA/provider hỗ trợ JPQL ON hoặc thiết kế truy vấn tương thích |
| Kết quả bị nhân dòng khi nối nhiều collection | Cardinality của các collection nhân với nhau | Tách query, dùng EXISTS hoặc projection phù hợp |

## 12. Quy trình chọn JOIN, LEFT JOIN và ON

Khi viết truy vấn, hãy trả lời lần lượt:

1. Entity gốc nào phải luôn xuất hiện trong kết quả?
2. Nếu không có association, bản ghi gốc có bị loại không?
3. Nếu có association nhưng không thỏa điều kiện, bản ghi gốc có được giữ không?
4. Cần trả về entity gốc, cặp entity hay projection?
5. Join collection có tạo nhiều dòng cho cùng entity gốc không?
6. Có cần tải association vào persistence context hay chỉ cần dùng nó để lọc?
7. Nếu dùng Page, count query có đếm đúng entity gốc không?

Quy tắc thực hành:

- Dùng INNER JOIN khi chỉ cần entity gốc có association phù hợp.
- Dùng LEFT JOIN khi cần giữ entity gốc kể cả khi không có association phù hợp.
- Dùng ON cho điều kiện quyết định association phía phải nào được ghép.
- Dùng WHERE cho điều kiện lọc kết quả cuối cùng.
- Dùng DISTINCT hoặc count distinct khi cần loại trùng entity gốc.
- Dùng FETCH khi cần tải association; đừng nhầm fetch join với join dùng cho projection.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại và không cần nhân dòng kết quả.

## Checklist trước khi merge

- [ ] JPQL dùng đúng entity name và property path.
- [ ] Đã xác định association path và alias rõ ràng.
- [ ] INNER JOIN/LEFT JOIN phù hợp với yêu cầu giữ hay loại entity gốc.
- [ ] Điều kiện ON và WHERE được đặt đúng ngữ nghĩa.
- [ ] Join collection đã xét khả năng nhân dòng.
- [ ] DISTINCT và count query đếm đúng đối tượng cần trả về.
- [ ] JOIN thường và JOIN FETCH được dùng đúng mục đích.
- [ ] Phân trang không bị ảnh hưởng bởi collection fetch join.
- [ ] Projection xử lý được giá trị null ở phía LEFT JOIN.
- [ ] Integration test có cả trường hợp có association, không có association và association không thỏa ON.

## Kết luận

INNER JOIN chỉ giữ các entity gốc có association phù hợp; LEFT JOIN giữ toàn bộ phía trái và trả null cho phía phải khi không có kết quả ghép. ON bổ sung điều kiện ngay trong phép nối, còn WHERE lọc các dòng sau khi nối. Với LEFT JOIN, đặt điều kiện phía phải trong WHERE có thể loại các dòng null và làm mất ý nghĩa giữ phía trái. Hãy xác định rõ kết quả cần trả về, kiểm soát dòng trùng từ collection, phân biệt JOIN với JOIN FETCH và kiểm thử cả trường hợp không có association.
