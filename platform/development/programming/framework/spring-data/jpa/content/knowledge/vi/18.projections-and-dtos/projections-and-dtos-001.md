# Vì sao nên chọn dữ liệu cần đọc thay vì luôn tải Entity

## Mục tiêu

Khi đọc dữ liệu bằng Spring Data JPA, cách quen thuộc là truy vấn và nhận về một entity. Tuy nhiên, nhiều use case chỉ cần một phần thông tin: tên và email để hiển thị danh sách, vài trường để tạo báo cáo, hoặc một giá trị tổng hợp để hiển thị thống kê. Tải entity đầy đủ trong những trường hợp đó có thể tạo thêm chi phí đọc cột, tạo object, theo dõi trạng thái và tải association không cần thiết.

Spring Data JPA hỗ trợ projection để truy vấn đúng hình dạng dữ liệu mà use case cần. Projection có thể là interface, DTO/record, scalar value hoặc kiểu kết quả động. Khi cần cập nhật nghiệp vụ, entity managed vẫn là lựa chọn phù hợp.

Sau bài này, bạn có thể:

- Phân biệt entity query với projection query.
- Chọn dữ liệu cần đọc thay vì luôn tải entity.
- Dùng interface projection, DTO/record, scalar và dynamic projection.
- Kết hợp projection với JPQL, JOIN và phân trang.
- Phân biệt projection với EntityGraph và fetch join.
- Nhận biết khi projection không giúp query nhanh hơn.
- Thiết kế ranh giới đọc/ghi và kiểm thử kết quả projection.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Vì sao không phải lúc nào cũng tải Entity?

Entity JPA đại diện cho đối tượng domain được ánh xạ với dữ liệu persistent. Khi một entity được nạp trong persistence context, provider thường theo dõi trạng thái của nó để hỗ trợ dirty checking, identity management, cascade và các thao tác persistence.

Ví dụ:

```java
Employee employee = employeeRepository.findById(id).orElseThrow();

String name = employee.getFullName();
String email = employee.getEmail();
```

Nếu màn hình chỉ hiển thị tên và email, việc tải entity có thể lấy thêm các thuộc tính persistent khác mà màn hình không dùng. Entity còn có thể tham chiếu tới Department, Address hoặc các collection. Việc truy cập association sau đó có thể phát sinh thêm query.

Không có nghĩa mọi lần đọc entity đều tải toàn bộ object graph. JPA fetch strategy quyết định cách association được tải; provider cũng có thể hỗ trợ lazy basic attribute trong một số mapping. Tuy nhiên, truy vấn entity thường được thiết kế để khôi phục một entity có thể tham gia persistence context, còn projection cho phép biểu diễn trực tiếp dữ liệu cần cho một use case đọc.

### 1.1. Những chi phí có thể tránh

Khi chỉ cần một vài trường, projection có thể giúp giảm:

- Số cột được chọn và lượng dữ liệu truyền từ database.
- Số object entity và proxy được tạo.
- Chi phí snapshot/dirty checking của entity managed.
- Rủi ro truy cập lazy association ngoài transaction.
- Dữ liệu dư thừa được chuyển tới service hoặc API.
- Khả năng vô tình serialize entity graph hoặc lộ field không cần thiết.

Mức cải thiện thực tế phụ thuộc query, schema, index, database, cache và số lượng dữ liệu. Projection không tự động làm mọi query nhanh hơn; cần xem SQL được sinh và đo hiệu năng.

### 1.2. Ví dụ so sánh

Một entity có nhiều thuộc tính:

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;
    private String phone;
    private String address;
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    // Constructor, getters và các phương thức domain.
}
```

Nếu màn hình danh sách chỉ cần ID, tên và email, có thể dùng một kiểu kết quả riêng thay vì trả Employee:

```java
public record EmployeeListItem(
        Long id,
        String fullName,
        String email
) {
}
```

Truy vấn projection chỉ định đúng các trường cần thiết. Service nhận dữ liệu đã có hình dạng phù hợp với màn hình và không cần chuyển đổi toàn bộ entity.

## 2. Entity query và projection query khác nhau

| Tiêu chí | Entity query | Projection query |
|---|---|---|
| Kết quả | Entity được ánh xạ bởi JPA | Interface, DTO, record, scalar hoặc kiểu khác |
| Persistence context | Entity được quản lý khi được nạp trong context | DTO/scalar thông thường không được quản lý |
| Dirty checking | Có với entity managed | Không với DTO/scalar |
| Dữ liệu đọc | Theo mapping và fetch plan của entity | Có thể chọn đúng thuộc tính cần thiết |
| Mục đích phù hợp | Nghiệp vụ cần đọc rồi thay đổi entity | Danh sách, báo cáo, tìm kiếm, màn hình đọc |
| Association | Có thể dùng proxy/fetch plan | Chỉ chọn giá trị hoặc association cần cho kết quả |
| Ràng buộc vòng đời | Theo entity lifecycle | Không có entity lifecycle cho DTO thông thường |

Entity và projection giải quyết hai mục đích khác nhau. Nếu cần gọi phương thức domain, kiểm tra invariant hoặc cập nhật trạng thái, hãy tải entity managed. Nếu chỉ cần đọc dữ liệu để trình bày hoặc tính toán, projection thường phù hợp hơn.

Không nên xem projection là một phiên bản entity nhẹ để cập nhật. Một DTO chứa ID và vài field không tự có dirty checking hoặc optimistic locking như entity managed.

## 3. Interface projection

Interface projection là cách đơn giản để khai báo các getter tương ứng với thuộc tính muốn đọc.

### 3.1. Closed projection

Khai báo interface:

```java
public interface EmployeeSummary {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    List<EmployeeSummary> findByActiveTrue();
}
```

Spring Data nhận biết các getter tương ứng với thuộc tính của Employee và tạo projection cho kết quả. Đây là closed projection vì các thuộc tính cần thiết được xác định từ interface.

Closed projection có thể giúp Spring Data tối ưu truy vấn để chỉ lấy các thuộc tính được yêu cầu. Tuy nhiên, mức tối ưu cụ thể phụ thuộc kiểu projection, query và provider. Hãy kiểm tra SQL thực tế nếu số cột hoặc hiệu năng là yêu cầu quan trọng.

Gọi repository:

```java
List<EmployeeSummary> employees = repository.findByActiveTrue();

for (EmployeeSummary employee : employees) {
    System.out.println(employee.getFullName());
}
```

Projection interface thường được triển khai bằng proxy. Người gọi dùng getter mà không cần biết cơ chế tạo object bên dưới.

### 3.2. Projection với association

Có thể khai báo projection lồng nhau:

```java
public interface EmployeeWithDepartment {
    Long getId();
    String getFullName();
    DepartmentView getDepartment();

    interface DepartmentView {
        String getName();
    }
}
```

Projection lồng nhau tiện cho dữ liệu có cấu trúc, nhưng cần cẩn thận: truy cập nested property có thể yêu cầu JOIN hoặc materialize một phần association theo cách provider/Spring Data xử lý. Không giả định projection lồng nhau luôn chỉ chọn đúng một cột từ bảng liên quan.

Nếu cần kiểm soát chính xác SQL và các cột được chọn, DTO projection với JPQL constructor expression thường rõ ràng hơn.

### 3.3. Open projection

Open projection dùng biểu thức SpEL để tính giá trị từ target entity:

```java
public interface EmployeeLabel {
    @Value("#{target.fullName + ' <' + target.email + '>'}")
    String getLabel();
}
```

Vì biểu thức có thể truy cập nhiều thuộc tính của target, Spring Data khó suy luận chính xác tập cột tối thiểu cần tải. Do đó open projection có thể làm mất một phần lợi ích tối ưu của closed projection.

Dùng open projection khi biểu thức thực sự tiện lợi và đơn giản. Nếu logic trình bày phức tạp, DTO/service mapper thường dễ kiểm thử và kiểm soát hơn.

## 4. DTO và record projection

DTO projection tạo một object riêng chứa đúng dữ liệu cần trả về. Đây là lựa chọn rõ ràng cho API response, báo cáo hoặc kết quả tìm kiếm.

### 4.1. Record projection

Java record phù hợp với DTO bất biến:

```java
package com.example.demo.employee;

public record EmployeeListItem(
        Long id,
        String fullName,
        String email
) {
}
```

Spring Data JPA hỗ trợ class-based projection qua constructor phù hợp. Record có canonical constructor nên thường thuận tiện cho trường hợp này.

Repository có thể dùng derived query:

```java
List<EmployeeListItem> findByActiveTrue();
```

Spring Data cần xác định constructor và các thuộc tính phù hợp. Nếu DTO có nhiều constructor, có thể cần đánh dấu constructor được dùng bằng `@PersistenceCreator` theo quy tắc của Spring Data.

### 4.2. JPQL constructor expression

Với query tùy chỉnh, dùng `select new`:

```java
@Query("""
       select new com.example.demo.employee.EmployeeListItem(
           e.id,
           e.fullName,
           e.email
       )
       from Employee e
       where e.active = true
       order by e.fullName
       """)
List<EmployeeListItem> findActiveListItems();
```

JPQL constructor expression cần tên class đầy đủ (fully qualified class name) của DTO. Thứ tự và kiểu các biểu thức phải khớp constructor.

Ví dụ DTO class truyền thống:

```java
public class EmployeeListItem {

    private final Long id;
    private final String fullName;
    private final String email;

    public EmployeeListItem(
            Long id,
            String fullName,
            String email
    ) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
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
}
```

Không đặt `@Entity` lên DTO chỉ vì nó được trả về từ repository. DTO không phải entity và không cần mapping bảng.

### 4.3. Projection với JOIN

DTO projection có thể lấy trường từ nhiều entity trong một query:

```java
public record EmployeeDepartmentRow(
        Long employeeId,
        String employeeName,
        String departmentName
) {
}
```

```java
@Query("""
       select new com.example.demo.employee.EmployeeDepartmentRow(
           e.id,
           e.fullName,
           d.name
       )
       from Employee e
       join e.department d
       where e.active = true
       """)
List<EmployeeDepartmentRow> findActiveEmployeeDepartmentRows();
```

Query chỉ trả về các giá trị cần dùng. Không cần khởi tạo toàn bộ Department object hoặc đưa entity graph sang tầng API chỉ để hiển thị tên phòng ban.

Nếu association là optional và vẫn muốn giữ Employee không có Department, dùng `left join` thay cho `join`; khi đó `departmentName` trong record cần chấp nhận null.

## 5. Scalar và aggregate projection

Nếu chỉ cần một giá trị, không cần tạo DTO hoặc tải entity.

Ví dụ lấy email:

```java
@Query("""
       select e.email
       from Employee e
       where e.id = :id
       """)
Optional<String> findEmailById(@Param("id") Long id);
```

Ví dụ đếm nhân viên đang hoạt động:

```java
@Query("""
       select count(e)
       from Employee e
       where e.active = true
       """)
long countActiveEmployees();
```

Ví dụ tính tổng tiền theo phòng ban:

```java
@Query("""
       select d.id, d.name, count(e)
       from Employee e
       join e.department d
       where e.active = true
       group by d.id, d.name
       order by count(e) desc
       """)
List<Object[]> countActiveEmployeesByDepartment();
```

Kết quả `Object[]` cần ép kiểu theo đúng thứ tự cột và có thể khó bảo trì. Với query dùng lâu dài, nên tạo DTO:

```java
public record DepartmentEmployeeCount(
        Long departmentId,
        String departmentName,
        Long employeeCount
) {
}
```

```java
@Query("""
       select new com.example.demo.employee.DepartmentEmployeeCount(
           d.id,
           d.name,
           count(e)
       )
       from Employee e
       join e.department d
       where e.active = true
       group by d.id, d.name
       order by count(e) desc
       """)
List<DepartmentEmployeeCount> countByDepartment();
```

Aggregate query giúp database tính toán và chỉ trả kết quả tổng hợp, thay vì tải mọi entity về Java rồi tự đếm.

## 6. Dynamic projection

Có trường hợp cùng một điều kiện tìm kiếm nhưng caller cần nhiều hình dạng kết quả khác nhau. Spring Data hỗ trợ dynamic projection qua tham số Class:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    <T> List<T> findByActiveTrue(Class<T> type);
}
```

Caller chọn kiểu kết quả:

```java
List<EmployeeSummary> summaries =
        repository.findByActiveTrue(EmployeeSummary.class);

List<EmployeeListItem> items =
        repository.findByActiveTrue(EmployeeListItem.class);

List<Employee> entities =
        repository.findByActiveTrue(Employee.class);
```

Dynamic projection giúp tái sử dụng điều kiện query nhưng vẫn cho phép caller chọn entity hoặc projection phù hợp. Hãy tránh lạm dụng nếu các use case có yêu cầu fetch, join, authorization hoặc filtering khác nhau; khi đó các repository method riêng thường dễ hiểu hơn.

Spring Data nhận diện tham số Class dùng làm dynamic projection khi kiểu generic phù hợp với kiểu trả về. Nếu cần truyền một Class object như tham số query thông thường, hãy dùng một kiểu khai báo khác để không bị hiểu nhầm là dynamic projection parameter.

## 7. Chọn dữ liệu cần đọc từ association

Projection đặc biệt hữu ích khi dữ liệu hiển thị đến từ nhiều bảng nhưng chỉ cần một vài trường.

Ví dụ danh sách đơn hàng cần mã đơn, ngày tạo, tên khách hàng và tổng tiền. Không nhất thiết phải tải Order, Customer và toàn bộ collection OrderLine.

```java
public record OrderListItem(
        Long id,
        String orderNumber,
        Instant createdAt,
        String customerName,
        BigDecimal total
) {
}
```

```java
@Query("""
       select new com.example.demo.order.OrderListItem(
           o.id,
           o.orderNumber,
           o.createdAt,
           c.name,
           o.total
       )
       from Order o
       join o.customer c
       where o.status = :status
       order by o.createdAt desc
       """)
List<OrderListItem> findOrderList(
        @Param("status") OrderStatus status
);
```

Query trả về dữ liệu phẳng cho danh sách. Nếu cần tính tổng từ OrderLine, có thể dùng aggregate query hoặc subquery tùy mô hình; hãy tránh tải toàn bộ collection chỉ để cộng các giá trị trong Java.

Projection không thay thế fetch plan trong mọi trường hợp. Nếu use case cần thao tác trên entity graph hoặc gọi domain method, hãy tải entity và dùng `@EntityGraph` hoặc fetch join để kiểm soát association được nạp.

## 8. Projection và phân trang

Projection có thể kết hợp với `Pageable` để đọc dữ liệu theo từng trang:

```java
@Query("""
       select new com.example.demo.employee.EmployeeListItem(
           e.id,
           e.fullName,
           e.email
       )
       from Employee e
       where e.active = true
       """)
Page<EmployeeListItem> findActiveItems(Pageable pageable);
```

Gọi repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "fullName")
);

Page<EmployeeListItem> page =
        repository.findActiveItems(pageable);
```

Với JPQL DTO projection, Spring Data có thể suy ra count query cho query đơn giản. Nếu query phức tạp, JOIN hoặc GROUP BY, nên khai báo `countQuery` rõ ràng và bảo đảm nó đếm đúng số phần tử logic.

```java
@Query(
    value = """
            select new com.example.demo.employee.EmployeeListItem(
                e.id, e.fullName, e.email
            )
            from Employee e
            where e.department.id = :departmentId
            """,
    countQuery = """
            select count(e)
            from Employee e
            where e.department.id = :departmentId
            """
)
Page<EmployeeListItem> findItemsByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

Phân biệt:

- `Page<T>`: có metadata tổng số phần tử/trang; có thể cần count query.
- `Slice<T>`: cho biết còn trang tiếp theo hay không, không yêu cầu tổng số phần tử.
- `List<T>` với Pageable: lấy phần nội dung giới hạn, không có metadata trang.

Nếu giao diện chỉ cần nút “Xem thêm”, Slice có thể tránh chi phí count. Với dữ liệu rất lớn và phân trang sâu, cân nhắc keyset/scrolling phù hợp với version Spring Data thay vì OFFSET quá lớn.

## 9. Projection không giống EntityGraph hoặc fetch join

Ba kỹ thuật này có mục đích khác nhau:

| Kỹ thuật | Điều khiển điều gì? | Kết quả |
|---|---|---|
| Projection | Hình dạng dữ liệu được trả về | DTO/interface/scalar hoặc kiểu projection |
| EntityGraph | Association nào cần được tải | Entity |
| JOIN FETCH | Tải association trong query | Entity |
| DTO constructor query | Các biểu thức/cột cụ thể được chọn | DTO |

Nếu use case cần entity để cập nhật nhưng muốn tải Department cùng lúc, EntityGraph hoặc fetch join phù hợp:

```java
@EntityGraph(attributePaths = "department")
Optional<Employee> findById(Long id);
```

Nếu use case chỉ cần tên nhân viên và tên phòng ban, DTO projection có thể rõ ràng hơn:

```java
@Query("""
       select new com.example.demo.employee.EmployeeDepartmentRow(
           e.id, e.fullName, d.name
       )
       from Employee e
       join e.department d
       where e.id = :id
       """)
Optional<EmployeeDepartmentRow> findRowById(Long id);
```

Fetch join không đồng nghĩa projection. Nó thay đổi fetch plan của entity; projection thay đổi kiểu dữ liệu được trả về.

## 10. Khi nào vẫn nên tải Entity?

Projection không phải lựa chọn mặc định cho mọi query. Hãy tải entity managed khi:

- Nghiệp vụ cần thay đổi trạng thái entity.
- Cần gọi domain method và bảo vệ invariant.
- Cần cascade hoặc lifecycle callback.
- Cần optimistic locking qua `@Version`.
- Cần làm việc với association như một phần của domain model.
- Cần lưu entity mới hoặc cập nhật entity hiện có theo quy tắc JPA.

Ví dụ cập nhật trạng thái:

```java
@Transactional
public void deactivateEmployee(Long id) {
    Employee employee = repository.findById(id)
            .orElseThrow();

    employee.deactivate();
}
```

Entity được quản lý nên thay đổi được dirty checking khi flush. Dùng một projection chỉ chứa ID và active flag để cập nhật sẽ không tự tạo ra hành vi managed entity.

Nếu chỉ cần cập nhật một vài cột và không cần domain lifecycle, JPQL bulk update có thể phù hợp, nhưng cần xử lý persistence context và optimistic locking riêng. Đây là lựa chọn khác với projection đọc.

## 11. Không dùng Entity làm API response mặc định

Trả entity trực tiếp từ REST controller có thể tạo một số vấn đề:

- API phụ thuộc vào cấu trúc persistence/domain model.
- Thêm thuộc tính entity có thể vô tình thay đổi JSON contract.
- Lazy association có thể phát sinh query ngoài transaction.
- Quan hệ hai chiều có thể tạo vòng lặp serialize.
- Có thể lộ field nội bộ hoặc dữ liệu không dành cho client.
- Entity có thể chứa proxy hoặc trạng thái không phù hợp với serialization.

DTO projection hoặc DTO được map trong service giúp API chỉ công bố trường cần thiết:

```java
public record EmployeeResponse(
        Long id,
        String fullName,
        String email
) {
}
```

Controller:

```java
@RestController
@RequestMapping("/employees")
public class EmployeeController {

    private final EmployeeQueryService queryService;

    public EmployeeController(EmployeeQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping
    public List<EmployeeResponse> list() {
        return queryService.findActiveEmployees();
    }
}
```

DTO không thay thế authorization. Service vẫn phải kiểm tra quyền truy cập và chỉ chọn dữ liệu mà caller được phép xem.

## 12. Những giới hạn và chi phí cần cân nhắc

Projection có thể giảm dữ liệu và object, nhưng cũng có trade-off:

**Query phức tạp hơn.** DTO query có thể cần constructor expression, JOIN và count query. Khi logic thay đổi, query phải được cập nhật cùng DTO.

**Projection lồng nhau khó dự đoán.** Nested interface projection có thể tạo JOIN và tải nhiều dữ liệu hơn mong đợi. Xem SQL thực tế.

**Không có dirty checking.** DTO không thể thay thế entity trong quy trình cập nhật.

**Mapping constructor nhạy với thứ tự/kiểu.** JPQL constructor expression phải khớp constructor chính xác.

**Projection không tự giải quyết N+1 ở mọi trường hợp.** Nếu query lấy entity rồi code truy cập lazy association trong vòng lặp, N+1 vẫn có thể xảy ra. Hãy chọn đúng projection hoặc fetch plan.

**Native query phụ thuộc schema.** Native projection cần alias cột đúng và kiểu dữ liệu tương thích. Với DTO class, việc mapping native result có thể cần constructor mapping hoặc cơ chế mapping riêng tùy query/provider.

**Không phải query ít cột luôn nhanh hơn.** Index, cardinality, sort, join, cache và execution plan vẫn là yếu tố quan trọng. Đo query bằng dữ liệu gần production.

## 13. Kiểm thử projection

Dùng `@DataJpaTest` để xác nhận query trả đúng kiểu và giá trị:

```java
@DataJpaTest
class EmployeeProjectionRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void returnsOnlyEmployeeSummaryFields() {
        repository.save(new Employee(
                "An Nguyen",
                "an@example.com",
                true
        ));

        List<EmployeeSummary> result =
                repository.findByActiveTrue();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFullName()).isEqualTo("An Nguyen");
        assertThat(result.get(0).getEmail()).isEqualTo("an@example.com");
    }
}
```

Test giả định Employee có constructor tương ứng và repository khai báo interface projection như các ví dụ trước. `@DataJpaTest` thường chạy trong transaction và rollback sau test.

Với DTO constructor query, nên kiểm tra:

- Số phần tử và thứ tự kết quả.
- Mỗi giá trị ánh xạ đúng vào constructor argument.
- Kiểu số/ngày/enum tương thích.
- Association optional tạo giá trị null như dự kiến.
- Page content và count query nhất quán.
- Dynamic projection trả đúng loại được yêu cầu.

Để kiểm tra lợi ích hiệu năng, hãy bật SQL logging hoặc dùng datasource/query metrics để xác nhận số cột, số query và lượng dữ liệu. Test assertion đơn thuần không chứng minh query đã tối ưu.

## 14. Ví dụ chọn chiến lược theo use case

| Use case | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Mở trang chi tiết để chỉnh sửa Employee | Entity | Cần domain behavior và dirty checking |
| Danh sách nhân viên chỉ có tên/email | Interface hoặc DTO projection | Chỉ cần vài thuộc tính |
| Báo cáo tổng số nhân viên theo phòng ban | Aggregate DTO projection | Database thực hiện GROUP BY/COUNT |
| API trả một vài trường công khai | DTO projection | Kiểm soát JSON contract |
| Cần entity và Department đã tải | EntityGraph/fetch join | Cần thao tác với entity graph |
| Chọn kiểu kết quả theo caller | Dynamic projection | Tái sử dụng điều kiện query |
| Tải toàn bộ dữ liệu để xử lý domain | Entity | Cần trạng thái và hành vi entity |

Quy tắc thực tế: bắt đầu từ dữ liệu mà use case cần và hành động mà use case thực hiện. Nếu chỉ đọc, chọn projection gọn. Nếu cần thay đổi domain object, tải entity managed. Nếu cần association của entity, điều khiển fetch plan riêng.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Projection trả null ở một getter | Tên getter/property hoặc alias không khớp | Đối chiếu property Java và alias query |
| DTO query lỗi constructor | Sai FQCN, thứ tự hoặc kiểu tham số | Kiểm tra constructor/record canonical constructor |
| Interface projection tải nhiều dữ liệu | Open projection hoặc nested path khó tối ưu | Dùng closed projection hoặc DTO query rõ ràng |
| Không cập nhật được từ projection | Projection không phải entity managed | Tải entity trong transaction để cập nhật |
| Page có total sai | Count query không tương ứng với query projection | Khai báo countQuery chính xác |
| N+1 vẫn xảy ra | Truy cập association lazy ngoài query projection | Dùng DTO join hoặc fetch plan phù hợp |
| JSON lỗi lazy loading | Trả entity/proxy trực tiếp khỏi service | Map sang DTO trong transaction |
| Native projection không ánh xạ | Alias hoặc kiểu cột không khớp | Đặt alias đúng và kiểm thử trên database đích |
| Query không nhanh hơn | Bottleneck nằm ở JOIN/index/sort/database | Đo SQL và execution plan thay vì suy đoán |

## 16. Checklist chọn dữ liệu cần đọc

- [ ] Xác định chính xác màn hình/use case cần những trường nào.
- [ ] Nếu cần domain behavior hoặc cập nhật, tải entity managed.
- [ ] Nếu chỉ đọc, cân nhắc interface, DTO/record hoặc scalar projection.
- [ ] Dùng closed interface projection khi cấu trúc đơn giản.
- [ ] Dùng DTO constructor query khi cần JOIN hoặc kiểm soát cột rõ ràng.
- [ ] Dùng aggregate query khi database có thể tính toán thay ứng dụng.
- [ ] Dùng dynamic projection khi nhiều caller thực sự cần nhiều kiểu kết quả.
- [ ] Phân trang và khai báo count query khi cần.
- [ ] Không nhầm projection với EntityGraph/fetch join.
- [ ] Kiểm tra SQL, N+1, index và execution plan.
- [ ] Trả DTO qua API và kiểm tra authorization.
- [ ] Kiểm thử mapping, null, pagination và query trên provider/database thực tế.

## Kết luận

Không phải mọi use case đều cần một entity đầy đủ. Entity phù hợp khi nghiệp vụ cần trạng thái managed, dirty checking, domain method và lifecycle. Projection phù hợp khi use case chủ yếu đọc một tập trường hoặc giá trị tổng hợp cụ thể.

Spring Data JPA cung cấp interface projection, DTO/record projection, scalar result và dynamic projection. Hãy bắt đầu từ dữ liệu cần dùng, chọn query trả đúng hình dạng đó và đo SQL thực tế. Khi cần cập nhật, quay về entity managed; khi cần tải association, dùng EntityGraph hoặc fetch join theo use case. Cách chọn này giúp giảm dữ liệu dư thừa, giữ API rõ ràng và làm repository dễ bảo trì.
