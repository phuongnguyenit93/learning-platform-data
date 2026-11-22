# Rủi ro xóa dây chuyền và cập nhật dư thừa ở quan hệ lớn

## 1. Vấn đề khi một quan hệ có nhiều phần tử

Một entity cha có thể quản lý hàng trăm, hàng nghìn hoặc hàng triệu entity con. Ví dụ Department có rất nhiều Employee, Order có nhiều OrderLine hoặc một tài khoản có nhiều bản ghi lịch sử. Khi collection lớn, thao tác tưởng như đơn giản như xóa parent, gỡ một child hay thay đổi thứ tự có thể tạo ra lượng SQL lớn.

Các nguyên nhân thường gặp:

- Cascade remove truyền thao tác xóa từ parent xuống toàn bộ child.
- Orphan removal xóa child khi child bị gỡ khỏi association.
- ORM phải tải collection để xác định phần tử nào đã thay đổi.
- Mapping một chiều qua join table có thể khiến provider xóa và tạo lại nhiều hàng liên kết.
- Quan hệ hai chiều không được đồng bộ đúng phía sở hữu, dẫn đến trạng thái object không khớp với foreign key.
- Order column có thể yêu cầu cập nhật vị trí của nhiều phần tử sau khi xóa một phần tử.
- Nhiều tầng cùng thay đổi association có thể tạo thao tác lặp hoặc UPDATE không cần thiết.

Cần phân biệt hai mục tiêu: bảo toàn tính đúng đắn của vòng đời entity và tối ưu số câu SQL. Cascade và orphan removal giúp mô hình hóa vòng đời; chúng không tự động là giải pháp hiệu quả cho thao tác dữ liệu khối lượng lớn.

## 2. Phân biệt Cascade, orphanRemoval và ON DELETE CASCADE

Ba cơ chế này có tên gần giống nhau nhưng hoạt động ở các tầng khác nhau.

### 2.1. Cascade trong JPA

Cascade quy định một thao tác trên entity có được lan truyền tới entity liên quan hay không.

| Cascade type | Ý nghĩa |
|---|---|
| PERSIST | Persist parent có thể persist entity liên quan |
| MERGE | Merge parent có thể merge entity liên quan |
| REMOVE | Remove parent có thể remove entity liên quan |
| REFRESH | Refresh parent có thể refresh entity liên quan |
| DETACH | Detach parent có thể detach entity liên quan |
| ALL | Bao gồm tất cả các loại trên |

Ví dụ:

```java
@OneToMany(
    mappedBy = "department",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<Employee> employees = new ArrayList<>();
```

Nếu gọi entityManager.persist(department), thao tác persist có thể lan tới các Employee trong collection. Nhưng cấu hình trên không có CascadeType.REMOVE, nên xóa Department không tự động xóa Employee thông qua cascade này.

Cascade là quy tắc của persistence provider. Khi cascade remove, provider thường phải xử lý vòng đời từng entity liên quan; tùy mapping, provider và cấu hình, việc này có thể cần tải collection và phát ra nhiều lệnh DELETE.

### 2.2. orphanRemoval

orphanRemoval = true mô tả vòng đời child phụ thuộc parent. Khi child bị gỡ khỏi association được quản lý, JPA đánh dấu child để xóa khi đồng bộ persistence context.

```java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<Employee> employees = new ArrayList<>();
```

Ví dụ:

```java
department.removeEmployee(employee);
entityManager.flush();
```

Nếu Employee thực sự thuộc vòng đời của Department và đã bị gỡ khỏi quan hệ, provider sẽ xóa Employee. Orphan removal phù hợp với child không có ý nghĩa độc lập sau khi tách khỏi parent.

Không dùng orphan removal chỉ vì muốn tự động dọn dữ liệu. Nếu child được chia sẻ, có vòng đời riêng hoặc cần chuyển sang parent khác, xóa orphan có thể làm mất dữ liệu hợp lệ. Với quan hệ lớn, xóa hàng loạt child khỏi collection cũng có thể tạo ra rất nhiều thao tác xóa.

### 2.3. ON DELETE CASCADE ở database

Đây là hành vi của foreign key constraint trong database:

```sql
alter table employee
add constraint fk_employee_department
foreign key (department_id)
references department(id)
on delete cascade;
```

Khi database xóa một hàng Department, database tự xóa các hàng Employee tham chiếu tới Department đó. Việc này diễn ra bên trong database, không cần Hibernate tải từng Employee thành entity trước.

Sự khác biệt quan trọng:

| Cơ chế | Tầng thực thi | Có cần entity child được quản lý? | Lifecycle callback JPA |
|---|---|---|---|
| CascadeType.REMOVE | JPA provider | Thường cần xử lý entity liên quan | Có thể được thực thi theo vòng đời entity |
| orphanRemoval | JPA provider | Child được phát hiện là orphan trong association | Theo vòng đời remove của entity |
| ON DELETE CASCADE | Database | Không cần ORM tải child | Không gọi callback JPA cho từng child bị database xóa |

Database cascade thường hiệu quả với số lượng child rất lớn. Tuy nhiên, persistence context hoặc second-level cache của ORM có thể không biết những child nào đã bị database xóa. Cần quản lý trạng thái cache và entity đang được giữ trong bộ nhớ.

Hibernate có annotation provider-specific OnDelete để khai báo hành vi xóa ở foreign key. Nếu dùng annotation này với schema do Flyway/Liquibase quản lý, migration vẫn phải tạo constraint ON DELETE CASCADE thực tế. Không giả định annotation tự sửa một schema production đã tồn tại.

## 3. Cascade remove có thể gây tốn kém như thế nào?

Giả sử một Department có 50.000 Employee và mapping:

```java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<Employee> employees = new ArrayList<>();
```

Khi xóa Department, provider cần bảo đảm semantics cascade remove và orphan removal. Tùy mapping và Hibernate version, provider có thể phải tải hoặc duyệt collection, quản lý trạng thái các entity con và phát ra nhiều câu DELETE.

Những chi phí có thể xuất hiện:

- Nhiều câu SELECT để tải collection hoặc kiểm tra trạng thái.
- Nhiều entity được đưa vào persistence context.
- Tốn bộ nhớ cho entity, collection wrapper và snapshot dirty checking.
- Nhiều câu DELETE ở cấp entity.
- Nhiều callback hoặc listener được thực thi.
- Transaction kéo dài, giữ connection và lock lâu hơn.
- Tăng thời gian flush và nguy cơ timeout.

Không phải mọi cascade remove đều chắc chắn phát ra đúng một câu SELECT cộng N câu DELETE; SQL phụ thuộc mapping, provider, database và khả năng tối ưu. Tuy nhiên, cần giả định thao tác entity-by-entity có thể đắt khi collection rất lớn và đo SQL thực tế trước khi chọn cách triển khai.

### 3.1. Cascade phù hợp với aggregate nhỏ và vừa

Cascade remove là lựa chọn hợp lý khi:

- Child thực sự phụ thuộc vòng đời parent.
- Số lượng child có giới hạn thực tế.
- Nghiệp vụ cần callback, validation hoặc audit ở từng entity.
- Các thay đổi phải được quản lý trong persistence context.
- Xóa từng child là một phần của hành vi domain.

Ví dụ, Order có vài chục OrderLine. Xóa Order và các dòng hàng có thể là một thao tác aggregate tự nhiên.

### 3.2. Cascade không phải công cụ bulk delete

Khi cần xóa hàng trăm nghìn bản ghi, hãy cân nhắc thao tác theo tập hợp ở database thay vì tạo và remove từng entity. Nếu chuyển sang bulk delete, phải hiểu rằng bulk operation bỏ qua cascade và lifecycle callback của JPA. Đây là đánh đổi về semantics, không chỉ là cách viết SQL nhanh hơn.

## 4. Cập nhật dư thừa ở quan hệ hai chiều

### 4.1. Phía sở hữu quyết định foreign key

Với mapping:

```java
@Entity
class Department {

    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();
}

@Entity
class Employee {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;
}
```

Employee.department là owning side vì nó ánh xạ cột department_id. Department.employees là inverse side.

Nếu chỉ thay đổi collection inverse:

```java
department.getEmployees().add(employee);
```

thì foreign key có thể không được cập nhật như mong đợi. Cần thay đổi owning side:

```java
employee.setDepartment(department);
```

Trong quan hệ hai chiều, helper method nên đồng bộ cả hai phía trong bộ nhớ:

```java
public void addEmployee(Employee employee) {
    employees.add(employee);
    employee.setDepartment(this);
}

public void removeEmployee(Employee employee) {
    employees.remove(employee);
    employee.setDepartment(null);
}
```

Nếu helper được gọi nhiều lần hoặc logic ở nhiều tầng cùng cập nhật association, có thể phát sinh thao tác lặp, trạng thái collection khó dự đoán hoặc UPDATE không cần thiết. Hãy tập trung việc thay đổi quan hệ vào một phương thức domain rõ ràng.

### 4.2. INSERT rồi UPDATE do gán quan hệ quá muộn

Một luồng tạo dữ liệu có thể vô tình thực hiện:

1. Persist Employee khi department còn null.
2. Sau đó mới gán department.
3. Flush lần nữa.

Database có thể nhận INSERT với department_id null rồi UPDATE department_id. Nếu biết parent ngay từ đầu, hãy gán quan hệ trước khi persist:

```java
Employee employee = new Employee("An");
employee.setDepartment(department);
entityManager.persist(employee);
```

Khi persist và flush, provider có thể tạo INSERT chứa department_id ngay từ đầu. SQL cụ thể còn phụ thuộc ID generation, cascade và thứ tự flush, nhưng xây dựng object graph đầy đủ trước khi persist thường tránh được một lần cập nhật không cần thiết.

### 4.3. Không cập nhật collection và setter một cách phân tán

Tránh để controller, service, mapper và repository cùng sửa hai phía của association. Một nơi nên chịu trách nhiệm thay đổi quan hệ và duy trì invariant. Nếu nhiều tầng cùng gọi setter hoặc thêm/xóa phần tử, rất khó biết khi nào Hibernate đánh dấu collection dirty.

## 5. Rủi ro của OneToMany một chiều dùng JoinTable

Một mapping một chiều thường gặp:

```java
@OneToMany
@JoinTable(
    name = "department_employee",
    joinColumns = @JoinColumn(name = "department_id"),
    inverseJoinColumns = @JoinColumn(name = "employee_id")
)
private List<Employee> employees = new ArrayList<>();
```

Khi association được lưu trong join table, provider phải đồng bộ các hàng liên kết. Với một số mapping OneToMany một chiều qua association table trong Hibernate, khi xóa một phần tử khỏi collection, Hibernate có thể xóa các hàng liên kết của parent rồi insert lại các hàng còn lại. Điều này làm thao tác xóa một child trở thành O(N) thao tác dữ liệu liên kết.

Hành vi cụ thể phụ thuộc loại collection, mapping và phiên bản provider; không nên giả định mọi OneToMany JoinTable đều phát SQL giống nhau. Hãy bật SQL logging trong môi trường test và kiểm tra số lệnh khi thêm hoặc xóa một phần tử.

Nếu mỗi child thuộc tối đa một parent và schema cho phép, mapping ManyToOne ở child với foreign key trực tiếp thường dễ tối ưu hơn. Nếu cần join table, cân nhắc association entity khi quan hệ lớn hoặc cần cập nhật từng association.

## 6. Collection lớn và OrderColumn

### 6.1. Xóa một phần tử có thể cập nhật vị trí của nhiều phần tử

Khi dùng:

```java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "line_position")
private List<OrderLine> lines = new ArrayList<>();
```

database lưu thêm chỉ số vị trí. Nếu xóa phần tử ở đầu danh sách, các phần tử phía sau có thể phải dịch vị trí để duy trì thứ tự liên tục. Với danh sách lớn, một thao tác xóa có thể tạo nhiều UPDATE.

Nếu thứ tự chỉ cần ổn định khi đọc mà không cần lưu vị trí liên tục, cân nhắc @OrderBy theo một thuộc tính có index. @OrderBy sắp xếp kết quả truy vấn, không duy trì cột thứ tự riêng như @OrderColumn.

Nếu thứ tự là dữ liệu nghiệp vụ thực sự, chấp nhận chi phí cập nhật và thiết kế cách sắp xếp lại có kiểm soát. Đừng dùng @OrderColumn chỉ vì muốn collection Java có thứ tự.

### 6.2. List, Set và tính duy nhất

Set có thể ngăn phần tử trùng theo equals/hashCode trong bộ nhớ, nhưng không thay thế unique constraint ở database. Nếu hai transaction cùng thêm liên kết, database constraint mới là hàng rào cuối cùng.

Set yêu cầu equals/hashCode ổn định. Với entity có generated ID, ID có thể null trước persist rồi thay đổi sau persist; implementation sai có thể làm phần tử không tìm thấy trong HashSet. Không chọn Set chỉ để tối ưu hiệu năng nếu chưa giải quyết đúng identity semantics.

List phù hợp khi cần thứ tự hoặc chấp nhận phần tử lặp theo mô hình. Nếu thứ tự không có ý nghĩa, collection khác có thể biểu đạt ý định tốt hơn. Cần chọn dựa trên semantics và SQL provider sinh ra, không chỉ dựa vào cấu trúc Java.

## 7. Xóa khối lượng lớn bằng bulk operation

### 7.1. JPQL bulk delete

Khi nghiệp vụ cho phép xóa theo điều kiện và không cần xử lý từng entity, JPQL bulk delete có thể thực hiện một câu lệnh ở database:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    delete from Employee e
    where e.department.id = :departmentId
    """)
int deleteAllByDepartmentId(
    @Param("departmentId") Long departmentId
);
```

Phương thức này cần chạy trong transaction. flushAutomatically yêu cầu flush các thay đổi đang chờ trước bulk query. clearAutomatically clear persistence context sau query để tránh tiếp tục dùng entity cũ trong bộ nhớ.

Bulk JPQL:
- Thực thi theo tập hợp ở database.
- Không tải từng Employee thành entity managed.
- Không thực thi CascadeType.REMOVE cho từng entity.
- Không áp dụng orphanRemoval như thao tác remove từng entity.
- Không gọi lifecycle callback @PreRemove/@PostRemove cho từng entity.
- Có thể để lại entity đang managed với trạng thái cũ nếu không clear hoặc refresh.

Chỉ dùng khi nghiệp vụ chấp nhận bỏ qua xử lý vòng đời ở từng entity và có cách xử lý các quan hệ phụ thuộc.

### 7.2. Bulk delete phải xử lý foreign key

Nếu Employee còn được tham chiếu bởi bảng khác, database có thể từ chối DELETE do foreign key constraint. Cần xác định thứ tự xóa hoặc thiết kế ON DELETE CASCADE phù hợp.

Không mặc định bulk delete parent sẽ tự lan truyền qua cascade JPA. Bulk JPQL không thực hiện cascade remove của persistence provider. Nếu database có ON DELETE CASCADE thì database tự xử lý, nhưng đó là cơ chế riêng.

### 7.3. Spring Data derived delete và bulk delete khác nhau

Một derived delete method có thể được Spring Data triển khai bằng cách tìm entity rồi xóa từng instance để giữ semantics lifecycle. Một phương thức @Modifying với JPQL DELETE thường thực thi bulk query trực tiếp.

Không đánh đồng hai cách chỉ vì tên method đều có chữ delete. Hãy kiểm tra loại query được tạo và semantics của API cụ thể.

### 7.4. Xóa theo lô khi cần lifecycle

Nếu bắt buộc gọi callback hoặc cascade ở từng entity nhưng dữ liệu quá lớn, có thể xử lý theo batch:

1. Lấy một nhóm ID hoặc entity có giới hạn.
2. Xóa nhóm đó trong transaction.
3. Flush và clear persistence context.
4. Tiếp tục batch tiếp theo.

Cách này giảm lượng object tồn tại trong bộ nhớ và giới hạn thời gian transaction. Tuy nhiên, nó vẫn xử lý từng entity và có thể tốn nhiều round-trip hơn bulk SQL. Cần xác định tính nguyên tử: nhiều batch transaction có thể khiến một phần thao tác đã commit nếu batch sau thất bại.

## 8. Dùng database ON DELETE CASCADE đúng cách

Nếu child hoàn toàn phụ thuộc parent và số lượng child lớn, database cascade có thể là lựa chọn hiệu quả:

```sql
alter table employee
add constraint fk_employee_department
foreign key (department_id)
references department(id)
on delete cascade;
```

Sau đó, xóa Department có thể để database tự xóa Employee. Database thực thi hành động trong cùng lệnh xóa parent, thường hiệu quả hơn việc ORM tải và xóa từng child.

Nhưng cần chú ý:
- Database cascade không gọi JPA lifecycle callbacks cho từng child.
- Entity child đang nằm trong persistence context có thể trở nên stale.
- Second-level cache hoặc query cache có thể cần eviction/invalidation.
- Các bảng phụ thuộc khác phải có constraint phù hợp.
- Migration phải tạo đúng ON DELETE CASCADE; mapping Java không tự chứng minh schema đã có constraint.
- Nếu dùng Hibernate @OnDelete, đây là tính năng riêng của Hibernate, cần kiểm tra tài liệu phiên bản đang dùng.

Không nên kết hợp tùy tiện ORM cascade remove và database cascade cho cùng một thao tác. Nếu ORM đã xóa child trước, database cascade có thể không còn gì để xử lý; nếu database xóa ngầm, ORM có thể giữ trạng thái child cũ. Hãy chọn một chiến lược xóa chủ đạo cho use case và test rõ hành vi.

## 9. Giảm chi phí cập nhật collection lớn

### 9.1. Không tải collection chỉ để đếm

Thao tác department.getEmployees().size() có thể kích hoạt tải toàn bộ collection nếu collection chưa được khởi tạo. Với collection lớn, chỉ cần đếm thì dùng truy vấn COUNT:

```java
@Query("""
    select count(e)
    from Employee e
    where e.department.id = :departmentId
    """)
long countByDepartmentId(@Param("departmentId") Long departmentId);
```

Database có thể tính COUNT mà không truyền toàn bộ entity qua JDBC. Hiệu quả còn phụ thuộc index và execution plan.

### 9.2. Cập nhật theo ID thay vì load toàn bộ graph

Nếu use case chỉ gán một Employee vào Department, truy vấn Employee theo ID rồi cập nhật owning side. Không cần tải toàn bộ Department.employees chỉ để thêm một phần tử.

Nếu collection đã được tải và managed, hãy dùng helper method nhất quán. Nếu collection lớn và thao tác đơn lẻ, thiết kế repository/service theo ID có thể tránh hydrate cả collection.

### 9.3. Batch JDBC của Hibernate

Hibernate có thể gom các câu INSERT/UPDATE/DELETE thành JDBC batch:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
```

Batch size là số lệnh được gom trong một batch gửi qua JDBC; giá trị phù hợp cần đo trên database và driver thực tế. order_inserts và order_updates giúp sắp xếp lệnh theo entity/table để tăng khả năng gom batch.

Lưu ý:
- ID generation kiểu IDENTITY thường hạn chế khả năng batch INSERT của Hibernate vì cần nhận ID ngay sau từng insert.
- Batch giảm round-trip nhưng không biến N thao tác entity thành một câu SQL set-based.
- Batch delete vẫn cần xử lý entity/cascade theo semantics ORM.
- Driver và database có thể có giới hạn hoặc hành vi riêng.
- Theo dõi số SQL và thời gian flush để xác nhận batch thực sự hoạt động.

### 9.4. Flush và clear theo batch

Với tác vụ tạo hoặc cập nhật nhiều entity, có thể định kỳ flush rồi clear:

```java
for (int i = 0; i < employees.size(); i++) {
    entityManager.persist(employees.get(i));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
```

Đây là mẫu minh họa cho batch insert. Sau clear, các entity trước đó trở thành detached; không tiếp tục giả định chúng còn managed. Với quan hệ phức tạp, cần quản lý ID và tham chiếu giữa các batch cẩn thận.

Flush đồng bộ SQL xuống database nhưng không commit transaction. Clear giải phóng persistence context; nó không rollback dữ liệu đã flush. Nếu tất cả batch nằm trong một transaction dài, transaction vẫn giữ tài nguyên cho tới khi kết thúc.

## 10. Association entity cho quan hệ lớn hoặc có metadata

Khi quan hệ có dữ liệu riêng, ví dụ ngày phân công, trạng thái, vai trò, người tạo hoặc thời gian hết hiệu lực, hãy biến association thành entity:

```java
@Entity
@Table(name = "department_assignment")
public class DepartmentAssignment {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "employee_id", nullable = false)
    private Employee employee;

    @Column(nullable = false)
    private LocalDate assignedAt;

    protected DepartmentAssignment() {
    }
}
```

Cách này cho phép truy vấn, thêm và xóa từng association bằng ID mà không cần hydrate toàn bộ collection trên parent. Nó cũng tạo chỗ đặt unique constraint, index và lifecycle riêng.

Nếu một Employee chỉ được có một assignment hiện hành, có thể đặt unique constraint trên employee_id. Nếu cần lưu lịch sử, mô hình có thể dùng effective_from/effective_to hoặc trạng thái và constraint phù hợp. Thiết kế phải phản ánh quy tắc nghiệp vụ thật.

## 11. Kiểm tra SQL thay vì đoán

Khi tối ưu quan hệ lớn, bật SQL log trong môi trường local/test:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Bind logging có thể lộ dữ liệu nhạy cảm, chỉ bật có kiểm soát và không để ở production.

Đo các tình huống cụ thể:
- Xóa một child khỏi collection.
- Xóa parent có ít child.
- Xóa parent có collection lớn.
- Chuyển child từ parent này sang parent khác.
- Thêm nhiều child mới.
- Xóa bằng bulk JPQL.
- Xóa bằng database ON DELETE CASCADE.

Quan sát:
- Số câu SELECT và DELETE.
- Có câu UPDATE dư thừa hay không.
- Có xóa rồi insert lại toàn bộ join table rows hay không.
- Collection có bị tải toàn bộ không.
- Có nhiều UPDATE do OrderColumn hay không.
- Batch có thực sự được gửi tới JDBC driver không.
- Transaction duration, lock và số hàng bị ảnh hưởng.

Test nên chạy trên database cùng loại với production nếu hành vi phụ thuộc dialect, constraint, cascade hoặc execution plan. H2 hữu ích cho test nhanh nhưng không thay thế được integration test trên database thực tế.

## 12. Checklist lựa chọn chiến lược

- [ ] Child có thực sự phụ thuộc vòng đời parent không?
- [ ] Số lượng child tối đa có giới hạn rõ ràng không?
- [ ] Có cần lifecycle callback hoặc xử lý nghiệp vụ cho từng child không?
- [ ] Cascade REMOVE và orphanRemoval có đúng với quyền sở hữu domain không?
- [ ] Có thể dùng database ON DELETE CASCADE cho thao tác xóa khối lượng lớn không?
- [ ] Nếu dùng bulk JPQL, đã xử lý persistence context và cache chưa?
- [ ] Mapping có tạo join table không cần thiết hoặc thao tác delete/reinsert lớn không?
- [ ] Có OrderColumn khiến nhiều vị trí phải cập nhật không?
- [ ] Có thể truy vấn COUNT hoặc cập nhật theo ID thay vì tải collection không?
- [ ] Đã đo JDBC batch và SQL thực tế chưa?
- [ ] Foreign key, unique constraint và index đã được định nghĩa trong schema chưa?
- [ ] Nếu xóa theo nhiều batch, tính nguyên tử và khả năng resume đã rõ chưa?

## 13. Kết luận

Cascade remove và orphanRemoval hữu ích khi child thực sự thuộc vòng đời parent và số lượng association nằm trong mức có thể quản lý bằng ORM. Với collection lớn, các cơ chế này có thể kéo theo tải entity, nhiều lệnh DELETE, callback, dirty checking và transaction dài.

Foreign key mapping thường đơn giản hơn cho quan hệ một-nhiều; join table, collection ordering và cách provider đồng bộ collection có thể tạo thêm nhiều thao tác. Khi workload lớn, hãy cân nhắc bulk JPQL, database ON DELETE CASCADE, batch xử lý hoặc association entity. Mỗi lựa chọn có semantics khác nhau: bulk query bỏ qua cascade/lifecycle callback, còn database cascade không tự đồng bộ persistence context và cache của Hibernate.

Quyết định đúng cần dựa trên vòng đời domain, quy mô dữ liệu và SQL thực tế. Hãy chọn chiến lược xóa/cập nhật rõ ràng, đặt constraint tại database, quản lý trạng thái ORM sau bulk operation và kiểm thử trên database tương ứng với môi trường triển khai.