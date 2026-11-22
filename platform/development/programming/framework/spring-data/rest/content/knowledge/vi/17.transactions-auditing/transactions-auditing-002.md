# Vì sao sự kiện After* không đồng nghĩa với transaction đã commit trong Spring Data REST

## Mục tiêu

Spring Data REST phát các event như `AfterCreateEvent`, `AfterSaveEvent`, `AfterDeleteEvent` và `AfterLinkSaveEvent` khi REST exporter xử lý một entity hoặc association. Từ “After” cho biết một bước xử lý của exporter đã diễn ra xong. Nó **không phải tên của transaction phase** và không tự bảo đảm rằng database transaction đã commit.

Muốn hiểu chính xác thời điểm listener chạy, cần tách ba khái niệm:

1. **Repository operation:** lời gọi `save()`, `delete()` hoặc thao tác association đã trả về.
2. **Spring application event:** exporter publish event và listener mặc định được gọi đồng bộ trong luồng publish.
3. **Transaction completion:** transaction manager thực sự commit hoặc rollback transaction đang bao quanh thao tác.

Trong trường hợp repository tự mở transaction và không có transaction bao ngoài, lời gọi repository có thể commit trước khi exporter phát event After*. Nhưng nếu repository tham gia một transaction đã tồn tại, event After* vẫn có thể được phát khi transaction đó còn mở và sau đó bị rollback. Vì thế không thể dùng tiền tố After* như một cam kết “đã commit”.

## 1. Các event Before* và After* của Spring Data REST

REST exporter phát tám repository events trong quá trình xử lý entity:

| Trước thao tác | Sau thao tác | Ý nghĩa |
| --- | --- | --- |
| `BeforeCreateEvent` | `AfterCreateEvent` | Tạo entity mới |
| `BeforeSaveEvent` | `AfterSaveEvent` | Lưu/cập nhật entity |
| `BeforeLinkSaveEvent` | `AfterLinkSaveEvent` | Gắn hoặc cập nhật association link |
| `BeforeDeleteEvent` | `AfterDeleteEvent` | Xóa entity khỏi repository |

Các event này được phát bởi Spring Data REST REST exporter. Có thể nhận chúng bằng `ApplicationListener`, `AbstractRepositoryEventListener` hoặc annotated handler với `@RepositoryEventHandler`.

Từ “Before” và “After” mô tả thứ tự tương đối với thao tác repository mà exporter thực hiện. Chúng không tương đương với các phase `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` của Spring transaction synchronization.

## 2. Thứ tự thực thi trong REST exporter

Ví dụ với một request cập nhật item:

~~~http
PUT /api/orders/42
Content-Type: application/json
~~~

Trong source hiện tại của `RepositoryEntityController`, luồng cập nhật được triển khai theo thứ tự khái quát:

~~~java
publishEvent(new BeforeSaveEvent(domainObject));

Object saved = invoker.invokeSave(domainObject);

publishEvent(new AfterSaveEvent(saved));
~~~

Luồng xóa item tương tự:

~~~java
publishEvent(new BeforeDeleteEvent(entity));

invoker.invokeDeleteById(id);

publishEvent(new AfterDeleteEvent(entity));
~~~

Có thể hình dung:

~~~text
REST request
    |
    v
Before* event
    |
    v
RepositoryInvoker gọi save/delete
    |
    v
Repository method trả về
    |
    v
After* event
    |
    v
Exporter hoàn tất response
~~~

Điểm quan trọng là exporter phát After* sau khi lời gọi repository trả về. Exporter không đổi tên event thành transaction callback và cũng không tự bảo đảm rằng mọi transaction bao quanh lời gọi đó đã kết thúc.

Với Spring Data JPA, các method CRUD của `SimpleJpaRepository` thường có `@Transactional`. Nếu không có transaction bao ngoài, lời gọi repository có thể tự mở và hoàn tất transaction trước khi trả về cho exporter. Trong trường hợp phổ biến đó, After* có thể được publish sau commit của transaction repository.

Nhưng nếu lời gọi repository tham gia một transaction đã có sẵn, repository không tự commit transaction bao ngoài. Method trả về chỉ có nghĩa phần việc của method đã xong; transaction bên ngoài vẫn có thể commit hoặc rollback sau đó. Đây là lý do After* không phải là một cam kết commit độc lập với transaction boundary thực tế.

## 3. Hai kịch bản transaction cho cùng một AfterSaveEvent

### Kịch bản A: repository tự sở hữu transaction

Giả sử request đi qua REST exporter và không có transaction bao ngoài:

~~~text
REST exporter
    |
    | invokeSave()
    v
Transaction của repository bắt đầu
    |
    | INSERT / UPDATE
    v
Repository method kết thúc
    |
    | Transaction manager commit
    v
invokeSave() trả về
    |
    | publish AfterSaveEvent
    v
Listener chạy
~~~

Trong kịch bản này, transaction của repository thường đã commit khi exporter publish AfterSaveEvent. Nếu listener ghi log hoặc gửi notification, thao tác đó diễn ra sau transaction repository.

Tuy nhiên, đó là hệ quả của transaction boundary đang dùng, không phải bảo đảm được suy ra từ tên AfterSaveEvent. Một repository implementation hoặc cấu hình transaction khác có thể có boundary khác.

### Kịch bản B: có transaction bao ngoài

Giả sử một transaction bao quanh request hoặc lời gọi repository:

~~~text
Transaction bên ngoài bắt đầu
    |
    v
REST exporter
    |
    | BeforeSaveEvent
    v
Repository save tham gia transaction bên ngoài
    |
    | SQL chạy trong transaction đang mở
    v
Repository method trả về
    |
    | AfterSaveEvent được publish
    v
Listener chạy
    |
    v
Transaction bên ngoài tiếp tục
    |
    +---- COMMIT
    |
    +---- ROLLBACK
~~~

Ở đây AfterSaveEvent được phát trước khi transaction bên ngoài kết thúc. Listener có thể đã chạy, nhưng dữ liệu vẫn có thể bị rollback sau đó.

Ví dụ, một request được thực hiện trong transaction của test hoặc một transaction interceptor bao ngoài. Repository tham gia transaction hiện tại; event After* được publish khi transaction đó còn mở. Nếu transaction bị đánh dấu rollback-only, database sẽ không giữ thay đổi mặc dù listener đã nhận event.

Vì vậy, câu hỏi cần đặt ra không phải chỉ là “event tên gì?”, mà là “ai đang sở hữu transaction và transaction đó kết thúc ở đâu?”.

## 4. Sự kiện Spring mặc định chạy đồng bộ

Spring Data REST events là các Spring application events tùy biến. Mặc định, Spring application event listener chạy đồng bộ: publisher gọi `publishEvent(...)`, listener được gọi trong cùng luồng xử lý trước khi lời gọi publish kết thúc.

Điều này có nghĩa:

- Khi Before* được publish, handler mặc định chạy trước khi exporter gọi repository operation.
- Khi After* được publish, handler mặc định chạy sau khi repository invocation trả về.
- Exception không được xử lý trong synchronous listener có thể truyền ngược về publisher.
- Listener đồng bộ không tự tạo transaction mới và cũng không tự chờ transaction commit.
- Nếu event được chuyển qua thread khác hoặc boundary bất đồng bộ, thứ tự và transaction context cần được xem xét riêng.

Synchronous chỉ mô tả cách listener được gọi; nó không nói transaction đang ở phase nào.

## 5. Vì sao listener After* có thể chạy nhưng dữ liệu vẫn rollback?

Giả sử một handler ghi nhận event vào bộ nhớ hoặc gửi message ngay khi nhận AfterSaveEvent:

~~~java
@Component
@RepositoryEventHandler(Order.class)
public class OrderEventHandler {

    private final NotificationService notificationService;

    public OrderEventHandler(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @HandleAfterSave
    public void afterSave(Order order) {
        notificationService.notifyUpdated(order.getId());
    }
}
~~~

Nếu AfterSaveEvent được phát khi transaction bao ngoài còn mở, notification có thể gửi thành công trước khi transaction kết thúc. Sau đó transaction rollback do một lỗi ở bước khác.

Kết quả:

- Người nhận đã nhận notification “Order đã cập nhật”.
- Database không lưu thay đổi Order.
- Hệ thống ngoài và database không còn đồng nhất.

Tình huống tương tự xảy ra khi handler gửi email, gọi webhook, publish message lên broker hoặc xóa cache ngay trong After*.

Nếu After* được publish sau khi repository-owned transaction đã commit, rollback của transaction đó không còn xảy ra nữa. Nhưng handler vẫn có thể thất bại sau commit, hoặc một transaction bao ngoài khác vẫn chưa hoàn tất. Do đó không nên dùng After* như một cơ chế bảo đảm thứ tự giữa database và hệ thống ngoài.

## 6. Dùng @TransactionalEventListener khi cần transaction phase

Spring Framework cung cấp `@TransactionalEventListener` để gắn listener với vòng đời transaction. Phase mặc định là `AFTER_COMMIT`.

Các phase:

| Phase | Thời điểm listener chạy | Use case |
| --- | --- | --- |
| `BEFORE_COMMIT` | Ngay trước khi transaction commit | Kiểm tra hoặc chuẩn bị dữ liệu trong transaction hiện tại |
| `AFTER_COMMIT` | Chỉ sau khi commit thành công | Gửi notification, cập nhật cache/index sau khi dữ liệu đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Xử lý bù hoặc cảnh báo khi thao tác thất bại |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Dọn dẹp tài nguyên hoặc công việc cần biết transaction đã hoàn tất |

Ví dụ:

~~~java
@Component
public class OrderCommittedListener {

    private final NotificationService notificationService;

    public OrderCommittedListener(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChangedEvent event) {
        notificationService.notifyUpdated(event.orderId());
    }
}
~~~

Listener trên chỉ chạy sau commit thành công của transaction chứa thời điểm event được publish.

**Điều kiện quan trọng:** event phải được publish trong khi transaction đang hoạt động để Spring đăng ký listener vào transaction đó. Nếu không có transaction, `@TransactionalEventListener` mặc định không chạy listener. Có thể bật `fallbackExecution = true`, nhưng khi không có transaction, listener sẽ chạy theo fallback thay vì đợi một commit không tồn tại.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderChangedEvent event) {
    // Nếu không có transaction, method vẫn được gọi theo fallback.
}
~~~

Không dùng fallbackExecution như cách tạo bảo đảm commit. Khi không có transaction, không có commit phase để chờ.

## 7. Một giới hạn quan trọng khi nghe trực tiếp Spring Data REST After* event

Có thể viết:

~~~java
@Component
public class RepositoryAfterSaveListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onAfterSave(AfterSaveEvent event) {
        // Xử lý sau commit nếu event được publish trong transaction.
    }
}
~~~

Nhưng không được giả định listener này luôn chạy khi Spring Data REST phát AfterSaveEvent.

Nếu repository invocation đã tự hoàn tất transaction trước khi exporter publish AfterSaveEvent, tại thời điểm publish có thể không còn transaction đang hoạt động. Trong trường hợp đó, transactional listener mặc định không được đăng ký và sẽ không chạy.

Nếu có transaction bao ngoài, event được publish trong transaction đó và listener có thể được đăng ký để chạy sau commit. Vì vậy cần kiểm tra transaction boundary thực tế của request và repository, thay vì chỉ đổi annotation trên handler.

Khi nghiệp vụ bắt buộc phải có một sự kiện gắn với commit, cách rõ ràng hơn là publish domain event từ bên trong service method có transaction được kiểm soát:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void updateOrder(Order order) {
        Order saved = repository.save(order);

        publisher.publishEvent(
                new OrderChangedEvent(saved.getId()));
    }
}
~~~

Event được publish khi transaction của service còn hoạt động. Listener `@TransactionalEventListener(AFTER_COMMIT)` có thể đăng ký vào transaction đó và chỉ chạy sau khi commit thành công.

Nếu cần giữ API Spring Data REST mặc định, hãy xác định liệu có transaction bao ngoài request hay không. Nếu không có và yêu cầu nghiệp vụ cần event gắn chặt với transaction, cân nhắc custom controller/service endpoint để transaction và thời điểm publish event được kiểm soát rõ ràng.

## 8. Ghi dữ liệu trong listener AFTER_COMMIT cần transaction mới

Spring Framework lưu ý rằng ở các phase `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`, transaction gốc đã hoàn tất, nhưng một số transactional resource có thể vẫn còn được bind và truy cập trong quá trình callback.

Vì vậy, nếu listener sau commit gọi repository để ghi thêm dữ liệu, thao tác đó có thể tham gia resource của transaction cũ nhưng không có commit tiếp theo. Kết quả là lệnh ghi mới không được commit như mong muốn.

Nếu listener cần ghi database sau commit, hãy mở transaction mới, thường bằng một service bean riêng:

~~~java
@Service
public class OrderAuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(Long orderId) {
        // Persist audit record trong transaction mới.
    }
}
~~~

~~~java
@Component
public class OrderCommittedListener {

    private final OrderAuditWriter auditWriter;

    public OrderCommittedListener(OrderAuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChangedEvent event) {
        auditWriter.writeAudit(event.orderId());
    }
}
~~~

Đặt method transaction mới trên một Spring bean khác giúp lời gọi đi qua transaction proxy. Tránh tự gọi method `REQUIRES_NEW` trong cùng object vì self-invocation thường bỏ qua proxy và không tạo transaction mới.

## 9. Khi nào cần transactional outbox?

`@TransactionalEventListener(AFTER_COMMIT)` bảo đảm listener chỉ được gọi sau commit, nhưng nó không tạo ra một message broker transaction nguyên tử với database. Ví dụ process có thể crash sau khi database commit nhưng trước khi gửi message.

Nếu cần độ tin cậy cao cho tích hợp hệ thống:

1. Trong transaction nghiệp vụ, lưu thay đổi Order và một bản ghi Outbox.
2. Commit cả hai trong cùng database transaction.
3. Một worker đọc các bản ghi Outbox đã commit.
4. Worker gửi message tới broker hoặc webhook.
5. Worker đánh dấu đã gửi hoặc retry theo chính sách.
6. Consumer xử lý idempotent vì message có thể được gửi lại.

Minh họa:

~~~text
Một database transaction
   |
   +-- UPDATE orders
   |
   +-- INSERT outbox_events
   |
   v
COMMIT
   |
   v
Outbox relay
   |
   v
Message broker / webhook
~~~

Nếu request Spring Data REST không có transaction bao ngoài và After* chỉ được publish sau transaction repository đã hoàn tất, không thể giả định handler After* có thể ghi Outbox nguyên tử với thay đổi Order ban đầu. Hãy đưa thao tác ghi entity và outbox vào cùng một service transaction hoặc một custom endpoint có transaction boundary rõ ràng.

Outbox đặc biệt hữu ích với thanh toán, đơn hàng, tồn kho, thông báo và các quy trình mà việc mất message sau commit gây sai lệch nghiệp vụ.

## 10. Phân biệt @EventListener, @Async và @TransactionalEventListener

| Cơ chế | Khi nào chạy | Chờ commit? | Transaction context |
| --- | --- | --- | --- |
| `@EventListener` | Khi event được publish; mặc định đồng bộ | Không | Chạy trong luồng publish nếu đồng bộ |
| `@Async @EventListener` | Trên executor/thread khác | Không | Không kế thừa thread-bound transaction của publisher |
| `@TransactionalEventListener` | Theo phase đã chọn; mặc định AFTER_COMMIT | Có, nếu event được publish trong transaction | Gắn với transaction đã publish event |
| `@TransactionalEventListener(fallbackExecution = true)` | Theo phase khi có transaction; chạy fallback nếu không có | Không có commit để chờ trong trường hợp fallback | Không có transaction gốc trong trường hợp fallback |

Không thêm `@Async` chỉ để tránh làm chậm request nếu listener cần transaction context. Với listener cần chạy sau commit, dùng transaction-bound event trước; nếu cần xử lý nền, có thể để listener sau commit đẩy công việc vào queue/executor hoặc outbox relay.

Từ Spring Framework 6.1, transactional event listener còn hỗ trợ reactive transaction. Reactive transaction lưu context trong Reactor context thay vì thread-local; event cần mang transaction context phù hợp. Không áp dụng giả định thread-bound imperative cho reactive flow.

## 11. Kiểm thử để chứng minh After* chưa chắc đã commit

Test cần tạo được transaction bao ngoài thao tác REST exporter. Với MockMvc chạy đồng bộ trong cùng thread test, có thể dùng test transaction để quan sát event trước khi kết thúc transaction.

Ví dụ minh họa:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryEventTransactionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository repository;

    @Autowired
    AfterSaveProbe afterSaveProbe;

    @Test
    @Transactional
    void afterSaveEventCanRunBeforeOuterTransactionCompletes()
            throws Exception {

        Order order = repository.save(new Order("PO-42"));

        mockMvc.perform(put("/api/orders/{id}", order.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "orderNumber": "PO-42-UPDATED"
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        assertThat(afterSaveProbe.wasCalled()).isTrue();

        // Transaction test vẫn đang mở tại đây.
        // Nếu test đánh dấu rollback, thay đổi trong request tham gia
        // transaction này cũng có thể bị rollback.
        TestTransaction.flagForRollback();
        TestTransaction.end();

        Order persisted = repository.findById(order.getId()).orElseThrow();
        assertThat(persisted.getOrderNumber()).isEqualTo("PO-42");
    }
}
~~~

Ví dụ giả định MockMvc thực thi request trong cùng thread và repository tham gia transaction test đang mở. Nếu request chạy qua server thật, thread khác hoặc transaction manager khác, test boundary sẽ khác; phải thiết kế integration test phù hợp với kiến trúc thực tế.

Có thể kiểm tra transactional listener chỉ chạy sau commit:

~~~java
@Test
@Transactional
void transactionalListenerWaitsForCommit() throws Exception {
    mockMvc.perform(put("/api/orders/{id}", 42)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                { "orderNumber": "PO-42-UPDATED" }
                """))
        .andExpect(status().is2xxSuccessful());

    assertThat(afterCommitProbe.wasCalled()).isFalse();

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertThat(afterCommitProbe.wasCalled()).isTrue();
}
~~~

Ngoài ra, kiểm thử riêng các trường hợp:

- Không có transaction bao ngoài: xác định repository transaction kết thúc ở thời điểm nào.
- Có transaction bao ngoài rồi commit: After* có thể chạy trước commit, transactional listener chạy sau commit.
- Có transaction bao ngoài rồi rollback: synchronous After* handler có thể đã chạy, nhưng AFTER_COMMIT listener không chạy.
- Không có transaction: transactional listener mặc định không chạy.
- Có `fallbackExecution = true`: listener được gọi dù không có transaction, nhưng không có commit guarantee.
- Listener sau commit cần ghi database: xác nhận transaction `REQUIRES_NEW` thực sự commit.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| AfterSaveEvent đã chạy nhưng dữ liệu bị rollback | Event được publish trong transaction bao ngoài còn mở | Dùng transaction-bound listener nếu cần xử lý sau commit |
| Notification gửi rồi nhưng entity không được lưu | Side effect chạy trong synchronous After* trước khi transaction ngoài kết thúc | Đưa notification sang AFTER_COMMIT hoặc outbox |
| @TransactionalEventListener không chạy | Event được publish khi không có transaction | Publish event trong service transaction hoặc xác định rõ fallbackExecution |
| fallbackExecution=true nhưng listener chạy ngay | Không có transaction để đăng ký phase | Không coi fallback là AFTER_COMMIT |
| Listener AFTER_COMMIT ghi DB nhưng không thấy dữ liệu | Resource transaction cũ còn bind nhưng không có commit tiếp theo | Gọi service mở transaction REQUIRES_NEW |
| Handler chạy trên thread khác và không thấy transaction | Listener bất đồng bộ không kế thừa thread-bound context | Tách công việc async khỏi phần cần transaction |
| After* exception không rollback thay đổi đã commit | Repository-owned transaction có thể đã hoàn tất trước khi event được publish | Không dùng exception After* làm cơ chế rollback |
| Test chứng minh event chạy nhưng không chứng minh commit | Chỉ assert listener được gọi, không kiểm tra transaction outcome | Kiểm thử cả commit và rollback bằng transaction test |

## 13. Quy tắc chọn cơ chế

| Mục tiêu | Cơ chế |
| --- | --- |
| Chuẩn hóa hoặc kiểm tra entity trước khi exporter lưu | Before* event |
| Thực hiện logic sau khi repository invocation trả về | After* event |
| Chỉ chạy khi transaction commit thành công | `@TransactionalEventListener(AFTER_COMMIT)` với event được publish trong transaction |
| Phản ứng khi transaction rollback | `@TransactionalEventListener(AFTER_ROLLBACK)` |
| Chạy logic trước khi commit | `@TransactionalEventListener(BEFORE_COMMIT)` |
| Gửi message bền vững sau thay đổi database | Transactional outbox |
| Áp dụng cùng quy tắc cho REST, job và service | Service/domain layer dùng chung |

Hãy xác định transaction boundary trước khi chọn listener. Tên After* cho biết repository/exporter đã đi qua bước nào; chỉ transaction manager mới xác định được transaction đã commit hay rollback.

## Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Events](https://docs.spring.io/spring-data/rest/reference/events.html): danh sách tám event, annotated handler, ApplicationListener và mặc định Spring events chạy đồng bộ.
- [Spring Data REST — RepositoryEntityController source](https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryEntityController.java): source thể hiện exporter publish Before*, gọi RepositoryInvoker, rồi publish After*.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, các transaction phase, fallbackExecution và reactive transaction.
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): mặc định AFTER_COMMIT, hành vi khi không có transaction và lưu ý truy cập transactional resources sau completion.
- [Spring Framework API — TransactionPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html): định nghĩa BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.
- [Spring Data JPA — SimpleJpaRepository source](https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java): ví dụ các CRUD methods được đánh dấu transactional.
