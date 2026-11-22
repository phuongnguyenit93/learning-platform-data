# Kiểm thử ranh giới giao dịch thay vì suy luận từ tên phương thức

Khi kiểm thử ứng dụng có database, một lỗi thường gặp là nhìn tên phương thức như `saveOrder()`, `updateBalance()` hoặc `createPayment()` rồi cho rằng đã biết giao dịch bắt đầu và kết thúc ở đâu. Tên phương thức chỉ mô tả ý định của mã nguồn. Ranh giới transaction thực tế phụ thuộc vào transaction manager, cấu hình, annotation, propagation, cách gọi bean và transaction đang tồn tại ở thời điểm gọi.

Điều này đặc biệt quan trọng khi viết integration test với Spring. Một test method có `@Transactional` thường chạy bên trong transaction do Spring Test quản lý và rollback sau khi test kết thúc. Một service method có `@Transactional(propagation = REQUIRED)` được gọi trong test đó sẽ tham gia transaction sẵn có. Vì vậy, service method trả về chưa có nghĩa dữ liệu đã commit như khi ứng dụng chạy bình thường.

Muốn kiểm thử đúng, hãy xác định và quan sát **ranh giới transaction thực tế**: ai mở transaction, lời gọi nào tham gia transaction hiện có, lúc nào commit hoặc rollback xảy ra, và dữ liệu có còn nhìn thấy từ một transaction độc lập hay không.

## 1. Tên phương thức không xác định ranh giới transaction

Xét service sau:

```java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(CreateOrder command) {
        Order order = Order.create(command);
        orders.save(order);
        return order.getId();
    }
}
```

Tên `createOrder()` không tự tạo transaction. Transaction được mở vì lời gọi đi qua Spring proxy và transaction interceptor áp dụng cấu hình `@Transactional`. Nếu phương thức được gọi trong một transaction đã tồn tại với propagation mặc định `REQUIRED`, nó tham gia transaction đó.

Ngược lại, một phương thức tên `saveOrder()` không có nghĩa là nó tự mở transaction. Nó có thể:

- Được gọi bên trong transaction của service khác.
- Chạy không có transaction nếu không có cấu hình phù hợp.
- Tham gia transaction hiện tại do propagation `REQUIRED`.
- Mở transaction độc lập nếu được cấu hình `REQUIRES_NEW`.
- Chỉ thực hiện một phần công việc trong transaction, còn phần khác chạy ngoài transaction.

Do đó, khi kiểm thử, cần xem đường gọi và cấu hình transaction, không suy luận từ động từ trong tên phương thức.

Với Spring Data JPA, các phương thức CRUD kế thừa thường đã có cấu hình transaction ở repository implementation; các query method do ứng dụng tự khai báo không nhất thiết tự có transaction config. Một lời gọi `repository.save()` có thể tự chạy trong transaction repository nếu không có transaction ngoài. Điều đó vẫn khác với việc toàn bộ use case ở service có một transaction bao trùm nhiều thao tác. Nếu cần order, payment và audit cùng thành công hoặc thất bại, hãy đặt ranh giới ở service/use case phù hợp và kiểm thử toàn bộ lời gọi đó.

## 2. Ranh giới transaction trong Spring được quyết định bởi điều gì?

Một transaction thực tế được hình thành từ nhiều thành phần:

1. **Transaction manager:** ví dụ `PlatformTransactionManager` cho JDBC/JPA hoặc reactive transaction manager cho luồng reactive.
2. **Cấu hình transaction:** annotation `@Transactional`, cấu hình XML hoặc API lập trình như `TransactionTemplate`.
3. **Propagation:** quyết định lời gọi tham gia transaction hiện tại, tạo transaction mới, hoặc yêu cầu không có transaction.
4. **Cách gọi:** với proxy-based transaction management, lời gọi phải đi qua proxy để transaction interceptor được áp dụng.
5. **Thời điểm hoàn tất:** transaction chỉ commit/rollback khi ranh giới quản lý transaction kết thúc và quy tắc hoàn tất được thực thi.

Ví dụ một phương thức có annotation:

```java
@Transactional
public void updateInventory(Long productId, int quantity) {
    // đọc và cập nhật dữ liệu
}
```

Nếu một service khác gọi bean này qua proxy, interceptor áp dụng transaction. Nếu phương thức được gọi trực tiếp từ một phương thức khác trong cùng instance (`this.updateInventory(...)`), lời gọi nội bộ thường không đi qua proxy nên annotation trên phương thức được gọi có thể không được áp dụng như mong đợi.

### Self-invocation có thể làm sai giả định

```java
@Service
public class ReportService {

    public void generate() {
        writeReport();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeReport() {
        // ghi dữ liệu báo cáo
    }
}
```

Trong cấu hình proxy mặc định, `generate()` gọi `writeReport()` qua `this`, không qua proxy. Vì vậy, `REQUIRES_NEW` trên `writeReport()` có thể không được kích hoạt. Một test chỉ gọi `generate()` rồi kiểm tra kết quả không chứng minh rằng `writeReport()` đã chạy trong transaction độc lập.

Để kiểm thử đúng, gọi bean từ Spring context và thiết kế ranh giới service rõ ràng. Nếu cần một transaction độc lập, có thể chuyển phương thức đó sang bean riêng hoặc dùng `TransactionTemplate` với propagation được khai báo tường minh.

## 3. Hiểu propagation trước khi viết test

Propagation mô tả cách một lời gọi xử lý transaction hiện có.

| Propagation | Khi đã có transaction | Khi chưa có transaction |
|---|---|---|
| `REQUIRED` (mặc định) | Tham gia transaction hiện tại | Mở transaction mới |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và mở transaction mới | Mở transaction mới |
| `SUPPORTS` | Tham gia transaction hiện tại | Chạy không có transaction do lời gọi này tạo |
| `MANDATORY` | Tham gia transaction hiện tại | Ném lỗi vì không có transaction |
| `NOT_SUPPORTED` | Tạm treo transaction hiện tại và chạy không có transaction | Chạy không có transaction |
| `NEVER` | Ném lỗi nếu đang có transaction | Chạy không có transaction |
| `NESTED` | Có thể tạo savepoint bên trong transaction hiện tại nếu transaction manager hỗ trợ | Mở transaction mới theo hành vi hỗ trợ của manager |

Một service method `REQUIRED` có thể được gọi trong transaction của controller/service khác, trong transaction do test mở, hoặc ngoài mọi transaction. Cùng một phương thức có thể có hành vi hoàn tất khác nhau tùy ngữ cảnh gọi.

### Ví dụ: REQUIRED tham gia transaction của caller

```java
@Service
public class CheckoutService {
    private final OrderService orders;
    private final PaymentRecordService payments;

    @Transactional
    public void checkout(CheckoutCommand command) {
        Long orderId = orders.createOrder(command.order());
        payments.createPaymentRecord(orderId, command.amount());
    }
}
```

Nếu hai service con dùng `REQUIRED`, chúng thường tham gia transaction do `checkout()` mở. Khi `checkout()` commit, các thay đổi cùng commit. Nếu một lỗi làm transaction rollback, thay đổi của các service tham gia cũng rollback.

Một test gọi riêng `orders.createOrder()` không kiểm thử được toàn bộ ranh giới của `checkout()`. Nếu nghiệp vụ yêu cầu order và payment record phải cùng thành công hoặc cùng thất bại, hãy gọi `checkout()` qua bean Spring trong integration test và quan sát kết quả sau khi transaction thực sự kết thúc.

## 4. Cạm bẫy: transaction do test quản lý

Spring Test có thể tự mở transaction cho test method được đánh dấu `@Transactional`. Theo mặc định, transaction test-managed thường được rollback sau khi test kết thúc để dữ liệu không rò rỉ giữa các test.

Xét test:

```java
@SpringBootTest
@Transactional
class OrderServiceTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void createsOrder() {
        Long id = orderService.createOrder(command());

        assertTrue(orderRepository.findById(id).isPresent());
    }
}
```

Test có thể chạy thành công, nhưng điều đó chưa chứng minh `createOrder()` đã commit. Diễn biến thường là:

1. Spring Test mở transaction trước khi chạy test method.
2. Test gọi `orderService.createOrder()` qua proxy.
3. Phương thức service dùng `REQUIRED`, nên tham gia transaction test-managed.
4. Service trả về, nhưng transaction vẫn do test sở hữu và chưa commit.
5. Test kết thúc, Spring Test rollback transaction.

```text
Spring Test: BEGIN ───────────────────────────────────────── ROLLBACK
                 │
                 └── OrderService.createOrder() tham gia REQUIRED
                     save order
                     return id
```

Nếu test chỉ kiểm tra dữ liệu trong cùng transaction, nó có thể nhìn thấy dữ liệu chưa commit do chính transaction đó ghi. Test này xác nhận logic tạo đối tượng và lưu trong transaction hiện tại, nhưng không xác nhận hành vi commit ở ranh giới production của service.

## 5. Flush không đồng nghĩa với commit

Với JPA/Hibernate, `save()` có thể chỉ cập nhật persistence context. SQL có thể được gửi xuống database khi flush hoặc khi transaction commit.

```java
orderRepository.save(order);
orderRepository.flush();
```

`flush()` đồng bộ các thay đổi đang chờ xuống database trong transaction hiện tại. Nó hữu ích để phát hiện sớm một số lỗi SQL hoặc constraint được kiểm tra ngay khi thực thi câu lệnh. Nhưng flush **không commit transaction**.

| Thao tác | Ý nghĩa | Có kết thúc transaction không? |
|---|---|---:|
| `save()` | Đưa thay đổi vào persistence context/repository workflow | Không |
| `flush()` / `saveAndFlush()` | Đẩy thay đổi đang chờ xuống database | Không |
| `COMMIT` | Xác nhận transaction thành công và công bố thay đổi | Có |
| `ROLLBACK` | Hủy thay đổi chưa commit theo quy tắc transaction | Có |

Vì vậy, test gọi `saveAndFlush()` rồi đọc lại dữ liệu trong cùng transaction vẫn chưa chứng minh commit. Một số constraint được trì hoãn (deferred constraints) chỉ được kiểm tra khi commit; test chỉ flush có thể không phát hiện lỗi mà production gặp ở cuối transaction.

## 6. Cách kiểm thử service commit ở ranh giới thực tế

Nếu mục tiêu là xác nhận service method mở và kết thúc transaction như khi ứng dụng chạy, hãy tránh bọc test bằng transaction bên ngoài. Sau khi service trả về, đọc dữ liệu bằng một transaction độc lập.

Ví dụ:

```java
@SpringBootTest
class OrderCommitIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void serviceCommitsOrderBeforeReturning() {
        Long orderId = orderService.createOrder(command());

        TransactionTemplate readTransaction =
            new TransactionTemplate(transactionManager);

        Order persisted = readTransaction.execute(status ->
            orderRepository.findById(orderId).orElseThrow()
        );

        assertEquals(orderId, persisted.getId());
    }
}
```

Ở đây test không có transaction bao ngoài. Khi gọi `orderService.createOrder()`, proxy mở transaction cho service theo cấu hình `@Transactional`; khi phương thức kết thúc bình thường, transaction service commit. Sau đó `TransactionTemplate` mở transaction đọc riêng để xác nhận dữ liệu đã được commit và nhìn thấy từ transaction khác.

`Propagation.NOT_SUPPORTED` trên test method ngăn Spring Test tạo transaction cho test. Nếu test class hoặc test method có cấu hình transaction khác, hãy kiểm tra cấu hình thực tế để bảo đảm không có transaction ngoài đang bao lấy lời gọi service.

Một lựa chọn khác là gọi service không có `@Transactional` trên test method và thực hiện truy vấn xác minh qua một transaction mới. Mục tiêu vẫn là bảo đảm lần đọc xác minh không dùng persistence context hoặc transaction đã ghi dữ liệu.

## 7. Dùng TestTransaction khi muốn chủ động kết thúc transaction test

Đôi khi test cần chạy nhiều bước trong transaction test-managed, nhưng muốn chủ động commit trước khi xác minh. Spring Test cung cấp `TestTransaction` để điều khiển transaction đó.

```java
@SpringBootTest
@Transactional
class OrderTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void commitsWhenTestTransactionEnds() {
        Long orderId = orderService.createOrder(command());

        TestTransaction.flagForCommit();
        TestTransaction.end();

        TransactionTemplate readTransaction =
            new TransactionTemplate(transactionManager);

        Order persisted = readTransaction.execute(status ->
            orderRepository.findById(orderId).orElseThrow()
        );

        assertEquals(orderId, persisted.getId());
    }
}
```

`flagForCommit()` đánh dấu transaction test-managed hiện tại sẽ commit khi kết thúc; `end()` kết thúc transaction ngay. Sau `end()`, test có thể đọc trong transaction mới. Nếu cần tiếp tục các thao tác test-managed, `TestTransaction.start()` có thể mở transaction test tiếp theo khi framework cho phép.

Phương pháp này kiểm tra được kết quả sau commit của transaction test. Tuy nhiên, cần phân biệt mục tiêu: service `REQUIRED` vẫn tham gia transaction test-managed, nên `TestTransaction.end()` là nơi commit. Nếu cần chứng minh service tự commit khi phương thức trả về trong điều kiện production, test không có transaction bao ngoài (`NOT_SUPPORTED` hoặc không dùng `@Transactional`) sẽ trực tiếp hơn.

## 8. Kiểm thử rollback theo đúng ranh giới

Không chỉ commit cần được kiểm thử. Nếu service gặp lỗi, các thay đổi thuộc transaction của nó phải rollback theo quy tắc đã cấu hình.

Ví dụ service:

```java
@Transactional
public Long createOrderThenFail(CreateOrder command) {
    Order order = orders.save(Order.create(command));
    throw new IllegalStateException("Simulated failure");
}
```

Test không có transaction bao ngoài:

```java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void rollsBackOrderWhenServiceFails() {
    assertThrows(
        IllegalStateException.class,
        () -> orderService.createOrderThenFail(command())
    );

    boolean exists = new TransactionTemplate(transactionManager)
        .execute(status -> orderRepository.existsByBusinessKey("ORDER-TEST-1"));

    assertFalse(exists);
}
```

Sau khi exception thoát khỏi phương thức transactional, interceptor rollback transaction theo quy tắc. Test mở transaction đọc độc lập để xác nhận hàng không tồn tại.

### Quy tắc rollback mặc định

Trong Spring, mặc định transaction rollback khi phương thức thoát ra với `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo mặc định. Nếu nghiệp vụ yêu cầu rollback khi có checked exception, cấu hình rõ:

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // ghi nhiều hàng
}
```

Test cần dùng đúng loại exception và đúng cấu hình rollback mà ứng dụng dự kiến. Nếu test ném checked exception nhưng không có `rollbackFor`, kết quả có thể khác với giả định của người viết test.

## 9. Kiểm thử REQUIRES_NEW và transaction độc lập

`REQUIRES_NEW` tạm treo transaction hiện tại và mở một transaction mới. Transaction bên trong có thể commit độc lập, kể cả khi transaction bên ngoài sau đó rollback.

```java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String action) {
        // ghi audit record
    }
}
```

Giả sử một service bên ngoài gọi `recordAttempt()` rồi ném lỗi. Nếu lời gọi đi qua proxy và transaction mới commit thành công, audit record có thể vẫn tồn tại dù transaction ngoài rollback.

Khi test, cần tránh vô tình làm cho audit method tham gia transaction test-managed bằng cách đổi propagation hoặc gọi nội bộ qua `this`. Hãy kiểm tra bằng một transaction độc lập sau khi cả luồng đã kết thúc.

Ví dụ test khái niệm:

```java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void requiresNewCommitsIndependently() {
    assertThrows(RuntimeException.class, () -> outerService.runAndFail());

    boolean auditExists = new TransactionTemplate(transactionManager)
        .execute(status -> auditRepository.existsByAction("ATTEMPT"));

    assertTrue(auditExists);
}
```

Để test thực sự có ý nghĩa, `outerService` phải được gọi qua Spring bean proxy, `AuditService` phải được tiêm từ container, và lời gọi `recordAttempt()` phải đi qua proxy của bean đó.

## 10. Kiểm thử sự kiện chỉ chạy sau commit

Một số công việc chỉ được thực hiện sau khi transaction commit, chẳng hạn phát sự kiện, gửi thông báo hoặc cập nhật cache. Trong Spring, `@TransactionalEventListener` có thể gắn listener với phase như `AFTER_COMMIT`.

```java
@Component
public class OrderEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        // xử lý sau commit
    }
}
```

Nếu test method đang giữ transaction test-managed, service phát event có thể kết thúc nhưng listener `AFTER_COMMIT` chưa chạy vì transaction bên ngoài chưa commit. Test kiểm tra listener ngay sau khi service trả về có thể thất bại dù production behavior đúng.

Để kiểm thử:

- Kết thúc transaction thực sự bằng cách gọi service trong test không có transaction bao ngoài.
- Hoặc chủ động `TestTransaction.flagForCommit()` và `TestTransaction.end()` trước khi kiểm tra listener.
- Dùng một cơ chế quan sát đáng tin cậy như spy/mock listener, bảng outbox hoặc trạng thái database, tùy mục tiêu test.

Với side effect bên ngoài như gửi email, nên kiểm tra rằng sự kiện/outbox được ghi sau commit hoặc listener được kích hoạt theo đúng phase. Không nên dựa vào việc gọi phương thức service thành công để kết luận email đã được gửi đúng một lần.

## 11. Async và thread khác làm thay đổi ngữ cảnh transaction

Transaction gắn với ngữ cảnh thực thi do transaction manager quản lý. Trong mô hình imperative phổ biến của Spring, transaction thường gắn với thread hiện tại. Khi công việc được chuyển sang thread khác bằng `@Async`, executor hoặc callback bất đồng bộ, transaction của thread gọi không tự động truyền sang thread mới.

Ví dụ:

```java
@Async
public CompletableFuture<Void> updateSearchIndex(Long orderId) {
    // chạy trên thread của executor
}
```

Nếu test chỉ kiểm tra trạng thái ngay sau khi phương thức gọi trả về, công việc async có thể chưa chạy xong. Nếu công việc async truy cập database, nó có thể cần transaction riêng trong thread thực thi.

Khi kiểm thử, hãy:

- Chờ completion bằng `Future`, `CompletableFuture`, latch hoặc cơ chế đồng bộ phù hợp.
- Kiểm tra transaction được mở ở thread thực thi nếu công việc cần transaction.
- Không giả định transaction của test thread bao phủ công việc async.
- Tránh dùng `Thread.sleep()` cố định làm đồng bộ; nó dễ tạo test chập chờn và chậm.

Reactive transaction management có cơ chế truyền context khác, thường dựa trên Reactor Context thay vì ThreadLocal. Vì vậy, không áp dụng máy móc quy tắc thread-bound của imperative stack cho reactive pipeline.

## 12. Kiểm thử ranh giới với TransactionTemplate

`TransactionTemplate` hữu ích khi muốn tạo ranh giới transaction rõ ràng trong test hoặc trong mã ứng dụng lập trình.

Ví dụ mở transaction để thực hiện một nhóm thay đổi:

```java
TransactionTemplate transaction = new TransactionTemplate(transactionManager);

Long orderId = transaction.execute(status -> {
    Order order = orderRepository.save(Order.create(command));
    paymentRepository.save(PaymentRecord.forOrder(order));
    return order.getId();
});
```

Khi callback kết thúc bình thường, template hoàn tất transaction theo cấu hình. Nếu callback ném exception phù hợp với quy tắc rollback, transaction được rollback.

Trong test, có thể dùng `TransactionTemplate` để tạo một transaction ghi và một transaction đọc riêng:

```java
Long id = writeTransaction.execute(status -> {
    Order order = orderRepository.save(Order.create(command));
    return order.getId();
});

Order persisted = readTransaction.execute(status ->
    orderRepository.findById(id).orElseThrow()
);
```

Nếu hai template không được cấu hình để tham gia cùng một transaction bên ngoài, transaction ghi hoàn tất trước khi transaction đọc bắt đầu. Cách này giúp test biểu đạt rõ điều kiện “dữ liệu đã commit phải nhìn thấy từ transaction khác”.

## 13. Kiểm thử bằng database thật và vì sao mock không đủ

Mock repository có thể xác nhận service gọi `save()` hoặc `delete()` với tham số mong đợi. Nhưng mock không mô phỏng đầy đủ:

- Transaction manager thực tế.
- Commit, rollback và propagation.
- Locking, isolation và deadlock.
- Constraint được database thực thi.
- Flush và deferred constraint.
- Hành vi connection pool và transaction gắn với connection.

Vì vậy, test unit dùng mock phù hợp để kiểm tra logic điều phối đơn giản. Muốn kiểm thử ranh giới transaction, cần integration test với Spring context và database có hành vi gần production.

### Chọn database kiểm thử

H2 hoặc database in-memory có thể tiện cho test nhanh, nhưng hành vi khóa, isolation, constraint, SQL dialect và transaction có thể khác PostgreSQL/MySQL/SQL Server production. Với test liên quan đến lock, deadlock, deferred constraint hoặc isolation anomaly, ưu tiên chạy đúng loại DBMS và phiên bản gần production, thường qua Testcontainers hoặc môi trường database tích hợp.

Testcontainers giúp khởi động database thật cho test và hủy container sau đó. Dù vậy, vẫn cần cấu hình transaction manager, datasource và isolation level giống môi trường ứng dụng.

## 14. Cách quan sát transaction đang hoạt động

Trong Spring, có thể dùng `TransactionSynchronizationManager` để quan sát một số thuộc tính transaction trong mã chẩn đoán hoặc test:

```java
boolean active = TransactionSynchronizationManager
    .isActualTransactionActive();

boolean synchronizationActive = TransactionSynchronizationManager
    .isSynchronizationActive();
```

Điều này hữu ích để xác nhận có transaction thực tế ở thời điểm kiểm tra. Nhưng chỉ thấy `isActualTransactionActive() == true` không chứng minh transaction sẽ commit, cũng không cho biết transaction đó được mở bởi test, service hay caller.

Để xác nhận ranh giới, kết hợp quan sát này với:

- Xem transaction manager và propagation được áp dụng.
- Kiểm tra lời gọi có đi qua proxy hay không.
- Theo dõi log transaction/SQL khi cần.
- Kết thúc transaction rồi đọc dữ liệu từ một transaction độc lập.
- Kiểm tra rollback bằng cách xác nhận dữ liệu không tồn tại sau khi transaction kết thúc.

Không nên thêm assertion nội bộ vào mọi test chỉ để kiểm tra annotation. Hãy kiểm tra kết quả bên ngoài transaction vì đó mới là hành vi nghiệp vụ mà caller cần dựa vào.

## 15. Những tình huống test dễ đưa ra kết luận sai

| Cách test | Kết luận sai có thể rút ra | Cách kiểm tra đúng hơn |
|---|---|---|
| Test method `@Transactional`, service dùng `REQUIRED` | Service đã commit khi trả về | Gọi service trong test không có transaction bao ngoài hoặc chủ động kết thúc test transaction |
| Gọi `saveAndFlush()` rồi assertion trong cùng transaction | Dữ liệu đã commit | Đọc từ transaction/connection độc lập sau commit |
| Gọi transactional method qua `this` | Annotation `REQUIRES_NEW`/`REQUIRES_*` đã được áp dụng | Gọi qua Spring proxy hoặc dùng `TransactionTemplate` |
| Mock repository và kiểm tra `save()` được gọi | Database sẽ commit hoặc rollback đúng | Integration test với transaction manager và DB thật |
| Kiểm tra `AFTER_COMMIT` trước khi test transaction kết thúc | Listener không hoạt động | Commit transaction trước rồi mới xác nhận listener |
| Gọi `@Async` rồi assertion ngay | Công việc async đã hoàn tất | Chờ future/latch hoặc cơ chế đồng bộ có giới hạn |
| Chỉ chạy test trên H2 cho logic khóa | Production DB sẽ có hành vi khóa giống H2 | Kiểm thử trên cùng họ DBMS và isolation level production |
| Ném checked exception và mong transaction rollback mặc định | Spring luôn rollback | Cấu hình `rollbackFor` phù hợp và kiểm tra sau transaction |

## 16. Quy trình thiết kế một integration test cho transaction

Khi cần kiểm tra một nghiệp vụ có ranh giới transaction, có thể tiến hành theo trình tự:

1. **Viết rõ bất biến cần kiểm tra.** Ví dụ order và payment record phải cùng commit hoặc cùng rollback.
2. **Xác định transaction owner.** Transaction được mở ở service nào, test nào, hay transaction ngoài nào?
3. **Xác định propagation của từng lời gọi.** Các service con dùng `REQUIRED`, `REQUIRES_NEW` hay chế độ khác?
4. **Kiểm tra cách gọi.** Bean có được lấy từ Spring context và lời gọi có đi qua proxy không? Có self-invocation hoặc async boundary không?
5. **Chọn loại test phù hợp.** Test unit cho logic thuần; integration test với database thật cho commit/rollback/lock/constraint.
6. **Tạo ranh giới quan sát độc lập.** Sau khi transaction kết thúc, đọc dữ liệu từ transaction khác hoặc xác nhận dữ liệu đã bị rollback.
7. **Kiểm tra lỗi đúng loại.** Runtime exception, checked exception, deadlock, serialization failure và constraint violation có thể có quy tắc phục hồi khác nhau.
8. **Dọn dữ liệu có chủ đích.** Test có commit thật phải xóa dữ liệu bằng fixture/cleanup hoặc database/container riêng; không dựa vào rollback tự động nếu transaction đã commit.

## 17. Tự kiểm tra

**Tình huống 1:** Test method có `@Transactional` gọi service method `@Transactional(REQUIRED)`. Service trả về bình thường. Có thể kết luận transaction của service đã commit không?

**Đáp án:** Không. Service thường tham gia transaction test-managed. Transaction chỉ kết thúc khi Spring Test commit hoặc rollback transaction của test.

**Tình huống 2:** Test gọi `repository.saveAndFlush()` rồi tìm thấy hàng trong cùng transaction. Điều đó chứng minh điều gì?

**Đáp án:** Nó cho thấy thay đổi đã được flush xuống database và nhìn thấy trong transaction hiện tại. Nó không chứng minh transaction đã commit; rollback vẫn có thể hủy thay đổi.

**Tình huống 3:** Một phương thức `@Transactional(REQUIRES_NEW)` được gọi qua `this.method()`. Có chắc transaction mới được mở không?

**Đáp án:** Không trong proxy mode mặc định. Self-invocation không đi qua proxy nên transaction interceptor có thể không áp dụng annotation của phương thức được gọi.

**Tình huống 4:** Muốn xác nhận service commit trước khi trả về, test nên làm gì?

**Đáp án:** Không bọc lời gọi service trong transaction test-managed. Gọi bean service qua Spring proxy, để transaction service hoàn tất, rồi đọc dữ liệu bằng transaction độc lập.

**Tình huống 5:** Test một listener `AFTER_COMMIT` nhưng listener chưa chạy ngay sau khi service trả về. Nguyên nhân có thể là gì?

**Đáp án:** Service có thể đang tham gia transaction ngoài do test quản lý. Listener chỉ chạy khi transaction thực sự commit, nên cần kết thúc transaction trước khi assertion.

**Tình huống 6:** Một service chạy trong transaction rồi gọi phương thức `@Async` cập nhật database. Transaction của service có tự truyền sang thread async không?

**Đáp án:** Không trong mô hình imperative thread-bound thông thường. Công việc async cần transaction riêng nếu cần, và test phải chờ công việc hoàn tất trước khi kiểm tra kết quả.

Khi kiểm thử transaction, hãy quan sát dữ liệu ở phía bên kia của ranh giới commit hoặc rollback. Tên phương thức, annotation đơn lẻ hay việc flush thành công đều chưa đủ để chứng minh ranh giới thực tế. Chỉ khi xác định được transaction owner, propagation, đường gọi proxy và thời điểm hoàn tất, test mới phản ánh đúng hành vi mà ứng dụng sẽ có khi chạy.
