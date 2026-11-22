# @Commit và @Rollback để xác nhận hành vi lưu dữ liệu

Spring Test thường chạy mỗi phương thức kiểm thử có giao dịch trong một test-managed transaction. Mặc định, giao dịch này được rollback khi test kết thúc để dữ liệu kiểm thử không làm ảnh hưởng các test khác. Cơ chế đó rất tiện cho unit test có database, nhưng đôi khi ta cần xác nhận dữ liệu thật sự được commit hoặc chứng minh một thao tác bị rollback.

Hai annotation `@Commit` và `@Rollback` cho phép chọn kết quả cuối cùng của test-managed transaction. `@Commit` yêu cầu commit khi test kết thúc; `@Rollback` yêu cầu rollback và mặc định có giá trị `true`. Chúng đặc biệt hữu ích khi kiểm thử repository, service có `@Transactional`, transaction event và các quy tắc lưu dữ liệu. Để xác nhận trạng thái sau commit hoặc rollback, cần quan sát database sau khi transaction test đã kết thúc, thay vì chỉ đọc lại entity trong cùng persistence context.

## 1. Giao dịch mặc định của Spring Test

Spring TestContext Framework hỗ trợ transaction cho test thông qua `TransactionalTestExecutionListener`. Khi test class hoặc test method được đánh dấu `@Transactional`, Spring bắt đầu một test-managed transaction trước khi chạy test và kết thúc transaction sau khi test method hoàn tất.

Mặc định, transaction đó được rollback. Điều này có nghĩa là các câu lệnh insert, update hoặc delete thực hiện trong test sẽ không được commit xuống database sau khi test kết thúc, miễn là chúng tham gia cùng test-managed transaction.

Ví dụ với Spring Boot `@DataJpaTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomerDuringTest() {
        Customer customer = customerRepository.save(
                new Customer("lan@example.test")
        );

        // The test can use the saved entity while its transaction is active.
    }
}
```

`@DataJpaTest` mặc định mở transaction cho mỗi test method và rollback khi test kết thúc. Vì vậy, test có thể ghi dữ liệu để kiểm tra repository mà không để lại bản ghi sau đó.

Với `@SpringBootTest`, transaction không tự động được bật cho mọi test. Nếu muốn test-managed transaction, hãy đánh dấu test class hoặc method bằng `@Transactional`:

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTests {
    // Each test method runs in a test-managed transaction.
}
```

Khi test không có transaction do Spring Test quản lý, `@Commit` hoặc `@Rollback` không có transaction test để quyết định kết quả. Do đó, cần xác định rõ test có thực sự chạy trong test-managed transaction hay không.

## 2. @Rollback: mặc định giữ database sạch

`@Rollback` thuộc package `org.springframework.test.annotation`:

```java
import org.springframework.test.annotation.Rollback;
```

Annotation này cho biết test-managed transaction có được rollback khi test kết thúc hay không. Giá trị mặc định là `true`:

```java
@Test
@Rollback
void doesNotCommitChanges() {
    // Changes made in the test-managed transaction are rolled back.
}
```

Vì rollback vốn là hành vi mặc định của transactional test, việc viết `@Rollback` tường minh thường chỉ cần khi muốn làm rõ ý định của test hoặc override một cấu hình commit ở cấp class.

Có thể khai báo ở cấp class để áp dụng cho các phương thức kiểm thử transactional trong class:

```java
@DataJpaTest
@Rollback
class CustomerRepositoryTests {
    // Transactional test methods roll back by default.
}
```

`@Rollback(false)` có nghĩa là không rollback, do đó test-managed transaction sẽ được commit khi kết thúc:

```java
@Test
@Rollback(false)
void commitsChanges() {
    // The test-managed transaction is committed after the method.
}
```

Trong trường hợp muốn diễn đạt rõ ràng việc lưu dữ liệu, `@Commit` thường dễ đọc hơn `@Rollback(false)`.

## 3. @Commit: commit transaction khi test kết thúc

`@Commit` thuộc cùng package `org.springframework.test.annotation` và tương đương với `@Rollback(false)`:

```java
import org.springframework.test.annotation.Commit;
```

Ví dụ:

```java
@Test
@Commit
void commitsCustomer() {
    customerRepository.save(new Customer("lan@example.test"));
}
```

Nếu test chạy trong test-managed transaction, Spring commit transaction sau khi phương thức kiểm thử kết thúc. Dữ liệu đã tham gia transaction sẽ được commit theo transaction manager đang quản lý.

`@Commit` có thể khai báo ở cấp method hoặc class. Khi khai báo ở class, các test method transactional trong class sẽ commit theo cấu hình đó. Có thể dùng `@Rollback` ở một method cụ thể để yêu cầu rollback cho method đó; cấu hình method-level được ưu tiên so với cấu hình class-level.

Ví dụ một class mặc định commit, nhưng một test method vẫn rollback:

```java
@DataJpaTest
@Commit
class CustomerRepositoryCommitTests {

    @Test
    void commitsCustomer() {
        // This method commits.
    }

    @Test
    @Rollback
    void rollsBackTemporaryCustomer() {
        // This method explicitly rolls back.
    }
}
```

Không nên gắn `@Commit` vào toàn bộ test suite chỉ để kiểm tra một trường hợp lưu dữ liệu. Các test commit có thể để lại bản ghi, làm thay đổi dữ liệu mà test khác đọc hoặc gây lỗi unique constraint khi chạy lại. Hãy giới hạn commit vào test cần xác nhận hành vi commit và quản lý dữ liệu do test tạo ra.

## 4. Phân biệt @Commit, @Rollback và mặc định

| Cấu hình | Kết quả của test-managed transaction khi test kết thúc |
|---|---|
| `@Transactional` không có annotation kết quả | Rollback |
| `@Transactional` + `@Rollback` | Rollback |
| `@Transactional` + `@Rollback(true)` | Rollback |
| `@Transactional` + `@Rollback(false)` | Commit |
| `@Transactional` + `@Commit` | Commit |
| Không có test-managed transaction | Không có transaction test để annotation quyết định |

`@Commit` và `@Rollback` điều khiển kết quả của test-managed transaction do Spring Test tạo. Chúng không phải annotation thay thế cho transaction boundary trong mã ứng dụng. Ví dụ, `@Transactional` trên service vẫn xác định cách service tham gia transaction khi được gọi; `@Commit` quyết định kết quả của transaction do test framework quản lý.

## 5. Xác nhận dữ liệu trong cùng transaction và sau commit

Một điểm dễ nhầm là đọc được entity ngay sau khi gọi `save()` không chứng minh transaction đã commit.

Trong một test-managed transaction, lệnh:

```java
Customer saved = customerRepository.save(customer);
```

có thể đưa entity vào persistence context. Khi gọi `findById()` trong cùng persistence context, JPA có thể trả về entity đang được quản lý mà không cần đọc lại từ database. Ngay cả khi SQL đã được gửi tới database, transaction vẫn có thể chưa commit.

Vì vậy, cần phân biệt ba mức xác nhận:

1. **Entity đã được quản lý trong persistence context:** kiểm tra object hoặc trạng thái entity trong bộ nhớ.
2. **SQL đã được flush xuống database:** dùng `flush()` để buộc persistence context đồng bộ các thay đổi thành câu lệnh SQL trong transaction hiện tại.
3. **Transaction đã commit:** quan sát dữ liệu sau khi transaction test kết thúc, ví dụ qua `@AfterTransaction` hoặc một transaction mới.

### 5.1. Dùng flush và clear để kiểm tra round trip tới database

Với JPA, có thể dùng `EntityManager.flush()` và `clear()`:

```java
@DataJpaTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void persistsAndReloadsCustomerInsideTransaction() {
        Customer customer = customerRepository.save(
                new Customer("lan@example.test")
        );

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = customerRepository.findById(customer.getId())
                .orElseThrow();

        assertEquals("lan@example.test", reloaded.getEmail());
    }
}
```

`flush()` buộc JPA gửi các thay đổi xuống database trong transaction đang mở. `clear()` xóa các entity khỏi persistence context để lần truy vấn sau phải nạp lại dữ liệu. Test này xác nhận việc ghi và đọc qua database trong cùng transaction, nhưng transaction vẫn sẽ rollback theo mặc định khi test kết thúc.

`flush()` không đồng nghĩa với commit. Nếu constraint hoặc SQL statement lỗi, `flush()` có thể làm lỗi xuất hiện ngay trong test thay vì đợi đến lúc transaction kết thúc. Đây là cách hữu ích để phát hiện lỗi ghi dữ liệu, nhưng chưa chứng minh dữ liệu được commit bền vững.

### 5.2. Xác nhận trạng thái sau khi transaction kết thúc

Để chứng minh commit hoặc rollback, hãy đọc database sau khi test-managed transaction đã kết thúc. Spring Test cung cấp `@AfterTransaction` cho callback chạy sau transaction của test.

Ví dụ dùng `@Commit`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class CustomerCommitTests {

    private final String email = "commit-" + UUID.randomUUID() + "@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    @Commit
    void commitsInsertedCustomer() {
        jdbcTemplate.update(
                "insert into customer(email) values (?)",
                email
        );
    }

    @AfterTransaction
    void verifiesCommittedRow() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );

        assertThat(count).isEqualTo(1);

        jdbcTemplate.update(
                "delete from customer where email = ?",
                email
        );
    }
}
```

Ví dụ giả định schema có bảng `customer` và cột `email`. `@JdbcTest` cung cấp test-managed transaction; `@Commit` yêu cầu commit sau test method; `@AfterTransaction` đọc lại database sau khi transaction đó kết thúc. Giá trị email duy nhất giúp tránh trùng dữ liệu giữa các lần chạy. Callback cũng xóa bản ghi đã commit để test không để lại dữ liệu lâu dài.

Trong ví dụ thực tế, nếu cần kiểm tra qua repository thay vì SQL trực tiếp, có thể inject repository hoặc `JdbcTemplate` để đọc sau transaction. Điều quan trọng là thao tác đọc xác nhận phải diễn ra sau khi transaction test đã kết thúc và không dùng lại entity đang được quản lý từ persistence context trước đó.

### 5.3. Xác nhận rollback sau test

Với rollback, có thể bỏ `@Rollback` vì đó là mặc định, rồi dùng `@AfterTransaction` kiểm tra bản ghi không còn:

```java
@JdbcTest
class CustomerRollbackTests {

    private final String email = "rollback-" + UUID.randomUUID() + "@example.test";

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackInsertedCustomerByDefault() {
        jdbcTemplate.update(
                "insert into customer(email) values (?)",
                email
        );

        Integer countInsideTransaction = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );
        assertThat(countInsideTransaction).isEqualTo(1);
    }

    @AfterTransaction
    void verifiesRowWasRolledBack() {
        Integer countAfterTransaction = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );

        assertThat(countAfterTransaction).isZero();
    }
}
```

Trong test method, bản ghi có thể được đọc thấy vì nó vẫn nằm trong transaction hiện tại. Sau khi test kết thúc, Spring rollback transaction; callback `@AfterTransaction` kiểm tra bản ghi không còn trong database.

`@AfterTransaction` được gọi ngoài test-managed transaction. Vì vậy, thao tác JDBC trong callback không tham gia transaction đã rollback hoặc commit trước đó. Nếu hệ thống có transaction manager hoặc datasource đặc biệt, hãy bảo đảm cách đọc hậu kiểm thực sự quan sát database đã được cập nhật.

## 6. Kiểm thử service có @Transactional

Trong ứng dụng, service thường quản lý transaction bằng `@Transactional`:

```java
@Service
class CustomerService {

    private final CustomerRepository repository;

    CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email) {
        return repository.save(new Customer(email));
    }
}
```

Nếu test cũng chạy trong một test-managed transaction với propagation mặc định `REQUIRED`, transaction của service thường tham gia transaction đang được test mở. Khi method `register()` trả về, transaction chưa nhất thiết commit; transaction bên ngoài do test quản lý vẫn đang hoạt động.

Ví dụ:

```java
@SpringBootTest
@Transactional
class CustomerServiceTests {

    @Autowired
    private CustomerService customerService;

    @Test
    void registersCustomer() {
        Customer customer = customerService.register("lan@example.test");

        assertNotNull(customer.getId());
    }
}
```

Test này xác nhận service thực hiện thao tác trong transaction, nhưng transaction của test sẽ rollback khi kết thúc. Nó không chứng minh service đã commit độc lập ngay khi method trả về.

Nếu muốn kiểm tra hành vi lưu bền vững qua transaction do test quản lý, có thể dùng `@Commit`:

```java
@SpringBootTest
@Transactional
class CustomerServiceCommitTests {

    @Autowired
    private CustomerService customerService;

    @Test
    @Commit
    void commitsCustomerRegisteredByService() {
        customerService.register("lan@example.test");
    }
}
```

Để xác nhận dữ liệu thực sự tồn tại sau commit, kết hợp với `@AfterTransaction` như ví dụ trước. Chỉ kiểm tra ID được trả về hoặc entity còn trong persistence context chưa đủ để chứng minh transaction đã commit.

## 7. Kiểm tra hành vi rollback khi service ném exception

Một mục tiêu quan trọng của kiểm thử transaction là xác nhận các thay đổi được rollback khi có lỗi. Giả sử service lưu đơn hàng rồi thực hiện một bước nghiệp vụ có thể thất bại:

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    OrderService(
            OrderRepository orderRepository,
            InventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public void placeOrder(Order order) {
        orderRepository.save(order);
        inventoryService.reserve(order);
    }
}
```

Nếu `reserve()` ném một unchecked exception và transaction được quản lý đúng, transaction có thể bị đánh dấu rollback-only. Test có thể xác nhận bản ghi không tồn tại sau khi transaction kết thúc.

Một điểm cần phân biệt là exception có được ném ra khỏi transaction boundary hay bị bắt và xử lý bên trong service. Nếu service bắt exception rồi tiếp tục và không đánh dấu rollback-only, transaction có thể commit theo quy tắc bình thường. Quy tắc rollback cũng phụ thuộc loại exception và cấu hình rollback của transaction manager.

`@Commit` không ép transaction commit nếu transaction đã bị đánh dấu rollback-only. Nếu transaction bị đánh dấu rollback-only, yêu cầu commit ở cuối test có thể dẫn tới rollback hoặc lỗi khi commit tùy tình huống. Vì vậy, hãy kiểm tra trạng thái transaction và exception thực tế, không dùng `@Commit` như cách bỏ qua rollback rule của ứng dụng.

## 8. Dùng TestTransaction để điều khiển transaction trong test

Trong một số tình huống, cần commit hoặc rollback ngay giữa test method, sau đó tiếp tục thực hiện assertion hoặc một giai đoạn kiểm thử khác. Spring Test cung cấp `TestTransaction` để điều khiển test-managed transaction theo chương trình.

Các method thường dùng:

| Method | Ý nghĩa |
|---|---|
| `TestTransaction.isActive()` | Kiểm tra test-managed transaction hiện tại có đang hoạt động không |
| `TestTransaction.flagForCommit()` | Đánh dấu transaction hiện tại sẽ commit khi kết thúc bằng `end()` |
| `TestTransaction.flagForRollback()` | Đánh dấu transaction hiện tại sẽ rollback khi kết thúc bằng `end()` |
| `TestTransaction.isFlaggedForRollback()` | Kiểm tra transaction đang được đánh dấu rollback hay không |
| `TestTransaction.end()` | Kết thúc transaction hiện tại theo cờ commit/rollback đã đặt |
| `TestTransaction.start()` | Bắt đầu một test-managed transaction mới nếu lifecycle cho phép |

Ví dụ commit giữa test:

```java
@SpringBootTest
@Transactional
class CustomerTransactionTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void commitsThenReadsCommittedData() {
        String email = "commit-now@example.test";
        customerRepository.save(new Customer(email));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from customer where email = ?",
                Integer.class,
                email
        );
        assertThat(count).isEqualTo(1);

        TestTransaction.start();
    }
}
```

`flagForCommit()` không commit ngay; nó đặt cờ cho lần `end()` tiếp theo. Sau `end()`, transaction đã kết thúc và test có thể truy vấn dữ liệu đã commit. `start()` mở một test-managed transaction mới nếu test cần tiếp tục thao tác trong transaction; transaction mới này vẫn theo quy tắc rollback mặc định khi kết thúc test nếu không được đánh dấu commit.

Nếu chỉ cần commit toàn bộ test ở cuối method, `@Commit` ngắn gọn hơn. Dùng `TestTransaction` khi cần nhiều giai đoạn transaction trong cùng một test hoặc cần xác nhận dữ liệu ngay sau commit mà vẫn tiếp tục thực hiện các thao tác khác.

Không gọi `TestTransaction.end()` nếu không có test-managed transaction đang hoạt động. Có thể kiểm tra bằng `TestTransaction.isActive()` trước khi điều khiển transaction.

## 9. Callback @BeforeTransaction và @AfterTransaction

Spring Test cung cấp hai callback để thực hiện công việc trước và sau test-managed transaction:

- `@BeforeTransaction`: chạy trước khi transaction của test bắt đầu.
- `@AfterTransaction`: chạy sau khi transaction của test đã kết thúc bằng commit hoặc rollback.

Chúng khác với `@BeforeEach` và `@AfterEach` của JUnit Jupiter. Với transactional test, các callback JUnit `@BeforeEach` và `@AfterEach` thường chạy bên trong test-managed transaction; `@BeforeTransaction` và `@AfterTransaction` được thiết kế cho thao tác ở ngoài transaction đó.

Ví dụ:

```java
@DataJpaTest
class OrderTransactionTests {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeTransaction
    void verifyInitialState() {
        // Runs before the test-managed transaction begins.
    }

    @Test
    @Commit
    void insertsOrder() {
        // Insert data inside the test-managed transaction.
    }

    @AfterTransaction
    void verifyFinalState() {
        // Runs after the test transaction has committed.
    }
}
```

Các method callback phải tuân theo quy tắc của Spring Test và không nhận tham số. Chúng hữu ích khi cần chuẩn bị dữ liệu độc lập với transaction test hoặc kiểm tra trạng thái database sau khi transaction kết thúc.

Nếu dùng callback để dọn dữ liệu đã commit, cần bảo đảm thao tác cleanup chạy ngoài transaction đã kết thúc và có thể tự commit. Với nhiều transaction manager hoặc database, hãy kiểm tra callback đang dùng đúng datasource và transaction boundary.

## 10. Transaction propagation ảnh hưởng đến rollback như thế nào?

`@Commit` và `@Rollback` chỉ quyết định kết quả của test-managed transaction. Các transaction độc lập được tạo bởi code ứng dụng có thể có vòng đời riêng.

### 10.1. PROPAGATION_REQUIRED

Đây là propagation mặc định của `@Transactional`. Nếu test đã mở transaction và service dùng `REQUIRED`, service tham gia transaction hiện có. Khi test rollback, các thay đổi trong transaction chung cũng rollback.

### 10.2. PROPAGATION_REQUIRES_NEW

`REQUIRES_NEW` tạm ngưng transaction hiện tại và mở một transaction độc lập. Nếu transaction mới commit thành công, dữ liệu của nó có thể tồn tại ngay cả khi test-managed transaction bên ngoài rollback.

Ví dụ:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
```

Nếu test gọi method này trong một transaction test rồi để mặc định rollback, transaction audit riêng vẫn có thể đã commit. Không nên giả định rollback của test sẽ xóa mọi thay đổi được tạo bởi `REQUIRES_NEW`.

Khi kiểm thử code dùng propagation này, hãy dùng database test cô lập, dữ liệu định danh duy nhất và cleanup rõ ràng. Có thể xác nhận dữ liệu audit sau transaction như ví dụ `@AfterTransaction`.

### 10.3. NOT_SUPPORTED và NEVER

Với test-managed transaction, `@Transactional(propagation = Propagation.NOT_SUPPORTED)` yêu cầu test chạy không có transaction test được quản lý. `NEVER` yêu cầu không có transaction; nếu có transaction, việc thực thi sẽ không phù hợp với cấu hình đó.

Khi test không có test-managed transaction, `@Commit` hoặc `@Rollback` không có transaction để kết thúc. Các method repository hoặc service được gọi có thể tự mở transaction riêng theo cấu hình của chúng. Hãy đọc đúng transaction boundary của từng thành phần trước khi kết luận dữ liệu sẽ rollback.

### 10.4. Transaction lồng và savepoint

`NESTED` có thể sử dụng savepoint nếu transaction manager và database hỗ trợ. Khả năng rollback một phần phụ thuộc transaction manager; không nên suy luận rằng mọi cấu hình JPA đều hỗ trợ nested transaction giống nhau. Nếu bài test dựa vào savepoint, cần xác nhận transaction manager thực tế hỗ trợ và kiểm tra kết quả trên database.

## 11. Hành vi after-commit và transactional event

Một số logic chỉ chạy sau khi transaction commit, ví dụ `@TransactionalEventListener` với phase mặc định `AFTER_COMMIT`:

```java
@Component
class OrderEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        // Notify another system after the transaction commits.
    }
}
```

Nếu test-managed transaction rollback theo mặc định, listener `AFTER_COMMIT` sẽ không được gọi như khi giao dịch thực sự commit. Vì vậy, test chỉ publish event rồi kiểm tra listener đã gửi thông báo có thể thất bại hoặc không kiểm tra đúng luồng nếu transaction chưa commit.

Có thể dùng `@Commit` để xác nhận listener chạy sau commit:

```java
@SpringBootTest
@Transactional
class OrderEventListenerTests {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private NotificationGateway notificationGateway;

    @Test
    @Commit
    void sendsNotificationAfterOrderCommit() {
        orderService.createOrder("CUS-1");

        // Verify in a suitable after-commit observation point.
    }
}
```

Nếu cần xác minh tương tác chỉ sau khi commit, có thể dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` ngay trong test, sau đó verify mock hoặc kiểm tra trạng thái do listener tạo ra. Điều này làm rõ thời điểm listener được kích hoạt.

Không phải mọi event listener đều chạy sau commit. `@EventListener` thông thường chạy khi event được publish; `@TransactionalEventListener` chạy theo transaction phase đã cấu hình. Test phải phản ánh đúng loại listener mà ứng dụng sử dụng.

## 12. Những giới hạn của @Transactional trên test

`@Transactional` trên test được xử lý bởi Spring TestContext Framework và có một số khác biệt so với `@Transactional` trên service thông thường.

Các thuộc tính quan trọng như transaction manager có thể được chỉ định bằng `value` hoặc `transactionManager`. Với test-managed transaction, Spring Test chỉ hỗ trợ một tập thuộc tính giới hạn; `propagation` chỉ hỗ trợ `NOT_SUPPORTED` và `NEVER` để điều khiển việc có dùng test-managed transaction hay không. Các thuộc tính như `isolation`, `timeout`, `readOnly`, `rollbackFor` và `noRollbackFor` không được dùng để cấu hình test-managed transaction theo cùng cách như transaction trên method nghiệp vụ.

Nếu cần kiểm tra rollback rule của service, hãy để transaction boundary của service quyết định và thiết kế test phù hợp. Không đặt `rollbackFor` trên test method rồi kỳ vọng Spring Test tự áp dụng quy tắc đó cho transaction test.

Một giới hạn khác là transaction test thường được gắn với thread thực thi test. Một số assertion timeout kiểu preemptive có thể chạy phần thân test trong thread khác. Khi đó, thao tác database ở thread mới có thể không tham gia test-managed transaction và dữ liệu có thể không được rollback như dự kiến.

Ví dụ cần thận trọng:

```java
assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
    customerRepository.save(new Customer("lan@example.test"));
});
```

Nếu test framework chạy lambda ở thread khác, transaction được gắn với thread ban đầu không tự động truyền sang thread mới. Với transactional test, ưu tiên timeout không preemptive hoặc quản lý transaction tường minh cho công việc chạy ở thread khác.

## 13. Các sai lầm thường gặp

**Nghĩ rằng save() đồng nghĩa với commit.** `save()` có thể chỉ cập nhật persistence context. Dùng `flush()` để buộc SQL chạy và dùng `@AfterTransaction` hoặc transaction mới để xác nhận kết quả sau commit.

**Nghĩ rằng @Commit có tác dụng khi không có transaction test.** Annotation chỉ quyết định kết quả của test-managed transaction. Hãy kiểm tra `@Transactional` hoặc annotation test slice có mở transaction hay không.

**Dùng @Commit cho mọi test repository.** Dữ liệu có thể tồn tại sau test, ảnh hưởng test chạy sau và làm việc chạy lại không ổn định. Giữ rollback mặc định và chỉ commit ở test cần chứng minh hành vi commit.

**Chỉ đọc lại entity trong cùng persistence context.** JPA có thể trả về object đang được quản lý mà không truy vấn database. Dùng `flush()` và `clear()` để kiểm tra round trip, rồi hậu kiểm sau transaction để xác nhận commit.

**Cho rằng @Rollback sẽ hoàn tác REQUIRES_NEW.** Transaction độc lập có thể commit riêng và tồn tại sau rollback của transaction bên ngoài. Hãy kiểm tra propagation của service.

**Cho rằng @Commit ghi đè rollback-only.** Nếu transaction đã bị đánh dấu rollback-only, yêu cầu commit ở cuối test không thể biến nó thành transaction hợp lệ để commit.

**Dùng @Transactional trên test để kiểm tra after-commit event nhưng không commit.** Listener `AFTER_COMMIT` chỉ chạy khi transaction thực sự commit. Dùng `@Commit` hoặc `TestTransaction` nếu mục tiêu là xác nhận giai đoạn đó.

**Dùng @AfterEach để kiểm tra dữ liệu sau rollback.** `@AfterEach` thường chạy bên trong test-managed transaction. Muốn kiểm tra trạng thái sau khi transaction kết thúc, dùng `@AfterTransaction`.

**Dùng timeout preemptive trong transactional test mà không xét thread.** Transaction test thường gắn với thread chạy test. Công việc ở thread khác có thể thoát khỏi transaction và để lại dữ liệu.

## 14. Quy trình thiết kế test xác nhận commit hoặc rollback

Khi cần kiểm tra hành vi lưu dữ liệu, hãy xác định rõ điều test muốn chứng minh:

1. **Kiểm tra entity hoặc kết quả trong bộ nhớ:** assertion trực tiếp trên object có thể đủ.
2. **Kiểm tra SQL và mapping:** gọi `flush()`, sau đó `clear()` và đọc lại trong cùng transaction.
3. **Kiểm tra commit thật:** dùng `@Commit` hoặc `@Rollback(false)`, rồi đọc dữ liệu sau transaction bằng `@AfterTransaction` hoặc một transaction mới.
4. **Kiểm tra rollback thật:** giữ mặc định rollback hoặc dùng `@Rollback`, rồi xác nhận dữ liệu không còn sau transaction.
5. **Kiểm tra event sau commit:** kết thúc transaction bằng commit trước khi xác minh listener `AFTER_COMMIT`.
6. **Kiểm tra transaction độc lập:** xem propagation như `REQUIRES_NEW`, transaction manager và các thao tác ngoài transaction test.
7. **Giữ dữ liệu test cô lập:** dùng ID/email duy nhất, database riêng hoặc cleanup rõ ràng cho dữ liệu đã commit.

Ví dụ, một bài test repository thông thường nên dùng rollback mặc định để không để lại dữ liệu. Một bài test chuyên xác nhận commit nên dùng `@Commit` và callback hậu kiểm để chứng minh dữ liệu tồn tại sau transaction. Một bài test rollback nên kiểm tra trạng thái database sau khi Spring kết thúc transaction, không chỉ kiểm tra trong method trước khi rollback.

`@Commit` và `@Rollback` điều khiển kết quả của test-managed transaction trong Spring Test. Transactional test mặc định rollback; `@Commit` hoặc `@Rollback(false)` yêu cầu commit, còn `@Rollback` yêu cầu rollback. Muốn xác nhận dữ liệu đã được commit hoặc rollback, hãy quan sát database sau khi transaction kết thúc bằng `@AfterTransaction`, hoặc chủ động kết thúc transaction bằng `TestTransaction`. Đồng thời, cần xét `flush()`, persistence context, propagation như `REQUIRES_NEW`, after-commit event và vòng đời dữ liệu để bài kiểm thử chứng minh đúng hành vi lưu trữ mà ứng dụng cần bảo vệ.
