# Kiểm thử transaction

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi publisher phát event trong một transaction, thời điểm listener được gọi và kết quả xử lý phụ thuộc vào commit hoặc rollback của transaction đó. Kiểm thử transaction giúp xác minh event chỉ được xử lý ở thời điểm phù hợp, dữ liệu không bị ghi dở dang và lỗi listener không làm sai trạng thái nghiệp vụ.

Một bài kiểm thử event transaction cần quan sát cả ba phần: transaction của publisher, thời điểm dispatch listener và transaction riêng của listener nếu có. Chỉ kiểm tra rằng publishEvent đã được gọi là chưa đủ để chứng minh event được giao sau commit hoặc không được giao khi rollback.

## 1. Transaction ảnh hưởng đến application event như thế nào?

Giả sử OrderService cập nhật trạng thái đơn hàng thành CONFIRMED và công bố OrderConfirmed trong cùng transaction. Một listener cập nhật read model hoặc gửi yêu cầu cho module khác. Nếu listener chạy trước khi transaction commit, nó có thể đọc trạng thái chưa được commit hoặc tạo side effect dù transaction gốc sau đó rollback.

Spring cung cấp transactional event listener để gắn thời điểm xử lý event với transaction đã phát event. Các phase thường dùng:

| Phase | Thời điểm gọi listener | Khi publisher transaction rollback |
| --- | --- | --- |
| BEFORE_COMMIT | Trước khi transaction commit. | Không chạy nếu transaction rollback. |
| AFTER_COMMIT | Sau khi transaction commit thành công. Đây là phase mặc định. | Không chạy. |
| AFTER_ROLLBACK | Sau khi transaction rollback. | Được gọi. |
| AFTER_COMPLETION | Sau khi transaction kết thúc, dù commit hay rollback. | Được gọi. |

Với @TransactionalEventListener, listener mặc định cần có transaction đang hoạt động tại thời điểm event được publish. Nếu không có transaction, listener không được gọi trừ khi bật fallbackExecution=true. Không nên bật fallback một cách tùy tiện vì cùng một event khi đó có thể được xử lý theo hai đường thời gian khác nhau.

## 2. Kiểm thử commit và rollback riêng biệt

Hai tình huống nền tảng cần được kiểm thử:

- **Commit:** transaction ghi dữ liệu thành công; listener AFTER_COMMIT được gọi sau khi commit.
- **Rollback:** transaction bị hủy; listener AFTER_COMMIT không được gọi và thay đổi dữ liệu của transaction gốc không tồn tại.

Một test cần xác minh kết quả quan sát được ở database hoặc một collaborator được theo dõi. Chỉ assert rằng publisher đã gọi ApplicationEventPublisher.publishEvent không kiểm tra được transaction phase.

Ví dụ publisher:

~~~java
public record OrderConfirmed(UUID orderId) {}

@Service
@RequiredArgsConstructor
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();
        events.publishEvent(new OrderConfirmed(orderId));
    }
}
~~~

Listener chỉ chạy sau commit:

~~~java
@Component
@RequiredArgsConstructor
class OrderProjectionListener {

    private final OrderProjectionService projections;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        projections.refresh(event.orderId());
    }
}
~~~

Trong ví dụ, OrderService ghi trạng thái và phát event trong một transaction. Listener được gọi sau khi transaction đó commit. Nếu transaction bị rollback, listener AFTER_COMMIT không được gọi.

## 3. Vì sao test có @Transactional thường không kích hoạt AFTER_COMMIT?

Spring Test mặc định rollback transaction của test method có @Transactional sau khi method kết thúc. Nếu test gọi OrderService trong transaction của test, transaction bên ngoài vẫn đang mở khi assertion chạy. Listener AFTER_COMMIT chưa được gọi vì chưa có commit thật.

Một test như sau có thể tạo hiểu nhầm:

~~~java
@Test
@Transactional
void publishesEvent() {
    orderService.confirm(orderId);

    // Transaction test vẫn đang mở tại đây.
    // Listener AFTER_COMMIT chưa nhất thiết đã chạy.
}
~~~

Flush không phải commit. Việc gọi EntityManager.flush() chỉ đồng bộ thay đổi xuống database trong transaction hiện tại; nó không kết thúc transaction và không kích hoạt AFTER_COMMIT.

Có ba cách phổ biến để kiểm soát transaction trong test:

1. Không đánh dấu test method @Transactional và để service mở/commit transaction của nó.
2. Dùng TransactionTemplate để chủ động commit hoặc rollback.
3. Dùng TestTransaction trong test có @Transactional để kết thúc transaction kiểm thử theo cách được chỉ định.

Chọn một cách phù hợp và xác minh rằng assertion được thực hiện sau đúng transaction boundary.

## 4. Dùng TransactionTemplate để kiểm thử commit

TransactionTemplate giúp test mở một transaction thật, thực hiện thao tác và để transaction manager commit khi callback kết thúc bình thường:

~~~java
@SpringBootTest
class OrderEventTransactionIntegrationTest {

    @Autowired
    TransactionTemplate transactionTemplate;

    @Autowired
    OrderService orderService;

    @Autowired
    OrderProjectionRepository projections;

    @Test
    void updatesProjectionAfterCommit() {
        transactionTemplate.executeWithoutResult(status ->
            orderService.confirm(orderId)
        );

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
            assertThat(projections.findByOrderId(orderId)).isPresent()
        );
    }
}
~~~

Đây là ví dụ integration test; orderId cần được tạo trong fixture của test. Awaitility được dùng để chờ listener bất đồng bộ nếu listener chạy async. Nếu listener đồng bộ AFTER_COMMIT, assertion có thể hoàn tất ngay sau khi TransactionTemplate trả về.

Nếu service mở transaction riêng với propagation mặc định REQUIRED, lời gọi service tham gia transaction do TransactionTemplate tạo. Khi callback kết thúc, transaction ngoài commit và kích hoạt listener. Nếu test đã có một transaction bao ngoài, TransactionTemplate có thể tham gia transaction đó; vì vậy cần tránh vô tình giữ một test transaction chưa commit.

## 5. Dùng TransactionTemplate để kiểm thử rollback

Để kiểm tra rollback, đánh dấu transaction rollback-only trước khi callback kết thúc:

~~~java
@Test
void doesNotRunAfterCommitListenerOnRollback() {
    transactionTemplate.executeWithoutResult(status -> {
        orderService.confirm(orderId);
        status.setRollbackOnly();
    });

    assertThat(orderRepository.findById(orderId))
        .get()
        .extracting(Order::getStatus)
        .isEqualTo(OrderStatus.PENDING);

    assertThat(orderProjectionRepository.findByOrderId(orderId))
        .isEmpty();
}
~~~

Sau khi TransactionTemplate trả về, transaction đã rollback. Listener AFTER_COMMIT không được gọi; dữ liệu write model và publication record thuộc transaction gốc cũng không được commit. Test nên xác minh cả dữ liệu gốc lẫn read model để tránh trường hợp một side effect bị ghi ngoài transaction dự kiến.

Nếu listener là async, không cần chờ một listener AFTER_COMMIT vốn không được gọi; tuy nhiên, test có thể dùng spy hoặc counter để xác minh không có invocation trong một khoảng kiểm tra phù hợp. Tránh dựa vào sleep dài cố định.

## 6. Dùng TestTransaction với test transaction

Khi cần dùng transaction do Spring Test quản lý, TestTransaction cho phép kết thúc transaction hiện tại với kết quả commit hoặc rollback có chủ đích:

~~~java
@SpringBootTest
@Transactional
class OrderEventCommitTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderProjectionRepository projections;

    @Test
    void afterCommitListenerRuns() {
        orderService.confirm(orderId);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
            assertThat(projections.findByOrderId(orderId)).isPresent()
        );
    }
}
~~~

Để kiểm tra rollback, dùng flagForRollback() trước TestTransaction.end(), sau đó xác minh listener AFTER_COMMIT không chạy và dữ liệu không được commit. TestTransaction.end() kết thúc transaction hiện tại; nếu test cần transaction mới cho phần assertion tiếp theo, có thể dùng TestTransaction.start() theo nhu cầu.

Không gọi TestTransaction.flagForCommit() chỉ để làm test pass nếu test cần xác minh hành vi rollback mặc định. Mục tiêu là kiểm soát rõ ràng transaction outcome mà test đang chứng minh.

## 7. Kiểm thử từng transaction phase

Không phải mọi listener đều dùng AFTER_COMMIT. Nếu ứng dụng dùng các phase khác, hãy kiểm tra đúng thời điểm:

| Phase | Kịch bản test |
| --- | --- |
| BEFORE_COMMIT | Trong transaction, xác minh handler được gọi trước commit; nếu handler ném exception phù hợp, kiểm tra transaction có rollback theo cấu hình. |
| AFTER_COMMIT | Commit transaction rồi xác minh handler được gọi; rollback thì không gọi. |
| AFTER_ROLLBACK | Rollback transaction rồi xác minh handler rollback được gọi. |
| AFTER_COMPLETION | Kiểm tra handler được gọi sau cả commit lẫn rollback và có thể phân biệt completion status nếu cần. |

Một listener BEFORE_COMMIT có thể tham gia vào kết quả transaction; lỗi của nó có thể ngăn commit. Listener AFTER_COMMIT không thể rollback transaction gốc vì transaction đó đã hoàn tất. Nếu AFTER_COMMIT listener thất bại, cần cơ chế retry/recovery riêng phù hợp.

Không dùng AFTER_COMPLETION để thực hiện side effect chỉ được phép xảy ra khi commit, vì phase này cũng chạy sau rollback. Nếu chỉ cần phản ứng khi rollback, dùng AFTER_ROLLBACK.

## 8. Kiểm thử @ApplicationModuleListener

Trong Spring Modulith, @ApplicationModuleListener là lựa chọn thuận tiện cho listener liên module. Annotation này kết hợp xử lý bất đồng bộ với transactional event listener ở phase AFTER_COMMIT và transaction riêng cho phần xử lý listener theo cấu hình của Spring Modulith.

Do listener bất đồng bộ, publisher có thể trả về trước khi handler hoàn tất. Test phải chờ một dấu hiệu hoàn tất có giới hạn thời gian, chẳng hạn projection được ghi, latch được mở hoặc event kết quả được phát.

~~~java
@Component
class InventoryListener {

    private final InventoryService inventory;

    InventoryListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserve(event.orderId());
    }
}
~~~

Khi kiểm thử, cần xác minh:

- Transaction publisher đã commit trước khi listener bắt đầu.
- Listener chạy ở luồng bất đồng bộ theo cấu hình.
- Lỗi listener không làm transaction publisher đã commit bị rollback.
- Transaction của listener commit hoặc rollback độc lập.
- Publication được đánh dấu hoàn tất khi listener xử lý thành công theo cơ chế registry.
- Publication còn incomplete khi listener thất bại theo cấu hình và có thể recovery.

Không giả định thread khác tự động chia sẻ transaction hoặc persistence context của publisher. Transaction không truyền qua thread; listener cần transaction riêng nếu thực hiện thay đổi dữ liệu.

## 9. Kiểm thử transaction propagation của listener

Một listener AFTER_COMMIT thông thường được gọi sau khi transaction gốc hoàn tất. Tài nguyên transaction có thể vẫn được giữ trong quá trình callback completion, nhưng các thay đổi ghi thêm vào cùng tài nguyên không tự động được commit như một transaction mới. Nếu listener cần ghi database, hãy mở transaction mới bằng propagation phù hợp.

Ví dụ:

~~~java
@Component
class AuditListener {

    private final AuditRepository auditRepository;

    AuditListener(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    void on(OrderConfirmed event) {
        auditRepository.save(AuditEntry.forOrder(event.orderId()));
    }
}
~~~

Trong test, xác minh audit record tồn tại sau khi listener hoàn tất và vẫn tồn tại sau khi mở một transaction đọc mới. Đồng thời, kiểm tra nếu listener ném exception thì transaction gốc vẫn đã commit; audit transaction riêng bị rollback và publication cần được recovery theo cơ chế đang dùng.

@ApplicationModuleListener đã cung cấp transaction riêng cho listener theo cấu hình annotation. Tránh thêm propagation không cần thiết nếu không có lý do; hãy hiểu rõ transaction boundary để không vô tình tạo nhiều transaction lồng nhau.

## 10. Kiểm thử Event Publication Registry

Event Publication Registry theo dõi publication đến transactional listener. Registry ghi nhận publication trong transaction phát event và đánh dấu completed khi listener xử lý thành công. Điều này cho phép kiểm tra tính nhất quán giữa transaction publisher, việc giao event và trạng thái completion.

Các tình huống integration test quan trọng:

1. Publisher transaction commit: publication record được lưu cho transactional listener.
2. Publisher transaction rollback: publication record thuộc transaction đó không tồn tại sau rollback.
3. Listener xử lý thành công: publication được đánh dấu completed.
4. Listener ném exception: publication chưa hoàn tất và có thể được tìm để recovery theo cấu hình.
5. Listener được resubmit: handler xử lý an toàn và publication hoàn tất sau khi thành công.

API truy vấn hoặc resubmit publication có thể khác theo phiên bản Spring Modulith. Dùng API được cung cấp bởi phiên bản ứng dụng đang khóa và tránh phụ thuộc trực tiếp vào tên bảng nội bộ của registry trong test.

Registry cần persistent publication repository nếu yêu cầu kiểm tra phục hồi sau restart. Store chỉ trong bộ nhớ không thể chứng minh durability qua process restart. Trong integration test, dùng database phù hợp với cấu hình production để xác minh transaction và persistence.

## 11. Kiểm thử failure window và idempotency

Một tình huống quan trọng: listener đã commit side effect nhưng process dừng trước khi registry đánh dấu publication completed. Khi ứng dụng phục hồi, publication có thể được giao lại. Test cần chứng minh handler không tạo side effect lần hai.

Ví dụ, listener tạo reservation theo orderId. Có thể đặt unique constraint trên orderId hoặc lưu eventId đã xử lý trong cùng transaction với reservation. Khi event được giao lại, handler nhận diện duplicate và kết thúc an toàn.

Các assertion nên có:

- Một eventId chỉ tạo một reservation hoặc audit action.
- Retry sau rollback có thể thực hiện lại thay đổi chưa commit.
- Retry sau side effect đã commit không nhân đôi tác động.
- Publication chỉ completed khi listener xử lý thành công.
- Một listener thành công không làm publication của listener khác tự động completed.

Không nên kiểm thử duplicate chỉ bằng cách gọi method handler hai lần với mock repository. Cần có ít nhất một integration test xác minh unique constraint, transaction rollback và persistence inbox trên database.

## 12. Kiểm thử nhiều listener và nhiều transaction

Một event có thể được nhận bởi nhiều transactional listener. Mỗi listener có publication và transaction xử lý riêng. Nếu listener A commit thành công nhưng listener B thất bại, dữ liệu của A có thể đã commit; transaction của B không tự rollback A.

Ví dụ event OrderConfirmed được nhận bởi Inventory listener và Notification listener:

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Cả hai listener thành công | Hai publication đều completed và hai side effect tồn tại. |
| Inventory thành công, Notification lỗi | Inventory side effect vẫn tồn tại; publication Notification còn incomplete. |
| Inventory rollback, Notification thành công | Notification có thể hoàn tất độc lập; Inventory cần recovery. |
| Publisher rollback | Không listener AFTER_COMMIT nào xử lý event của transaction đó. |

Test không nên giả định thứ tự hoàn tất giữa các listener bất đồng bộ. Dùng điều kiện chờ riêng cho từng side effect hoặc publication state. Nếu nghiệp vụ yêu cầu Notification chỉ gửi sau khi Inventory thành công, phải mô hình hóa quan hệ bước bằng event kết quả hoặc process manager thay vì dựa vào thứ tự thread.

## 13. Transaction isolation và kiểm thử concurrency

Transaction test cần kiểm tra các tình huống cạnh tranh khi hai event hoặc hai listener cùng cập nhật một aggregate/read model. Một test chạy tuần tự không phát hiện được lost update, unique constraint race hoặc optimistic locking conflict.

Các kịch bản nên bao gồm:

- Hai event cùng cập nhật một order trong hai transaction.
- Một transaction commit trong khi transaction khác rollback.
- Hai lần giao cùng eventId đồng thời.
- Listener cập nhật projection khi publisher phát event mới hơn.
- Deadlock hoặc optimistic lock conflict được phân loại và retry theo chính sách.

Sử dụng barrier/latch để điều khiển thời điểm hai transaction chạy đồng thời, thay vì sleep để hy vọng race xảy ra. Xác minh invariant sau khi cả hai transaction hoàn tất, ví dụ reservation chỉ tồn tại một lần và aggregate version không bị lùi.

Isolation level mặc định có thể khác nhau giữa database. Nếu correctness phụ thuộc vào locking hoặc constraint cụ thể, cần chạy integration test với cùng loại database như môi trường production; H2 có thể không tái hiện đầy đủ hành vi lock, isolation hoặc constraint của PostgreSQL/MySQL.

## 14. Kiểm thử không có transaction và fallbackExecution

Nếu event được publish ngoài transaction, @TransactionalEventListener mặc định không chạy. Có thể bật fallbackExecution=true để listener vẫn được gọi khi không có transaction:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
void on(OrderConfirmed event) {
    // Xử lý cả khi event không được phát trong transaction.
}
~~~

Test cần có hai trường hợp: publish bên trong transaction và publish ngoài transaction. Xác minh listener chạy đúng theo chính sách đã chọn. Khi fallbackExecution bật, event publish ngoài transaction không có commit boundary để chờ; handler được gọi theo cơ chế fallback và không có bảo đảm nguyên tử với thay đổi database nào khác.

Nếu nghiệp vụ yêu cầu event luôn gắn với commit, thường nên giữ fallbackExecution=false và bảo đảm publisher gọi trong transaction. Test này giúp phát hiện đường gọi vô tình bỏ qua transaction.

## 15. Kiểm thử transaction khi dùng @RecordApplicationEvents

Spring Test cung cấp @RecordApplicationEvents để ghi nhận application events được publish trong phạm vi test. Có thể inject ApplicationEvents và kiểm tra event đã được công bố:

~~~java
@SpringBootTest
@RecordApplicationEvents
class OrderEventPublicationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderConfirmed() {
        orderService.confirm(orderId);

        assertThat(applicationEvents.stream(OrderConfirmed.class))
            .hasSize(1);
    }
}
~~~

@RecordApplicationEvents xác minh event đã được publish, không tự chứng minh listener AFTER_COMMIT đã chạy hoặc transaction đã commit. Để kiểm tra transaction phase, kết hợp với TransactionTemplate/TestTransaction và assertion trên side effect hoặc listener invocation.

Nếu test có transaction bao ngoài, event có thể đã được ghi nhận trong ApplicationEvents trong khi listener vẫn đang chờ commit. Phải phân biệt rõ “đã publish” với “đã được listener xử lý”.

## 16. Kiểm thử event phase bằng sơ đồ

Luồng commit:

~~~mermaid
sequenceDiagram
    participant T as Publisher transaction
    participant P as ApplicationEventPublisher
    participant L as AFTER_COMMIT listener
    participant D as Listener database transaction
    T->>T: Update write model
    T->>P: Publish event
    P-->>T: Register transactional listener
    T->>T: Commit
    T->>L: Invoke listener
    L->>D: Begin REQUIRES_NEW
    D->>D: Apply side effect
    D->>D: Commit
~~~

Luồng rollback:

~~~mermaid
sequenceDiagram
    participant T as Publisher transaction
    participant P as ApplicationEventPublisher
    participant L as AFTER_COMMIT listener
    T->>T: Update write model
    T->>P: Publish event
    P-->>T: Register transactional listener
    T->>T: Rollback
    Note over L: AFTER_COMMIT listener is not invoked
~~~

Hai sơ đồ mô tả thứ tự logic. Với listener bất đồng bộ, việc listener bắt đầu có thể xảy ra trên thread khác sau commit; test phải chờ completion thay vì giả định thời điểm đồng bộ với lời gọi publisher.

## 17. Những lỗi thường gặp khi viết transaction test

| Lỗi trong test | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Test có @Transactional rồi assert listener chạy ngay | Transaction test chưa commit. | Dùng TransactionTemplate hoặc TestTransaction để commit trước assertion. |
| Gọi flush rồi chờ AFTER_COMMIT | Flush không kết thúc transaction. | Commit transaction thật. |
| Dùng sleep cố định cho async listener | Thời gian xử lý biến động và test dễ chập chờn. | Chờ điều kiện với timeout hữu hạn. |
| Chỉ verify publishEvent | Không chứng minh phase hoặc side effect. | Kiểm tra database/listener/publication state. |
| Bắt exception trong listener rồi chỉ log | Framework có thể xem listener đã hoàn tất. | Ném lại lỗi hoặc ghi nhận outcome/quarantine rõ ràng. |
| Dùng H2 cho mọi transaction behavior | Có thể khác database production về lock/isolation. | Thêm integration test với database tương thích production. |
| Giả định listener A và B có thứ tự | Listener async độc lập không bảo đảm thứ tự hoàn tất. | Kiểm tra độc lập hoặc mô hình hóa orchestration. |
| Chỉ test thành công, không test rollback | Bỏ sót event được xử lý dù transaction gốc thất bại. | Có test commit và rollback riêng. |
| Không kiểm tra duplicate | Crash window có thể lặp side effect. | Test idempotency và unique constraint trên database. |

## 18. Checklist kiểm thử transaction

- Test phân biệt rõ event đã publish với listener đã xử lý.
- Test AFTER_COMMIT xác minh listener chỉ chạy sau commit.
- Test rollback xác minh AFTER_COMMIT không chạy và dữ liệu không được commit.
- Test BEFORE_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION nếu ứng dụng sử dụng các phase đó.
- Test không có transaction xác minh hành vi fallbackExecution.
- Test không vô tình giữ outer test transaction khi cần commit thật.
- Test async listener chờ completion bằng điều kiện và timeout hữu hạn.
- Test transaction riêng của listener xác minh side effect được commit độc lập.
- Test Event Publication Registry cho commit, rollback, listener failure và recovery.
- Test failure window và idempotency để duplicate không lặp side effect.
- Test nhiều listener xác minh publication và transaction độc lập.
- Test concurrency bao phủ duplicate, lock conflict và invariant dữ liệu.
- Integration test dùng database phù hợp để xác minh isolation, locking và constraint.
- Test xác minh health/observability không thay thế assertion transaction correctness.

Kiểm thử transaction giúp bảo vệ ranh giới giữa thay đổi nghiệp vụ và việc giao event. Khi test điều khiển được commit/rollback, hiểu rõ phase của listener, chờ đúng async completion và xác minh publication registry cùng side effect trên database, ứng dụng có thể phát hiện sớm lỗi giao event trước commit, mất xử lý sau rollback, ghi dữ liệu ngoài transaction và duplicate sau recovery.
