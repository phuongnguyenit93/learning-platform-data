# Phân biệt rollback trong test với hành vi sau commit thực tế

Spring Data JDBC thường được kiểm thử bằng các integration test chạy trong transaction. Cách này giúp dữ liệu test được rollback sau mỗi test và giảm nhu cầu dọn database thủ công. Tuy nhiên, transaction do test framework quản lý có thể che khuất hành vi commit thật của service.

Ví dụ, một test dùng **@DataJdbcTest** lưu aggregate, đọc lại rồi kết thúc thành công. Test vẫn có thể rollback toàn bộ transaction ở cuối method. Điều đó chứng minh repository đọc/ghi được trong transaction của test, nhưng chưa chứng minh dữ liệu đã commit và có thể được một transaction khác nhìn thấy.

Để kiểm tra đúng hành vi production, cần phân biệt:

- **Test-managed transaction:** transaction do Spring TestContext mở và kết thúc quanh test method.
- **Application transaction:** transaction do service hoặc repository mở qua **@Transactional**.
- **Commit thực tế:** transaction vật lý được commit và dữ liệu trở nên bền vững theo semantics của database.
- **Rollback để cô lập test:** thao tác dọn dữ liệu mà test framework thực hiện sau khi assertion hoàn tất.

Bài học này giải thích transaction mặc định của test slice, cách application transaction tham gia transaction của test, cách kiểm tra commit và rollback thực tế, cách dùng **@Commit**, **@Rollback** và **TestTransaction**, cùng những tình huống dễ gây kết quả kiểm thử sai.

## 1. Vì sao test rollback mặc định?

Spring TestContext hỗ trợ chạy test method trong transaction. Các test slice như **@DataJdbcTest** thường được cấu hình transaction để thay đổi database được rollback sau khi test kết thúc.

Ví dụ:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAnOrder() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-100")
        );

        PurchaseOrder loaded = orders.findById(saved.getId())
            .orElseThrow();

        assertEquals("SO-100", loaded.getOrderNumber());
    }
}
~~~

Test có thể thành công dù dữ liệu được rollback ngay sau khi method kết thúc. Đây là hành vi mong muốn đối với test repository: mỗi test bắt đầu với dữ liệu sạch hơn và không để lại hàng đã tạo cho test sau.

### 1.1. Rollback của test không phải rollback nghiệp vụ

Giả sử service có transaction:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(String orderNumber) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(orderNumber)
        );
        return saved.getId();
    }
}
~~~

Nếu test gọi service trong transaction do **@DataJdbcTest** tạo, transaction **REQUIRED** của service thường tham gia transaction đang tồn tại. Khi test kết thúc, test framework rollback transaction đó.

Test chứng minh service có thể ghi dữ liệu trong transaction hiện tại. Nó chưa chứng minh transaction do service mở độc lập sẽ commit khi method kết thúc trong một request production.

### 1.2. Test slice và SpringBootTest

**@DataJdbcTest** là test slice tập trung vào Spring Data JDBC và thường được đánh dấu transactional. Các thay đổi database được rollback sau mỗi test theo cấu hình mặc định của slice.

**@SpringBootTest** không tự động có cùng semantics rollback cho mọi test method. Nếu test được đánh dấu **@Transactional**, Spring TestContext mới quản lý test transaction theo cấu hình đó. Nếu không, transaction do service mở có thể commit như khi ứng dụng chạy bình thường.

Không suy luận chỉ từ tên annotation. Hãy xác định test class có test-managed transaction hay không và transaction manager nào đang được chọn.

## 2. Ba lớp transaction cần phân biệt

Trong một integration test, có thể tồn tại nhiều phạm vi transaction logic:

~~~text
Spring TestContext
    |
    +-- Test-managed transaction T_test
            |
            +-- Test method
                    |
                    +-- OrderService @Transactional(REQUIRED)
                    |       |
                    |       +-- Repository.save()
                    |
                    +-- Repository.findById()
~~~

Nếu service dùng cùng transaction manager và propagation REQUIRED, service tham gia T_test. Khi đó service không tự commit riêng khi method trả về.

| Phạm vi | Ai quản lý? | Thời điểm kết thúc |
|---|---|---|
| Test-managed transaction | Spring TestContext | Sau test method, mặc định rollback |
| Application transaction mới | Spring transaction interceptor | Khi service method kết thúc |
| Transaction tham gia bằng REQUIRED | Transaction manager của transaction hiện tại | Cùng thời điểm transaction vật lý bên ngoài kết thúc |
| REQUIRES_NEW | Transaction manager của service | Commit/rollback độc lập khi method bên trong kết thúc |

Một assertion chạy trong cùng transaction có thể nhìn thấy dữ liệu chưa commit do chính transaction đó ghi. Điều này không chứng minh một connection khác hoặc một ứng dụng khác đã nhìn thấy dữ liệu.

## 3. Kiểm tra repository trong test transaction

Với test repository, rollback mặc định thường là phù hợp:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void persistsAnOrderWithinTheTestTransaction() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-200")
        );

        assertTrue(orders.findById(saved.getId()).isPresent());
    }
}
~~~

Test này kiểm tra mapping và thao tác repository trong transaction test. Nó không cần commit dữ liệu để hoàn thành mục tiêu.

### 3.1. Dữ liệu trong transaction chưa chắc đã được commit

Một transaction thường có thể đọc lại thay đổi do chính nó ghi trước khi commit. Vì vậy, đoạn test sau không chứng minh commit:

~~~java
orders.save(order);
assertTrue(orders.findById(order.getId()).isPresent());
~~~

Hai thao tác có thể dùng cùng connection và cùng transaction. Để kiểm tra khả năng nhìn thấy sau commit, cần kết thúc transaction bằng commit rồi đọc trong một transaction hoặc connection mới.

## 4. Kiểm tra service commit thật bằng NOT_SUPPORTED

Một cách rõ ràng là tắt test-managed transaction cho test method. Khi đó service tự mở và kết thúc transaction theo annotation của nó.

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@DataJdbcTest
@Import(OrderService.class)
class OrderServiceCommitTest {

    @Autowired
    OrderService orderService;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void serviceCommitsBeforeReturning() {
        Long id = orderService.createOrder("SO-300");

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            id
        );

        assertEquals(1, count);
    }
}
~~~

Với **NOT_SUPPORTED**, test method không chạy trong test-managed transaction. Khi gọi **orderService.createOrder()**, transaction do service mở được commit khi method kết thúc bình thường. Truy vấn tiếp theo có thể đọc dữ liệu đã commit.

Lưu ý:

- Test slice vẫn có thể cung cấp database và repository infrastructure.
- Cần import service và dependency của nó vào test context.
- Service phải dùng transaction manager của DataSource đang được test.
- Dữ liệu đã commit có thể tồn tại sau test, vì test transaction không còn để rollback.
- Cần dọn dữ liệu bằng fixture cleanup, schema riêng hoặc database test dùng riêng.

Không dùng test này trên database dùng chung mà không có chiến lược cleanup rõ ràng.

## 5. Kiểm tra rollback thực tế của service

Muốn chứng minh service rollback khi nghiệp vụ thất bại, hãy để service tự quản lý transaction và quan sát database sau khi method ném exception.

Service:

~~~java
@Service
public class CheckoutService {

    private final PurchaseOrderRepository orders;
    private final InventoryRepository inventory;

    public CheckoutService(
            PurchaseOrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(CreateOrderCommand command) {
        orders.save(PurchaseOrder.create(command));
        inventory.decrease(command.productId(), command.quantity());

        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Test:

~~~java
@DataJdbcTest
@Import(CheckoutService.class)
class CheckoutRollbackTest {

    @Autowired
    CheckoutService checkout;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void rollsBackWritesWhenServiceFails() {
        CreateOrderCommand command = sampleCommand();

        assertThrows(
            IllegalStateException.class,
            () -> checkout.checkout(command)
        );

        Integer orderCount = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE order_number = ?",
            Integer.class,
            command.orderNumber()
        );

        assertEquals(0, orderCount);
    }
}
~~~

Vì test không có transaction bao ngoài, transaction của **checkout()** được mở và rollback bởi Spring transaction interceptor khi runtime exception thoát khỏi method. Truy vấn sau đó chạy ngoài transaction đã rollback và xác nhận hàng không tồn tại.

Để kiểm tra rollback của nhiều bảng, hãy truy vấn trạng thái từng bảng hoặc repository tương ứng. Chỉ kiểm tra đơn hàng chưa đủ nếu use case còn cập nhật tồn kho, audit hoặc outbox.

### 5.1. Kiểm tra checked exception

Mặc định, Spring rollback với **RuntimeException** và **Error**. Checked exception không tự động làm rollback theo quy tắc mặc định.

Nếu nghiệp vụ yêu cầu rollback với checked exception:

~~~java
@Transactional(rollbackFor = InventoryException.class)
public void checkout(CreateOrderCommand command)
        throws InventoryException {
    orders.save(PurchaseOrder.create(command));
    inventory.reserve(command);
    throw new InventoryException("Reservation failed");
}
~~~

Integration test cần xác nhận đúng rollback rule:

1. Tắt test-managed transaction.
2. Gọi service và xác nhận checked exception được ném ra.
3. Đọc lại các bảng liên quan.
4. Xác nhận dữ liệu đã rollback.

Nếu bỏ rollbackFor, test có thể phát hiện dữ liệu đã commit dù method ném checked exception, tùy cách exception thoát khỏi transaction boundary.

## 6. Dùng @Commit và @Rollback(false)

Nếu muốn test-managed transaction commit khi test kết thúc, có thể dùng **@Commit**:

~~~java
@DataJdbcTest
class CommittedRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    @Commit
    void commitsTestTransaction() {
        orders.save(PurchaseOrder.create("SO-400"));
    }
}
~~~

**@Commit** là cách diễn đạt rõ rằng transaction do test quản lý cần commit khi test kết thúc. Có thể dùng **@Rollback(false)** với ý nghĩa tương đương:

~~~java
@Test
@Rollback(false)
void commitsTestTransaction() {
    // ...
}
~~~

Mặc định, test-managed transaction rollback. **@Rollback** có thể cấu hình hành vi đó; **@Commit** là cách viết chuyên biệt cho trường hợp commit.

### 6.1. Assertion trong test xảy ra trước commit cuối method

Với **@Commit**, transaction thường chỉ commit sau khi test method kết thúc. Vì vậy, assertion thực hiện bên trong method vẫn chạy trước commit.

Nếu cần kiểm tra sau commit, dùng **TestTransaction** để chủ động kết thúc transaction rồi mới truy vấn:

~~~java
@DataJdbcTest
class ExplicitTestCommitTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    @Transactional
    void commitsBeforeCheckingFromOutsideTheTestTransaction() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-500")
        );

        TestTransaction.flagForCommit();
        TestTransaction.end();

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            saved.getId()
        );

        assertEquals(1, count);
    }
}
~~~

**TestTransaction.flagForCommit()** yêu cầu transaction test commit khi kết thúc; **TestTransaction.end()** kết thúc transaction ngay tại vị trí gọi. Sau đó, câu SELECT chạy ngoài test transaction đã commit.

Nếu cần thêm thao tác database trong cùng test, có thể gọi **TestTransaction.start()** để bắt đầu một test-managed transaction mới. Hãy kiểm tra trạng thái bằng **TestTransaction.isActive()** khi cần.

### 6.2. Commit test data cần cleanup

Khi dùng **@Commit** hoặc **flagForCommit()**, dữ liệu có thể còn trong database sau test. Cần:

- Dùng database/schema riêng cho test.
- Tạo dữ liệu có khóa duy nhất để tránh xung đột.
- Dọn dữ liệu bằng SQL/repository sau assertion hoặc reset schema.
- Không dựa vào rollback tự động sau test nữa.

Một test commit chỉ nên giữ dữ liệu khi mục tiêu kiểm thử thực sự cần trạng thái sau commit.

## 7. Dùng TestTransaction để kiểm tra nhiều giai đoạn

**TestTransaction** hữu ích khi một test cần điều khiển transaction test theo từng giai đoạn:

~~~java
@Test
@Transactional
void checksStateAcrossCommitAndNewTransaction() {
    PurchaseOrder saved = orders.save(
        PurchaseOrder.create("SO-600")
    );

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertEquals(
        1,
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
            Integer.class,
            saved.getId()
        )
    );

    TestTransaction.start();
    orders.deleteById(saved.getId());
}
~~~

Ở đây:

1. Transaction test đầu tiên ghi aggregate.
2. Test đánh dấu commit và kết thúc transaction.
3. Assertion kiểm tra dữ liệu sau commit.
4. Test bắt đầu transaction mới.
5. Dọn dữ liệu trong transaction mới; transaction này có thể rollback khi test kết thúc.

Cách này hữu ích khi muốn kiểm tra commit mà vẫn giữ khả năng cleanup bằng rollback ở giai đoạn sau.

## 8. REQUIRES_NEW có thể commit dù test transaction rollback

Một trường hợp dễ gây nhầm lẫn là service dùng **Propagation.REQUIRES_NEW** trong khi test đã mở transaction.

~~~java
@Service
public class AuditService {

    private final OrderAuditRepository audits;

    public AuditService(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        audits.save(new OrderAudit(event));
    }
}
~~~

Nếu test có transaction T_test và gọi service audit:

1. Spring tạm ngưng T_test.
2. AuditService mở transaction vật lý mới T_inner.
3. T_inner commit khi method audit kết thúc.
4. T_test tiếp tục.
5. Khi test kết thúc, T_test rollback.

Bản ghi audit đã commit trong T_inner vẫn có thể tồn tại. Rollback của test transaction không hoàn tác một transaction độc lập đã commit.

Điều này có thể khiến test slice để lại dữ liệu dù mặc định rollback. Hãy chú ý các service dùng REQUIRES_NEW, đặc biệt khi chúng ghi vào cùng database test.

### 8.1. Cách kiểm tra REQUIRES_NEW có chủ đích

Nếu muốn kiểm tra semantics độc lập:

- Tạo test có transaction ngoài.
- Gọi service REQUIRES_NEW.
- Xác nhận kết quả transaction trong đã commit.
- Làm transaction ngoài rollback.
- Dùng một truy vấn ngoài transaction để xác nhận dữ liệu của inner vẫn còn.

Test phải có cleanup cho bản ghi đã commit độc lập.

## 9. NESTED và savepoint trong test

**Propagation.NESTED** dùng savepoint bên trong transaction vật lý hiện tại nếu transaction manager hỗ trợ. Khi nested scope rollback về savepoint, transaction ngoài có thể tiếp tục.

Nếu transaction ngoài chính là test-managed transaction, mọi thay đổi còn lại vẫn có thể bị rollback khi test kết thúc.

~~~text
BEGIN T_test
  INSERT order
  SAVEPOINT S1
    INSERT optional_note
  ROLLBACK TO S1
  UPDATE order
ROLLBACK T_test
~~~

Sau test:

- Hàng optional note đã bị rollback về savepoint.
- Thay đổi order còn tồn tại trong T_test cho đến cuối test.
- Rollback test cuối cùng loại bỏ cả thay đổi order.

Không nhầm việc nested rollback thành commit của phần outer. Muốn kiểm tra trạng thái sau commit, vẫn cần commit transaction ngoài.

## 10. Kiểm tra transaction synchronization và callback sau commit

Một số code đăng ký callback chạy sau khi transaction commit, ví dụ qua **TransactionSynchronizationManager** hoặc cơ chế event có phase **AFTER_COMMIT**.

Nếu test-managed transaction mặc định rollback, callback afterCommit sẽ không chạy như trong một transaction commit thành công. Một test chỉ gọi service rồi kết thúc bằng rollback không chứng minh hành vi sau commit.

Ví dụ đăng ký synchronization:

~~~java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Thực hiện hành động sau commit.
        }
    }
);
~~~

Để kiểm tra:

1. Chạy test trong transaction.
2. Ghi nhận callback chưa được thực hiện trước commit.
3. Đánh dấu transaction test commit.
4. Kết thúc transaction.
5. Xác nhận callback đã chạy.

Nếu callback phát message hoặc gọi hệ thống ngoài, nên dùng spy/fake thay vì gửi request thật trong test. Với outbox pattern, ưu tiên xác nhận outbox row được commit cùng aggregate rồi test publisher riêng.

## 11. Nhiều transaction manager trong test

Ứng dụng Spring Data JDBC có thể cấu hình nhiều DataSource và transaction manager. Test cần chọn đúng manager để rollback hoặc commit đúng database.

Ví dụ:

~~~java
@DataJdbcTest
@Transactional(transactionManager = "ordersTransactionManager")
class OrdersRepositoryTest {
    // ...
}
~~~

Nếu test truy cập cả orders và inventory, một test-managed transaction gắn với orders manager không tự bao phủ transaction của inventory manager.

Hãy xác định:

- Repository đang dùng DataSource nào.
- Test transaction đang dùng transaction manager nào.
- Service có chọn manager tường minh không.
- Có transaction REQUIRES_NEW hoặc transaction độc lập ở database khác không.
- Dữ liệu nào cần commit/rollback và cần cleanup riêng.

Hai transaction manager JDBC thông thường không tạo thành một transaction nguyên tử. Test cũng không thể chứng minh atomicity đa database chỉ bằng rollback của một manager.

## 12. Preemptive timeout có thể làm sai transaction test

Transaction của Spring TestContext thường được gắn với thread đang chạy test. Một số API timeout của test framework chạy code trong thread khác, ví dụ JUnit **assertTimeoutPreemptively**.

Nếu test method đang có test-managed transaction nhưng phần code được thực thi trong thread khác, transaction context không tự truyền sang thread đó. Các thao tác database có thể chạy ngoài transaction test và commit thật, khiến dữ liệu tồn tại ngoài dự kiến.

Với test cần kiểm soát transaction:

- Tránh preemptive timeout chạy test body trên thread khác.
- Nếu cần timeout, chọn cách không chuyển execution sang thread khác hoặc thiết kế transaction riêng cho worker.
- Dọn dữ liệu có thể commit ngoài transaction.
- Không giả định thread-local transaction context tự truyền qua executor hoặc @Async.

Đây là lý do một test có vẻ được rollback vẫn có thể để lại dữ liệu nếu thao tác persistence thực tế chạy trên thread khác.

## 13. Sequence và generated ID sau rollback

Một transaction rollback không nhất thiết trả lại giá trị sequence hoặc identity đã cấp. Nhiều database cấp sequence value theo cơ chế không transactional; vì vậy sau rollback có thể xuất hiện khoảng trống trong ID.

Ví dụ:

1. Insert nhận ID 101.
2. Transaction rollback.
3. Insert tiếp theo nhận ID 102.

Khoảng trống này không chứng minh hàng ID 101 đã commit. Khi test, hãy kiểm tra sự tồn tại của row hoặc dữ liệu nghiệp vụ, không giả định ID phải liên tục.

Tương tự, DDL và một số thao tác database có transaction semantics riêng. Không khái quát rằng mọi thay đổi database đều rollback giống INSERT/UPDATE thông thường.

## 14. Kiểm tra commit bằng một connection khác

Nếu mục tiêu là xác nhận transaction commit có thể được nhìn thấy từ một transaction khác, test cần đọc qua một transaction/connection mới sau khi commit.

Một query ngay trong transaction đã ghi chỉ chứng minh transaction đó nhìn thấy thay đổi của chính nó. Nó không kiểm tra visibility từ bên ngoài.

Các cách thực hiện:

- Kết thúc test transaction bằng TestTransaction.end() sau khi gọi flagForCommit(), rồi query lại.
- Tắt test-managed transaction bằng Propagation.NOT_SUPPORTED để service commit độc lập rồi query.
- Dùng một transaction template hoặc connection độc lập sau khi commit.

Nếu kiểm tra read replica, cần xét replication lag. Commit trên primary không đảm bảo replica nhìn thấy dữ liệu ngay lập tức.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test xanh nhưng dữ liệu không tồn tại sau test | Test-managed transaction rollback mặc định | Đây là hành vi test slice; dùng commit test nếu cần xác nhận persistence sau test |
| Test thấy row nhưng production không thấy | Assertion chạy trong cùng transaction chưa commit | Commit rồi đọc từ transaction/connection khác |
| Service rollback không được kiểm chứng | Test transaction bao ngoài che khuất transaction của service | Dùng NOT_SUPPORTED để service tự mở transaction |
| Dữ liệu vẫn tồn tại sau test rollback | Service dùng REQUIRES_NEW và inner transaction đã commit | Cleanup riêng hoặc test semantics độc lập có chủ đích |
| Callback AFTER_COMMIT không chạy | Test transaction kết thúc bằng rollback | Dùng @Commit hoặc TestTransaction.flagForCommit() |
| Dữ liệu SQL trực tiếp tồn tại ngoài ý muốn | Code chạy trên thread khác không tham gia test transaction | Tránh preemptive timeout hoặc thiết kế transaction/cleanup riêng |
| ID bị nhảy sau rollback | Sequence/identity không rollback | Kiểm tra row, không yêu cầu ID liên tục |
| Test commit làm ảnh hưởng test khác | Dữ liệu được giữ lại | Dùng database/schema riêng và cleanup |
| Rollback test không tác động database thứ hai | Test transaction chỉ quản lý một transaction manager | Chọn manager đúng và kiểm tra từng resource |
| Checked exception không rollback | Rollback rule mặc định không áp dụng checked exception | Cấu hình rollbackFor nếu nghiệp vụ yêu cầu |
| @Commit nhưng assertion vẫn chưa thấy commit | Assertion chạy trước khi test method kết thúc | Dùng TestTransaction.end() để commit ngay trong test |
| NESTED bị hiểu là transaction độc lập | Savepoint không phải transaction vật lý riêng | Phân biệt rollback savepoint với commit REQUIRES_NEW |

## 16. Chọn chiến lược test theo mục tiêu

| Mục tiêu | Cách test phù hợp |
|---|---|
| Kiểm tra mapping và CRUD repository | @DataJdbcTest với rollback mặc định |
| Kiểm tra service tham gia transaction hiện tại | Test transaction mặc định, kiểm tra dữ liệu trong transaction |
| Kiểm tra service commit khi method thành công | NOT_SUPPORTED, gọi service và đọc lại sau khi method trả về |
| Kiểm tra service rollback khi runtime exception | NOT_SUPPORTED, gọi service, xác nhận row không tồn tại |
| Kiểm tra checked exception rollback | NOT_SUPPORTED và rollbackFor |
| Kiểm tra transaction test commit | @Commit hoặc TestTransaction.flagForCommit() |
| Kiểm tra callback sau commit | Chủ động commit bằng TestTransaction |
| Kiểm tra REQUIRES_NEW | Tạo transaction ngoài, gọi inner, rollback outer và xác nhận inner còn |
| Kiểm tra NESTED | Kiểm tra savepoint trong transaction ngoài, sau đó kiểm tra outer rollback |
| Kiểm tra nhiều DataSource | Chọn transaction manager riêng và xác nhận trạng thái từng database |

Không cần tắt rollback mặc định cho mọi test. Hãy dùng test rollback cho repository/mapping và tạo một số integration test riêng để kiểm tra commit, rollback nghiệp vụ và transaction độc lập.

## 17. Quy trình viết integration test transaction

Khi thiết kế test cho một use case Spring Data JDBC:

1. **Xác định mục tiêu:** kiểm tra mapping, commit, rollback, visibility hay callback sau commit?
2. **Xác định test transaction:** test slice có tự mở transaction không?
3. **Xác định application transaction:** service dùng propagation và manager nào?
4. **Chọn ranh giới:** để test rollback mặc định, dùng NOT_SUPPORTED hay chủ động commit?
5. **Thực hiện use case:** gọi qua Spring bean proxy để transaction interceptor hoạt động.
6. **Quan sát đúng phạm vi:** đọc trong cùng transaction hay sau commit bằng connection mới?
7. **Kiểm tra tất cả bảng:** aggregate, child rows, audit, outbox và dữ liệu liên quan.
8. **Cleanup:** dọn mọi transaction đã commit độc lập.
9. **Kiểm tra ngoại lệ:** runtime, checked, caught exception và rollback-only.
10. **Kiểm tra môi trường:** dùng database/driver phù hợp với semantics đang xác nhận.

## 18. Bài tập thực hành

### Bài 1 — Quan sát rollback mặc định

1. Tạo test với @DataJdbcTest.
2. Lưu một aggregate và đọc lại trong test.
3. Kết thúc test.
4. Dùng một test hoặc truy vấn độc lập để xác nhận row đã bị rollback.
5. Giải thích vì sao assertion ban đầu vẫn thành công.

### Bài 2 — Kiểm tra commit thật của service

1. Tạo service method có @Transactional.
2. Viết test với Propagation.NOT_SUPPORTED.
3. Gọi service.
4. Query lại bằng JdbcTemplate.
5. Xác nhận dữ liệu tồn tại sau khi service method trả về.
6. Dọn dữ liệu đã commit.

### Bài 3 — Kiểm tra rollback nghiệp vụ

1. Tạo service ghi hai bảng rồi ném RuntimeException.
2. Tắt test-managed transaction.
3. Gọi service và bắt exception.
4. Query cả hai bảng.
5. Xác nhận mọi thay đổi thuộc transaction đã rollback.

### Bài 4 — Kiểm tra checked exception

1. Đổi lỗi thành checked exception.
2. Chạy test khi không có rollbackFor.
3. Quan sát trạng thái database.
4. Thêm rollbackFor.
5. Chạy lại và so sánh.

### Bài 5 — TestTransaction và AFTER_COMMIT

1. Viết test-managed transaction.
2. Ghi aggregate và đăng ký callback sau commit.
3. Xác nhận callback chưa chạy trước commit.
4. Gọi flagForCommit() và end().
5. Xác nhận callback chạy và dữ liệu đã commit.

### Bài 6 — REQUIRES_NEW

1. Mở transaction ngoài trong test.
2. Gọi audit service dùng REQUIRES_NEW.
3. Đánh dấu rollback transaction ngoài.
4. Kết thúc transaction ngoài.
5. Xác nhận bản ghi audit độc lập vẫn tồn tại.
6. Dọn bản ghi audit.

## 19. Kết luận

Rollback mặc định của **@DataJdbcTest** và các test transaction khác giúp cô lập dữ liệu giữa các test. Tuy nhiên, transaction test có thể bao ngoài và làm service dùng **REQUIRED** tham gia cùng một transaction chưa commit. Một assertion đọc được dữ liệu trong transaction đó không chứng minh service đã commit.

Muốn kiểm tra commit hoặc rollback thực tế của service, hãy để service tự quản lý transaction, thường bằng cách tắt test-managed transaction với **Propagation.NOT_SUPPORTED**. Khi cần chủ động commit transaction test, dùng **@Commit**, **@Rollback(false)** hoặc **TestTransaction.flagForCommit()** và **TestTransaction.end()**. Sau commit, đọc lại từ transaction/connection mới để xác nhận visibility.

Đặc biệt chú ý **REQUIRES_NEW**, nhiều transaction manager, callback sau commit và code chạy trên thread khác. Những trường hợp này có thể tạo dữ liệu đã commit dù test transaction bên ngoài rollback. Chọn chiến lược test theo đúng hành vi cần chứng minh, rồi dọn dữ liệu đã commit để các test còn lại không bị ảnh hưởng.
