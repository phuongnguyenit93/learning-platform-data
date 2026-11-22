# Xử lý sự kiện theo giai đoạn giao dịch bằng @TransactionalEventListener

Một nghiệp vụ Spring thường cần thực hiện thêm công việc sau khi ghi dữ liệu: gửi email, làm mới cache, cập nhật search index, ghi audit hoặc thông báo sang module khác. Nếu chạy side effect ngay trong method service, nó có thể xảy ra trước khi database commit. Nếu transaction sau đó rollback, dữ liệu không tồn tại nhưng email hoặc message đã được gửi.

Spring cung cấp `@TransactionalEventListener` để gắn thời điểm xử lý application event với một phase của transaction. Mặc định listener chạy ở `AFTER_COMMIT`. Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.

Cơ chế này giúp xử lý theo kết quả transaction trong cùng ứng dụng. Tuy nhiên, application event chỉ tồn tại trong process và không phải hàng đợi bền vững. Với message quan trọng cần retry hoặc phải được giao sau khi process restart, cần cân nhắc transactional outbox hoặc broker có lưu trữ.

## 1. Vì sao cần transaction-bound event?

Ví dụ service tạo đơn hàng và gửi email trực tiếp:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    emailService.sendConfirmation(order.getId());
    return order.getId();
}
~~~

Email được gửi trước khi transaction hoàn tất. Nếu flush hoặc commit gặp lỗi, database rollback nhưng email vẫn đã gửi.

Thay vào đó, publish event trong transaction:

~~~java
import java.time.Instant;
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    events.publishEvent(new OrderPlacedEvent(order.getId(), Instant.now()));
    return order.getId();
}
~~~

Listener:

~~~java
@Component
public class OrderNotificationListener {

    private final EmailService emailService;

    public OrderNotificationListener(EmailService emailService) {
        this.emailService = emailService;
    }

    @TransactionalEventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailService.sendConfirmation(event.orderId());
    }
}
~~~

Không khai báo phase đồng nghĩa với `AFTER_COMMIT`. Listener chỉ chạy khi transaction chứa lệnh publish commit thành công. Nếu transaction rollback, listener mặc định không chạy.

Spring đăng ký việc xử lý event với transaction synchronization tại thời điểm publish. Listener được gọi khi transaction đạt phase đã chọn.

## 2. @EventListener khác @TransactionalEventListener

`@EventListener` thông thường xử lý event ngay khi event được publish. Theo mặc định, nó chạy đồng bộ trên thread publish event.

`@TransactionalEventListener` đăng ký callback theo phase của transaction. Khi có transaction phù hợp, callback được trì hoãn cho tới phase đó.

| Đặc điểm | @EventListener | @TransactionalEventListener |
|---|---|---|
| Thời điểm | Ngay lúc publish | Theo transaction phase |
| Cần transaction | Không | Có, mặc định |
| Phân biệt commit/rollback | Không tự phân biệt | Có thể chọn phase |
| Khi không có transaction | Vẫn chạy | Mặc định bị bỏ qua |
| Use case | Event nội bộ không phụ thuộc commit | Side effect phụ thuộc kết quả transaction |

Hai listener có thể cùng nhận một event:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void handleImmediately(OrderPlacedEvent event) {
        System.out.println("Event was published");
    }

    @TransactionalEventListener
    public void handleAfterCommit(OrderPlacedEvent event) {
        System.out.println("Order transaction committed");
    }
}
~~~

Listener thường chạy tại lệnh publish; listener transaction-bound chờ phase tương ứng. Không dùng `@EventListener` thường cho side effect chỉ được phép xảy ra sau commit.

## 3. Bốn transaction phase

Thuộc tính `phase` nhận giá trị từ `TransactionPhase`.

### 3.1. BEFORE_COMMIT

`BEFORE_COMMIT` chạy trước khi transaction commit. Dùng khi công việc cần tham gia cùng transaction và phải rollback cùng dữ liệu gốc nếu thất bại.

Ví dụ ghi audit trong cùng transaction:

~~~java
@Component
public class OrderAuditListener {

    private final OrderAuditRepository audits;

    public OrderAuditListener(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void record(OrderPlacedEvent event) {
        audits.save(new OrderAudit(event.orderId(), "ORDER_PLACED"));
    }
}
~~~

Nếu listener ném runtime exception trước commit, transaction có thể rollback và cả order lẫn audit record đều không được commit.

BEFORE_COMMIT không chứng minh rằng transaction chắc chắn sẽ commit. Flush, constraint hoặc commit vẫn có thể thất bại sau callback. Không gửi email hoặc gọi API ngoài ở phase này nếu không có cơ chế bù trừ phù hợp.

### 3.2. AFTER_COMMIT

`AFTER_COMMIT` chỉ chạy sau khi transaction commit thành công. Đây là phase mặc định, phù hợp cho email, cache invalidation, search indexing hoặc kích hoạt công việc tiếp theo.

~~~java
@Component
public class SearchIndexListener {

    private final SearchIndexer indexer;

    public SearchIndexListener(SearchIndexer indexer) {
        this.indexer = indexer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void index(OrderPlacedEvent event) {
        indexer.indexOrder(event.orderId());
    }
}
~~~

Nếu transaction rollback, listener không chạy. Nếu listener thất bại sau commit, dữ liệu nghiệp vụ gốc vẫn đã commit; callback không thể đảo ngược kết quả đó. Cần có cách quan sát lỗi và retry phù hợp với tầm quan trọng của side effect.

### 3.3. AFTER_ROLLBACK

`AFTER_ROLLBACK` chạy khi transaction kết thúc bằng rollback. Có thể dùng để ghi metric, log kỹ thuật hoặc kích hoạt quy trình xử lý lỗi.

~~~java
@Component
public class OrderRollbackListener {

    private final FailureMetrics metrics;

    public OrderRollbackListener(FailureMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacedEvent event) {
        metrics.increment("order.transaction.rollback");
    }
}
~~~

Listener chỉ nhận event đã được publish. Nếu exception xảy ra trước lệnh publish, không có event để listener xử lý. Nếu cần ghi audit vào database sau rollback, hãy mở transaction mới; transaction gốc đã kết thúc.

### 3.4. AFTER_COMPLETION

`AFTER_COMPLETION` chạy sau khi transaction hoàn tất, bất kể commit hay rollback. Dùng cho cleanup hoặc metric không phụ thuộc outcome.

~~~java
@Component
public class CompletionListener {

    private final TransactionMetrics metrics;

    public CompletionListener(TransactionMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void completed(OrderPlacedEvent event) {
        metrics.recordCompletion(event.orderId());
    }
}
~~~

Nếu cần phân biệt thành công và rollback, dùng riêng AFTER_COMMIT và AFTER_ROLLBACK. AFTER_COMPLETION không có nghĩa là transaction thành công.

| Phase | Thời điểm | Mục đích |
|---|---|---|
| BEFORE_COMMIT | Trước commit | Công việc cùng transaction |
| AFTER_COMMIT | Sau commit thành công | Side effect chỉ chạy khi dữ liệu đã commit |
| AFTER_ROLLBACK | Sau rollback | Ghi nhận hoặc xử lý hậu rollback |
| AFTER_COMPLETION | Sau commit hoặc rollback | Cleanup và metric chung |

## 4. Thiết kế event payload

Nên định nghĩa event bất biến, chỉ chứa dữ liệu listener cần. Ví dụ:

~~~java
package com.example.orders;

import java.time.Instant;

public record OrderPlacedEvent(
        Long orderId,
        Instant occurredAt) {
}
~~~

Publisher:

~~~java
import java.time.Instant;
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(CreateOrderCommand command) {
        PurchaseOrder order = orders.save(
                new PurchaseOrder(command.customerId(), command.total())
        );

        events.publishEvent(
                new OrderPlacedEvent(order.getId(), Instant.now())
        );

        return order.getId();
    }
}
~~~

Event được publish trước commit là chủ ý. Spring đợi phase trước khi gọi transactional listener.

### 4.1. Vì sao thường truyền ID thay vì entity?

Tránh truyền toàn bộ JPA entity nếu listener chỉ cần ID:

- Entity có thể chứa lazy association và gây lazy loading sau commit.
- Entity có thể thay đổi sau lúc event được tạo.
- Payload entity làm các module phụ thuộc chặt vào mapping persistence.
- ID cho phép listener tải trạng thái cần thiết trong transaction riêng.

Nếu listener cần snapshot chính xác tại thời điểm phát sinh event, đưa các trường cần thiết vào immutable event. Nếu listener cần trạng thái mới nhất, truyền ID và tải lại trong transaction của listener.

### 4.2. Publish sau khi có khóa chính

Nếu ID do database sinh tự động, bảo đảm ID có trước khi tạo event. Với một số chiến lược sinh khóa, `save()` có thể cấp ID ngay; chiến lược khác cần flush để insert được thực hiện.

Không flush chỉ để đoán ID khi mapping đã bảo đảm ID có sẵn. Kiểm tra `@GeneratedValue` và chiến lược sinh khóa của ứng dụng.

## 5. Vòng đời xử lý event

Luồng phổ biến:

~~~text
Service mở transaction
        |
        v
Ghi entity
        |
        v
publishEvent(event)
        |
        +--> @EventListener chạy ngay
        |
        +--> @TransactionalEventListener đăng ký phase
        |
        v
Service method kết thúc
        |
        v
Spring flush và commit
        |
        +--> Rollback --> AFTER_ROLLBACK
        |                AFTER_COMPLETION
        |
        +--> Commit ----> AFTER_COMMIT
                         AFTER_COMPLETION
~~~

BEFORE_COMMIT chạy trước commit thực tế. Sau callback này, transaction vẫn có thể rollback do lỗi flush hoặc constraint.

Listener transaction-bound mặc định được gọi đồng bộ khi transaction đến phase. Nếu dùng async, callback sẽ dispatch công việc sang executor và cần xử lý khác biệt về thread/transaction.

## 6. Khi event được publish ngoài transaction

Mặc định `@TransactionalEventListener` yêu cầu transaction đang hoạt động khi event được publish. Nếu không có transaction, listener bị bỏ qua.

Có thể bật fallback:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void handle(OrderPlacedEvent event) {
    // Chạy ngay khi không có transaction.
}
~~~

Khi không có transaction, Spring không thể thực hiện semantics BEFORE_COMMIT hoặc AFTER_COMMIT. Với `fallbackExecution = true`, listener chạy ngay theo fallback thay vì chờ một transaction không tồn tại.

Chỉ bật fallback nếu nghiệp vụ chấp nhận hai hành vi: có transaction thì đợi phase; không có transaction thì chạy ngay. Nếu listener chỉ đúng sau khi database commit, giữ mặc định false và bảo đảm publisher chạy trong transaction.

### 6.1. Kiểm tra transaction boundary

`@Transactional` thường được áp dụng qua Spring AOP proxy. Trong cấu hình proxy mặc định, self-invocation (một method gọi method khác trong cùng class) không đi qua proxy nên có thể không mở transaction như mong đợi.

Nếu listener không chạy, kiểm tra:

- Publisher có thực sự chạy trong transaction không?
- Method được gọi qua Spring bean proxy không?
- Transaction có kết thúc trước khi publish không?
- Có đang dùng reactive transaction hay transaction thread-bound?
- Có bật fallback không?

Đừng bật fallback chỉ để che một transaction boundary bị cấu hình sai.

## 7. Ghi database sau AFTER_COMMIT cần transaction mới

Sau AFTER_COMMIT, transaction gốc đã commit nhưng transactional resources có thể vẫn còn được giữ trong quá trình hoàn tất synchronization. Nếu listener ghi database, thao tác có thể vẫn tham gia resource của transaction cũ nhưng không có lần commit tiếp theo.

Nếu listener cần ghi database sau commit, mở transaction độc lập bằng `Propagation.REQUIRES_NEW`:

~~~java
@Component
public class OrderHistoryListener {

    private final OrderHistoryRepository history;

    public OrderHistoryListener(OrderHistoryRepository history) {
        this.history = history;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeHistory(OrderPlacedEvent event) {
        history.save(new OrderHistory(
                event.orderId(),
                event.occurredAt()
        ));
    }
}
~~~

REQUIRES_NEW tạo transaction riêng để history record có thể commit độc lập sau transaction tạo đơn hàng.

Không dùng propagation REQUIRED rồi giả định nó luôn tạo transaction mới trong callback after-completion. Nếu cần một commit riêng, chỉ rõ REQUIRES_NEW.

### 7.1. AFTER_ROLLBACK ghi audit

Tương tự, nếu listener sau rollback phải ghi audit vào database, dùng transaction mới:

~~~java
@Component
public class RollbackAuditListener {

    private final FailureAuditRepository audits;

    public RollbackAuditListener(FailureAuditRepository audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(OrderPlacedEvent event) {
        audits.save(new FailureAudit(
                event.orderId(),
                "ORDER_TRANSACTION_ROLLED_BACK"
        ));
    }
}
~~~

Audit này có thể commit dù transaction nghiệp vụ ban đầu rollback. Hãy xác định rõ ý nghĩa record vì nó phản ánh một lần thử nghiệp vụ, không phải một order đã được commit.

## 8. Kết hợp @Async

Mặc định listener chạy đồng bộ ở transaction phase. Nếu listener gửi email, gọi API hoặc xử lý chậm, nó có thể kéo dài thời gian hoàn tất lời gọi transaction.

Có thể dispatch bằng `@Async`:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class AsyncOrderNotificationListener {

    private final EmailService emailService;

    public AsyncOrderNotificationListener(EmailService emailService) {
        this.emailService = emailService;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void sendNotification(OrderPlacedEvent event) {
        emailService.sendConfirmation(event.orderId());
    }
}
~~~

Listener được kích hoạt sau commit; method được chuyển sang async executor. Thread async không kế thừa transaction hoặc persistence context của thread commit.

Nếu async listener cần repository, mở transaction mới:

~~~java
@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void updateNotificationState(OrderPlacedEvent event) {
    notificationRepository.markPending(event.orderId());
}
~~~

Tách listener sang bean riêng, dùng public method và bảo đảm lời gọi đi qua Spring proxy để annotation AOP hoạt động. Không gọi trực tiếp method async/transactional trong cùng class rồi kỳ vọng proxy tự áp dụng.

### 8.1. Async không đồng nghĩa với durable

`@Async` chỉ chuyển công việc sang executor. Nếu JVM dừng sau commit nhưng trước khi executor xử lý listener, event in-process có thể bị mất.

Các rủi ro khác:

- Executor hết queue hoặc từ chối task.
- Worker thất bại giữa chừng.
- Exception của async void method không được trả về caller như lời gọi đồng bộ.
- Không có retry bền vững mặc định.
- Nhiều thread có thể hoàn tất task theo thứ tự khác nhau.

Với thông báo quan trọng, cần retry, theo dõi lỗi và idempotency. Nếu event phải tồn tại qua process crash, dùng outbox hoặc broker có lưu trữ.

## 9. Transaction-bound event và transactional outbox

`@TransactionalEventListener` gắn listener với transaction trong process. Nó không tự lưu event vào database.

Khoảng thời gian rủi ro:

1. Database commit thành công.
2. Process dừng trước khi listener gửi message.
3. Dữ liệu nghiệp vụ đã tồn tại nhưng hệ thống khác không nhận được event.

Nếu listener gọi API ngoài và API lỗi, Spring cũng không tự đưa event trở lại queue bền vững.

### 9.1. Mô hình outbox

Ghi dữ liệu nghiệp vụ và outbox message trong cùng transaction:

~~~java
import java.time.Instant;
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    outbox.save(new OutboxMessage(
            UUID.randomUUID(),
            "ORDER_PLACED",
            order.getId().toString(),
            Instant.now()
    ));

    return order.getId();
}
~~~

Cả hai insert thuộc cùng transaction:

- Rollback: order và outbox record cùng rollback.
- Commit: cả hai cùng tồn tại.
- Relay đọc outbox chưa gửi, publish sang broker và đánh dấu đã gửi.
- Process restart vẫn có thể đọc record còn tồn tại và tiếp tục.

### 9.2. AFTER_COMMIT chỉ là tín hiệu đánh thức relay

Có thể dùng local event để đánh thức relay sớm:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void wakeOutboxPublisher(OrderPlacedEvent event) {
    outboxSignal.notifyNewMessage();
}
~~~

Đây chỉ là tối ưu giảm độ trễ. Relay vẫn phải quét outbox định kỳ hoặc có cơ chế phục hồi độc lập vì tín hiệu in-process có thể mất.

### 9.3. Idempotency và delivery ít nhất một lần

Relay có thể gửi message thành công rồi process dừng trước khi đánh dấu outbox đã gửi. Khi chạy lại, message có thể được gửi lần nữa. Vì vậy outbox thường hướng tới delivery ít nhất một lần.

Consumer cần xử lý idempotent bằng event ID:

~~~java
@Transactional
public void handle(OrderPlacedMessage message) {
    if (processedMessages.existsById(message.eventId())) {
        return;
    }

    updateProjection(message);
    processedMessages.save(
            new ProcessedMessage(message.eventId())
    );
}
~~~

Ghi event ID đã xử lý và cập nhật dữ liệu trong cùng transaction giúp tránh xử lý trùng. Với side effect ngoài database, cần idempotency key hoặc một outbox tiếp theo.

## 10. Thứ tự listener với @Order

Nếu nhiều listener cùng xử lý một event và cùng phase, có thể dùng `@Order`:

~~~java
@Component
public class OrderedOrderListeners {

    @Order(10)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderPlacedEvent event) {
        // Chạy trước listener có order 20.
    }

    @Order(20)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void recordAudit(OrderPlacedEvent event) {
        // Chạy sau listener có order 10.
    }
}
~~~

Giá trị order nhỏ hơn có độ ưu tiên cao hơn. Dùng ordering khi có phụ thuộc thực sự. `@Order` không thay đổi transaction phase; listener AFTER_COMMIT không chạy trước BEFORE_COMMIT chỉ vì order nhỏ hơn.

Với async listener, thứ tự dispatch không bảo đảm thứ tự hoàn tất. Nếu các bước phụ thuộc nhau, dùng orchestration rõ ràng hoặc workflow/message processing thay vì dựa vào thứ tự thread.

## 11. Transaction propagation và event

Listener gắn với transaction đang hoạt động tại thời điểm publish:

- `PROPAGATION_REQUIRED` thường tham gia transaction hiện tại; listener đợi transaction đó hoàn tất.
- `PROPAGATION_REQUIRES_NEW` tạm treo transaction bên ngoài và mở transaction mới. Event publish trong transaction mới được xử lý khi transaction mới kết thúc.
- Nếu transaction REQUIRES_NEW commit, AFTER_COMMIT listener của nó có thể chạy dù transaction bên ngoài sau đó rollback.

Hãy xác định event thuộc transaction nào. Với nested transaction/savepoint, semantics phụ thuộc transaction manager và cách savepoint được quản lý; không coi rollback savepoint là một transaction độc lập đã hoàn tất. Nếu cần event chỉ sau commit cuối cùng, kiểm thử trên transaction manager thực tế.

## 12. Điều kiện lọc và event class

`@TransactionalEventListener` kế thừa thuộc tính của `@EventListener` như điều kiện SpEL và event class.

Ví dụ chỉ xử lý event giá trị lớn:

~~~java
@Component
public class HighValueOrderListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            condition = "#event.total() >= 1000"
    )
    public void handle(HighValueOrderEvent event) {
        // Xử lý đơn hàng giá trị lớn.
    }
}
~~~

Có thể khai báo event class nếu listener không cần tham số:

~~~java
@TransactionalEventListener(
        classes = OrderPlacedEvent.class,
        phase = TransactionPhase.AFTER_COMMIT
)
public void handle() {
    // Không nhận event argument.
}
~~~

Thông thường nên nhận event làm tham số vì listener cần ID hoặc metadata.

## 13. Reactive transaction và thread-bound context

Từ Spring Framework 6.1, transactional event listener có thể làm việc với transaction thread-bound qua `PlatformTransactionManager` và reactive transaction qua `ReactiveTransactionManager`.

Hai mô hình lưu context khác nhau:

- Transaction imperative truyền thống gắn với thread.
- Reactive transaction dùng Reactor Context, không dựa vào ThreadLocal thông thường.

Khi publish event trong reactive transaction, cần mang transaction context theo event bằng `TransactionalEventPublisher`. Không giả định lời gọi `ApplicationEventPublisher.publishEvent` thông thường tự mang Reactor Context.

Spring Data JPA dùng JDBC và persistence context imperative, vì vậy ví dụ trong bài tập trung vào PlatformTransactionManager. Ứng dụng dùng R2DBC/reactive transaction cần theo tài liệu reactive event publisher tương ứng.

## 14. Kiểm thử transaction phase

Test phải thực sự commit hoặc rollback để xác nhận callback. Nếu test method có `@Transactional` mặc định và Spring Test rollback sau test, listener AFTER_COMMIT sẽ không chạy như một transaction commit thành công.

Dùng `TransactionTemplate` để chủ động kết thúc transaction.

### 14.1. Probe ghi nhận các phase

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

@Component
public class TransactionPhaseProbe {

    private final List<String> calls = new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderPlacedEvent event) {
        calls.add("BEFORE_COMMIT");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlacedEvent event) {
        calls.add("AFTER_COMMIT");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderPlacedEvent event) {
        calls.add("AFTER_ROLLBACK");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(OrderPlacedEvent event) {
        calls.add("AFTER_COMPLETION");
    }

    public List<String> calls() {
        return List.copyOf(calls);
    }

    public void reset() {
        calls.clear();
    }
}
~~~

Đây là test helper. Với test chạy song song, dùng probe riêng cho mỗi test context hoặc đồng bộ hóa trạng thái.

### 14.2. Kiểm thử commit và rollback

~~~java
import java.time.Instant;
@SpringBootTest
class TransactionalEventListenerTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private ApplicationEventPublisher events;

    @Autowired
    private TransactionPhaseProbe probe;

    @Test
    void commitRunsBeforeCommitAfterCommitAndCompletion() {
        probe.reset();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status ->
                events.publishEvent(new OrderPlacedEvent(10L, Instant.now()))
        );

        assertThat(probe.calls()).containsExactly(
                "BEFORE_COMMIT",
                "AFTER_COMMIT",
                "AFTER_COMPLETION"
        );
    }

    @Test
    void rollbackRunsAfterRollbackAndCompletion() {
        probe.reset();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            events.publishEvent(new OrderPlacedEvent(11L, Instant.now()));
            status.setRollbackOnly();
        });

        assertThat(probe.calls()).containsExactly(
                "AFTER_ROLLBACK",
                "AFTER_COMPLETION"
        );
    }
}
~~~

Ví dụ giả định probe chỉ có đúng bốn listener và callback chạy đồng bộ. Test commit xác nhận BEFORE_COMMIT, AFTER_COMMIT, AFTER_COMPLETION. Test rollback xác nhận AFTER_ROLLBACK và AFTER_COMPLETION; BEFORE_COMMIT không chạy khi transaction đã được đánh dấu rollback-only trước commit.

### 14.3. Test event ngoài transaction

Publish event ngoài transaction:

~~~java
import java.time.Instant;
events.publishEvent(new OrderPlacedEvent(12L, Instant.now()));
~~~

Với `fallbackExecution = false`, transactional listener không được gọi. Viết test riêng nếu có listener bật fallback.

### 14.4. Test exception và async

Tạo listener BEFORE_COMMIT ném exception rồi xác nhận transaction rollback. Với listener AFTER_COMMIT, xác nhận dữ liệu nghiệp vụ vẫn tồn tại dù callback thất bại vì commit đã hoàn tất.

Với `@Async`, không assert ngay sau khi transaction kết thúc. Dùng latch, Awaitility hoặc cơ chế đồng bộ test để đợi executor; tránh sleep cố định. Nếu công việc quan trọng, test outbox/relay và retry thay vì chỉ kiểm tra local callback.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không chạy | Publish ngoài transaction | Kiểm tra transaction boundary hoặc fallback có chủ đích |
| Listener chạy trước commit | Dùng @EventListener thường | Dùng @TransactionalEventListener |
| Side effect xảy ra dù rollback | Thực hiện trước commit | Chuyển sang AFTER_COMMIT |
| Ghi DB sau AFTER_COMMIT nhưng không lưu | Dùng resource đã hoàn tất | Dùng REQUIRES_NEW |
| Gửi email dù insert thất bại | Gửi trực tiếp trong service | Gửi qua AFTER_COMMIT |
| Async listener không thấy transaction gốc | Chạy trên thread khác | Mở transaction riêng nếu cần |
| Event mất khi process dừng | Application event chỉ tồn tại trong process | Dùng outbox hoặc broker bền vững |
| Message bị xử lý trùng | Relay retry sau crash | Dùng event ID và idempotent consumer |
| Test AFTER_COMMIT không chạy | Test transaction rollback | Dùng TransactionTemplate hoặc commit thật |
| AFTER_COMPLETION bị hiểu là thành công | Phase chạy cả commit và rollback | Dùng AFTER_COMMIT |
| Listener phụ thuộc thứ tự không rõ | Không có ordering | Dùng @Order hoặc orchestration |

## 16. Checklist triển khai

- [ ] Event chỉ chứa dữ liệu listener cần, thường là ID hoặc immutable snapshot.
- [ ] Publisher chạy trong transaction nếu cần transaction phase.
- [ ] Chọn đúng BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK hoặc AFTER_COMPLETION.
- [ ] BEFORE_COMMIT chỉ làm việc phải cùng transaction.
- [ ] AFTER_COMMIT dùng cho side effect chỉ được phép chạy sau commit.
- [ ] Không nhầm AFTER_COMPLETION với thành công.
- [ ] Không bật fallbackExecution nếu không chấp nhận chạy ngoài transaction.
- [ ] Không phụ thuộc lazy entity graph sau khi persistence context kết thúc.
- [ ] Ghi DB sau completion dùng REQUIRES_NEW khi cần commit riêng.
- [ ] Async listener không giả định transaction gốc truyền sang thread khác.
- [ ] Side effect quan trọng có retry, idempotency và quan sát lỗi.
- [ ] Dùng outbox cho event phải tồn tại qua process crash.
- [ ] @Order chỉ dùng khi có phụ thuộc thực sự.
- [ ] Test commit, rollback, no-transaction, exception và async riêng biệt.
- [ ] Test transaction thật, không dựa vào test mặc định luôn rollback.
- [ ] Kiểm thử trên transaction manager và provider của ứng dụng.

## 17. Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — các phase, fallbackExecution và reactive transaction.
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — phase mặc định, điều kiện cần transaction và thuộc tính listener.
- [Spring Framework — TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html) — ý nghĩa các phase.
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — callback trước/sau commit và completion, resource sau completion.
- [Spring Framework — TransactionalEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html) — truyền transaction context trong reactive flow.
- [Spring Framework — @Async Support](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — cấu hình executor và xử lý bất đồng bộ.

`@TransactionalEventListener` gắn xử lý event với kết quả transaction và tránh side effect xảy ra trước khi dữ liệu được commit. Hãy chọn phase đúng, mở transaction mới khi callback sau completion cần ghi database, và không nhầm application event với hàng đợi bền vững. Với công việc cần retry hoặc phải giao chắc chắn sang hệ thống khác, transactional outbox cùng consumer idempotent là nền tảng đáng tin cậy hơn.
