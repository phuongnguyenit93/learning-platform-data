# @BeforeEach và @AfterEach trong phạm vi giao dịch kiểm thử

Trong một bài kiểm thử Spring có transaction do TestContext Framework quản lý, thứ tự chuẩn bị dữ liệu, chạy test và dọn dữ liệu quyết định trạng thái nào được nhìn thấy và thay đổi nào được rollback. Hai lifecycle method của JUnit Jupiter là **@BeforeEach** và **@AfterEach** thường được dùng để chuẩn bị fixture và kiểm tra trạng thái sau mỗi test. Khi test được đánh dấu **@Transactional**, cả hai phương thức này chạy trong test-managed transaction của Spring.

Điều đó có nghĩa là dữ liệu được ghi trong **@BeforeEach**, thay đổi trong test method và thao tác trong **@AfterEach** thường cùng nằm trong một transaction. Theo mặc định, Spring rollback transaction sau test method. Vì vậy, **@AfterEach** có thể nhìn thấy những thay đổi vừa thực hiện, còn trạng thái database sau khi transaction kết thúc thường trở về trạng thái trước test.

Spring cũng cung cấp hai annotation riêng là **@BeforeTransaction** và **@AfterTransaction**. Chúng cho phép thực hiện công việc trước khi transaction bắt đầu và sau khi transaction đã commit hoặc rollback. Phân biệt đúng bốn lifecycle hook này giúp tránh việc kiểm tra dữ liệu ở sai thời điểm, cleanup không có tác dụng hoặc test vô tình để lại dữ liệu đã commit.

## 1. Test-managed transaction là gì?

Spring TestContext Framework có thể mở một transaction bao quanh mỗi test method. Transaction này được gọi là *test-managed transaction*. Nó được quản lý bởi **TransactionalTestExecutionListener** và thường được kích hoạt khi test class hoặc test method có **@Transactional**.

Ví dụ:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesAnOrder() {
        repository.save(new OrderEntity("order-176", "customer-12"));

        assertTrue(repository.findById("order-176").isPresent());
    }
}
~~~

Spring bắt đầu transaction cho test, chạy phương thức kiểm thử, rồi kết thúc transaction theo chính sách rollback hoặc commit đã cấu hình. Mặc định, test-managed transaction được rollback sau mỗi test method.

Điều này giúp test persistence có thể ghi dữ liệu và kiểm tra kết quả ngay trong cùng transaction mà không để lại thay đổi lâu dài trong database. Tuy nhiên, rollback chỉ áp dụng cho thao tác tham gia transaction đó. Message đã gửi đến broker, HTTP request đã gửi ra ngoài, file đã ghi hoặc transaction độc lập đã commit sẽ không tự động được hoàn tác.

### Test-managed transaction khác transaction của ứng dụng

Có hai loại transaction cần phân biệt:

- **Test-managed transaction** được Spring TestContext mở quanh test method vì test có cấu hình transactional.
- **Spring-managed transaction** được ứng dụng mở khi một method có **@Transactional** được gọi qua cơ chế transaction của Spring.

Một service có propagation **REQUIRED** thường tham gia transaction hiện tại của test. Nếu service dùng **REQUIRES_NEW**, Spring tạm dừng transaction của test và mở một transaction độc lập. Transaction độc lập đó có thể commit và tồn tại sau khi transaction của test rollback.

Vì vậy, câu nói “test có @Transactional nên mọi dữ liệu đều được rollback” chỉ đúng với các thay đổi tham gia test-managed transaction.

## 2. Thứ tự thực thi của @BeforeEach và @AfterEach

Khi test được tích hợp với SpringExtension, Spring TestContext tham gia vòng đời JUnit Jupiter. Với test-managed transaction thông thường, trình tự khái quát là:

~~~text
JUnit tạo test instance
        |
        v
Spring inject dependency vào test instance
        |
        v
Spring TestContext: beforeTestMethod
        |
        +--> @BeforeTransaction
        |
        +--> Bắt đầu test-managed transaction
        |
        v
JUnit @BeforeEach
        |
        v
JUnit @BeforeTestExecution (nếu có)
        |
        v
JUnit @Test
        |
        v
JUnit @AfterTestExecution (nếu có)
        |
        v
JUnit @AfterEach
        |
        v
Spring TestContext: afterTestMethod
        |
        +--> Commit hoặc rollback test-managed transaction
        |
        +--> @AfterTransaction
        |
        v
Hoàn tất test method
~~~

Sơ đồ mô tả thứ tự phổ biến khi SpringExtension và TransactionalTestExecutionListener quản lý test. Các extension khác có thể bổ sung callback của riêng chúng, nhưng nguyên tắc quan trọng vẫn là transaction được Spring bắt đầu trước lifecycle method **@BeforeEach** và kết thúc sau **@AfterEach**.

Do đó:

- **@BeforeEach** có thể tạo dữ liệu nằm trong transaction của test.
- Test method nhìn thấy dữ liệu được chuẩn bị trong **@BeforeEach**.
- **@AfterEach** có thể đọc hoặc thay đổi dữ liệu trong cùng transaction.
- Sau khi **@AfterEach** hoàn tất, Spring mới thực hiện rollback hoặc commit.
- **@AfterTransaction** chạy sau khi test-managed transaction đã kết thúc.

Nếu test không có test-managed transaction, **@BeforeEach** và **@AfterEach** vẫn chạy theo vòng đời JUnit bình thường, nhưng không có transaction bao quanh chúng chỉ vì chúng là lifecycle method.

## 3. Chuẩn bị dữ liệu bằng @BeforeEach

**@BeforeEach** chạy trước từng test method. Đây là vị trí phù hợp để tạo fixture, đặt trạng thái ban đầu hoặc reset collaborator cho mỗi lần kiểm thử.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepareData() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void findsPreparedOrder() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        assertEquals("customer-12", order.getCustomerId());
        assertEquals("PENDING", order.getStatus());
    }

    @Test
    void changesOrderStatus() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        order.setStatus("PAID");

        assertEquals(
                "PAID",
                repository.findById("order-176").orElseThrow().getStatus()
        );
    }
}
~~~

Mỗi test method có một lần chạy **@BeforeEach**. Dữ liệu được lưu trong test-managed transaction. Khi test kết thúc và transaction rollback, bản ghi được tạo trong lần chạy đó cũng được hoàn tác.

Vì vậy, nếu hai test dùng cùng ID, chúng vẫn có thể chạy độc lập khi mỗi lần chạy được bao quanh bởi transaction riêng và không có thao tác nào commit dữ liệu ra ngoài. Nếu test chạy song song hoặc có transaction độc lập, nên dùng ID riêng để tránh xung đột.

### Không cần xóa database một cách rộng rãi

Một số test dùng **@BeforeEach** để gọi **deleteAll()** trước khi tạo dữ liệu. Cách này có thể phù hợp với database riêng cho test, nhưng cần hiểu tác động transaction:

- Nếu deleteAll chạy trong test-managed transaction, thao tác xóa cũng bị rollback ở cuối test.
- Dữ liệu đã tồn tại trước test có thể xuất hiện trở lại sau rollback.
- Nếu deleteAll chạy trong transaction độc lập hoặc được commit, dữ liệu có thể bị xóa thật.

Hãy tránh dùng thao tác xóa rộng trên database dùng chung. Tạo fixture với ID riêng hoặc dọn đúng phạm vi dữ liệu mà test sở hữu sẽ an toàn và dễ hiểu hơn.

## 4. Kiểm tra trạng thái trước khi rollback bằng @AfterEach

**@AfterEach** chạy sau test method nhưng trước khi Spring kết thúc test-managed transaction. Vì vậy, nó vẫn nhìn thấy dữ liệu được tạo hoặc thay đổi trong test.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderLifecycleTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void updatesOrder() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        order.setStatus("PAID");
    }

    @AfterEach
    void verifiesStateBeforeRollback() {
        OrderEntity order = repository.findById("order-176")
                .orElseThrow();

        assertEquals("PAID", order.getStatus());
    }
}
~~~

Trong ví dụ, **@AfterEach** đọc trạng thái PAID vì transaction chưa rollback. Đây là thời điểm phù hợp để xác nhận những thay đổi cuối cùng của test trước khi transaction kết thúc.

Nếu mục tiêu là kiểm tra dữ liệu đã được commit và tồn tại sau khi transaction kết thúc, **@AfterEach** chưa phải thời điểm phù hợp. Hãy dùng **@AfterTransaction** hoặc một test khác đọc dữ liệu sau khi transaction đã hoàn tất.

### Cleanup trong @AfterEach có thể bị rollback

Giả sử **@AfterEach** gọi:

~~~java
@AfterEach
void cleanUp() {
    repository.deleteById("order-176");
}
~~~

Nếu thao tác xóa tham gia cùng test-managed transaction và transaction sẽ rollback, thao tác xóa cũng bị rollback. Bản ghi được tạo trong **@BeforeEach** vẫn bị loại bỏ bởi rollback của transaction, nhưng thao tác cleanup không được commit riêng.

Đây là hành vi mong đợi trong nhiều test persistence. Không cần thêm cleanup database nếu toàn bộ dữ liệu đã được tạo và thay đổi trong transaction sẽ rollback.

Nếu test được cấu hình commit, cleanup trong **@AfterEach** có thể được commit cùng transaction. Hãy xác định rõ mục tiêu của test trước khi quyết định dọn dữ liệu ở đây.

## 5. @BeforeTransaction và @AfterTransaction khác gì?

Spring TestContext cung cấp hai annotation để chạy code ở ngoài test-managed transaction:

- **@BeforeTransaction** chạy trước khi transaction của test bắt đầu.
- **@AfterTransaction** chạy sau khi transaction của test đã commit hoặc rollback.

Hai annotation này thuộc Spring TestContext Framework, không phải lifecycle annotation của JUnit Jupiter. Chúng được xử lý bởi **TransactionalTestExecutionListener**.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderPersistenceTestConfig.class)
@Transactional
class OrderTransactionBoundaryTest {

    @Autowired
    private OrderRepository repository;

    @BeforeTransaction
    void verifyStateBeforeTestTransaction() {
        assertFalse(repository.existsById("order-176"));
    }

    @BeforeEach
    void prepareData() {
        repository.save(
                new OrderEntity("order-176", "customer-12", "PENDING")
        );
    }

    @Test
    void seesPreparedOrderInsideTransaction() {
        assertTrue(repository.existsById("order-176"));
    }

    @AfterEach
    void verifyBeforeRollback() {
        assertTrue(repository.existsById("order-176"));
    }

    @AfterTransaction
    void verifyStateAfterRollback() {
        assertFalse(repository.existsById("order-176"));
    }
}
~~~

Ví dụ giả định database test bắt đầu ở trạng thái không có bản ghi có ID order-176 và test dùng transaction manager phù hợp. Trình tự quan sát là:

1. **@BeforeTransaction** kiểm tra trạng thái trước test-managed transaction.
2. Spring bắt đầu transaction.
3. **@BeforeEach** tạo bản ghi.
4. Test method nhìn thấy bản ghi.
5. **@AfterEach** vẫn nhìn thấy bản ghi vì transaction chưa kết thúc.
6. Spring rollback transaction theo mặc định.
7. **@AfterTransaction** kiểm tra bản ghi không còn trong database.

Nếu test dùng **@Commit** hoặc **@Rollback(false)**, kết quả sau transaction sẽ khác: dữ liệu được commit và **@AfterTransaction** có thể nhìn thấy bản ghi.

### Khi nào cần hai hook này?

Dùng **@BeforeTransaction** khi cần:

- Kiểm tra baseline đã commit trước khi test bắt đầu.
- Chuẩn bị dữ liệu cần tồn tại ngoài transaction của test.
- Xác minh dữ liệu được commit từ test trước hoặc từ một tiến trình khác.
- Thiết lập trạng thái mà transaction của test phải đọc như dữ liệu đã commit.

Dùng **@AfterTransaction** khi cần:

- Xác minh rollback đã loại bỏ thay đổi.
- Xác minh commit đã lưu dữ liệu.
- Dọn dữ liệu được commit hoặc được tạo ngoài transaction.
- Kiểm tra trạng thái sau khi transaction kết thúc.

Hai hook này chỉ có ý nghĩa khi test-managed transaction thực sự được tạo. Nếu test không có transaction, chúng không thay thế **@BeforeEach** và **@AfterEach**.

## 6. So sánh bốn lifecycle hook

| Hook | Thời điểm | Có nằm trong test-managed transaction? | Mục đích thường gặp |
|---|---|---|---|
| @BeforeTransaction | Trước khi transaction bắt đầu | Không | Kiểm tra baseline hoặc chuẩn bị dữ liệu ngoài transaction |
| @BeforeEach | Trước từng test method | Có, nếu test có transaction | Tạo fixture cho từng test |
| @AfterEach | Sau từng test method, trước khi transaction kết thúc | Có, nếu test có transaction | Kiểm tra trạng thái trước rollback/commit |
| @AfterTransaction | Sau khi transaction kết thúc | Không | Kiểm tra kết quả commit/rollback hoặc cleanup sau transaction |

Một điểm khác biệt nữa là **@BeforeAll** và **@AfterAll** của JUnit Jupiter chạy một lần cho test class. Chúng không nằm trong transaction riêng của từng test method do Spring TestContext quản lý. Không nên dùng chúng để tạo dữ liệu mà mỗi test method cần nhìn thấy trong transaction của nó, trừ khi chủ động quản lý transaction và trạng thái dùng chung.

## 7. Dùng @Transactional ở class hay test method?

Có thể đặt **@Transactional** trên test class để các test method trong class đều chạy trong test-managed transaction:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@Transactional
class AllOrderTests {
}
~~~

Hoặc đặt trên một test method cụ thể:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class MixedTransactionTests {

    @Test
    @Transactional
    void runsInsideTestTransaction() {
        // Test body
    }

    @Test
    void runsWithoutTestManagedTransaction() {
        // Test body
    }
}
~~~

Khi transaction chỉ cần cho một số test, method-level annotation giúp phạm vi rõ ràng. Khi toàn bộ class kiểm tra persistence và cần rollback mặc định, class-level annotation có thể gọn hơn.

Đặt **@Transactional** trên test class hoặc test method để cấu hình test-managed transaction. Đánh dấu riêng một phương thức **@BeforeEach** hoặc **@AfterEach** bằng **@Transactional** không phải cách đáng tin cậy để yêu cầu Spring tạo một transaction độc lập cho lifecycle method. Nếu cần transaction riêng trong một hook, hãy dùng **TransactionTemplate** hoặc gọi một service có transaction boundary được cấu hình rõ ràng.

### Chọn transaction manager khi có nhiều manager

Một ApplicationContext có thể chứa nhiều **PlatformTransactionManager**, ví dụ một manager cho database đơn hàng và một manager cho database báo cáo. Nếu test dùng sai manager, dữ liệu được kiểm tra có thể không thuộc transaction đang rollback.

Có thể chỉ định manager bằng qualifier trong **@Transactional**:

~~~java
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
}
~~~

Hoặc dùng thuộc tính **transactionManager**. Hãy bảo đảm repository và service được test tham gia đúng transaction manager mà test-managed transaction sử dụng.

## 8. Mặc định rollback và khi nào commit

Spring TestContext mặc định rollback test-managed transaction sau mỗi test method. Đây là chính sách an toàn cho test persistence vì test không để lại dữ liệu.

Có thể điều khiển hành vi bằng **@Rollback**:

~~~java
@Test
@Rollback
void rollsBackByDefault() {
    // Changes are rolled back after the test
}
~~~

Để yêu cầu commit:

~~~java
@Test
@Commit
void commitsChangesAfterTheTest() {
    // Changes are committed after the test
}
~~~

**@Commit** tương đương với cấu hình rollback false. Có thể dùng **@Rollback(false)** nếu muốn thể hiện rõ giá trị thuộc tính.

Chỉ commit khi test cần xác minh hành vi phụ thuộc vào dữ liệu đã được commit, hoặc cần tạo dữ liệu bền vững cho một bước tích hợp được thiết kế riêng. Test commit phải có chiến lược dọn dữ liệu, nếu không những lần chạy sau có thể gặp duplicate key hoặc đọc nhầm dữ liệu cũ.

Không nên chuyển toàn bộ test class sang commit chỉ để một test xác minh dữ liệu đã lưu. Có thể đặt chính sách commit trên method cụ thể hoặc dùng **TestTransaction** để kết thúc transaction có chủ đích.

### Điều khiển transaction bằng TestTransaction

Spring TestContext cung cấp **TestTransaction** để kiểm tra và điều khiển test-managed transaction trong lúc test chạy.

Ví dụ:

~~~java
@Test
@Transactional
void commitsWhenExplicitlyRequested() {
    repository.save(new OrderEntity("order-commit-1", "customer-1", "PAID"));

    assertTrue(TestTransaction.isActive());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertFalse(TestTransaction.isActive());
}
~~~

**flagForCommit()** đánh dấu transaction hiện tại sẽ commit khi kết thúc bằng **end()**. Nếu không đánh dấu commit, transaction thường rollback theo mặc định. Sau khi kết thúc, có thể bắt đầu transaction mới bằng **TestTransaction.start()** nếu test cần thực hiện thêm thao tác trong một transaction khác.

Không nên gọi **TestTransaction.end()** chỉ để tránh cleanup thông thường. Nó làm thay đổi vòng đời transaction của test và có thể khiến các thao tác tiếp theo chạy ngoài transaction nếu không bắt đầu lại.

## 9. @BeforeEach chuẩn bị dữ liệu trong cùng transaction với test

Một lợi ích của việc dùng **@BeforeEach** trong test transactional là dữ liệu chuẩn bị và hành vi được kiểm tra cùng tham gia transaction.

Ví dụ service cập nhật trạng thái đơn hàng:

~~~java
@SpringJUnitConfig(OrderServiceTestConfig.class)
@Transactional
class OrderServiceTransactionTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void createPendingOrder() {
        repository.save(
                new Order("order-176", OrderStatus.PENDING)
        );
    }

    @Test
    void marksOrderAsPaid() {
        orderService.markPaid("order-176");

        assertEquals(
                OrderStatus.PAID,
                repository.findById("order-176").orElseThrow().status()
        );
    }
}
~~~

Nếu **markPaid** dùng propagation **REQUIRED**, lời gọi service thường tham gia transaction đang mở của test. Khi test kết thúc, thay đổi trạng thái và bản ghi fixture đều rollback.

Cách này phù hợp để kiểm tra logic persistence trong cùng transaction. Tuy nhiên, nó không chứng minh dữ liệu đã được commit và có thể đọc từ một transaction khác. Nếu mục tiêu là kiểm tra tính nhìn thấy sau commit, cần kết thúc transaction hoặc dùng một bài test khác quan sát sau transaction.

## 10. Lưu ý với propagation REQUIRES_NEW

Một service method có **Propagation.REQUIRES_NEW** yêu cầu Spring mở transaction độc lập. Transaction test hiện tại bị tạm dừng trong lúc transaction mới chạy.

Ví dụ:

~~~java
@Service
class AuditService {

    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        repository.save(new AuditEntry(event));
    }
}
~~~

Nếu test gọi **auditService.record(...)**, bản ghi audit có thể được commit trong transaction riêng. Sau đó, transaction của test rollback nhưng bản ghi audit vẫn tồn tại.

Điều này ảnh hưởng cả dữ liệu setup. Nếu **@BeforeEach** tạo một bản ghi trong transaction test nhưng service được gọi dùng **REQUIRES_NEW**, transaction độc lập có thể không nhìn thấy bản ghi chưa commit đó. Cơ sở dữ liệu thông thường không cho transaction khác đọc dữ liệu chưa commit của transaction test.

Khi cần chuẩn bị dữ liệu cho transaction độc lập:

- Tạo dữ liệu baseline đã commit trước khi test transaction bắt đầu, có thể dùng **@BeforeTransaction**.
- Dùng một transaction setup riêng và kết thúc nó trước khi gọi service.
- Thiết kế test để xác minh đúng ranh giới commit của service.
- Dọn dữ liệu được commit bởi transaction độc lập sau test.

Đừng giả định rollback của test sẽ thu hồi mọi thay đổi do service tạo ra. Hãy xem propagation và transaction manager của từng collaborator.

## 11. @BeforeEach và @AfterEach khi test không dùng transaction

Nếu test class không có **@Transactional**, hai lifecycle method vẫn hoạt động nhưng không có transaction test-managed bao quanh.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderServiceTestConfig.class)
class NonTransactionalOrderTest {

    @Autowired
    private OrderRepository repository;

    @BeforeEach
    void prepare() {
        repository.save(new Order("order-176", OrderStatus.PENDING));
    }

    @Test
    void readsOrder() {
        assertTrue(repository.findById("order-176").isPresent());
    }

    @AfterEach
    void cleanUp() {
        repository.deleteById("order-176");
    }
}
~~~

Trong ví dụ này, mỗi phương thức repository có thể tự chạy transaction theo cấu hình của repository hoặc service. Lệnh save có thể đã commit trước khi test method bắt đầu. Vì vậy, nếu test thất bại trước cleanup hoặc cleanup không chạy thành công, dữ liệu có thể còn lại.

Đối với test không transactional, cần một chiến lược cleanup rõ ràng:

- Dùng ID riêng cho từng test.
- Dọn đúng bản ghi do test tạo.
- Dùng schema hoặc database riêng khi có nhiều test chạy song song.
- Dùng container hoặc fixture lifecycle để reset tài nguyên.
- Đặt cleanup trong hook teardown phù hợp và bảo đảm xử lý cả trường hợp lỗi.

Không nên cho rằng chỉ vì có **@BeforeEach** và **@AfterEach** thì dữ liệu tự được rollback. Rollback là hành vi của transaction manager, không phải của JUnit lifecycle.

## 12. @AfterEach không phải lúc nào cũng là nơi xác minh kết quả cuối cùng

Có hai loại assertion thường bị nhầm:

- Assertion về trạng thái bên trong transaction, trước khi rollback hoặc commit.
- Assertion về trạng thái đã được commit hoặc rollback trong database sau transaction.

**@AfterEach** phù hợp với loại thứ nhất. **@AfterTransaction** phù hợp với loại thứ hai.

Ví dụ, nếu test dùng mặc định rollback:

~~~java
@AfterEach
void seesUncommittedChange() {
    assertTrue(repository.existsById("order-176"));
}
~~~

Assertion có thể đúng vì bản ghi vẫn tồn tại trong transaction hiện tại.

Sau rollback:

~~~java
@AfterTransaction
void doesNotSeeRolledBackChange() {
    assertFalse(repository.existsById("order-176"));
}
~~~

Assertion thứ hai xác minh trạng thái sau khi transaction kết thúc.

Nếu dùng **@Commit**, kết quả sau transaction có thể là bản ghi vẫn tồn tại. Hãy viết expected tương ứng với chính sách transaction của test. Không dùng một assertion giống nhau cho cả rollback và commit.

## 13. Ảnh hưởng của @Sql và dữ liệu chuẩn bị

Spring TestContext hỗ trợ **@Sql** để chạy SQL script trước hoặc sau test method. Nó thường được dùng cùng transaction test để chuẩn bị fixture.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
@Sql(
    scripts = "/sql/order-before-test.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderSqlTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void readsSqlFixture() {
        assertTrue(repository.existsById("order-176"));
    }
}
~~~

Với cấu hình mặc định, SQL script có thể tham gia transaction hiện tại khi có transaction phù hợp. Khi đó, dữ liệu do script tạo cũng rollback cùng test.

Nếu **@Sql** dùng transaction mode riêng hoặc test không có transaction, hành vi commit và cleanup có thể khác. Hãy xem cấu hình **SqlConfig.TransactionMode** và transaction manager được chọn cho script.

Có thể dùng **@Sql** ở phase **AFTER_TEST_METHOD** để chạy cleanup script. Tuy nhiên, nếu script chạy trong transaction sắp rollback, thao tác cleanup cũng có thể rollback. Hãy xác định dữ liệu có được commit hay không trước khi quyết định dùng script sau test.

Đừng kết hợp **@BeforeEach**, **@Sql** và **@AfterEach** để cùng chuẩn bị một fixture nếu không có lý do rõ ràng. Chọn một nguồn setup chính giúp thứ tự và trách nhiệm dễ hiểu hơn.

## 14. Thread boundary có thể làm mất hiệu lực rollback

Test-managed transaction của Spring gắn với thread hiện tại. Transaction context thường được lưu trong ThreadLocal thông qua transaction synchronization.

Nếu code được kiểm tra chạy trên thread khác, transaction của test không tự động truyền sang thread đó.

Các trường hợp dễ gặp:

- **@Async** chạy method trên executor.
- HTTP request được xử lý bởi server thread khi dùng server thật.
- Tác vụ được gửi vào executor hoặc scheduler.
- Test dùng timeout theo kiểu chạy assertion trong thread riêng.
- Một consumer message xử lý dữ liệu ở thread khác.

Một ví dụ quan trọng là **assertTimeoutPreemptively** của JUnit Jupiter. Cơ chế này có thể chạy đoạn code test trong một thread riêng để ngắt khi hết thời gian. Nếu đoạn code ghi database trong thread đó, nó không tham gia test-managed transaction gắn với thread ban đầu. Thay đổi có thể commit và không bị rollback như mong đợi.

Với test transactional có thao tác database, hãy cẩn thận khi dùng timeout preemptive. Có thể dùng timeout không preemptive hoặc thiết kế cleanup rõ ràng cho tác vụ chạy ở thread riêng.

Nếu cần kiểm tra async behavior, hãy đợi tác vụ hoàn tất, xác định transaction boundary của thread xử lý và dọn dữ liệu sau khi tác vụ đã kết thúc. Không dựa vào **@Transactional** trên test method để rollback mọi thread trong ứng dụng.

## 15. Test chạy song song và trạng thái dùng chung

JUnit Jupiter có thể chạy test song song khi được cấu hình. Mỗi test-managed transaction gắn với thread và transaction manager tương ứng, nhưng database, schema, bảng và singleton bean có thể vẫn được chia sẻ.

Nếu hai test cùng dùng một ID, cùng xóa toàn bộ bảng hoặc cùng thay đổi dữ liệu chung, chúng có thể xung đột dù mỗi test có transaction riêng.

Các cách giảm xung đột:

- Dùng ID riêng theo test hoặc theo test run.
- Tránh **deleteAll()** trên bảng được test khác sử dụng.
- Dùng database/schema/container riêng cho nhóm test cần cô lập cao.
- Không giữ mutable fixture dùng chung giữa các test.
- Chỉ bật parallel execution khi dữ liệu và hạ tầng đã được thiết kế cho nó.

Rollback giúp hoàn tác thay đổi của từng transaction, nhưng không tự giải quyết mọi vấn đề đồng thời. Ví dụ, hai transaction có thể tranh chấp unique key hoặc khóa bản ghi trước khi một transaction rollback.

## 16. Lựa chọn hook theo mục tiêu

| Mục tiêu | Hook phù hợp | Lý do |
|---|---|---|
| Tạo fixture cho mỗi test | @BeforeEach | Chạy trong test transaction nếu có |
| Kiểm tra kết quả ngay sau test method | @AfterEach | Transaction chưa kết thúc |
| Kiểm tra baseline trước transaction | @BeforeTransaction | Chạy ngoài transaction |
| Kiểm tra dữ liệu sau rollback/commit | @AfterTransaction | Transaction đã kết thúc |
| Tạo dữ liệu cần commit trước test transaction | @BeforeTransaction | Dữ liệu có thể được commit độc lập |
| Dọn dữ liệu đã commit ngoài test transaction | @AfterTransaction | Cleanup diễn ra sau transaction |
| Chuẩn bị một lần cho cả class | @BeforeAll | Không thuộc transaction từng test method |
| Dọn tài nguyên một lần sau cả class | @AfterAll | Không thuộc transaction từng test method |

Hãy bắt đầu bằng câu hỏi: assertion hoặc thao tác cần diễn ra trước hay sau khi transaction kết thúc? Nếu cần nhìn thấy thay đổi chưa commit, dùng **@AfterEach**. Nếu cần xác nhận trạng thái đã commit hoặc rollback, dùng **@AfterTransaction**.

## 17. Các lỗi thường gặp

### Nghĩ rằng @AfterEach chạy sau rollback

Với Spring TestContext và test-managed transaction thông thường, **@AfterEach** chạy trước khi transaction được kết thúc. Nếu cần kiểm tra kết quả sau rollback, hãy dùng **@AfterTransaction**.

### Tạo fixture trong @BeforeAll

**@BeforeAll** chạy một lần cho class, còn transaction test thường được tạo riêng cho mỗi test method. Dữ liệu được tạo ngoài transaction có thể được commit và dùng chung giữa các test. Nếu fixture cần độc lập theo từng test, hãy dùng **@BeforeEach**.

### Xóa dữ liệu trong @AfterEach rồi mong dữ liệu được xóa vĩnh viễn

Nếu cleanup tham gia transaction test và transaction rollback, thao tác xóa cũng rollback. Hãy dùng **@AfterTransaction** hoặc transaction cleanup riêng khi cần xóa dữ liệu đã commit.

### Cho rằng @Transactional trên lifecycle method mở transaction riêng

Transaction listener quản lý test transaction dựa trên cấu hình test class hoặc test method. Đánh dấu **@BeforeEach** hoặc **@AfterEach** bằng **@Transactional** không phải cách tạo transaction độc lập đáng tin cậy cho hook.

### Quên propagation REQUIRES_NEW

Thay đổi được commit trong transaction độc lập không bị rollback cùng test transaction. Hãy kiểm tra propagation của service và transaction manager.

### Ghi dữ liệu trên thread khác

Transaction của test gắn với thread hiện tại. Async task, HTTP server thread hoặc timeout preemptive có thể ghi dữ liệu ngoài transaction đó.

### Dùng chung ID khi test chạy song song

Hai test có thể cùng tạo hoặc xóa một bản ghi. Dùng ID riêng và cleanup theo phạm vi.

### Cho rằng @DirtiesContext thay thế rollback

**@DirtiesContext** quản lý ApplicationContext cache. Nó không tự hoàn tác transaction đã commit hoặc side effect bên ngoài.

### Không xác định đúng transaction manager

Khi context có nhiều manager, test có thể rollback manager khác với manager mà repository sử dụng. Hãy chỉ định qualifier phù hợp.

## 18. Ví dụ tổng hợp: xác minh trước và sau transaction

Ví dụ sau thể hiện cả hai thời điểm: **@AfterEach** kiểm tra trạng thái trong transaction và **@AfterTransaction** kiểm tra trạng thái sau rollback.

~~~java
@SpringJUnitConfig(OrderTransactionTestConfig.class)
@Transactional
class OrderTransactionLifecycleTest {

    private static final String ORDER_ID = "order-lifecycle-176";

    @Autowired
    private OrderRepository repository;

    @Autowired
    private OrderService orderService;

    @BeforeTransaction
    void verifyInitialState() {
        assertFalse(repository.existsById(ORDER_ID));
    }

    @BeforeEach
    void createPendingOrder() {
        repository.save(
                new Order(ORDER_ID, OrderStatus.PENDING)
        );
    }

    @Test
    void confirmsOrderInsideTestTransaction() {
        orderService.confirm(ORDER_ID);

        Order order = repository.findById(ORDER_ID).orElseThrow();

        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @AfterEach
    void verifiesStateBeforeTransactionEnds() {
        Order order = repository.findById(ORDER_ID).orElseThrow();

        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @AfterTransaction
    void verifiesRollback() {
        assertFalse(repository.existsById(ORDER_ID));
    }
}
~~~

Ví dụ giả định service dùng transaction propagation tham gia transaction hiện tại, repository và service cùng dùng transaction manager, và ID chưa tồn tại trước test. Khi test hoàn tất, thay đổi được rollback; **@AfterTransaction** đọc trạng thái database sau khi rollback.

Nếu thay class hoặc method bằng **@Commit**, assertion cuối cần đổi để mong đợi bản ghi tồn tại. Nếu service dùng **REQUIRES_NEW**, cần thiết kế lại fixture và assertion vì service có thể commit ngoài transaction của test.

## 19. Quy trình thiết kế lifecycle cho transactional test

Khi viết một test persistence, hãy xác định:

1. Test có thực sự cần test-managed transaction không?
2. Transaction được bật ở class hay method?
3. **@BeforeEach** cần tạo dữ liệu trong transaction hay cần dữ liệu đã commit trước đó?
4. Test method và service dùng propagation nào?
5. **@AfterEach** cần xác minh trạng thái chưa commit hay dọn thay đổi trong transaction?
6. Có cần **@BeforeTransaction** hoặc **@AfterTransaction** để kiểm tra ngoài transaction không?
7. Transaction manager nào đang được sử dụng?
8. Có transaction độc lập, thread khác hoặc side effect ngoài database không?
9. Test mặc định rollback hay được đánh dấu commit?
10. Dữ liệu có thể xung đột khi test chạy song song không?

Một quy tắc thực hành hữu ích là để **@BeforeEach** chuẩn bị dữ liệu cho từng test, để test method thực hiện hành vi cần kiểm tra, và dùng **@AfterEach** cho assertion cần nhìn thấy trạng thái trong transaction hiện tại. Khi cần kiểm tra kết quả sau commit hoặc rollback, chuyển assertion đó sang **@AfterTransaction**.

## 20. Nguyên tắc cần nhớ

- **@BeforeEach** chạy trước từng test method; nếu test có test-managed transaction, nó chạy bên trong transaction đó.
- **@AfterEach** chạy sau test method nhưng trước khi Spring kết thúc test-managed transaction.
- Spring mặc định rollback test-managed transaction sau mỗi test method.
- **@BeforeTransaction** chạy trước khi transaction bắt đầu.
- **@AfterTransaction** chạy sau khi transaction commit hoặc rollback.
- **@BeforeAll** và **@AfterAll** không thuộc transaction riêng của từng test method.
- Cleanup trong **@AfterEach** có thể bị rollback cùng transaction.
- **REQUIRES_NEW**, async thread và request xử lý ở server thread có thể tạo thay đổi tồn tại sau rollback của test.
- Dùng **@Commit**, **@Rollback** và **TestTransaction** có chủ đích.
- Cô lập dữ liệu bằng ID riêng và cleanup đúng phạm vi.

Khi hiểu rõ thời điểm transaction bắt đầu và kết thúc, việc chọn lifecycle hook trở nên dễ dự đoán. **@BeforeEach** và **@AfterEach** phù hợp với dữ liệu và assertion bên trong transaction; **@BeforeTransaction** và **@AfterTransaction** dành cho công việc cần quan sát trạng thái bên ngoài transaction. Phân chia đúng thời điểm giúp test xác minh được cả trạng thái trong transaction lẫn kết quả cuối cùng sau commit hoặc rollback.

