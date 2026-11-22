# flush, saveAndFlush và saveAllAndFlush

## Mục tiêu

Trong JPA, thay đổi trên entity đang được quản lý thường được theo dõi trong persistence context và đồng bộ xuống database khi flush. Spring Data JPA cung cấp các phương thức `flush()`, `saveAndFlush(entity)` và `saveAllAndFlush(entities)` để ứng dụng chủ động yêu cầu đồng bộ ở những thời điểm cần thiết.

Ba phương thức có vai trò khác nhau:

- `flush()`: đồng bộ tất cả thay đổi đang chờ trong persistence context xuống database.
- `saveAndFlush(entity)`: lưu một entity theo cơ chế của repository, sau đó flush persistence context.
- `saveAllAndFlush(entities)`: lưu một nhóm entity, sau đó flush persistence context.

Flush không kết thúc transaction và không đồng nghĩa commit. Hiểu rõ ranh giới này giúp xác định đúng thời điểm SQL được gửi, phát hiện lỗi constraint sớm, đọc lại dữ liệu trong cùng transaction và tối ưu xử lý nhiều bản ghi.

Sau bài này, bạn có thể phân biệt save, flush và commit; chọn giữa save, saveAndFlush và saveAllAndFlush; biết flush ảnh hưởng tới toàn bộ persistence context; hiểu khi nào lỗi database xuất hiện; dùng flush đúng trong transaction, test và batch processing; tránh giả định saveAllAndFlush luôn tạo một câu SQL bulk insert.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Persistence context và thời điểm ghi SQL

JPA quản lý các entity thông qua persistence context. Khi entity đang ở trạng thái managed, provider theo dõi thay đổi trên các thuộc tính persistent. Cơ chế này gọi là dirty checking.

Ví dụ:

```java
@Transactional
public void renameEmployee(Long id) {
    Employee employee = employeeRepository.findById(id)
            .orElseThrow();

    employee.setFullName("An Nguyen");
    // Chưa cần gọi save() lần nữa.
}
```

Khi transaction kết thúc thành công, JPA sẽ flush các thay đổi cần thiết trước khi commit. Provider tạo SQL tương ứng, ví dụ UPDATE employees, rồi database thực thi câu lệnh trong transaction.

Ta cần phân biệt ba thời điểm:

1. **Thay đổi object:** Java object managed thay đổi trong bộ nhớ.
2. **Flush:** JPA đồng bộ thay đổi của persistence context với database bằng SQL.
3. **Commit:** database xác nhận transaction thành công và các thay đổi trở thành dữ liệu đã commit.

```text
Thay đổi entity managed
        |
        v
Persistence context ghi nhận thay đổi
        |
        | flush()
        v
SQL được gửi tới database
        |
        | commit transaction
        v
Transaction hoàn tất thành công
```

Flush không làm transaction kết thúc. Nếu transaction rollback sau khi flush, các thay đổi SQL thuộc transaction đó vẫn bị rollback.

## 2. flush(): đồng bộ persistence context

`EntityManager.flush()` yêu cầu JPA đồng bộ trạng thái của persistence context hiện tại xuống database. Spring Data JPA cung cấp phương thức tương ứng trên `JpaRepository`:

```java
void flush();
```

Ví dụ:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void updateAndFlush(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("An Nguyen");

        entityManager.flush();
        // UPDATE được gửi tới database trong transaction hiện tại.
        // Transaction vẫn tiếp tục chạy sau dòng này.
    }
}
```

### 2.1. Flush áp dụng cho entity nào?

Flush không chỉ ghi entity mà ta vừa gọi `save` hoặc entity được truyền vào một phương thức cụ thể. Nó đồng bộ các thay đổi cần thiết của toàn bộ persistence context.

```java
@Transactional
public void flushAllPendingChanges(Long firstId, Long secondId) {
    Employee first = employeeRepository.findById(firstId).orElseThrow();
    Employee second = employeeRepository.findById(secondId).orElseThrow();

    first.setFullName("First updated");
    second.setFullName("Second updated");

    employeeRepository.flush();
}
```

Cả hai thay đổi đều có thể được gửi xuống database khi flush. Các entity managed khác có thay đổi trong cùng persistence context cũng có thể được đồng bộ.

Vì vậy, flush là thao tác ở cấp persistence context, không phải lệnh chỉ ghi một entity.

### 2.2. Flush không phải commit

Sau khi flush:

- SQL đã được gửi tới database và được thực thi trong transaction hiện tại.
- Các constraint có thể được kiểm tra và lỗi có thể xuất hiện.
- Transaction vẫn mở nếu đang được quản lý bởi một transaction bên ngoài.
- Transaction khác thường chưa nhìn thấy thay đổi chưa commit, tùy isolation level và database.
- Rollback vẫn có thể hoàn tác các thay đổi đã flush.

Ví dụ:

```java
@Transactional
public void flushThenFail(Long id) {
    Employee employee = employeeRepository.findById(id).orElseThrow();

    employee.setFullName("Temporary name");
    employeeRepository.flush();

    throw new IllegalStateException("Cancel operation");
}
```

Nếu exception làm transaction rollback, UPDATE đã flush cũng bị rollback. Việc SQL đã chạy không có nghĩa dữ liệu đã được commit.

### 2.3. Khi nào JPA tự flush?

Không phải lúc nào ứng dụng cũng cần gọi `flush()` thủ công. Với flush mode mặc định `AUTO`, JPA có thể tự flush tại những thời điểm cần bảo đảm kết quả truy vấn nhất quán, ví dụ trước một query có thể bị ảnh hưởng bởi thay đổi đang chờ, và trước khi transaction commit.

Các flush mode:

- `FlushModeType.AUTO`: provider phải bảo đảm các thay đổi có liên quan được phản ánh trong kết quả truy vấn; provider có thể flush vào thời điểm phù hợp.
- `FlushModeType.COMMIT`: provider được phép trì hoãn flush cho tới commit, nhưng vẫn có thể flush sớm trong một số tình huống.

Không nên dựa vào một lịch flush cụ thể ngoài hợp đồng JPA. Nếu cần SQL được gửi trước một thao tác tiếp theo hoặc cần phát hiện lỗi tại một điểm xác định, gọi flush rõ ràng.

## 3. save(entity): yêu cầu lưu entity

`JpaRepository` kế thừa phương thức `save` từ hợp đồng CRUD:

```java
<S extends T> S save(S entity);
```

Với Spring Data JPA, `save` xác định entity mới hay cũ rồi chọn thao tác JPA:

- Entity được nhận diện là mới: thường gọi `EntityManager.persist(entity)`.
- Entity được nhận diện là existing: thường gọi `EntityManager.merge(entity)`.

`save` không cam kết SQL sẽ được gửi ngay tại dòng gọi. Nếu entity vẫn managed, thay đổi có thể chỉ được theo dõi trong persistence context và flush sau đó.

Ví dụ:

```java
@Transactional
public Employee createEmployee(String fullName) {
    Employee employee = new Employee(fullName);

    Employee saved = employeeRepository.save(employee);

    // saved có thể đã được quản lý trong persistence context.
    // SQL có thể chưa được flush ở thời điểm này.
    return saved;
}
```

Nếu entity được merge, object trả về từ `save` có thể khác object đầu vào. Hãy dùng giá trị trả về khi tiếp tục thao tác.

Với entity managed đã được tải trong transaction, sửa thuộc tính thường không cần gọi `save` lại; dirty checking sẽ ghi thay đổi khi flush.

## 4. saveAndFlush(entity): lưu rồi flush ngay

`JpaRepository` cung cấp:

```java
<S extends T> S saveAndFlush(S entity);
```

Về ý nghĩa, phương thức này:

1. Gọi cơ chế save của repository để persist hoặc merge entity.
2. Gọi flush để đồng bộ persistence context xuống database.
3. Trả về entity đã lưu theo hợp đồng save.

Ví dụ:

```java
@Transactional
public Employee createAndFlush(String fullName) {
    Employee employee = new Employee(fullName);

    Employee saved = employeeRepository.saveAndFlush(employee);

    // Các thay đổi đang chờ trong persistence context đã được flush.
    return saved;
}
```

Dùng `saveAndFlush` khi cần yêu cầu flush ngay sau khi lưu entity, chẳng hạn:

- Muốn phát hiện lỗi constraint tại một điểm cụ thể trong nghiệp vụ.
- Cần bảo đảm SQL đã được thực thi trước khi chạy một thao tác tiếp theo trong cùng transaction.
- Cần lấy giá trị do database tạo sau khi INSERT/UPDATE và provider đã đồng bộ giá trị đó vào entity.
- Đang thực hiện một quy trình persistence cần ranh giới flush rõ ràng.

Không cần dùng `saveAndFlush` cho mọi lần lưu. Flush quá thường xuyên có thể làm giảm cơ hội gom nhiều thay đổi thành batch SQL và tạo thêm round trip tới database.

### 4.1. saveAndFlush không chỉ flush entity truyền vào

Giả sử persistence context đang có ba entity managed và cả ba đều có thay đổi. Gọi:

```java
employeeRepository.saveAndFlush(employee);
```

có thể flush thay đổi của cả ba entity, không chỉ `employee`. Đây là hệ quả của việc flush ở cấp persistence context.

Nếu chỉ muốn ghi một nhóm entity cụ thể, hãy cân nhắc transaction/persistence context phù hợp. Không giả định `saveAndFlush` là lệnh update riêng một hàng.

## 5. saveAllAndFlush(entities): lưu nhiều entity rồi flush

`JpaRepository` còn cung cấp:

```java
<S extends T> List<S> saveAllAndFlush(Iterable<S> entities);
```

Phương thức này nhận một Iterable entity, lưu từng entity theo cơ chế repository và flush sau khi hoàn tất nhóm lưu.

Ví dụ:

```java
@Transactional
public List<Employee> importSmallGroup(List<EmployeeInput> inputs) {
    List<Employee> employees = inputs.stream()
            .map(input -> new Employee(input.fullName()))
            .toList();

    return employeeRepository.saveAllAndFlush(employees);
}
```

Kết quả là danh sách entity đã lưu theo hợp đồng repository. Phương thức hữu ích khi một nhóm nhỏ entity cần được đồng bộ xuống database trước bước tiếp theo trong cùng transaction.

### 5.1. saveAllAndFlush có phải một câu bulk INSERT?

Không. Tên phương thức không cam kết toàn bộ danh sách được ghi bằng đúng một câu SQL hoặc một bulk insert duy nhất.

Spring Data JPA xử lý các entity theo cơ chế save; JPA provider quyết định SQL và cách batching dựa trên mapping, ID generation, JDBC batching và database.

Một nhóm entity có thể tạo ra nhiều câu INSERT/UPDATE. Nếu muốn tối ưu batch, cần cấu hình và đo lường riêng.

### 5.2. Persistence context vẫn giữ entity managed

`saveAllAndFlush` flush dữ liệu nhưng không tự clear persistence context. Các entity vẫn có thể đang managed sau khi phương thức trả về.

Nếu xử lý hàng trăm nghìn bản ghi, chỉ gọi `saveAllAndFlush` lặp lại có thể khiến persistence context giữ nhiều object và snapshot. Hãy cân nhắc flush rồi clear theo từng batch.

## 6. So sánh ba phương thức

| Phương thức | Lưu entity? | Flush? | Phạm vi flush |
|---|---|---|---|
| `flush()` | Không tự gọi save cho entity đầu vào | Có | Toàn persistence context |
| `saveAndFlush(entity)` | Có, một entity | Có, sau save | Toàn persistence context |
| `saveAllAndFlush(entities)` | Có, một nhóm entity | Có, sau saveAll | Toàn persistence context |

Các API CRUD liên quan:

| Phương thức | Ý nghĩa |
|---|---|
| `save(entity)` | Yêu cầu lưu một entity, chưa bảo đảm flush ngay |
| `saveAll(entities)` | Yêu cầu lưu một nhóm entity, chưa bảo đảm flush ngay |
| `flush()` | Flush các thay đổi đang chờ |
| `saveAndFlush(entity)` | Save một entity rồi flush |
| `saveAllAndFlush(entities)` | Save một nhóm entity rồi flush |

Chọn phương thức theo yêu cầu:

- Lưu thông thường trong transaction: `save` hoặc dirty checking.
- Lưu một entity và cần SQL thực thi ngay: `saveAndFlush`.
- Lưu một nhóm và cần flush sau nhóm đó: `saveAllAndFlush`.
- Đã thay đổi nhiều managed entity và muốn đồng bộ toàn context: `flush`.

## 7. Constraint violation và thời điểm phát hiện lỗi

Nhiều lỗi database chỉ xuất hiện khi SQL được gửi xuống database. Nếu chỉ gọi `save`, lỗi có thể được phát hiện ở lần flush tự động trước query hoặc trước commit.

Ví dụ bảng employees có unique constraint trên email. Khi lưu hai employee cùng email, database sẽ từ chối một trong các câu INSERT/UPDATE.

```java
@Transactional
public Employee createEmployee(String email) {
    Employee employee = new Employee(email);

    Employee saved = employeeRepository.save(employee);

    employeeRepository.flush();
    // Vi phạm unique constraint có thể xuất hiện tại đây.

    return saved;
}
```

Gọi flush giúp xác định lỗi gần với thao tác lưu hơn. Exception cụ thể phụ thuộc provider/database và cách Spring dịch lỗi; thường có thể gặp exception thuộc nhóm data integrity hoặc persistence exception.

### 7.1. Bắt lỗi ở đâu?

Có thể xử lý lỗi ở service hoặc tầng xử lý exception bên ngoài transaction. Nếu transaction đã bị đánh dấu rollback-only sau lỗi persistence, không nên tiếp tục ghi dữ liệu trong transaction đó như thể vẫn bình thường.

Ví dụ xử lý exception ở caller:

```java
try {
    employeeService.createEmployee(email);
} catch (DataIntegrityViolationException ex) {
    // Chuyển thành lỗi nghiệp vụ phù hợp, ví dụ email đã tồn tại.
}
```

Nếu cần kiểm tra duplicate trước khi lưu để trả thông báo thân thiện, có thể dùng exists query. Tuy nhiên, kiểm tra trước không loại bỏ race condition giữa hai transaction đồng thời; unique constraint trong database vẫn là cơ chế bảo vệ cuối cùng.

### 7.2. Flush lỗi không thể sửa bằng cách tiếp tục cùng transaction

Sau khi một câu lệnh SQL thất bại, transaction có thể không còn dùng được tùy database/provider và trạng thái transaction. Cách an toàn là để transaction rollback, sau đó xử lý ở transaction mới nếu cần.

Không bắt exception rồi tiếp tục gọi repository trong cùng transaction mà không hiểu rollback-only state. Spring có thể báo lỗi khi commit vì transaction đã bị đánh dấu rollback-only.

## 8. Generated ID và giá trị do database sinh

Một lý do thường gặp để flush là cần giá trị database tạo ra sau khi lưu.

Ví dụ ID tự tăng:

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
}
```

Với chiến lược `IDENTITY`, provider thường cần thực hiện INSERT để lấy ID được database cấp. Vì vậy, ID có thể có ngay sau `save` trong nhiều trường hợp. Tuy nhiên, thời điểm chính xác phụ thuộc ID generation strategy và provider.

`saveAndFlush` bảo đảm persistence context được flush trước khi phương thức hoàn tất bình thường, nhưng không có nghĩa mọi giá trị computed/default/trigger của database đều tự động được nạp lại vào object. Nếu mapping/provider không tự lấy lại giá trị generated, có thể cần `refresh(entity)` sau flush.

Ví dụ:

```java
Employee saved = employeeRepository.saveAndFlush(employee);

entityManager.refresh(saved);
// Đọc lại trạng thái database nếu cần giá trị do trigger/default cập nhật.
```

Chỉ refresh khi cần; thao tác này ghi đè trạng thái hiện tại của entity bằng dữ liệu database.

## 9. Transaction boundary và khả năng nhìn thấy dữ liệu

Phải xem `saveAndFlush` trong bối cảnh transaction.

### 9.1. Có transaction bên ngoài

```java
@Transactional
public void process(Long id) {
    Employee employee = employeeRepository.findById(id).orElseThrow();

    employee.setFullName("Updated");
    employeeRepository.flush();

    // Transaction vẫn mở.
    // Các thao tác tiếp theo trong transaction có thể đọc thay đổi này.
}
```

Khi service có `@Transactional`, lời gọi repository tham gia transaction hiện tại theo propagation mặc định. Flush chỉ gửi SQL; commit được thực hiện khi service method kết thúc thành công qua transaction interceptor.

### 9.2. Không có transaction bên ngoài

Các phương thức ghi kế thừa từ Spring Data repository thường có transaction configuration riêng. Nếu gọi `saveAndFlush` trực tiếp mà không có transaction bên ngoài, transaction do repository mở có thể commit khi phương thức hoàn tất thành công.

Do đó, để phối hợp nhiều thao tác thành một nghiệp vụ nguyên tử, nên đặt `@Transactional` ở service bao trùm toàn bộ nghiệp vụ.

### 9.3. Transaction khác có nhìn thấy dữ liệu sau flush không?

Thông thường, transaction khác không nhìn thấy thay đổi chưa commit. Flush không làm dữ liệu trở nên đã commit.

Khả năng đọc còn phụ thuộc isolation level và database. Không dùng flush như một cách công bố dữ liệu cho transaction khác. Nếu cần transaction khác nhìn thấy dữ liệu, transaction hiện tại phải commit theo quy trình nghiệp vụ.

## 10. Batch processing: flush và clear theo lô

Với lượng dữ liệu lớn, có thể xử lý từng nhóm nhỏ:

```java
@Service
public class EmployeeImportService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importEmployees(List<EmployeeInput> inputs) {
        int batchSize = 50;

        for (int i = 0; i < inputs.size(); i++) {
            EmployeeInput input = inputs.get(i);

            entityManager.persist(new Employee(input.fullName()));

            if ((i + 1) % batchSize == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

Vì sao dùng cả hai?

- `flush()`: gửi SQL của nhóm hiện tại xuống database.
- `clear()`: detach toàn bộ entity trong persistence context, giúp giảm bộ nhớ do JPA không phải giữ mọi entity và snapshot đã xử lý.

Cần chú ý:

- `clear()` detach tất cả entity trong context, kể cả entity không thuộc batch hiện tại.
- Không dùng các entity đã clear như thể chúng còn managed.
- Nếu cần giữ thay đổi trước clear, phải flush trước.
- Nếu transaction vẫn là một transaction lớn, lock và transaction log vẫn có thể kéo dài. Có thể chia thành nhiều transaction theo batch khi nghiệp vụ cho phép.
- JDBC batching cần cấu hình provider và driver; flush/clear chỉ kiểm soát persistence context, không tự bảo đảm batching.
- Với `GenerationType.IDENTITY`, khả năng batching INSERT có thể bị hạn chế tùy Hibernate và database.

Một cấu hình Hibernate thường dùng để thử JDBC batching:

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

Các giá trị cần đo bằng dữ liệu thực tế. Batch quá lớn có thể tăng bộ nhớ và thời gian lock; batch quá nhỏ có thể tăng số round trip.

## 11. Kiểm thử flush

`@DataJpaTest` thường chạy trong transaction và rollback sau mỗi test. Có thể dùng `flush()` để buộc SQL chạy trước assertion, giúp phát hiện lỗi mapping/constraint tại vị trí test rõ ràng.

Ví dụ:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void saveAndFlushPersistsEmployee() {
        Employee employee = new Employee("An Nguyen");

        Employee saved = repository.saveAndFlush(employee);

        assertThat(saved.getId()).isNotNull();

        entityManager.clear();

        Employee loaded = repository.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getFullName()).isEqualTo("An Nguyen");
    }
}
```

Test giả định entity dùng ID được sinh, repository và test dependencies đã được cấu hình. `saveAndFlush` gửi INSERT xuống database; `clear` buộc lần đọc tiếp theo nạp lại entity thay vì dùng instance đang managed.

Một test khác có thể kiểm tra nhóm:

```java
@Test
void saveAllAndFlushStoresAllEmployees() {
    List<Employee> saved = repository.saveAllAndFlush(List.of(
            new Employee("An"),
            new Employee("Binh")
    ));

    assertThat(saved).hasSize(2);
    assertThat(saved).allMatch(employee -> employee.getId() != null);
}
```

Trong test có constraint violation, hãy flush bên trong assertion để lỗi xảy ra tại điểm kiểm tra thay vì đợi đến teardown/commit của test framework. Cách bắt exception cụ thể cần phù hợp với provider, Spring exception translation và database đang dùng.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ rằng save đã gửi SQL ngay | Save có thể chỉ thay đổi persistence context | Gọi flush khi cần SQL thực thi tại một thời điểm rõ ràng |
| Nghĩ rằng flush đã commit | Nhầm đồng bộ SQL với kết thúc transaction | Để transaction commit thành công |
| Lỗi unique chỉ xuất hiện cuối transaction | SQL chưa được flush tại nơi gọi save | Flush có chủ đích để phát hiện lỗi sớm |
| saveAndFlush làm nhiều SQL chạy | Flush áp dụng toàn persistence context | Kiểm tra các entity managed đang có thay đổi |
| saveAllAndFlush không tạo một bulk INSERT | API không cam kết một câu SQL | Cấu hình JDBC batching và đo lường |
| Bộ nhớ vẫn tăng khi lặp saveAllAndFlush | Flush không clear persistence context | Flush rồi clear theo batch |
| Dữ liệu đã flush nhưng transaction khác chưa thấy | Transaction chưa commit | Commit theo ranh giới nghiệp vụ |
| Exception đã bắt nhưng commit vẫn thất bại | Transaction đã bị đánh dấu rollback-only | Để transaction rollback và xử lý ở transaction mới |
| Generated column vẫn cũ trong object | Provider chưa nạp lại giá trị database sinh | Refresh hoặc cấu hình generated property phù hợp |

## 13. Checklist chọn flush API

- [ ] Chỉ cần yêu cầu lưu entity: dùng `save`.
- [ ] Cần lưu một entity rồi flush ngay: dùng `saveAndFlush`.
- [ ] Cần lưu một nhóm entity rồi flush: dùng `saveAllAndFlush`.
- [ ] Đã thay đổi managed entities và cần đồng bộ toàn context: dùng `flush`.
- [ ] Cần giữ thay đổi trước clear: flush trước clear.
- [ ] Cần đọc giá trị do database sinh: kiểm tra provider có tự đồng bộ hay cần refresh.
- [ ] Cần phối hợp nhiều thao tác nguyên tử: đặt transaction ở service.
- [ ] Xử lý dữ liệu lớn: cân nhắc flush/clear theo batch và JDBC batching.
- [ ] Không dùng flush như commit hoặc cơ chế làm dữ liệu hiển thị cho transaction khác.
- [ ] Kiểm thử constraint bằng cách flush tại điểm cần xác nhận.

## Kết luận

`flush()` đồng bộ mọi thay đổi đang chờ trong persistence context xuống database. `saveAndFlush(entity)` lưu một entity rồi flush; `saveAllAndFlush(entities)` lưu một nhóm rồi flush. Cả ba thao tác đều hoạt động trong transaction và không tự commit transaction bên ngoài.

Dùng save thông thường cho phần lớn thao tác CRUD. Chỉ chủ động flush khi cần SQL chạy trước một bước tiếp theo, muốn phát hiện lỗi database tại điểm xác định hoặc đang điều khiển batch processing. Với dữ liệu lớn, kết hợp flush và clear theo lô, cấu hình JDBC batching và kiểm tra hiệu năng bằng số liệu thực tế.
