# Khai báo truy vấn bằng @Query

## Mục tiêu

Spring Data JPA cho phép khai báo truy vấn trực tiếp trên repository bằng annotation `@Query`. Cách này hữu ích khi truy vấn có nhiều điều kiện, JOIN, projection, phân trang hoặc khi tên derived query trở nên dài và khó đọc.

Mặc định, `@Query` của Spring Data JPA sử dụng JPQL (Jakarta Persistence Query Language). JPQL truy vấn trên entity và thuộc tính Java; provider chuyển câu JPQL thành SQL phù hợp với database. Khi cần dùng SQL theo tên bảng/cột cụ thể, có thể đặt `nativeQuery = true`.

Sau bài này, bạn có thể:

- Viết JPQL bằng `@Query` và phân biệt JPQL với SQL.
- Truyền tham số an toàn bằng tên hoặc vị trí.
- Dùng JOIN, điều kiện, sắp xếp và biểu thức trong JPQL.
- Trả về entity, Optional, DTO hoặc interface projection.
- Phân trang với Page và khai báo countQuery.
- Thực hiện UPDATE/DELETE bằng `@Modifying`.
- Dùng native SQL đúng lúc và kiểm thử truy vấn.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. @Query là gì?

Với Spring Data JPA, có thể định nghĩa query ngay trên phương thức repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("select e from Employee e where e.active = true")
    List<Employee> findAllActive();
}
```

Spring Data đọc annotation khi tạo repository và thực thi query khi phương thức được gọi. Với ví dụ trên:

- `Employee` là entity name.
- `e` là alias của entity.
- `e.active` là thuộc tính Java của entity.
- `findAllActive()` trả về danh sách entity thỏa điều kiện.

JPQL dùng tên entity và thuộc tính Java, không dùng tên bảng và tên cột SQL. Nếu entity được khai báo `@Entity(name = "StaffMember")`, JPQL tham chiếu `StaffMember`; tên bảng trong `@Table` không quyết định tên entity trong JPQL.

### 1.1. Khi nào nên dùng @Query?

Dùng derived query cho điều kiện đơn giản và tên phương thức vẫn dễ hiểu, ví dụ `findByEmailIgnoreCase`. Dùng `@Query` khi:

- Cần JOIN nhiều entity hoặc kết hợp điều kiện phức tạp.
- Cần kiểm soát chính xác JPQL.
- Cần projection hoặc phép tính tổng hợp.
- Cần khai báo UPDATE/DELETE.
- Tên derived query trở nên dài hoặc khó bảo trì.
- Cần dùng native SQL vì tính năng đặc thù của database.

Không cần viết `@Query` cho mọi phương thức. Derived query thường ngắn gọn hơn đối với truy vấn đơn giản.

## 2. Khai báo JPQL cơ bản

Giả sử entity Employee:

```java
package com.example.demo.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Employee() {
    }

    public Employee(String fullName, String email, boolean active) {
        this.fullName = fullName;
        this.email = email;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Repository:

```java
package com.example.demo.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           order by e.fullName asc
           """)
    List<Employee> findActiveEmployees();

    @Query("""
           select e
           from Employee e
           where lower(e.email) = lower(:email)
           """)
    Optional<Employee> findByEmailIgnoreCase(
            @Param("email") String email
    );
}
```

Ví dụ dùng Java text block để viết JPQL nhiều dòng. JPQL có thể viết thành chuỗi một dòng hoặc nhiều dòng; text block giúp query dễ đọc hơn.

### 2.1. SELECT và alias

Cấu trúc cơ bản:

```text
select <alias>
from <EntityName> <alias>
where <condition>
order by <property>
```

Alias giúp tham chiếu entity và thuộc tính. Ví dụ:

```sql
select e
from Employee e
where e.active = true
```

Đây là JPQL, không phải SQL. Không viết `select * from employees` trong một query JPQL thông thường. JPQL chọn entity hoặc biểu thức, còn tên entity/field được lấy từ mapping Java.

### 2.2. Điều kiện và toán tử

JPQL hỗ trợ các toán tử quen thuộc:

- So sánh: `=`, `<>`, `>`, `>=`, `<`, `<=`.
- Logic: `AND`, `OR`, `NOT`.
- Kiểm tra null: `IS NULL`, `IS NOT NULL`.
- Tập hợp: `IN`, `NOT IN`.
- Khoảng: `BETWEEN ... AND ...`.
- Chuỗi: `LIKE`, `NOT LIKE`.
- Tồn tại: `EXISTS`, `NOT EXISTS`.

Ví dụ:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.id between :fromId and :toId
       """)
List<Employee> findActiveBetweenIds(
        @Param("fromId") Long fromId,
        @Param("toId") Long toId
);
```

Có thể kết hợp điều kiện bằng ngoặc để làm rõ thứ tự:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
         and (lower(e.fullName) like lower(:pattern)
              or lower(e.email) like lower(:pattern))
       """)
List<Employee> searchActive(
        @Param("pattern") String pattern
);
```

Giá trị truyền vào `pattern` phải chứa ký tự wildcard nếu muốn tìm chuỗi con, ví dụ `%an%`. Không nối trực tiếp dữ liệu người dùng vào chuỗi JPQL.

## 3. Truyền tham số vào query

Spring Data JPA hỗ trợ tham số có tên và tham số vị trí.

### 3.1. Named parameters

Dùng dấu hai chấm trước tên tham số:

```java
@Query("""
       select e
       from Employee e
       where e.email = :email
         and e.active = :active
       """)
List<Employee> findByEmailAndActive(
        @Param("email") String email,
        @Param("active") boolean active
);
```

Ưu điểm của named parameter:

- Tên tham số thể hiện rõ ý nghĩa.
- Ít nhầm thứ tự khi query có nhiều tham số.
- Dễ đọc và dễ bảo trì khi thêm điều kiện.

Nên dùng `@Param` để liên kết tên trong query với tham số Java một cách tường minh. Một số cấu hình có thể lấy tên tham số từ metadata biên dịch, nhưng `@Param` giúp code rõ ràng và ít phụ thuộc cấu hình.

### 3.2. Positional parameters

Tham số vị trí dùng ký hiệu `?1`, `?2`:

```java
@Query("""
       select e
       from Employee e
       where e.email = ?1
         and e.active = ?2
       """)
List<Employee> findByEmailAndStatus(
        String email,
        boolean active
);
```

Số thứ tự bắt đầu từ 1. Nếu đổi thứ tự tham số trong method hoặc query, cần cập nhật cho khớp. Với nhiều tham số, named parameter thường dễ hiểu hơn.

Không trộn lẫn named parameter và positional parameter trong cùng một query.

### 3.3. Truyền collection vào IN

Có thể truyền danh sách vào điều kiện IN:

```java
@Query("""
       select e
       from Employee e
       where e.id in :ids
       """)
List<Employee> findAllByIds(@Param("ids") Collection<Long> ids);
```

Hãy quyết định rõ hành vi khi collection rỗng trước khi gọi repository. Cách database/provider xử lý biểu thức IN với danh sách rỗng có thể khác nhau; ở service có thể trả danh sách rỗng ngay nếu không có ID cần tìm.

### 3.4. Tìm chuỗi và LIKE

Ví dụ tìm tên theo một phần chuỗi:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
List<Employee> searchByName(@Param("keyword") String keyword);
```

JPQL hỗ trợ `CONCAT`. Có thể dùng `LOWER`, `UPPER`, `LENGTH`, `TRIM` và các hàm chuẩn khác. Một số database/provider hỗ trợ thêm hàm riêng; nếu dùng hàm đặc thù, kiểm tra tính tương thích trước khi chuyển database.

Khi cần tìm chính xác chuỗi chứa ký tự wildcard `%` hoặc `_`, phải xử lý escape theo cú pháp LIKE và database phù hợp. Không giả định ký tự người dùng nhập luôn là văn bản thuần.

## 4. JOIN và truy vấn quan hệ entity

JPQL hỗ trợ JOIN qua association đã khai báo trong entity.

Giả sử Employee có quan hệ many-to-one tới Department:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Truy vấn nhân viên theo tên phòng ban:

```java
@Query("""
       select e
       from Employee e
       join e.department d
       where lower(d.name) = lower(:departmentName)
       """)
List<Employee> findByDepartmentName(
        @Param("departmentName") String departmentName
);
```

`e.department` là association trong mapping JPA. `d` là alias của Department.

### 4.1. INNER JOIN và LEFT JOIN

- `JOIN` hoặc `INNER JOIN`: chỉ trả về entity có association khớp.
- `LEFT JOIN`: vẫn giữ entity bên trái ngay cả khi association không tồn tại; các thuộc tính phía phải có thể null.

Ví dụ:

```java
@Query("""
       select e
       from Employee e
       left join e.department d
       where d is null or d.name = :departmentName
       """)
List<Employee> findWithoutDepartmentOrInDepartment(
        @Param("departmentName") String departmentName
);
```

Có thể JOIN nhiều association trong cùng query. Hãy dùng alias rõ ràng để query dễ đọc và tránh điều kiện JOIN nhầm.

### 4.2. JOIN FETCH

`JOIN FETCH` yêu cầu provider tải association cùng lúc với entity nguồn:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.active = true
       """)
List<Employee> findActiveWithDepartment();
```

Fetch join hữu ích khi service sẽ truy cập association trong cùng use case, giúp tránh N+1 query. Fetch join không tạo một DTO riêng; nó vẫn trả entity và association được tải vào persistence context.

Với collection fetch join và phân trang, cần đặc biệt cẩn thận vì một entity cha có thể xuất hiện nhiều hàng sau JOIN, ảnh hưởng tới giới hạn trang và kết quả đếm. Hãy kiểm tra SQL, dùng chiến lược tải phù hợp hoặc chia thành query ID phân trang rồi tải chi tiết.

## 5. Projection: chỉ lấy dữ liệu cần thiết

Không phải lúc nào repository cũng cần trả về toàn bộ entity. Projection giúp lấy đúng các trường mà màn hình hoặc nghiệp vụ cần.

### 5.1. Interface projection

Khai báo interface:

```java
public interface EmployeeNameView {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Query cần đặt alias khớp với tên property projection:

```java
@Query("""
       select e.id as id,
              e.fullName as fullName,
              e.email as email
       from Employee e
       where e.active = true
       """)
List<EmployeeNameView> findActiveEmployeeNames();
```

Spring Data ánh xạ các cột kết quả vào getter tương ứng. Tên alias là phần quan trọng; nếu alias không khớp, projection có thể không nhận đúng giá trị.

### 5.2. DTO projection bằng constructor expression

Tạo DTO có constructor phù hợp:

```java
package com.example.demo.employee;

public record EmployeeSummary(
        Long id,
        String fullName,
        String email
) {
}
```

JPQL dùng constructor expression:

```java
@Query("""
       select new com.example.demo.employee.EmployeeSummary(
           e.id, e.fullName, e.email
       )
       from Employee e
       where e.active = true
       order by e.fullName
       """)
List<EmployeeSummary> findActiveSummaries();
```

JPQL cần tên class đầy đủ trong constructor expression. Thứ tự và kiểu tham số phải khớp constructor/record canonical constructor. DTO không phải entity và không được quản lý bởi persistence context.

Projection giúp giảm lượng dữ liệu đọc và tránh trả entity graph không cần thiết. Chọn projection theo use case; nếu nghiệp vụ cần cập nhật entity, thường nên tải entity managed.

### 5.3. Aggregate projection

JPQL hỗ trợ các hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN` và `MAX`.

Ví dụ đếm nhân viên theo trạng thái:

```java
@Query("""
       select count(e)
       from Employee e
       where e.active = :active
       """)
long countByActive(@Param("active") boolean active);
```

Ví dụ nhóm theo phòng ban:

```java
@Query("""
       select d.name, count(e)
       from Employee e
       join e.department d
       group by d.name
       having count(e) >= :minimum
       order by count(e) desc
       """)
List<Object[]> countEmployeesByDepartment(
        @Param("minimum") long minimum
);
```

Kết quả `Object[]` có thể khó đọc và dễ nhầm vị trí. Với query aggregate dùng thường xuyên, cân nhắc DTO projection hoặc interface projection phù hợp.

## 6. Phân trang với @Query

Một phương thức có tham số `Pageable` có thể trả về `Page<T>`. Spring Data áp dụng giới hạn và sắp xếp cho query.

Ví dụ:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
Page<Employee> searchByName(
        @Param("keyword") String keyword,
        Pageable pageable
);
```

Gọi repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "fullName")
);

Page<Employee> page =
        employeeRepository.searchByName("an", pageable);

List<Employee> content = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Chỉ số trang bắt đầu từ 0. Tên thuộc tính trong Sort là property của entity, ví dụ `fullName`, không phải tên cột SQL `full_name`.

### 6.1. countQuery

Với JPQL đơn giản, Spring Data thường có thể suy ra count query từ câu SELECT. Với query phức tạp, JOIN, DISTINCT hoặc projection đặc biệt, nên khai báo `countQuery` rõ ràng:

```java
@Query(
    value = """
            select e
            from Employee e
            join e.department d
            where d.id = :departmentId
              and e.active = true
            """,
    countQuery = """
            select count(e)
            from Employee e
            join e.department d
            where d.id = :departmentId
              and e.active = true
            """
)
Page<Employee> findActiveByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

Count query phải đếm đúng tập kết quả của query chính. Nếu query chính dùng DISTINCT hoặc JOIN collection tạo ra nhiều hàng cho một entity, cần thiết kế count query tương ứng, có thể dùng `count(distinct e.id)`.

### 6.2. Page, Slice và List

- `Page<T>`: có nội dung và metadata tổng số phần tử/trang; thường cần count query.
- `Slice<T>`: cho biết có trang tiếp theo hay không, không yêu cầu tổng số phần tử.
- `List<T>` với Pageable: chỉ lấy phần dữ liệu được giới hạn; không cung cấp metadata trang.

Nếu màn hình chỉ cần nút “Tải thêm”, `Slice` có thể tiết kiệm chi phí count. Nếu cần tổng số trang, dùng `Page`.

## 7. UPDATE và DELETE với @Modifying

JPQL SELECT là query mặc định. Khi dùng `@Query` để UPDATE hoặc DELETE, cần thêm `@Modifying` để Spring Data thực thi query như một thao tác thay đổi dữ liệu.

### 7.1. UPDATE

```java
@Modifying
@Query("""
       update Employee e
       set e.active = :active
       where e.id = :id
       """)
int updateActive(
        @Param("id") Long id,
        @Param("active") boolean active
);
```

Giá trị trả về là số hàng bị ảnh hưởng. Phương thức cần chạy trong transaction, thường đặt `@Transactional` ở service:

```java
@Service
public class EmployeeService {

    private final EmployeeRepository repository;

    public EmployeeService(EmployeeRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deactivate(Long id) {
        int updated = repository.updateActive(id, false);

        if (updated == 0) {
            throw new IllegalArgumentException("Employee not found");
        }
    }
}
```

### 7.2. DELETE

```java
@Modifying
@Query("""
       delete from Employee e
       where e.active = false
       """)
int deleteInactiveEmployees();
```

JPQL bulk DELETE tác động trực tiếp tới database. Nó không tải từng entity để gọi remove theo vòng đời thông thường.

### 7.3. Persistence context sau bulk update/delete

Bulk UPDATE/DELETE không tự đồng bộ các entity đã được nạp trong persistence context. Nếu Employee đang managed trước khi chạy bulk update, object đó có thể vẫn giữ giá trị cũ trong bộ nhớ.

Có thể dùng các thuộc tính:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
       update Employee e
       set e.active = false
       where e.department.id = :departmentId
       """)
int deactivateByDepartment(
        @Param("departmentId") Long departmentId
);
```

- `flushAutomatically = true`: flush thay đổi đang chờ trước khi chạy bulk query.
- `clearAutomatically = true`: clear persistence context sau khi query chạy để tránh tiếp tục dùng entity instance cũ.

Clear detach tất cả entity trong context, nên hãy cân nhắc nếu service còn cần dùng các entity đang managed.

Bulk query bỏ qua dirty checking và lifecycle callback của từng entity; không tự thực hiện cascade như thao tác remove trên từng entity. Nó cũng không tự áp dụng optimistic locking/version increment theo cách cập nhật entity thông thường. Nếu entity có `@Version`, hãy thiết kế điều kiện version và cập nhật version rõ ràng khi nghiệp vụ cần bảo vệ concurrency.

## 8. Native SQL với nativeQuery = true

Khi JPQL không diễn đạt được truy vấn hoặc cần dùng tính năng riêng của database, có thể dùng native SQL:

```java
@Query(
    value = """
            select *
            from employees
            where lower(email) = lower(:email)
            """,
    nativeQuery = true
)
Optional<Employee> findByEmailNative(
        @Param("email") String email
);
```

Khác với JPQL:

- Native SQL dùng tên bảng `employees`.
- Native SQL dùng tên cột `email`.
- Cú pháp phụ thuộc database.
- Kết quả entity cần tương thích với mapping của entity.
- Thay đổi schema hoặc database có thể yêu cầu sửa query.

### 8.1. Native query phân trang

Với native query trả Page, nên khai báo count query rõ ràng:

```java
@Query(
    value = """
            select *
            from employees
            where active = true
            order by full_name
            """,
    countQuery = """
            select count(*)
            from employees
            where active = true
            """,
    nativeQuery = true
)
Page<Employee> findActiveNative(Pageable pageable);
```

Khả năng tự phân tích query và áp dụng dynamic sort cho native SQL phụ thuộc version Spring Data JPA và độ phức tạp của câu SQL. Với query phức tạp, hãy khai báo rõ count query và thứ tự trong SQL, đồng thời kiểm thử trên database thực tế.

### 8.2. Native projection

Có thể trả interface projection nếu cột SQL được alias đúng tên getter:

```java
public interface EmployeeRow {
    Long getId();
    String getFullName();
}
```

```java
@Query(
    value = """
            select id as id, full_name as fullName
            from employees
            where active = true
            """,
    nativeQuery = true
)
List<EmployeeRow> findActiveRows();
```

Native query hữu ích khi cần SQL đặc thù, nhưng tăng phụ thuộc vào schema/database. Chỉ dùng khi có lý do rõ ràng; với truy vấn nghiệp vụ thông thường, JPQL dễ bảo trì và chuyển database hơn.

## 9. SpEL và entityName

Spring Data JPA cho phép dùng một số biểu thức SpEL trong `@Query`. Một trường hợp hữu ích là `#{#entityName}`, tham chiếu tên entity của repository domain type:

```java
@NoRepositoryBean
public interface BaseReadRepository<T, ID>
        extends Repository<T, ID> {

    @Query("select e from #{#entityName} e where e.id = :id")
    Optional<T> findOneById(@Param("id") ID id);
}
```

Các repository cụ thể có thể kế thừa base interface này. `#entityName` giúp tái sử dụng query khi entity name thay đổi hoặc nhiều entity dùng chung cấu trúc truy vấn.

SpEL trong query có phạm vi và quy tắc riêng của Spring Data. Chỉ dùng biểu thức được tài liệu hỗ trợ; tránh tạo query động bằng cách ghép chuỗi tùy ý từ input người dùng.

## 10. Quy tắc an toàn và hiệu năng

**Dùng bind parameter.** Luôn truyền dữ liệu qua `@Param` hoặc positional parameter. Không nối chuỗi input trực tiếp vào JPQL/SQL vì có nguy cơ injection và lỗi escape.

**Chỉ lấy dữ liệu cần thiết.** Dùng DTO/interface projection nếu không cần toàn bộ entity.

**Kiểm soát N+1.** Dùng JOIN FETCH hoặc EntityGraph theo use case; xem SQL thực tế trước khi đổi fetch mặc định.

**Cẩn thận với collection fetch và pagination.** JOIN collection có thể nhân bản hàng, làm phân trang hoặc count sai. Thiết kế query và count query riêng khi cần.

**Bulk update/delete cần transaction.** Dùng `@Modifying` và transaction rõ ràng. Đồng bộ persistence context sau bulk query nếu service còn dùng entity đã nạp.

**Kiểm tra index theo truy vấn thực tế.** Các điều kiện lọc, JOIN và ORDER BY thường quyết định index cần thiết. Xem execution plan và dữ liệu thật trước khi thêm index.

**Không giả định JPQL hỗ trợ mọi hàm SQL.** JPQL có tập hàm chuẩn; hàm riêng database có thể cần native query hoặc function được provider hỗ trợ.

**Đặt query dễ đọc.** Với JPQL dài, dùng text block, alias ngắn gọn và xuống dòng theo điều kiện. Nếu query quá phức tạp, cân nhắc custom repository implementation.

## 11. Kiểm thử @Query

Dùng `@DataJpaTest` để kiểm tra query với database test:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void findsEmployeeByEmailIgnoringCase() {
        repository.save(
                new Employee("An Nguyen", "an@example.com", true)
        );

        Optional<Employee> result =
                repository.findByEmailIgnoreCase("AN@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getFullName())
                .isEqualTo("An Nguyen");
    }
}
```

Test giả định repository đã khai báo phương thức `findByEmailIgnoreCase` bằng JPQL như ví dụ ở trên, entity và test dependencies đã được cấu hình. `@DataJpaTest` thường chạy trong transaction và rollback sau mỗi test.

Nên kiểm thử:

- Tham số bình thường, null nếu query cho phép và chuỗi có ký tự đặc biệt.
- Không có kết quả và có nhiều kết quả.
- JOIN khi association có/không có dữ liệu.
- Projection alias và DTO constructor.
- Page/ Slice cùng count query.
- Bulk update/delete và số hàng bị ảnh hưởng.
- Native query trên đúng loại database production.
- Persistence context sau bulk query.

Với query native hoặc hàm đặc thù, embedded database có thể không tương thích. Dùng Testcontainers hoặc database test tương ứng để xác minh cú pháp và hành vi thực tế.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Query không tìm thấy entity | Dùng tên bảng thay cho entity name trong JPQL | Dùng tên entity theo mapping |
| Unknown path/property | Dùng tên cột SQL thay cho thuộc tính Java | Kiểm tra property và association của entity |
| Parameter not bound | Tên @Param không khớp placeholder | Đối chiếu :name với @Param("name") |
| Optional trả về nhiều kết quả | Điều kiện query không duy nhất | Dùng List hoặc bảo đảm unique constraint |
| Projection nhận null | Alias không khớp getter | Đặt alias đúng tên property projection |
| DTO constructor không khớp | Sai FQCN, thứ tự hoặc kiểu tham số | Kiểm tra constructor expression |
| Page có total sai | Count query không tương đương query chính | Khai báo countQuery chính xác |
| Update/delete không chạy | Thiếu @Modifying hoặc transaction | Thêm @Modifying và transaction phù hợp |
| Entity managed giữ dữ liệu cũ | Bulk query bỏ qua persistence context | Dùng clear/refresh phù hợp |
| Native query lỗi trên production | SQL phụ thuộc database/schema | Kiểm thử với database đích |
| Query trả dữ liệu trùng | JOIN collection tạo nhiều hàng | Dùng DISTINCT hoặc điều chỉnh query |
| SQL injection | Nối input vào chuỗi query | Dùng bind parameter |

## 13. Checklist trước khi đưa query vào repository

- [ ] JPQL dùng entity name và property Java đúng.
- [ ] Tham số được bind bằng named hoặc positional parameter.
- [ ] Kiểu trả về phù hợp với số lượng kết quả.
- [ ] Projection alias/DTO constructor khớp query.
- [ ] Page có countQuery đúng khi cần.
- [ ] Bulk UPDATE/DELETE có @Modifying và transaction.
- [ ] Persistence context được đồng bộ sau bulk query khi cần.
- [ ] Native query dùng đúng tên bảng/cột và được kiểm thử trên database đích.
- [ ] Query không nối trực tiếp input người dùng.
- [ ] Đã xem SQL và execution plan nếu query quan trọng về hiệu năng.

## Kết luận

`@Query` giúp khai báo truy vấn rõ ràng ngay trên repository. JPQL truy vấn theo entity và property Java, hỗ trợ điều kiện, JOIN, projection, aggregate và phân trang. `@Modifying` mở rộng cách dùng cho bulk UPDATE/DELETE; `nativeQuery = true` cho phép dùng SQL đặc thù database.

Hãy ưu tiên named parameter, chọn kiểu trả về đúng, khai báo countQuery khi cần và kiểm soát persistence context sau bulk query. Giữ query tập trung vào việc truy xuất dữ liệu và kiểm thử với database phù hợp sẽ giúp repository dễ đọc, an toàn và ổn định.
