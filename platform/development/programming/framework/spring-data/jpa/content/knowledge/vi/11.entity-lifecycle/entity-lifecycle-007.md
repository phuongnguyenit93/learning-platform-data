# detach, clear, refresh và khi cần đồng bộ lại trạng thái

## Mục tiêu

JPA quản lý entity thông qua một persistence context (ngữ cảnh lưu trữ). Trong một persistence context, entity đã được nạp hoặc lưu sẽ ở trạng thái managed; thay đổi trên entity managed được JPA theo dõi và có thể được ghi xuống database khi flush.

Ba thao tác `EntityManager.detach`, `EntityManager.clear` và `EntityManager.refresh` điều khiển mối quan hệ giữa object Java đang nằm trong bộ nhớ và dữ liệu trong database:

- `detach(entity)`: ngừng quản lý một entity cụ thể.
- `clear()`: ngừng quản lý tất cả entity trong persistence context.
- `refresh(entity)`: nạp lại trạng thái database của một entity managed, ghi đè trạng thái hiện tại trong bộ nhớ.

Bài này giải thích vòng đời entity, khác biệt giữa ba thao tác, thời điểm sử dụng, ảnh hưởng tới transaction, bulk query, lazy loading và các lỗi thường gặp.

Sau bài này, bạn có thể:

- Phân biệt transient/new, managed, detached và removed.
- Biết thay đổi nào được JPA tự động đồng bộ.
- Dùng detach/clear để kiểm soát persistence context và bộ nhớ.
- Dùng refresh khi cần lấy lại trạng thái đang có trong database.
- Tránh mất thay đổi chưa flush hoặc ghi đè dữ liệu ngoài ý muốn.
- Kết hợp flush/clear/refresh an toàn trong service và batch processing.

Ví dụ dùng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Persistence context và vòng đời entity

Persistence context là tập hợp entity instance mà một EntityManager đang quản lý. Có thể xem nó như một vùng làm việc theo dõi các object Java và trạng thái database tương ứng.

Khi một entity ở trạng thái managed:

- JPA theo dõi thay đổi trên các thuộc tính persistent.
- Entity có identity trong persistence context: cùng một entity/database identity được biểu diễn bằng cùng một managed instance trong context đó.
- Khi flush, JPA đồng bộ thay đổi với database bằng INSERT, UPDATE hoặc DELETE phù hợp.
- Khi transaction commit, các thay đổi đã flush được commit theo transaction.

Bốn trạng thái thường gặp:

| Trạng thái | Ý nghĩa | JPA có tự theo dõi thay đổi không? |
|---|---|---|
| New / transient | Object mới được tạo bằng Java, chưa được persistence context quản lý | Không |
| Managed / persistent | Entity đang được EntityManager quản lý | Có |
| Detached | Entity từng được quản lý nhưng đã rời persistence context | Không |
| Removed | Entity managed đã được đánh dấu xóa | Có, JPA sẽ đồng bộ thao tác DELETE khi flush |

### 1.1. Sơ đồ chuyển trạng thái

<box border radius="lg" padding={3} gap={2}>
  <box background="surface-secondary" radius="md" padding={3} align="center">
    **New / transient**
    <caption color="secondary">new Employee(...)</caption>
  </box>
  <row justify="center">
    <icon name="arrow-down" color="secondary" size="lg"/>
    <caption color="secondary">persist() hoặc save() khi được nhận diện là mới</caption>
  </row>
  <box background="rgba(22,163,74,0.10)" radius="md" padding={3} align="center">
    **Managed**
    <caption color="secondary">Được theo dõi trong persistence context</caption>
  </box>
  <grid columns={2} gap={2}>
    <grid-item>
      <box align="center" gap={1}>
        <icon name="arrow-down" color="secondary"/>
        <caption color="secondary">detach() / clear()</caption>
        <box background="surface-secondary" radius="md" padding={2} width="100%" align="center">
          **Detached**
          <caption color="secondary">Không còn dirty checking</caption>
        </box>
      </box>
    </grid-item>
    <grid-item>
      <box align="center" gap={1}>
        <icon name="arrow-down" color="secondary"/>
        <caption color="secondary">remove()</caption>
        <box background="surface-secondary" radius="md" padding={2} width="100%" align="center">
          **Removed**
          <caption color="secondary">Sẽ bị xóa khi flush</caption>
        </box>
      </box>
    </grid-item>
  </grid>
  <caption color="secondary">Entity detached có thể được merge để tạo một managed instance mới. Entity removed có thể được persist lại theo quy tắc JPA trước khi xóa thực sự xảy ra.</caption>
</box>

### 1.2. Ví dụ entity

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String fullName;

    protected Employee() {
    }

    public Employee(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
```

Trong một service có `@Transactional`, lời gọi `findById` trả về entity managed trong persistence context của transaction. Nếu thay đổi `fullName`, JPA có thể ghi thay đổi khi flush mà không cần gọi `save` lần nữa.

## 2. flush khác commit và clear như thế nào?

Trước khi dùng detach/clear/refresh, cần phân biệt `flush` và commit.

- **Flush**: đồng bộ các thay đổi đang được persistence context theo dõi xuống database bằng SQL. Flush không kết thúc transaction.
- **Commit**: kết thúc transaction thành công và làm cho các thay đổi thuộc transaction được commit.
- **Clear**: loại bỏ tất cả entity đang managed khỏi persistence context; không tự ghi hoặc commit thay đổi.
- **Refresh**: nạp lại trạng thái entity từ database vào một entity đang managed.

Ví dụ:

```java
@Transactional
public void updateEmployee(Long id) {
    Employee employee = repository.findById(id).orElseThrow();

    employee.setFullName("An Nguyen");

    entityManager.flush(); // Gửi UPDATE xuống database.
    // Transaction vẫn đang mở tại đây.

    entityManager.clear(); // Employee không còn managed.
    // Commit chỉ diễn ra khi transaction kết thúc thành công.
}
```

Nếu transaction rollback sau khi flush, các thay đổi SQL thuộc transaction vẫn bị rollback theo cơ chế transaction của database. Flush không đồng nghĩa dữ liệu đã được commit và nhìn thấy từ mọi transaction khác.

JPA có thể tự flush trước một số truy vấn hoặc trước commit tùy flush mode. Vì vậy, đừng dựa vào giả định rằng SQL chỉ được gửi khi gọi rõ `flush()`.

## 3. detach(entity): ngừng quản lý một entity

`EntityManager.detach(entity)` loại bỏ một entity managed cụ thể khỏi persistence context. Sau khi detach:

- Entity trở thành detached.
- Thay đổi trên object không còn được dirty checking tự động.
- Gọi getter/setter vẫn hoạt động trên object Java.
- Thay đổi đó không tự ghi xuống database khi transaction commit.
- Lazy relationship chưa được tải có thể không còn truy cập được sau khi entity detached, tùy provider và trạng thái proxy.

Ví dụ:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void detachExample(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        entityManager.detach(employee);

        employee.setFullName("Changed in memory");
        // Không có UPDATE tự động cho thay đổi sau detach.
    }
}
```

Entity vẫn là object Java bình thường. `detach` không xóa object khỏi bộ nhớ Java, không xóa hàng database và không kết thúc transaction. Nó chỉ ngừng quản lý entity trong persistence context.

### 3.1. Muốn lưu lại entity detached thì làm gì?

Dùng `merge` hoặc `repository.save` theo chiến lược phù hợp:

```java
@Transactional
public Employee updateDetached(Employee detached) {
    Employee managed = entityManager.merge(detached);

    managed.setFullName("Updated through managed instance");

    return managed;
}
```

`merge` sao chép trạng thái của object đầu vào sang một instance managed và trả về instance managed đó. Object đầu vào vẫn detached; hãy tiếp tục dùng giá trị trả về.

Cẩn thận khi merge object nhận từ request chỉ chứa một phần thuộc tính. Merge có thể sao chép các giá trị null/default từ object đầu vào lên entity managed, làm mất dữ liệu nếu object không chứa đầy đủ trạng thái cần thiết. Với cập nhật nghiệp vụ, thường nên tải entity hiện có rồi thay đổi những field được phép.

### 3.2. CascadeType.DETACH

Nếu quan hệ có khai báo `CascadeType.DETACH`, thao tác detach có thể lan tới entity liên quan:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.DETACH
)
@JoinColumn(name = "department_id")
private Department department;
```

Không cần thêm cascade detach cho mọi quan hệ. Chỉ dùng khi vòng đời persistence context của entity liên quan cần được xử lý cùng nhau. `CascadeType.ALL` cũng bao gồm DETACH, nhưng không nên chọn ALL theo thói quen nếu không cần mọi cascade operation.

## 4. clear(): detach toàn bộ persistence context

`EntityManager.clear()` loại bỏ tất cả entity managed khỏi persistence context hiện tại.

Ví dụ:

```java
@Transactional
public void clearExample(Long firstId, Long secondId) {
    Employee first = entityManager.find(Employee.class, firstId);
    Employee second = entityManager.find(Employee.class, secondId);

    first.setFullName("Changed before clear");

    entityManager.flush();
    entityManager.clear();

    Employee reloaded = entityManager.find(Employee.class, firstId);
    // reloaded là managed instance mới trong persistence context hiện tại.
}
```

Sau `clear()`, cả `first` và `second` đều detached. Lần `find` tiếp theo tạo/nạp một managed instance mới trong persistence context hiện tại.

### 4.1. clear không xóa dữ liệu database

Tên phương thức có thể gây nhầm lẫn, nhưng `clear()` không có nghĩa là xóa bảng hoặc xóa dữ liệu. Nó chỉ xóa các entity khỏi persistence context.

| Thao tác | Kết quả |
|---|---|
| `entityManager.clear()` | Detach tất cả entity managed |
| `repository.deleteAll()` | Yêu cầu xóa các entity của repository |
| `entityManager.remove(entity)` | Đánh dấu entity managed để xóa |
| `entityManager.flush()` | Đồng bộ thay đổi xuống database |

### 4.2. clear có thể làm mất thay đổi chưa flush

Đây là điểm cần đặc biệt chú ý.

```java
@Transactional
public void unsafeClear(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    employee.setFullName("New name");

    entityManager.clear();
    // Entity đã detached trước khi thay đổi được flush.
    // Thay đổi "New name" có thể bị mất.
}
```

Nếu muốn giữ các thay đổi đã thực hiện trước khi clear, hãy flush trước:

```java
employee.setFullName("New name");

entityManager.flush();
entityManager.clear();
```

Flush gửi UPDATE xuống database trong transaction. Clear sau đó loại entity khỏi persistence context. Nếu transaction rollback, UPDATE vẫn bị rollback.

### 4.3. Dùng clear trong batch processing

Khi xử lý hàng chục nghìn entity trong một transaction, persistence context có thể giữ nhiều object và snapshot, làm tăng bộ nhớ. Có thể flush và clear theo từng lô:

```java
@Transactional
public void importEmployees(List<EmployeeInput> inputs) {
    int batchSize = 50;
    int count = 0;

    for (EmployeeInput input : inputs) {
        Employee employee = new Employee(input.fullName());
        entityManager.persist(employee);

        count++;

        if (count % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Mẫu này giúp persistence context không tăng mãi theo số lượng entity đã xử lý. Tuy nhiên:

- `clear()` detach mọi entity, không chỉ những entity trong batch vừa xử lý.
- Các object còn giữ trong biến Java vẫn tồn tại nhưng không còn managed.
- Nếu có quan hệ lazy chưa tải, truy cập sau clear có thể gây lỗi.
- Flush không commit. Một transaction rất lớn vẫn có thể giữ lock và log transaction lâu; cân nhắc chia transaction theo batch nếu nghiệp vụ cho phép.
- Với Hibernate, batch insert/update còn cần cấu hình JDBC batching và chiến lược ID phù hợp; flush/clear một mình không bảo đảm một câu SQL batch.

## 5. refresh(entity): nạp lại trạng thái từ database

`EntityManager.refresh(entity)` đọc lại trạng thái database của một entity managed và ghi đè trạng thái hiện tại của object trong persistence context.

Dùng refresh khi:

- Một câu SQL/native query hoặc một tiến trình bên ngoài đã thay đổi hàng mà entity hiện tại đang giữ.
- Trigger hoặc cơ chế database cập nhật giá trị mà ứng dụng cần đọc lại.
- Muốn loại bỏ thay đổi cục bộ chưa flush và lấy lại trạng thái database.
- Cần làm mới entity sau một thao tác persistence đặc biệt.

Ví dụ:

```java
@Transactional
public Employee refreshExample(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    entityManager.refresh(employee);

    return employee;
}
```

Sau refresh, các thuộc tính persistent của `employee` được đồng bộ lại với dữ liệu database nhìn thấy trong transaction hiện tại.

### 5.1. refresh ghi đè thay đổi trong bộ nhớ

Ví dụ:

```java
@Transactional
public void refreshDiscardsLocalChange(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    employee.setFullName("Local unsaved value");

    entityManager.refresh(employee);

    // fullName được nạp lại từ database.
    // Giá trị "Local unsaved value" bị bỏ.
}
```

Nếu thay đổi chưa flush, refresh sẽ ghi đè thay đổi đó. Vì vậy, chỉ refresh khi chủ ý bỏ trạng thái cục bộ hoặc đã đồng bộ các thay đổi cần giữ.

Nếu cần giữ thay đổi của mình trước khi nạp lại, có thể flush trước rồi refresh:

```java
employee.setFullName("An Nguyen");

entityManager.flush();
entityManager.refresh(employee);
```

Trong cùng transaction, refresh sẽ đọc trạng thái database mà transaction hiện tại nhìn thấy, bao gồm các thay đổi đã flush của chính transaction. Refresh không commit transaction.

### 5.2. refresh yêu cầu entity managed

`refresh` được dùng với entity đang managed. Nếu truyền một object detached hoặc new, JPA không thể refresh object đó như một entity đang được quản lý và có thể ném `IllegalArgumentException`.

Nếu entity detached, hãy nạp lại qua repository/EntityManager hoặc merge rồi refresh instance managed trả về:

```java
Employee managed = entityManager.merge(detachedEmployee);
entityManager.refresh(managed);
```

Tuy nhiên, merge trước refresh có thể sao chép trạng thái detached vào managed instance trước khi refresh ghi đè lại. Nếu mục tiêu chỉ là lấy dữ liệu mới nhất, tải lại entity bằng ID thường rõ ràng hơn.

Nếu hàng đã bị xóa trong database hoặc không còn tồn tại trong trạng thái nhìn thấy của transaction, refresh có thể thất bại. Hãy xử lý trường hợp entity không còn tồn tại.

### 5.3. CascadeType.REFRESH

Có thể khai báo cascade refresh:

```java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.REFRESH
)
private List<Employee> employees = new ArrayList<>();
```

Khi refresh Department, thao tác có thể lan tới các Employee liên quan theo cascade. Dùng có chủ đích vì refresh có thể ghi đè thay đổi cục bộ trên cả các entity con đang managed. `CascadeType.ALL` cũng bao gồm REFRESH.

## 6. So sánh detach, clear và refresh

| Thao tác | Phạm vi | Trạng thái sau thao tác | Dữ liệu trong bộ nhớ |
|---|---|---|---|
| `detach(entity)` | Một entity | Entity detached | Giữ nguyên giá trị hiện tại, nhưng không còn dirty checking |
| `clear()` | Toàn persistence context | Tất cả entity managed trở thành detached | Object Java vẫn còn nhưng không còn được theo dõi |
| `refresh(entity)` | Một entity managed, có thể cascade | Entity vẫn managed | Bị ghi đè bằng trạng thái database |

Chọn thao tác theo mục tiêu:

- Muốn ngừng theo dõi một object cụ thể: `detach`.
- Muốn giải phóng toàn bộ managed entities khỏi persistence context: `clear`.
- Muốn nạp lại dữ liệu database cho entity đang managed: `refresh`.
- Muốn lưu thay đổi đang chờ trước khi detach/clear: `flush` trước.
- Muốn cập nhật entity detached thành managed instance: `merge` hoặc tải lại theo ID.

## 7. Khi nào cần đồng bộ lại trạng thái với database?

Persistence context là cache cấp một của EntityManager. Một entity đã managed có thể giữ dữ liệu cũ so với database nếu một thao tác khác thay đổi hàng mà không cập nhật object đang nằm trong context.

Các tình huống thường gặp:

### 7.1. Bulk JPQL update/delete

Bulk update/delete chạy trực tiếp trên database và không cập nhật từng entity instance đang managed trong persistence context.

Ví dụ:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update Employee e
       set e.active = false
       where e.department.id = :departmentId
       """)
int deactivateByDepartmentId(@Param("departmentId") Long departmentId);
```

Ý nghĩa:

- `flushAutomatically = true`: flush các thay đổi đang chờ trước khi chạy bulk query.
- `clearAutomatically = true`: clear persistence context sau khi query chạy để tránh tiếp tục dùng entity instance cũ.

Nếu không clear, entity Employee đã nạp trước bulk update có thể vẫn giữ `active = true` trong bộ nhớ dù database đã chuyển thành false.

Đặt phương thức bulk query trong transaction phù hợp; `@Modifying` không tự thay thế `@Transactional`.

### 7.2. Native SQL hoặc stored procedure

Nếu native SQL/stored procedure cập nhật một hàng mà EntityManager đang quản lý, entity trong persistence context có thể không tự biết thay đổi.

Có thể flush trước nếu cần giữ các thay đổi đang chờ, chạy SQL, sau đó refresh entity cụ thể hoặc clear context rồi tải lại.

Ví dụ nguyên tắc:

```java
entityManager.flush();

entityManager.createNativeQuery("""
    update employees
    set full_name = :name
    where id = :id
    """)
    .setParameter("name", "An Nguyen")
    .setParameter("id", id)
    .executeUpdate();

entityManager.clear();
```

Đoạn mã minh họa quy trình; trong ứng dụng nên đặt trong service có transaction và dùng parameter binding như ví dụ. Clear sẽ detach toàn bộ entity đang managed, vì vậy chỉ dùng khi phù hợp với phạm vi công việc.

### 7.3. Trigger hoặc giá trị database sinh

Database trigger, default expression hoặc computed column có thể cập nhật giá trị sau INSERT/UPDATE. Nếu ứng dụng cần đọc lại giá trị cuối cùng, có thể:

1. Flush để gửi INSERT/UPDATE.
2. Refresh entity để đọc trạng thái database.
3. Hoặc dùng cơ chế mapping/generated property phù hợp với provider và database.

Không cần refresh sau mọi lần save. Chỉ dùng khi có giá trị database tạo/cập nhật mà provider chưa tự đồng bộ vào entity theo mapping hiện tại.

### 7.4. Transaction isolation vẫn có hiệu lực

Refresh đọc dữ liệu mà transaction hiện tại được phép nhìn thấy theo isolation level. Nếu transaction đang chạy ở mức isolation như REPEATABLE READ, refresh có thể vẫn nhìn thấy snapshot cũ dù transaction khác đã commit thay đổi.

Refresh không vượt qua isolation của database và không đảm bảo luôn nhìn thấy mọi thay đổi mới nhất toàn hệ thống. Khi cần dữ liệu mới theo snapshot mới, có thể phải kết thúc transaction hiện tại và bắt đầu transaction khác, tùy yêu cầu nghiệp vụ và isolation level.

## 8. EntityManager trong Spring Data JPA

Trong ứng dụng Spring, thường inject EntityManager bằng `@PersistenceContext`:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameAndRefresh(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("An Nguyen");

        entityManager.flush();
        entityManager.refresh(employee);
    }
}
```

Trong Spring Boot, EntityManager được inject thường là proxy phù hợp với persistence context gắn với transaction hiện tại. Với transaction-scoped persistence context, thao tác refresh yêu cầu transaction đang hoạt động; nếu gọi trong ngữ cảnh không có transaction phù hợp, JPA có thể ném `TransactionRequiredException`.

Các thao tác `detach`, `clear` và `refresh` không thay thế transaction. Chúng điều khiển trạng thái persistence context bên trong vòng đời transaction.

## 9. Ví dụ đầy đủ: detach và merge

```java
@Service
public class EmployeeLifecycleService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Employee renameThenDetach(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("Changed before detach");
        entityManager.flush();

        entityManager.detach(employee);

        employee.setFullName("Changed after detach");
        // Thay đổi sau detach không được dirty checking.

        Employee managed = entityManager.merge(employee);
        // merge trả về managed instance.
        return managed;
    }
}
```

Trong ví dụ:

- Thay đổi đầu tiên được flush xuống database.
- Sau detach, entity không còn managed.
- Thay đổi thứ hai chỉ nằm trong object Java.
- Merge sao chép trạng thái object detached vào một instance managed.
- Instance trả về từ merge là object cần dùng tiếp trong transaction.

Lưu ý rằng merge sao chép trạng thái của entity detached. Nếu object chứa dữ liệu cũ hoặc null ở những field không được gửi từ client, merge có thể ghi đè giá trị hiện có. Trong nghiệp vụ cập nhật, cách an toàn thường là tải entity managed rồi chỉ sửa các thuộc tính được phép.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Thay đổi object không được lưu | Entity đã detached hoặc chưa managed | Tải entity trong transaction hoặc merge và dùng instance trả về |
| Mất thay đổi sau clear | Clear trước khi flush | Flush trước clear nếu cần giữ thay đổi |
| Giá trị trong bộ nhớ quay về dữ liệu cũ | Refresh ghi đè thay đổi cục bộ | Chỉ refresh khi chủ ý nạp lại; flush trước nếu cần giữ thay đổi |
| Refresh ném IllegalArgumentException | Entity không managed hoặc không còn tồn tại | Tải lại entity theo ID hoặc merge rồi refresh instance managed |
| LazyInitializationException sau detach | Lazy association chưa được tải và context đã đóng | Fetch trước khi detach hoặc ánh xạ DTO trong transaction |
| Entity cũ sau bulk update | Bulk query không đồng bộ managed entities | Dùng flush/clear hoặc refresh phù hợp |
| Clear làm các object khác mất dirty checking | Clear detach toàn bộ context | Chỉ clear khi đã xử lý mọi thay đổi cần giữ |
| Dữ liệu refresh vẫn cũ | Isolation level giữ snapshot | Kết thúc transaction và đọc lại trong transaction mới khi cần snapshot mới |

## 11. Checklist chọn thao tác

- [ ] Entity đang managed hay detached?
- [ ] Có thay đổi nào chưa flush cần giữ không?
- [ ] Muốn detach một entity hay toàn bộ persistence context?
- [ ] Muốn nạp lại database state hay chỉ dừng dirty checking?
- [ ] Có bulk JPQL/native SQL hoặc trigger làm dữ liệu trong context cũ không?
- [ ] Lazy relationship nào sẽ cần truy cập sau detach/clear?
- [ ] Transaction và isolation level hiện tại có đáp ứng yêu cầu đọc dữ liệu không?
- [ ] Có thể dùng DTO/fetch query thay vì giữ entity graph lâu không?

## Kết luận

`detach(entity)` ngừng quản lý một entity; `clear()` ngừng quản lý toàn bộ entity trong persistence context; `refresh(entity)` nạp lại trạng thái database và ghi đè trạng thái hiện tại của entity managed. Flush đồng bộ thay đổi xuống database nhưng không commit transaction.

Hãy dùng detach/clear khi cần kiểm soát persistence context hoặc xử lý batch, và dùng refresh khi có thay đổi ngoài context cần phản ánh vào entity đang managed. Trước khi detach/clear, xác định rõ thay đổi chưa flush; trước khi refresh, xác định rõ thay đổi trong bộ nhớ có thể bị ghi đè. Hiểu các ranh giới này giúp tránh mất dữ liệu, lỗi lazy loading và trạng thái entity không đồng bộ.
