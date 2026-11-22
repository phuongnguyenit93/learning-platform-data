# Test-managed transaction so với giao dịch do ứng dụng quản lý

Trong kiểm thử Spring, một transaction có thể được bắt đầu bởi hạ tầng kiểm thử hoặc bởi logic của ứng dụng. Hai trường hợp đều có thể sử dụng cùng PlatformTransactionManager và cùng cơ sở dữ liệu, nhưng bên chịu trách nhiệm bắt đầu, kết thúc và quyết định commit/rollback khác nhau.

**Test-managed transaction** là transaction có vòng đời do Spring TestContext Framework điều khiển cho một test method. **Application-managed transaction** là transaction được code ứng dụng bắt đầu, thường thông qua @Transactional trên service hoặc TransactionTemplate. Hiểu ranh giới này giúp giải thích vì sao một test mặc định rollback dữ liệu, vì sao service có thể tham gia transaction của test, và vì sao một thao tác REQUIRES_NEW hoặc một request chạy ở thread khác vẫn có thể commit dữ liệu.

## 1. Hai loại transaction khác nhau ở đâu?

| Khía cạnh | Test-managed transaction | Application-managed transaction |
|---|---|---|
| Ai bắt đầu? | Spring TestContext Framework, thông qua TransactionalTestExecutionListener. | Logic ứng dụng, chẳng hạn service được gọi qua proxy @Transactional hoặc code dùng TransactionTemplate. |
| Mục tiêu | Cô lập dữ liệu và trạng thái trong một lần test. | Bảo đảm một đơn vị nghiệp vụ của ứng dụng có ranh giới transaction phù hợp. |
| Thời điểm kết thúc | Spring Test kết thúc transaction sau test method và mặc định rollback. | Transaction interceptor hoặc code quản lý transaction commit/rollback theo kết quả xử lý của ứng dụng. |
| Quyết định commit/rollback | Thường điều khiển bằng @Rollback, @Commit hoặc TestTransaction. | Theo kết quả xử lý, exception và quy tắc transaction của ứng dụng. |
| Phạm vi phổ biến | Một test method chạy trong thread test. | Một service method hoặc một khối công việc do ứng dụng xác định. |

Hai loại này không phải hai transaction manager riêng biệt. Spring Test thường yêu cầu một PlatformTransactionManager từ context, rồi dùng manager đó bắt đầu transaction test. Khi service được gọi trong cùng thread và cùng transaction manager, transaction do ứng dụng yêu cầu có thể tham gia transaction đang tồn tại.

## 2. Test-managed transaction được tạo như thế nào?

Spring TestContext Framework cung cấp TransactionalTestExecutionListener để hỗ trợ transaction cho test. Listener này được đăng ký mặc định khi dùng cơ chế Spring TestContext tiêu chuẩn.

Khi test class hoặc test method được đánh dấu @Transactional, listener bắt đầu transaction trước khi thực thi test method. Sau khi test kết thúc, listener mặc định rollback transaction để dữ liệu không rò sang test khác.

```text
JUnit Jupiter chạy test
        |
        v
Spring TestContext chuẩn bị test
        |
        v
TransactionalTestExecutionListener
        | bắt đầu test-managed transaction
        v
@BeforeEach
        |
        v
Test method
        |
        v
@AfterEach
        |
        v
Spring Test kết thúc transaction
        |
        +-- rollback mặc định (hoặc commit theo cấu hình)
```

Ví dụ:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAnAccount() {
        Account account = new Account("ACC-100");

        accountRepository.save(account);

        assertThat(accountRepository.findByCode("ACC-100")).isPresent();
    }
}
```

Trong ví dụ, test có thể đọc lại dữ liệu vừa ghi trong cùng transaction. Sau test, Spring Test rollback transaction theo mặc định. Vì vậy, dữ liệu được ghi trong transaction test thường không tồn tại sau khi phương thức test kết thúc.

### 2.1. Cần có transaction manager

Để test-managed transaction hoạt động, Spring context phải cung cấp một transaction manager phù hợp. Với JDBC, đó có thể là DataSourceTransactionManager; với JPA, thường là JpaTransactionManager.

```java
@Configuration
class PersistenceTestConfiguration {

    @Bean
    DataSource dataSource() {
        // Tạo DataSource dành cho test.
        return createTestDataSource();
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

Đây là ví dụ cấu hình JDBC minh họa; phương thức createTestDataSource() đại diện cho cách dự án cung cấp datasource thật cho test. Nếu context có nhiều transaction manager, hãy chỉ định manager phù hợp trên test bằng thuộc tính transactionManager của @Transactional:

```java
@Transactional(transactionManager = "ordersTransactionManager")
class OrderRepositoryTest {
}
```

Có thể dùng tên bean hoặc qualifier tương ứng theo cấu hình. Nếu Spring không tìm được transaction manager duy nhất hoặc chọn nhầm manager, test có thể không chạy trong transaction mà ta mong đợi.

## 3. Rollback mặc định và cách yêu cầu commit

Test-managed transaction được rollback mặc định. Cơ chế này làm cho test có thể chuẩn bị dữ liệu, thực hiện thao tác ghi và assertion trong một transaction mà không cần tự dọn mọi row sau từng lần chạy.

### 3.1. @Rollback

@Rollback điều khiển việc transaction của test có được rollback sau khi hoàn tất hay không:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
@Rollback
class AccountRepositoryTest {

    @Test
    void rollsBackAfterTest() {
        // Dữ liệu được ghi trong transaction test sẽ rollback sau test.
    }
}
```

Không truyền giá trị hoặc đặt @Rollback(true) có nghĩa rollback. Có thể đặt @Rollback(false) để commit transaction test:

```java
@Test
@Rollback(false)
void commitsTestTransaction() {
    // Dữ liệu được commit khi test kết thúc.
}
```

### 3.2. @Commit

@Commit là cách diễn đạt rõ ràng rằng test-managed transaction cần commit:

```java
@Test
@Commit
void persistsFixtureForLaterVerification() {
    // Transaction test được commit sau khi test hoàn tất.
}
```

@Commit tương đương về ý định với @Rollback(false). Có thể đặt các annotation này ở cấp class hoặc method theo nhu cầu. Annotation ở method có thể ghi đè cấu hình mặc định áp dụng từ class.

Hãy dùng commit trong test khi cần xác nhận dữ liệu tồn tại sau ranh giới transaction hoặc khi có bước kiểm tra độc lập chạy sau đó. Vì dữ liệu đã commit sẽ tồn tại trong database, test phải có chiến lược dọn dữ liệu để không làm ảnh hưởng lần chạy sau.

## 4. Application-managed transaction được bắt đầu bởi code ứng dụng

Trong ứng dụng, transaction thường được khai báo ở service method:

```java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        Account source = accountRepository.getReferenceById(fromId);
        Account target = accountRepository.getReferenceById(toId);

        source.withdraw(amount);
        target.deposit(amount);
    }
}
```

Khi ứng dụng gọi transfer() qua Spring proxy, transaction interceptor bắt đầu transaction nếu chưa có transaction phù hợp, gọi phương thức và quyết định commit hoặc rollback theo kết quả thực thi. Đây là application-managed transaction vì ranh giới nghiệp vụ do annotation trên service quy định.

Code cũng có thể quản lý transaction tường minh bằng TransactionTemplate:

```java
public class TransferService {

    private final TransactionTemplate transactionTemplate;
    private final AccountRepository accountRepository;

    public TransferService(
            TransactionTemplate transactionTemplate,
            AccountRepository accountRepository) {
        this.transactionTemplate = transactionTemplate;
        this.accountRepository = accountRepository;
    }

    public void transfer(long fromId, long toId, BigDecimal amount) {
        transactionTemplate.executeWithoutResult(status -> {
            Account source = accountRepository.getReferenceById(fromId);
            Account target = accountRepository.getReferenceById(toId);
            source.withdraw(amount);
            target.deposit(amount);
        });
    }
}
```

TransactionTemplate dùng transaction manager được cấu hình và kết thúc transaction theo kết quả callback. Cách này phù hợp khi cần ranh giới transaction rõ ràng trong code mà không dựa vào annotation proxy.

## 5. Application transaction tham gia test-managed transaction

Một test có thể mở test-managed transaction rồi gọi service có @Transactional. Kết quả phụ thuộc propagation của service.

Với propagation mặc định REQUIRED, service tham gia transaction đang tồn tại trên cùng thread và cùng transaction manager. Service không tạo một transaction độc lập; khi test kết thúc và rollback, thay đổi do service thực hiện cũng được rollback.

```text
Test method
    |
    +-- Spring Test bắt đầu transaction T1
    |
    +-- gọi OrderService.create()
             |
             +-- @Transactional(REQUIRED)
                       |
                       +-- tham gia transaction T1

Test kết thúc
    |
    +-- Spring Test rollback T1
             +-- thay đổi từ service cũng rollback
```

Ví dụ:

```java
@SpringJUnitConfig(classes = OrderApplicationTestConfiguration.class)
@Transactional
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceWriteIsRolledBackWithTheTest() {
        Order order = orderService.create(new CreateOrderCommand("SKU-1", 2));

        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
```

Assertion đọc được đơn hàng vì nó đang chạy trong cùng transaction và nhìn thấy thay đổi chưa commit của chính transaction đó. Sau khi test kết thúc, rollback của test hoàn tác thay đổi.

Điều này hữu ích cho integration test vì có thể kiểm tra nhiều bean cùng tham gia một luồng nghiệp vụ mà vẫn giữ database sạch sau test.

## 6. Propagation quyết định ranh giới giữa hai transaction

Propagation mô tả cách một lời gọi nghiệp vụ xử lý khi thread hiện tại đã có transaction. Khi service được gọi bên trong test-managed transaction, propagation của service quyết định service tham gia, tạm dừng hay yêu cầu một transaction khác.

| Propagation | Khi có test-managed transaction | Kết quả đối với rollback của test |
|---|---|---|
| REQUIRED | Tham gia transaction hiện tại. | Thay đổi thuộc transaction test và được rollback cùng test. |
| REQUIRES_NEW | Tạm dừng transaction test và bắt đầu transaction độc lập. | Transaction mới có thể commit riêng; rollback test không hoàn tác phần đã commit. |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager và resource hỗ trợ. | Thay đổi nằm trong transaction ngoài; rollback test vẫn hoàn tác transaction ngoài. |
| SUPPORTS | Tham gia transaction nếu có; nếu không thì chạy không transaction. | Trong test-managed transaction, thường tham gia transaction test. |
| MANDATORY | Yêu cầu transaction hiện tại phải tồn tại. | Thành công khi được gọi trong test-managed transaction; lỗi nếu không có transaction. |
| NOT_SUPPORTED | Tạm dừng transaction hiện tại và chạy không transaction. | Thao tác không nằm trong rollback của test; cách ghi dữ liệu phụ thuộc resource và cơ chế tự quản lý của nó. |
| NEVER | Yêu cầu không có transaction hiện tại. | Sẽ báo lỗi nếu được gọi khi test-managed transaction đang hoạt động. |

### 6.1. REQUIRES_NEW có thể commit ngoài transaction test

Giả sử một service ghi audit bằng propagation REQUIRES_NEW:

```java
@Service
class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        // Ghi audit trong transaction độc lập.
    }
}
```

Khi test đang ở trong transaction T1, lời gọi audit tạm dừng T1 và mở T2. Nếu T2 commit thành công, Spring khôi phục T1 sau đó. Cuối test, rollback T1 không thể undo T2 đã commit.

Đây là lý do một test có @Transactional vẫn có thể để lại dữ liệu sau khi chạy. Khi gặp trường hợp này, cần dọn dữ liệu audit đã commit hoặc thiết kế test để kiểm tra nó bằng một fixture riêng.

### 6.2. NOT_SUPPORTED chạy ngoài transaction test

Một phương thức NOT_SUPPORTED tạm dừng transaction đang có trong thời gian thực thi. Nếu phương thức thực hiện thao tác ghi bằng một cơ chế tự commit hoặc một transaction độc lập, thay đổi đó không nằm trong transaction test và không được rollback cùng test.

Không nên dùng NOT_SUPPORTED chỉ để tránh lỗi rollback mà không hiểu code bên trong đang dùng cơ chế transaction nào. Hãy xác định rõ thao tác cần kiểm tra có phải được commit độc lập hay không.

### 6.3. NESTED phụ thuộc khả năng savepoint

NESTED thường được thực hiện bằng savepoint trong transaction hiện tại. Nó không giống REQUIRES_NEW: nested transaction không nhất thiết tạo một transaction vật lý độc lập. Khả năng hỗ trợ phụ thuộc transaction manager, driver và cấu hình resource. Nếu không có hỗ trợ savepoint, lời gọi có thể thất bại hoặc không có ngữ nghĩa mà test mong đợi.

## 7. Test không có test-managed transaction vẫn kiểm tra application transaction

Không phải test nào cũng cần đặt @Transactional ở cấp test. Nếu mục tiêu là kiểm tra service tự mở và commit transaction theo hành vi ứng dụng, hãy gọi service trong test không có transaction bao quanh:

```java
@SpringJUnitConfig(classes = OrderApplicationTestConfiguration.class)
class OrderServiceCommitTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void serviceTransactionCommitsAfterMethodReturns() {
        Order order = orderService.create(new CreateOrderCommand("SKU-1", 2));

        // Truy vấn sau khi service transaction đã kết thúc.
        assertThat(orderRepository.findById(order.getId())).isPresent();
    }
}
```

Trong ví dụ này, nếu OrderService.create() được gọi qua Spring proxy và có @Transactional, service tự bắt đầu và commit transaction theo quy tắc ứng dụng. Assertion sau lời gọi kiểm tra dữ liệu đã được commit.

Test này cần dọn dữ liệu sau khi chạy, chẳng hạn xóa order theo id trong @AfterEach hoặc dùng database riêng cho test. Nếu muốn kiểm tra rollback khi service ném exception, hãy tạo một test riêng xác nhận dữ liệu không được lưu theo quy tắc rollback của service.

## 8. Điều khiển test-managed transaction bằng TestTransaction

Annotation @Commit và @Rollback đủ cho nhiều trường hợp. Khi cần kết thúc transaction giữa test method, bắt đầu transaction mới hoặc quyết định commit theo logic runtime, Spring Test cung cấp TestTransaction.

Các thao tác chính:

| API | Ý nghĩa |
|---|---|
| TestTransaction.isActive() | Kiểm tra test-managed transaction có đang hoạt động không. |
| TestTransaction.flagForCommit() | Đánh dấu transaction hiện tại sẽ commit khi kết thúc. |
| TestTransaction.flagForRollback() | Đánh dấu transaction hiện tại sẽ rollback khi kết thúc. |
| TestTransaction.end() | Kết thúc transaction hiện tại theo quyết định commit/rollback đã đánh dấu. |
| TestTransaction.start() | Bắt đầu một test-managed transaction mới. |

Ví dụ commit một phần rồi tiếp tục kiểm tra trong transaction mới:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountTransactionTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void commitsFirstPhaseAndRunsSecondPhaseInNewTransaction() {
        accountRepository.save(new Account("ACC-200"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(accountRepository.findByCode("ACC-200")).isPresent();

        TestTransaction.start();
        accountRepository.save(new Account("ACC-201"));
        // Transaction mới sẽ rollback theo mặc định khi test kết thúc.
    }
}
```

Sau end(), transaction test đầu tiên đã kết thúc. Assertion truy vấn sau commit xác nhận dữ liệu đã tồn tại. start() mở transaction test mới; nếu không đánh dấu commit, transaction mới sẽ rollback khi test hoàn tất.

Không gọi TestTransaction trong test không có test-managed transaction. API này điều khiển transaction do Spring Test quản lý, không phải công cụ chung để commit bất kỳ application transaction nào.

## 9. Callback chạy trong và ngoài test-managed transaction

Thời điểm callback chạy ảnh hưởng việc dữ liệu fixture có nằm trong transaction test hay không.

| Callback | Quan hệ với test-managed transaction |
|---|---|
| @BeforeTransaction | Chạy trước khi transaction test bắt đầu. |
| @BeforeEach | Chạy trong transaction test nếu test được cấu hình transactional. |
| Test method | Chạy trong transaction test nếu được cấu hình transactional. |
| @AfterEach | Chạy trước khi transaction test kết thúc, do đó vẫn trong transaction test. |
| @AfterTransaction | Chạy sau khi transaction test đã kết thúc. |
| @BeforeAll / @AfterAll | Chạy ngoài transaction của từng test method. |

Ví dụ:

```java
@SpringJUnitConfig(classes = PersistenceTestConfiguration.class)
@Transactional
class AccountLifecycleTest {

    @BeforeTransaction
    void verifyDatabaseBeforeTransaction() {
        // Kiểm tra trạng thái đã commit trước khi transaction test bắt đầu.
    }

    @BeforeEach
    void prepareInsideTransaction() {
        // Fixture được tạo ở đây thuộc transaction test.
    }

    @AfterEach
    void inspectBeforeRollback() {
        // Vẫn có thể đọc thay đổi chưa commit trong transaction test.
    }

    @AfterTransaction
    void verifyAfterTransaction() {
        // Chạy sau commit/rollback của transaction test.
    }
}
```

Các callback @BeforeTransaction và @AfterTransaction là callback của Spring TestContext, không phải annotation lifecycle của JUnit. Chúng cần SpringExtension/TestContext được cấu hình và chỉ được gọi khi có test-managed transaction phù hợp.

## 10. Thread-bound transaction và giới hạn của rollback

Với transaction manager imperative thông dụng, transaction được gắn với thread hiện tại thông qua cơ chế thread-local. Spring bind transaction resources như JDBC connection vào thread đang chạy test.

Điều đó dẫn đến một giới hạn quan trọng: code chạy ở thread khác không tự động tham gia transaction test. Ví dụ:

```java
@Test
@Transactional
void writesFromAnotherThread() {
    executorService.submit(() -> orderService.create(command)).join();
}
```

Nếu executor chạy công việc trên thread khác, transaction test của thread test không tự truyền sang thread đó. Service có thể mở và commit transaction riêng. Khi test kết thúc, rollback của transaction test không hoàn tác được transaction riêng này.

Tương tự, test dùng preemptive timeout như assertTimeoutPreemptively() của JUnit Jupiter có thể chạy executable trong thread khác. Nếu thao tác database diễn ra trong thread đó, nó có thể nằm ngoài test-managed transaction dù phương thức test được đánh dấu @Transactional.

Một request gửi đến server thật cũng thường được xử lý ở thread của server:

```text
Test thread
  +-- test-managed transaction T1
        +-- gửi HTTP request
              |
              v
        Server request thread
          +-- application transaction T2

Rollback T1 không rollback T2 nếu T2 độc lập.
```

Vì vậy, khi dùng @SpringBootTest(webEnvironment = RANDOM_PORT) hoặc DEFINED_PORT, không nên giả định transaction của test bao trùm transaction xử lý request HTTP. Hãy dọn dữ liệu đã commit qua API hoặc repository phù hợp, dùng database/container riêng, hoặc thiết kế chiến lược kiểm thử dữ liệu rõ ràng.

## 11. Transaction test và @Transactional trên service

Khi cùng một service được gọi trong và ngoài test-managed transaction, kết quả có thể khác:

| Cách gọi | Ranh giới transaction |
|---|---|
| Test không có `@Transactional`, gọi service `@Transactional(REQUIRED)` | Service mở và kết thúc transaction của nó. |
| Test có `@Transactional`, gọi service `@Transactional(REQUIRED)` cùng thread | Service tham gia transaction test; test quyết định rollback/commit cuối cùng. |
| Test có `@Transactional`, gọi service `@Transactional(REQUIRES_NEW)` | Service mở transaction độc lập; transaction đó có thể commit trước khi test rollback. |
| Test có `@Transactional`, gọi service `@Transactional(NOT_SUPPORTED)` | Transaction test bị tạm dừng trong lời gọi; thao tác bên trong chạy ngoài transaction đó. |
| Test có `@Transactional`, gọi service qua thread khác | Transaction thread test không tự truyền sang thread mới. |

Điều này giải thích vì sao một test với @Transactional có thể không tái hiện đúng hành vi commit của service khi chạy trong ứng dụng. Nếu mục tiêu là xác nhận transaction boundary của service, hãy có ít nhất một test gọi service mà không có transaction test bao quanh và kiểm tra trạng thái sau khi service trả về.

## 12. Quy tắc rollback khi có exception

Đối với application-managed transaction được tạo bởi @Transactional, quy tắc rollback thường dựa trên loại exception: mặc định Spring rollback với unchecked exception và Error, còn checked exception không tự động rollback trừ khi cấu hình rollback rule phù hợp.

Test-managed transaction có cơ chế quyết định commit/rollback riêng của Spring Test. Mặc định, transaction test rollback sau khi test hoàn tất, kể cả khi test thất bại. Không nên suy luận rằng rollback của test đang chứng minh rollback rule của service hoạt động đúng; test có thể rollback toàn bộ transaction sau khi service đã hoàn thành.

Nếu muốn kiểm tra rollback rule của service, hãy gọi service qua proxy trong một test không có test-managed transaction, tạo điều kiện để service transaction kết thúc, rồi truy vấn trạng thái dữ liệu trong một transaction khác hoặc qua repository phù hợp.

Ví dụ khái niệm:

```java
@Service
class RegistrationService {

    private final RegistrationRepository repository;

    RegistrationService(RegistrationRepository repository) {
        this.repository = repository;
    }

    @Transactional(rollbackFor = IOException.class)
    public void registerThenFail() throws IOException {
        repository.save(new Registration("user-1"));
        throw new IOException("External registration failed");
    }
}
```

Nếu không khai báo rollbackFor, checked exception như IOException không mặc định khiến transaction application rollback. Với cấu hình ở ví dụ, transaction của service được rollback khi exception đó thoát khỏi phương thức qua proxy.

## 13. Một số thuộc tính @Transactional trên test cần được dùng đúng phạm vi

@Transactional trên test method/class được Spring Test sử dụng để điều khiển test-managed transaction. Cách diễn giải của annotation ở đây không hoàn toàn giống khi đặt trên service method.

Hãy lưu ý:

- Dùng @Commit và @Rollback để diễn đạt quyết định kết thúc test transaction.
- Chọn đúng transaction manager khi context có nhiều manager.
- Các propagation đặc biệt như NOT_SUPPORTED hoặc NEVER có thể làm test không chạy trong transaction như kỳ vọng.
- Không giả định mọi thuộc tính của @Transactional trên service đều được hỗ trợ hoặc có cùng ý nghĩa khi đặt trên test class/method. Hãy đối chiếu tài liệu đúng phiên bản Spring đang dùng.
- Nếu cần một transaction với isolation, timeout hoặc quy tắc rollback riêng cho nghiệp vụ, hãy cấu hình ở application service/transaction template và kiểm tra bằng bài test phù hợp.

Một test được đánh dấu @Transactional không tự chứng minh rằng service đã được gọi qua Spring proxy. Nếu test tạo service bằng new hoặc gọi phương thức nội bộ qua self-invocation, annotation trên service có thể không được áp dụng như trong ứng dụng.

## 14. Những lỗi thường gặp

### Nghĩ rằng mọi thao tác database đều rollback vì test có @Transactional

Rollback chỉ tác động đến transaction test đang quản lý. Transaction REQUIRES_NEW, transaction trên thread khác, request server thật hoặc thao tác không tham gia transaction đó có thể đã commit độc lập.

### Đọc dữ liệu sau khi transaction đã rollback

Nếu assertion được thực hiện sau @AfterTransaction, dữ liệu chỉ tồn tại trong transaction test đã bị rollback sẽ không còn. Nếu muốn kiểm tra dữ liệu trước khi rollback, assertion cần chạy trong test transaction; nếu muốn kiểm tra sau commit, dùng @Commit hoặc TestTransaction.

### Service tự mở transaction nhưng test không dùng Spring proxy

Tạo service bằng new không kích hoạt transaction interceptor. Nếu muốn kiểm tra application-managed transaction, hãy lấy service bean từ context và gọi qua proxy Spring.

### Dùng @Transactional trên test để kiểm tra rollback rule của service

Test transaction có thể rollback toàn bộ dữ liệu sau khi service hoàn thành, làm test vượt qua dù rollback rule của service không hoạt động như mong đợi. Kiểm tra transaction của service bằng một test không có transaction bao quanh.

### Dùng preemptive timeout với thao tác ghi dữ liệu

Test code có thể chạy trên thread khác với thread giữ transaction. Dữ liệu ghi ở thread phụ có thể commit độc lập. Dùng timeout không preemptive hoặc có chiến lược dọn dữ liệu rõ ràng khi test thao tác với database.

### Chạy test qua HTTP server rồi chờ rollback từ test thread

Request được xử lý trong server thread với transaction riêng. Test transaction không tự bao trùm request. Hãy dọn dữ liệu sau request hoặc dùng môi trường database cô lập.

### Quên rằng @BeforeEach và @AfterEach chạy trong test transaction

Fixture tạo trong @BeforeEach thường nằm trong transaction test và bị rollback cùng test. Nếu cần dữ liệu đã commit trước khi test transaction bắt đầu, dùng callback @BeforeTransaction hoặc cơ chế chuẩn bị dữ liệu độc lập.

### Nhầm @Commit với commit của service

@Commit yêu cầu commit test-managed transaction khi test hoàn tất. Nó không thay đổi propagation hoặc rollback rule của application service.

## 15. Chọn cách kiểm thử theo mục tiêu

| Mục tiêu | Cách kiểm thử phù hợp |
|---|---|
| Kiểm tra repository/service và tự động dọn dữ liệu sau test | Dùng test-managed transaction với `@Transactional` và rollback mặc định. |
| Kiểm tra service tham gia transaction đang có | Mở test-managed transaction rồi gọi service REQUIRED trên cùng thread. |
| Kiểm tra service tự commit khi chạy độc lập | Không đánh dấu test `@Transactional`; gọi service bean qua Spring proxy và xác nhận dữ liệu sau lời gọi. |
| Kiểm tra REQUIRES_NEW commit độc lập | Gọi service trong test transaction, sau đó xác nhận transaction độc lập vẫn tồn tại sau rollback của test và dọn dữ liệu. |
| Kiểm tra rollback rule của service | Gọi service qua proxy mà không có test transaction bao quanh, sau đó kiểm tra trạng thái đã commit. |
| Kiểm tra request qua server thật | Dùng chiến lược dọn dữ liệu riêng; không dựa vào transaction của test thread. |
| Cần commit một giai đoạn rồi tiếp tục test | Dùng `TestTransaction.flagForCommit()`, `end()` và `start()` khi đang có test-managed transaction. |

Test-managed transaction là công cụ cô lập dữ liệu theo vòng đời test. Application-managed transaction thể hiện ranh giới nghiệp vụ của code chạy trong ứng dụng. Khi hai loại transaction gặp nhau, propagation, transaction manager và thread đang thực thi quyết định thao tác nào được rollback cùng test và thao tác nào có thể commit độc lập.
