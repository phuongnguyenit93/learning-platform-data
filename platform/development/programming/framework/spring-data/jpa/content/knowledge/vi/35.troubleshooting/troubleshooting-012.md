# Lỗi chỉ xuất hiện lúc flush hoặc commit

Với JPA, gọi `repository.save(entity)` không đồng nghĩa mọi câu SQL đã được gửi xuống database ngay tại dòng lệnh đó. Entity thường được quản lý trong persistence context; Hibernate có thể trì hoãn câu lệnh INSERT hoặc UPDATE cho tới khi flush. Transaction cũng chỉ được commit sau khi phương thức nghiệp vụ hoàn tất và transaction manager thực hiện bước commit.

Vì vậy, một lỗi dữ liệu hoặc lỗi đồng thời có thể không xuất hiện tại `save()`. Nó chỉ lộ ra khi persistence context được flush, hoặc muộn hơn khi database xác nhận commit. Muốn chẩn đoán đúng, cần xác định lỗi xảy ra ở bước nào, đọc nguyên nhân gốc trong stack trace và kiểm thử đúng ranh giới transaction.

## 1. Phân biệt save, flush và commit

Ba thao tác có vai trò khác nhau:

- **save:** yêu cầu Spring Data JPA lưu entity. Repository thường gọi `EntityManager.persist()` cho entity mới hoặc `EntityManager.merge()` cho entity cần merge. Việc này cập nhật trạng thái persistence context; SQL có thể được gửi ngay hoặc được trì hoãn tùy provider, kiểu sinh ID và flush mode.
- **flush:** đồng bộ các thay đổi đang chờ trong persistence context xuống database bằng các câu SQL cần thiết. Flush không kết thúc transaction và không làm dữ liệu trở nên đã commit.
- **commit:** xác nhận transaction. Trước khi commit, JPA provider thường flush các thay đổi còn lại. Sau đó database hoàn tất transaction hoặc từ chối commit.

Ví dụ luồng đơn giản:

```text
repository.save(entity)
        |
        v
Entity được quản lý trong persistence context
        |
        v
flush: gửi INSERT / UPDATE / DELETE xuống database
        |
        v
commit: database xác nhận transaction
```

Một số thao tác có thể khiến flush xảy ra sớm hơn thời điểm commit. Với flush mode `AUTO`, JPA provider có thể flush trước một truy vấn nếu các thay đổi đang chờ có thể ảnh hưởng đến kết quả truy vấn. Vì vậy, lỗi đôi khi xuất hiện ở một câu query tưởng như chỉ đọc, dù nguyên nhân là entity đã được sửa trước đó.

Không nên dựa vào việc `save()` trả về bình thường để kết luận dữ liệu chắc chắn đã được ghi thành công. Việc ghi chỉ được xác nhận sau khi transaction commit thành công.

## 2. Vì sao lỗi bị trì hoãn?

JPA sử dụng dirty checking để theo dõi entity đang được quản lý. Khi ứng dụng thay đổi thuộc tính, provider có thể chỉ ghi nhận thay đổi trong bộ nhớ. SQL UPDATE được tạo khi flush.

Ví dụ:

```java
@Transactional
public void rename(Long id, String newName) {
    Customer customer = repository.findById(id)
            .orElseThrow();

    customer.setName(newName);

    // Chưa chắc SQL UPDATE đã chạy tại đây.
}
```

Nếu cột `name` có giới hạn độ dài, có ràng buộc unique hoặc database có trigger kiểm tra dữ liệu, lỗi có thể xuất hiện lúc flush. Khi phương thức `rename` kết thúc, transaction interceptor mới thực hiện commit; bước commit có thể kích hoạt flush cuối cùng và ném exception ra phía caller.

Các nguyên nhân thường gặp gồm:

- **Ràng buộc database:** vi phạm NOT NULL, UNIQUE, FOREIGN KEY, CHECK hoặc giới hạn kiểu dữ liệu.
- **Optimistic locking:** version của bản ghi đã bị transaction khác thay đổi; provider phát hiện khi thực hiện UPDATE có điều kiện version.
- **Pessimistic locking và deadlock:** database không cấp được khóa hoặc phát hiện deadlock khi SQL chạy.
- **Bean Validation:** constraint như `@NotNull`, `@Size` được kiểm tra tại các sự kiện lifecycle phù hợp, thường trong quá trình persist/update hoặc flush.
- **Entity lifecycle callback:** logic trong `@PrePersist`, `@PreUpdate` hoặc listener có thể ném exception.
- **Ràng buộc trì hoãn của database:** một số database cho phép constraint được kiểm tra tại cuối transaction thay vì ngay khi từng câu lệnh chạy, nên lỗi chỉ xuất hiện ở commit.

Thời điểm chính xác phụ thuộc JPA provider, database, JDBC driver, kiểu sinh khóa và cấu hình constraint. Một số INSERT có thể chạy sớm, chẳng hạn khi dùng chiến lược sinh ID cần database trả khóa ngay.

## 3. Dùng flush để làm lộ lỗi sớm hơn

Spring Data JPA cung cấp `saveAndFlush(entity)` và `flush()` thông qua `JpaRepository`. Có thể gọi chúng khi cần biết lỗi SQL ngay trong luồng xử lý hiện tại:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(Customer customer) {
        return repository.saveAndFlush(customer);
    }
}
```

Hoặc:

```java
@Transactional
public void update(Customer customer) {
    repository.save(customer);
    repository.flush();
}
```

`saveAndFlush` thực hiện lưu rồi yêu cầu flush. `flush()` đồng bộ tất cả thay đổi đang chờ trong persistence context của EntityManager liên quan, không chỉ entity vừa truyền vào repository. Do đó, một entity khác đã được sửa trước đó trong cùng persistence context cũng có thể gây lỗi tại lần flush này.

Flush giúp phát hiện sớm các lỗi mà database kiểm tra khi thực thi SQL, nhưng không bảo đảm mọi lỗi commit đều được phát hiện. Constraint được database trì hoãn tới cuối transaction, lỗi trong quá trình commit hoặc lỗi do transaction synchronization vẫn có thể xuất hiện sau khi flush đã thành công.

Cũng không nên gọi `saveAndFlush` sau mọi `save` như một thói quen. Flush thường xuyên có thể làm mất lợi ích gom batch, tăng số lần trao đổi với database và làm transaction tốn thời gian hơn. Chỉ flush sớm khi có lý do rõ ràng, chẳng hạn cần lấy kết quả kiểm tra constraint trước khi thực hiện bước tiếp theo.

## 4. Ví dụ: lỗi unique chỉ xuất hiện khi flush hoặc commit

Giả sử bảng customer có unique constraint trên email. Entity:

```java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void register(String email) {
        repository.save(new Customer(email));
        // INSERT có thể được trì hoãn đến flush hoặc commit.
    }
}
```

Nếu email đã tồn tại, lần gọi `register` có thể chỉ ném lỗi khi transaction interceptor flush và commit sau khi thân phương thức đã chạy xong. Nếu muốn lỗi do SQL xuất hiện ngay trong service, có thể đổi thành:

```java
@Transactional
public void register(String email) {
    repository.saveAndFlush(new Customer(email));
}
```

Cả hai cách đều phải xử lý trường hợp transaction thất bại. Việc flush sớm không làm cho thao tác trở nên đã commit; transaction vẫn có thể rollback hoặc gặp lỗi ở bước commit.

Trong thực tế, nên xác định rõ hành vi nghiệp vụ khi email trùng. Có thể kiểm tra trước để cải thiện thông báo cho người dùng, nhưng `existsByEmail` rồi `save` không loại bỏ race condition: hai request vẫn có thể cùng kiểm tra thấy email chưa tồn tại. Unique constraint ở database mới là lớp bảo vệ cuối cùng. Ứng dụng cần xử lý lỗi constraint để trả phản hồi phù hợp.

## 5. Exception thường thấy và cách đọc nguyên nhân gốc

Spring, JPA provider và JDBC driver có thể bọc cùng một lỗi qua nhiều lớp exception. Không nên chỉ nhìn exception ngoài cùng.

| Dấu hiệu | Ý nghĩa cần kiểm tra |
|---|---|
| `DataIntegrityViolationException` | Spring báo lỗi vi phạm tính toàn vẹn dữ liệu, thường liên quan constraint hoặc dữ liệu không hợp lệ |
| Hibernate `org.hibernate.exception.ConstraintViolationException` | SQL vi phạm constraint của database |
| `jakarta.validation.ConstraintViolationException` | Bean Validation constraint không đạt; đây là exception khác với exception cùng tên của Hibernate |
| `ObjectOptimisticLockingFailureException` | Spring báo xung đột optimistic locking |
| JPA `OptimisticLockException` | Version hoặc trạng thái optimistic lock không còn hợp lệ |
| `TransactionSystemException` | Transaction manager gặp lỗi trong quá trình hoàn tất transaction; cần xem cause và root cause |
| `UnexpectedRollbackException` | Transaction đã bị đánh dấu rollback-only nhưng luồng bên ngoài vẫn đi tới bước commit |
| `CannotAcquireLockException` hoặc lỗi deadlock từ database | Không lấy được khóa hoặc transaction bị database hủy do deadlock |

Với lỗi SQL, tìm các thông tin sau trong chuỗi `Caused by`:

- SQLState và vendor error code của database.
- Tên constraint bị vi phạm nếu driver cung cấp.
- Bảng, cột hoặc giá trị liên quan nếu thông báo có nêu.
- SQL statement đang chạy và vị trí repository/service khởi tạo thao tác.
- Loại exception gốc do JDBC driver hoặc JPA provider ném ra.

Không nhầm `org.hibernate.exception.ConstraintViolationException` với `jakarta.validation.ConstraintViolationException`. Một exception xuất phát từ database constraint, exception còn lại xuất phát từ Bean Validation. Cách sửa và vị trí cần kiểm tra khác nhau.

Thông báo SQL có thể chứa dữ liệu nhạy cảm. Chỉ bật log SQL và bind parameter ở môi trường phù hợp, kiểm soát quyền truy cập log và tránh ghi mật khẩu, token hoặc thông tin cá nhân không cần thiết.

## 6. Bắt exception ở đúng transaction boundary

Với phương thức `@Transactional`, Spring thường dùng proxy để mở transaction trước khi gọi method và commit sau khi method trả về. Vì vậy, lỗi commit có thể được ném ra sau khi thân method đã kết thúc, tại lời gọi qua proxy ở phía caller.

Ví dụ:

```java
try {
    customerService.register(email);
} catch (DataIntegrityViolationException ex) {
    // Ánh xạ lỗi constraint thành phản hồi nghiệp vụ phù hợp.
}
```

Đặt khối `try/catch` bên ngoài lời gọi service giúp bắt lỗi phát sinh cả trong thân method lẫn khi transaction interceptor commit. Tuy nhiên, exception cụ thể còn phụ thuộc provider và transaction manager; nếu cần phân loại, hãy kiểm tra cause chain thay vì chỉ dựa vào kiểu exception ngoài cùng.

Tránh bắt exception bên trong transaction rồi tiếp tục xử lý như thể transaction vẫn khỏe:

```java
@Transactional
public void register(String email) {
    try {
        repository.saveAndFlush(new Customer(email));
    } catch (DataIntegrityViolationException ex) {
        // Không nên bỏ qua rồi tiếp tục dùng transaction này.
    }

    // Transaction có thể đã rollback-only hoặc persistence context
    // không còn ở trạng thái phù hợp để tiếp tục.
}
```

Sau một lỗi persistence, transaction có thể đã bị đánh dấu rollback-only. Tiếp tục ghi dữ liệu có thể dẫn tới `UnexpectedRollbackException` ở cuối transaction hoặc các lỗi tiếp theo khó hiểu. Hãy để exception thoát khỏi transaction và xử lý ở tầng bên ngoài, hoặc chuyển công việc cần cô lập sang một transaction độc lập với propagation được thiết kế rõ ràng.

Cũng cần nhớ rằng một method `@Transactional` được gọi nội bộ từ method khác trong cùng object thường không đi qua proxy; annotation có thể không tạo transaction mới như bạn kỳ vọng. Hãy đặt transaction boundary tại bean/service được gọi qua Spring proxy và kiểm tra propagation của transaction đang tồn tại.

## 7. Phân biệt lỗi flush với lỗi commit thật sự

Có thể phân loại theo thời điểm quan sát:

**Lỗi ở flush**

- SQL INSERT/UPDATE/DELETE được gửi và database trả lỗi.
- Bean Validation hoặc callback lifecycle thất bại khi provider đồng bộ persistence context.
- Optimistic lock được phát hiện khi câu UPDATE có điều kiện version thực thi.
- Lỗi thường xuất hiện tại `flush()`, `saveAndFlush()` hoặc trước một query buộc provider flush.

**Lỗi ở commit**

- Database kiểm tra deferred constraint ở cuối transaction.
- Transaction manager hoặc database báo lỗi khi hoàn tất transaction.
- Transaction đã bị đánh dấu rollback-only từ một thao tác trước đó.
- Lỗi phát sinh trong transaction synchronization hoặc khi xác nhận commit.

Một lần flush thành công chỉ chứng minh các thay đổi đã được đồng bộ thành công tại thời điểm đó. Nó không chứng minh transaction đã commit. Chỉ sau khi transaction boundary hoàn tất bình thường mới có thể coi thay đổi đã commit.

## 8. Kiểm thử lỗi bị trì hoãn

Test repository thông thường có thể không phát hiện lỗi nếu test kết thúc trước khi flush. Trong `@DataJpaTest`, Spring thường mở transaction cho test và rollback sau khi test hoàn tất. Vì vậy, nên chủ động flush để kiểm tra lỗi SQL có thể phát hiện ở bước đó.

Ví dụ:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void duplicateEmailFailsOnFlush() {
        repository.saveAndFlush(new Customer("a@example.com"));

        assertThatThrownBy(() ->
                repository.saveAndFlush(
                        new Customer("a@example.com")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
```

Ví dụ này giả định unique constraint được tạo trong database test và exception được Spring dịch thành `DataIntegrityViolationException`. Với Hibernate/provider hoặc database khác, kiểu exception cụ thể có thể khác; hãy kiểm tra cause chain thực tế.

Để kiểm tra lỗi chỉ xuất hiện khi commit, test phải đi qua một transaction thực sự được commit. Nếu test đang có transaction bao ngoài như `@DataJpaTest`, một transaction template tham gia vào transaction đó có thể không commit độc lập. Có thể viết integration test không có transaction bao ngoài, gọi một service `@Transactional` qua Spring proxy, rồi bắt exception ở caller sau khi service trả về. Hoặc dùng `TransactionTemplate` với transaction riêng và để lời gọi `execute` hoàn tất commit trước khi assertion kiểm tra lỗi.

Khi kiểm thử optimistic locking, tạo hai transaction đọc cùng version, để transaction thứ nhất cập nhật và commit, sau đó cho transaction thứ hai cập nhật entity cũ. Xác nhận lỗi xuất hiện ở flush hoặc commit theo provider và transaction boundary đang dùng.

## 9. Quy trình chẩn đoán trong ứng dụng thực tế

Khi lỗi chỉ xuất hiện cuối request hoặc khi transaction đóng, thực hiện theo thứ tự:

1. **Xác định transaction boundary.** Tìm method `@Transactional` gần nhất, propagation và nơi gọi method qua Spring proxy.
2. **Tìm điểm flush.** Kiểm tra có `saveAndFlush`, `EntityManager.flush()`, query kích hoạt AUTO flush hay chỉ flush cuối transaction.
3. **Đọc toàn bộ cause chain.** Ghi lại exception gốc, SQLState, vendor code và constraint name.
4. **Đối chiếu dữ liệu và schema.** Kiểm tra nullability, unique, foreign key, độ dài cột, check constraint và version.
5. **Kiểm tra lifecycle.** Xem Bean Validation, `@PrePersist`, `@PreUpdate`, entity listener và callback tùy chỉnh.
6. **Kiểm tra cạnh tranh.** Với optimistic/pessimistic lock, xem transaction khác có sửa cùng bản ghi hoặc giữ khóa quá lâu không.
7. **Tạo test tái hiện.** Dùng database engine và constraint tương tự production; flush rõ ràng và tạo transaction commit thật khi cần kiểm tra lỗi commit.
8. **Xử lý ở đúng tầng.** Rollback transaction lỗi, ánh xạ lỗi kỹ thuật sang phản hồi nghiệp vụ và chỉ retry khi lỗi có tính tạm thời cùng thao tác có thể retry an toàn.

Đừng chỉ tăng timeout hoặc thêm `try/catch` quanh `save()` khi chưa biết lỗi gốc. Nếu nguyên nhân là unique constraint, tăng timeout không giúp. Nếu là optimistic lock, cần quyết định retry, tải lại dữ liệu hoặc báo xung đột theo nghiệp vụ.

## 10. Ghi nhớ

`save()` có thể chỉ cập nhật persistence context; SQL thường được gửi khi flush và transaction chỉ được xác nhận khi commit. Lỗi constraint, validation, callback, optimistic lock hoặc lỗi database có thể vì thế xuất hiện muộn. Dùng `flush()` hoặc `saveAndFlush()` để phát hiện sớm lỗi thực thi SQL khi cần, nhưng nhớ rằng flush không phải commit. Đặt xử lý exception bên ngoài transaction boundary, đọc root cause và kiểm thử cả trường hợp flush lẫn commit thực sự.