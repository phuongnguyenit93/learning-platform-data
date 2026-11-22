# Quy ước tên Entity.phươngThức và cơ chế tìm truy vấn trong Spring Data JPA

Spring Data JPA có thể tìm câu truy vấn cho một repository method theo tên quy ước. Với named query, tên truy vấn thường có dạng tên lớp domain, dấu chấm và tên phương thức repository, ví dụ Employee.findByEmailAddress. Khi repository gọi method tương ứng, Spring Data tìm named query đã khai báo trước; nếu không tìm thấy, chiến lược mặc định có thể phân tích tên method để tạo derived query.

Cơ chế này giúp tách câu JPQL khỏi repository interface, tái sử dụng truy vấn đã đặt tên và kiểm soát rõ việc ứng dụng phải có query khai báo hay được phép tự suy ra query. Bài học này trình bày quy ước đặt tên, cách khai báo bằng annotation hoặc orm.xml, thứ tự tìm query, tham số, kiểu trả về, ví dụ và cách kiểm thử.

## 1. Named query là gì?

Named query là câu truy vấn được khai báo trước với một tên định danh. JPA provider đăng ký truy vấn đó trong persistence unit để ứng dụng có thể gọi bằng tên.

Named query thường được viết bằng JPQL:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

Trong đó:

- Employee.findByEmailAddress là tên định danh của query.
- Employee là entity name trong JPQL nếu entity không đặt tên khác bằng @Entity(name = ...).
- e là alias của entity.
- e.emailAddress là thuộc tính Java của entity.
- :email là named parameter được truyền khi thực thi.

Named query có thể được khai báo bằng @NamedQuery/@NamedQueries trên entity hoặc trong file mapping XML như META-INF/orm.xml. Spring Data JPA có thể tra cứu query này khi tạo repository method tương ứng.

Named query phù hợp với truy vấn có cấu trúc ổn định, được dùng thường xuyên hoặc cần đặt tên rõ ràng. Với truy vấn nhỏ chỉ dùng một lần, @Query ngay trên repository method có thể dễ đọc hơn.

## 2. Quy ước tên Entity.phươngThức

Spring Data JPA sử dụng quy ước tên:

~~~text
<DomainClassSimpleName>.<RepositoryMethodName>
~~~

Ví dụ:

| Entity class | Repository method | Named query name |
|---|---|---|
| Employee | findByEmailAddress | Employee.findByEmailAddress |
| Employee | findActiveEmployees | Employee.findActiveEmployees |
| PurchaseOrder | findByOrderNumber | PurchaseOrder.findByOrderNumber |
| Product | searchByCategory | Product.searchByCategory |

Phần trước dấu chấm là tên đơn giản của lớp domain mà repository quản lý; phần sau dấu chấm là tên method chính xác trong repository. Tên có phân biệt chữ hoa/chữ thường, vì vậy phải giữ nhất quán.

Không dùng tên bảng database thay cho tên lớp domain trong quy ước. Ví dụ entity Employee ánh xạ tới bảng employees thì query name vẫn bắt đầu bằng Employee, không phải employees.

Cũng cần phân biệt hai tên:

- Named query name dùng quy ước của Spring Data: Employee.findByEmailAddress.
- Entity name trong JPQL dùng tên entity JPA: mặc định là Employee, nhưng có thể đổi bằng @Entity(name = "StaffMember").

Nếu entity đặt @Entity(name = "StaffMember"), named query vẫn được Spring Data tìm theo domain class simple name Employee.findByEmailAddress; phần JPQL bên trong query phải viết FROM StaffMember e. Đừng nhầm entity name trong JPQL với tên định danh named query.

## 3. Khai báo named query bằng @NamedQuery

Ví dụ entity Employee:

~~~java
package com.example.employee;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedQueries;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
@NamedQueries({
    @NamedQuery(
        name = "Employee.findByEmailAddress",
        query = """
                select e
                from Employee e
                where e.emailAddress = :email
                """
    ),
    @NamedQuery(
        name = "Employee.findActiveWithMinimumSalary",
        query = """
                select e
                from Employee e
                where e.active = true
                  and e.salary >= :minimumSalary
                order by e.name asc
                """
    )
})
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, unique = true, length = 200)
    private String emailAddress;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal salary;

    protected Employee() {
    }

    public Employee(
            String name,
            String emailAddress,
            boolean active,
            BigDecimal salary) {
        this.name = name;
        this.emailAddress = emailAddress;
        this.active = active;
        this.salary = salary;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getSalary() {
        return salary;
    }
}
~~~

@NamedQueries là container chứa nhiều @NamedQuery. Nếu chỉ có một query, có thể dùng trực tiếp @NamedQuery.

Query thứ nhất tìm nhân viên theo email. Query thứ hai lọc nhân viên đang hoạt động với mức lương tối thiểu rồi sắp xếp theo tên. Các query dùng entity name và thuộc tính Java; Hibernate sẽ chuyển chúng thành SQL theo database dialect.

Named query được đăng ký trong persistence unit. Lỗi cú pháp JPQL, entity name hoặc thuộc tính không tồn tại thường được phát hiện khi JPA provider khởi tạo metadata hoặc khi query được tạo, tùy provider và cấu hình. Vì vậy, nên chạy integration test và kiểm tra log khởi động sau khi thay đổi named query.

## 4. Gọi named query qua repository method

Repository method phải có tên khớp phần sau dấu chấm của named query:

~~~java
package com.example.employee;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    Optional<Employee> findByEmailAddress(
            @Param("email") String email);

    List<Employee> findActiveWithMinimumSalary(
            @Param("minimumSalary") BigDecimal minimumSalary);
}
~~~

Spring Data tìm:

- Employee.findByEmailAddress cho method findByEmailAddress.
- Employee.findActiveWithMinimumSalary cho method findActiveWithMinimumSalary.

Method findActiveWithMinimumSalary không tuân theo cú pháp derived query thông thường như findBy..., nhưng vẫn hoạt động khi named query cùng tên được khai báo. Đây là cách hữu ích để tách tên use case khỏi chi tiết JPQL.

Ví dụ gọi từ service:

~~~java
@Service
public class EmployeeService {

    private final EmployeeRepository repository;

    public EmployeeService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Optional<Employee> findByEmail(String email) {
        return repository.findByEmailAddress(email);
    }

    public List<Employee> findEligibleEmployees(BigDecimal minimumSalary) {
        return repository.findActiveWithMinimumSalary(minimumSalary);
    }
}
~~~

Named query đầu tiên dùng tham số :email, method khai báo @Param("email") để liên kết tham số Java. Query thứ hai làm tương tự với :minimumSalary. Dùng @Param giúp mapping rõ ràng và không phụ thuộc việc compiler có lưu tên tham số hay không.

## 5. Cơ chế tìm truy vấn của Spring Data JPA

Spring Data JPA cung cấp ba QueryLookupStrategy chính:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| CREATE | Luôn tạo query từ tên method | Muốn repository method mô tả truy vấn bằng quy ước tên |
| USE_DECLARED_QUERY | Yêu cầu tìm query đã khai báo; không có thì báo lỗi | Muốn mọi query phải được định nghĩa rõ |
| CREATE_IF_NOT_FOUND | Tìm query đã khai báo trước; nếu không có thì suy ra từ tên method | Cần kết hợp named query, @Query và derived query |

CREATE_IF_NOT_FOUND là chiến lược mặc định của Spring Data JPA.

Có thể hình dung thứ tự ở chế độ mặc định:

~~~mermaid
flowchart TD
    A[Repository method] --> B{Có @Query trên method?}
    B -->|Có| C[Dùng @Query]
    B -->|Không| D{Có named query phù hợp?}
    D -->|Có| E[Dùng named query Entity.method]
    D -->|Không| F[Phân tích tên method]
    F --> G[Derived query]
~~~

Sơ đồ mô tả nguyên tắc ưu tiên ở chế độ mặc định. Một method có @Query sẽ dùng câu query được khai báo ngay trên method; nếu không có, Spring Data có thể tìm named query theo quy ước. Nếu không tìm thấy declared query, CREATE_IF_NOT_FOUND chuyển sang derived query.

Nếu method không có @Query và named query không tồn tại, tên method phải hợp lệ theo quy tắc derived query. Ví dụ findByEmailAddress có thể được phân tích; findActiveWithMinimumSalary thường không phải một derived query hợp lệ nếu entity không có thuộc tính tương ứng.

## 6. Cấu hình QueryLookupStrategy

Thông thường không cần cấu hình vì CREATE_IF_NOT_FOUND là mặc định. Nếu muốn yêu cầu mọi method đều có declared query, có thể cấu hình USE_DECLARED_QUERY:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.USE_DECLARED_QUERY
)
public class RepositoryConfig {
}
~~~

Với USE_DECLARED_QUERY, method phải có query được khai báo, ví dụ @Query hoặc named query có tên phù hợp. Nếu thiếu query, Spring Data báo lỗi khi tạo repository thay vì tự phân tích tên method.

Muốn luôn tạo query từ tên method, có thể dùng:

~~~java
@EnableJpaRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.CREATE
)
~~~

CREATE bỏ qua named query để xây dựng query từ method name. Chỉ chọn khi dự án chủ ý dùng derived query cho các method đó.

Khi dùng Spring Boot, hãy cân nhắc cấu hình repository hiện có trước khi thêm @EnableJpaRepositories mới. Nếu đã có cấu hình scan repository, đặt queryLookupStrategy vào cấu hình đó để tránh vô tình thay đổi package được scan.

## 7. Named query trong META-INF/orm.xml

Có thể đặt named query trong file XML thay vì annotation trên entity. Cách này giúp tách metadata truy vấn khỏi mã lớp entity.

Tạo file:

~~~text
src/main/resources/META-INF/orm.xml
~~~

Ví dụ nội dung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <named-query name="Employee.findActiveWithMinimumSalary">
        <query>
            <![CDATA[
                select e
                from Employee e
                where e.active = true
                  and e.salary >= :minimumSalary
                order by e.name asc
            ]]>
        </query>
    </named-query>

</entity-mappings>
~~~

Spring Boot/JPA provider thường tự phát hiện file orm.xml ở vị trí chuẩn META-INF/orm.xml. Nếu dự án cấu hình mapping file ở vị trí khác, cần khai báo mapping resource tương ứng trong persistence configuration.

Không khai báo cùng một named query name ở nhiều nơi nếu không có chủ đích. Trùng tên query trong persistence unit có thể gây xung đột hoặc phụ thuộc quy tắc metadata override của provider. Chọn một nguồn định nghĩa rõ ràng cho từng query.

### Chọn annotation hay XML

| Cách khai báo | Ưu điểm | Hạn chế |
|---|---|---|
| @NamedQuery trên entity | Query ở gần entity, dễ tìm khi số lượng ít | Entity có thể nhiều annotation và chứa cả chi tiết truy vấn |
| META-INF/orm.xml | Tách query khỏi mã Java, quản lý mapping tập trung | Tên và cú pháp XML dễ sai, cần theo dõi file riêng |
| @Query trên repository method | Query ở ngay nơi sử dụng, dễ đọc cùng kiểu trả về | Repository có thể chứa nhiều JPQL dài |
| Derived query | Ít mã, dễ hiểu với điều kiện đơn giản | Khó biểu đạt query phức tạp hoặc nhiều phép join |

Không có lựa chọn duy nhất cho mọi dự án. Hãy dùng cách phù hợp với quy mô query, quy ước nhóm và khả năng bảo trì.

## 8. Tham số trong named query

JPQL hỗ trợ named parameter và positional parameter.

Named parameter:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

Repository:

~~~java
Optional<Employee> findByEmailAddress(
        @Param("email") String email);
~~~

Positional parameter:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = ?1"
)
~~~

Repository:

~~~java
Optional<Employee> findByEmailAddress(String email);
~~~

Named parameter thường dễ đọc và ít nhầm khi query có nhiều tham số. Positional parameter phụ thuộc thứ tự nên cần cẩn thận khi thay đổi chữ ký method.

Không trộn named parameter và positional parameter trong cùng một query. Tên trong @Param phải khớp chính xác với tên sau dấu hai chấm trong JPQL. Không đặt dấu hai chấm trong giá trị @Param.

Các tham số bind dùng cho giá trị dữ liệu. Không thể dùng bind parameter để thay thế tên entity, tên thuộc tính, từ khóa ORDER BY hoặc tên bảng động. Nếu cần lựa chọn cấu trúc query theo đầu vào, hãy dùng query động có kiểm soát hoặc Specification/Criteria API.

## 9. @Query có ưu tiên hơn named query

Nếu repository method vừa có @Query vừa có named query cùng tên, Spring Data JPA ưu tiên @Query khai báo trên method.

Ví dụ:

~~~java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.emailAddress = :email
             and e.active = true
           """)
    Optional<Employee> findByEmailAddress(
            @Param("email") String email);
}
~~~

Ở đây method dùng @Query trên repository. Named query Employee.findByEmailAddress nếu có sẽ không được dùng cho method này.

Quy tắc này hữu ích khi một repository cần điều chỉnh cách truy vấn mà không thay đổi named query dùng ở nơi khác. Tuy nhiên, không nên để hai định nghĩa khác nhau tồn tại lâu dài nếu nhóm không có lý do rõ ràng; chúng dễ gây nhầm lẫn khi bảo trì.

## 10. Named query và derived query khác nhau thế nào?

| Tiêu chí | Named query | Derived query |
|---|---|---|
| Nguồn câu truy vấn | @NamedQuery hoặc orm.xml | Tên repository method |
| Tên method | Có thể là tên use case bất kỳ nếu named query khớp | Phải theo cú pháp Spring Data |
| Câu JPQL | Viết tường minh khi khai báo query | Framework tự tạo |
| Query phức tạp | Dễ kiểm soát JPQL, join, projection | Tên method có thể quá dài hoặc không diễn đạt được |
| Thay đổi điều kiện | Sửa định nghĩa named query | Sửa method name |
| Kiểm tra tên thuộc tính | Provider kiểm tra query khai báo | Spring Data phân tích tên method |
| Tái sử dụng | Có thể gọi qua tên query đã đăng ký | Gắn với repository method |

Ví dụ derived query:

~~~java
List<Employee> findByActiveTrueAndSalaryGreaterThanEqualOrderByNameAsc(
        BigDecimal minimumSalary);
~~~

Ví dụ named query:

~~~java
List<Employee> findActiveWithMinimumSalary(
        @Param("minimumSalary") BigDecimal minimumSalary);
~~~

Derived query thích hợp với điều kiện đơn giản, tên ngắn và dễ hiểu. Named query thích hợp khi muốn kiểm soát JPQL hoặc dùng tên method thể hiện use case.

## 11. Kiểu trả về của repository method

Kiểu trả về phải phù hợp với số lượng và cấu trúc kết quả của named query.

| Kiểu trả về | Khi sử dụng |
|---|---|
| Entity | Query dự kiến trả về một entity |
| Optional<Entity> | Tối đa một entity, có thể không tìm thấy |
| List<Entity> | Có thể có nhiều entity |
| Page<Entity> | Cần phân trang và tổng số kết quả |
| Slice<Entity> | Cần phân trang nhưng không cần tổng số |
| Projection/DTO | Chỉ cần một số trường hoặc kết quả tính toán |
| Scalar như String, Long, BigDecimal | Query SELECT một biểu thức tương ứng |

Ví dụ query trả về entity:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

Repository có thể trả Optional<Employee> nếu email là duy nhất. Nếu query có thể trả nhiều bản ghi, dùng List<Employee> hoặc Page<Employee>.

Không khai báo Optional cho query có khả năng trả nhiều hơn một dòng. Nếu kết quả có nhiều dòng nhưng method yêu cầu một kết quả, Spring Data có thể ném IncorrectResultSizeDataAccessException hoặc lỗi tương ứng từ provider.

Với query trả scalar hoặc DTO, kiểu SELECT phải khớp kiểu trả về. Ví dụ select count(e) trả Long; select e.name trả String. Với constructor expression, kiểu và thứ tự tham số phải khớp constructor DTO.

## 12. Named query trả về DTO

JPQL có thể dùng constructor expression để tạo DTO:

~~~java
package com.example.employee;

public record EmployeeSummary(
        Long id,
        String name,
        String emailAddress
) {
}
~~~

Named query:

~~~java
@NamedQuery(
    name = "Employee.findSummariesByActive",
    query = """
            select new com.example.employee.EmployeeSummary(
                e.id, e.name, e.emailAddress
            )
            from Employee e
            where e.active = :active
            order by e.name
            """
)
~~~

Repository:

~~~java
List<EmployeeSummary> findSummariesByActive(
        @Param("active") boolean active);
~~~

Tên lớp DTO trong JPQL constructor expression phải là fully qualified class name. Constructor phải nhận đúng kiểu và thứ tự của các biểu thức SELECT. Java record có canonical constructor nên phù hợp với ví dụ này.

DTO projection tránh tải toàn bộ entity và quan hệ không cần thiết. Đây là lựa chọn tốt cho báo cáo hoặc API chỉ cần một phần dữ liệu.

## 13. Named query với phân trang và sắp xếp

Repository method có thể nhận Pageable để phân trang kết quả:

~~~java
Page<Employee> findActiveWithMinimumSalary(
        @Param("minimumSalary") BigDecimal minimumSalary,
        Pageable pageable);
~~~

Named query tương ứng vẫn dùng tên:

~~~text
Employee.findActiveWithMinimumSalary
~~~

Câu JPQL trong named query nên có thứ tự ổn định nếu dùng phân trang. Ví dụ order by e.name, e.id giúp kết quả ít bị thay đổi thứ tự giữa các trang khi nhiều nhân viên có cùng tên.

Với declared query và Pageable, Spring Data cần xác định query đếm để tạo thông tin tổng số phần tử. Tùy loại query và phiên bản Spring Data, framework có thể suy ra count query; nếu không suy ra được hoặc query phức tạp, cần cung cấp cách đếm phù hợp qua cơ chế khai báo query được hỗ trợ. Kiểm tra log SQL và test tổng số trang, không chỉ kiểm tra danh sách nội dung.

Nếu chỉ cần biết còn trang tiếp theo hay không, dùng Slice có thể tránh truy vấn đếm tổng số.

Sắp xếp động bằng Sort cần được kiểm tra với loại query và phiên bản đang dùng. Named query là câu JPQL đã khai báo; không giả định mọi biểu thức ORDER BY động đều có thể được nối vào an toàn. Với thứ tự cố định, khai báo ORDER BY ngay trong named query.

## 14. Native named query

JPA cũng hỗ trợ named native query để viết SQL theo database thay vì JPQL. Có thể khai báo bằng @NamedNativeQuery hoặc XML mapping.

Ví dụ:

~~~java
@NamedNativeQuery(
    name = "Employee.findByEmailAddressNative",
    query = "select * from employees where email_address = ?1",
    resultClass = Employee.class
)
~~~

Repository method:

~~~java
Optional<Employee> findByEmailAddressNative(String email);
~~~

Tên query vẫn theo quy ước domain class simple name cộng tên method. Native SQL dùng tên bảng/cột vật lý, ví dụ employees và email_address; JPQL dùng entity name và thuộc tính Java.

Native query phụ thuộc database dialect, schema và kiểu cột. Khi trả về entity, các cột cần thiết phải ánh xạ được vào entity. Với kết quả phức tạp hoặc DTO, có thể cần @SqlResultSetMapping hoặc cơ chế projection phù hợp. Chỉ dùng native query khi JPQL không diễn đạt thuận tiện hoặc cần tính năng SQL riêng; kiểm thử trên database thật.

## 15. Trùng tên và các trường hợp cần tránh

Named query name phải duy nhất trong persistence unit. Một số tình huống dễ gây xung đột:

- Hai entity có cùng tên domain class simple name trong các package khác nhau.
- Nhiều repository cùng domain type có method trùng tên nhưng mong muốn query khác nhau.
- Một method bị overload nhưng các chữ ký cần những câu query khác nhau.
- Annotation và orm.xml cùng khai báo một query name.
- Đổi tên method nhưng quên đổi named query name.
- Đổi tên entity hoặc thuộc tính trong JPQL nhưng không cập nhật query.

Vì named query name chỉ gồm domain class simple name và method name, hai repository cho cùng domain type với cùng method name sẽ tìm cùng một named query. Nếu cần hai câu truy vấn khác nhau, hãy dùng tên method khác hoặc khai báo @Query tường minh.

Method overload cũng không tạo được hai named query key riêng vì phần tên method giống nhau. Dùng tên method phân biệt hoặc @Query khi cần nhiều chữ ký khác nhau.

## 16. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Named query không được tìm thấy | Sai domain class name hoặc method name | Kiểm tra đúng mẫu Entity.method |
| Method không có query và không phân tích được | CREATE_IF_NOT_FOUND không tìm thấy named query rồi thử derived query | Khai báo named query hoặc đổi method sang tên derived hợp lệ |
| JPQL không tìm thấy entity | Dùng tên bảng hoặc sai @Entity(name) | Dùng entity name JPA trong câu JPQL |
| JPQL không tìm thấy thuộc tính | Dùng tên cột SQL thay cho thuộc tính Java | Kiểm tra entity property |
| Tham số không được bind | @Param không khớp tên :parameter | Đồng bộ tên tham số |
| Query trả quá nhiều kết quả | Method khai báo entity/Optional nhưng query không duy nhất | Dùng List/Page hoặc bảo đảm điều kiện unique |
| DTO projection lỗi | Sai fully qualified class name hoặc constructor signature | Kiểm tra kiểu và thứ tự SELECT |
| XML mapping không được tải | orm.xml sai vị trí hoặc namespace/version | Đặt trong META-INF và kiểm tra cấu hình JPA |
| Hai query ghi đè/xung đột | Trùng tên trong annotation/XML | Dùng tên duy nhất và một nguồn định nghĩa |
| Query chậm khi phân trang | Count query hoặc join tốn chi phí | Xem SQL, tối ưu query/count và index |
| Native query chạy khác giữa môi trường | SQL phụ thuộc database | Test trên database mục tiêu |

## 17. Kiểm thử named query với @DataJpaTest

Một integration test nên xác nhận named query được tìm đúng theo tên và tham số được bind chính xác.

Ví dụ:

~~~java
package com.example.employee;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void resolvesNamedQueryByDomainAndMethodName() {
        repository.save(new Employee(
                "An",
                "an@example.com",
                true,
                new BigDecimal("2500.00")));

        repository.save(new Employee(
                "Binh",
                "binh@example.com",
                false,
                new BigDecimal("3000.00")));

        var result = repository.findActiveWithMinimumSalary(
                new BigDecimal("2000.00"));

        assertThat(result)
                .extracting(Employee::getEmailAddress)
                .containsExactly("an@example.com");
    }

    @Test
    void bindsNamedParameterInNamedQuery() {
        repository.save(new Employee(
                "Lan",
                "lan@example.com",
                true,
                new BigDecimal("1800.00")));

        var result = repository.findByEmailAddress("lan@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Lan");
    }
}
~~~

Test thứ nhất sử dụng method findActiveWithMinimumSalary không có cú pháp derived query thông thường. Nó chứng minh Spring Data tìm được named query Employee.findActiveWithMinimumSalary. Test thứ hai kiểm tra named parameter :email được bind qua @Param.

@DataJpaTest thường dùng database nhúng nếu có trên classpath và chạy transaction cho từng test. Nếu named query dùng hàm SQL riêng, kiểu dữ liệu đặc thù hoặc native query, hãy chạy thêm integration test trên đúng database production.

## 18. Quy trình tìm lỗi khi repository khởi động thất bại

Khi ứng dụng báo lỗi tạo repository, kiểm tra theo thứ tự:

1. Lấy chính xác tên repository method.
2. Tạo tên named query theo EntitySimpleName.methodName.
3. Kiểm tra @NamedQuery hoặc orm.xml có khai báo đúng tên đó không.
4. Kiểm tra entity name và thuộc tính trong JPQL.
5. Kiểm tra tham số :name và @Param("name").
6. Nếu không có named query, xác định method có phải derived query hợp lệ không.
7. Kiểm tra QueryLookupStrategy có bị cấu hình thành USE_DECLARED_QUERY hoặc CREATE hay không.
8. Đọc nguyên nhân gốc trong log, đặc biệt lỗi JPQL syntax, unknown entity/property và parameter binding.

Với CREATE_IF_NOT_FOUND, một method không tìm thấy named query có thể chuyển sang bước phân tích tên. Vì vậy, thông báo lỗi có thể nói không tìm thấy property trong entity dù ý định ban đầu là dùng named query. Kiểm tra cả tên query và tên method để tìm nguyên nhân.

## 19. Nguyên tắc thiết kế thực tế

- Dùng quy ước EntitySimpleName.methodName chính xác và nhất quán.
- Giữ named query name duy nhất trong persistence unit.
- Dùng @Param với named parameter để liên kết rõ ràng.
- Ưu tiên JPQL khi có thể để truy vấn ít phụ thuộc database.
- Dùng @NamedQuery cho query ổn định cần đặt tên hoặc tách khỏi repository.
- Dùng @Query khi muốn câu truy vấn nằm cạnh method sử dụng.
- Dùng derived query cho điều kiện đơn giản và dễ đọc.
- Chọn USE_DECLARED_QUERY khi dự án cần bắt buộc khai báo mọi query; nếu không, giữ mặc định CREATE_IF_NOT_FOUND thường linh hoạt hơn.
- Không để method overload hoặc nhiều repository cùng domain type vô tình dùng chung một query name với ý nghĩa khác nhau.
- Dùng DTO cho báo cáo và API chỉ cần một phần dữ liệu.
- Kiểm thử named query khi khởi động và bằng @DataJpaTest.
- Với native query, xác minh trên database mục tiêu và quản lý schema bằng migration.

## 20. Checklist tự đánh giá

- [ ] Giải thích được named query và lý do đặt tên.
- [ ] Viết đúng quy ước EntitySimpleName.methodName.
- [ ] Phân biệt domain class simple name với JPA entity name và tên bảng.
- [ ] Khai báo nhiều named query bằng @NamedQueries.
- [ ] Định nghĩa named query trong META-INF/orm.xml.
- [ ] Tạo repository method có tên khớp named query.
- [ ] Giải thích được CREATE, USE_DECLARED_QUERY và CREATE_IF_NOT_FOUND.
- [ ] Biết CREATE_IF_NOT_FOUND là chiến lược mặc định.
- [ ] Biết @Query trên method ưu tiên hơn named query.
- [ ] Bind named parameter bằng @Param.
- [ ] Chọn đúng kiểu trả về entity, Optional, List, Page, Slice hoặc DTO.
- [ ] Hiểu giới hạn trùng tên và method overload.
- [ ] Phân biệt JPQL named query với native named query.
- [ ] Kiểm thử việc phân giải named query và tham số.

## 21. Kết luận

Quy ước EntitySimpleName.methodName là cầu nối giữa named query và repository method trong Spring Data JPA. Khi repository gọi method, Spring Data có thể tìm query đã khai báo theo tên đó; với CREATE_IF_NOT_FOUND, nếu không tìm thấy thì framework thử tạo derived query từ tên method.

Hiểu đúng thứ tự tìm query giúp lựa chọn giữa @NamedQuery, orm.xml, @Query và derived query. Đặt tên duy nhất, dùng @Param rõ ràng, chọn kiểu trả về phù hợp và kiểm thử với database mục tiêu sẽ giúp repository dễ đọc, dễ bảo trì và ít lỗi khi khởi động.
