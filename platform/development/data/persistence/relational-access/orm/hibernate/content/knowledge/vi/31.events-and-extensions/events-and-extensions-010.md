# Phân biệt sự kiện nội bộ ORM với sự kiện nghiệp vụ cần công bố sau commit

Trong Hibernate, từ **sự kiện** có thể chỉ những thứ rất khác nhau: một hàng vừa được `INSERT` trong lúc `flush`, một entity được nạp vào persistence context, một đơn hàng chuyển sang trạng thái **Đã thanh toán**, hoặc một thông điệp cần gửi sang hệ thống vận chuyển. Nếu gộp tất cả thành “event” và gửi message ngay trong một JPA callback, ứng dụng có thể gửi thông báo cho **một transaction sau đó bị rollback**, mất sự kiện khi process crash, hoặc tạo thông điệp trùng lặp khi retry.

Cần phân biệt ba lớp:

1. **Sự kiện nội bộ ORM (persistence/lifecycle event):** Phản ánh hoạt động kỹ thuật của Hibernate với entity và SQL như `@PrePersist`, `@PostUpdate`, `PreInsertEvent`, `PostInsertEvent`. Chúng gắn với *persistence lifecycle*, **không có nghĩa transaction đã commit**.
2. **Sự kiện nghiệp vụ (domain event):** Phản ánh một sự thật trong ngôn ngữ nghiệp vụ, ví dụ `OrderPaid`, `SubscriptionCancelled`, `InventoryReserved`. Sự kiện được tạo khi quy tắc nghiệp vụ được thực thi; không phụ thuộc việc Hibernate chạy một `INSERT` hay `UPDATE` cụ thể.
3. **Công bố sự kiện sau commit (post-commit notification/integration event):** Chỉ cho các hệ thống bên ngoài quan sát thay đổi khi transaction ghi dữ liệu đã commit thành công. Có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` cho thông báo *best-effort trong cùng process* hoặc **transactional outbox** khi cần truyền đáng tin cậy qua broker/webhook.

Ví dụ ngắn:

~~~java
@Transactional
public void payOrder(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();

    order.markPaid();  // Nghiệp vụ: đơn chuyển trạng thái PAID.

    publisher.publishEvent(new OrderPaid(
        order.getId(),
        order.getCustomerId(),
        Instant.now()
    ));
}
~~~

Lời gọi `publishEvent()` trên **Spring ApplicationEventPublisher** có thể diễn ra khi transaction còn mở. Nếu listener là `@EventListener`, nó có thể chạy *ngay*. Nếu listener dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`, Spring sẽ đăng ký xử lý sau khi transaction commit. Nhưng **ngay cả AFTER_COMMIT cũng chưa phải hệ thống gửi message bền vững**, vì process có thể chết sau commit nhưng trước khi listener hoàn tất.

> **Phạm vi:** Ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Framework 6.x và Spring Data JPA. Những API `org.hibernate.event.spi.*` là Hibernate-specific; các callback `jakarta.persistence.*` thuộc JPA. Đoạn code làm ví dụ nghiệp vụ tự chứa, tên package/import và cấu hình broker có thể được điều chỉnh theo ứng dụng. Hành vi retry, transaction synchronization, event multicaster và provider versions cần được kiểm chứng trên stack thực tế.

## 1. Mục tiêu của bài

Sau bài này, bạn có thể:

- Giải thích vì sao `@PostPersist`/`@PostUpdate` **không tương đương** “database đã commit”.
- Phân biệt Hibernate event listeners, JPA lifecycle callbacks, Spring application events và domain/integration events.
- Chọn đúng nơi tạo domain event và đúng thời điểm gây side effect bên ngoài.
- Hiểu Spring `@EventListener`, `@TransactionalEventListener` và các phase `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`.
- Giải thích giới hạn của listener chạy sau commit, bao gồm mất sự kiện khi crash và lỗi phát sinh sau khi dữ liệu đã commit.
- Thiết kế transactional outbox để ghi dữ liệu nghiệp vụ và sự kiện trong cùng transaction.
- Xử lý retries, duplicate deliveries, ordering, idempotency, metrics và integration tests.

## 2. Đặt sự kiện vào đúng trục thời gian

Giả sử một transaction thanh toán đơn hàng:

~~~text
BEGIN TRANSACTION
    |
    | Load Order
    | Kiểm tra điều kiện thanh toán
    | Thay đổi Order.status = PAID
    | Tạo domain event OrderPaid
    |
    | Hibernate flush
    |   -> SQL UPDATE orders ...
    |   -> ORM PreUpdate/PostUpdate events
    |
COMMIT
    |
    | Database commit thành công
    |
    | Post-commit listener / outbox dispatcher
    |   -> Email, Kafka, webhook, search indexing ...
~~~

**Mốc quyết định là COMMIT**, không phải thời điểm field Java đổi, không phải lúc `save()`, không phải lúc SQL `UPDATE` đã được gửi, và cũng không phải lúc `flush()` xong.

Transaction có thể rollback ở bất cứ thời điểm nào trước khi commit thành công: kiểm tra ràng buộc thất bại, optimistic lock conflict, deadlock, exception của service, timeout hoặc business rule thất bại.

## 3. Một nghiệp vụ, nhiều thay đổi persistence

Một hành động `OrderPaid` có thể gây ra:

- `UPDATE orders SET status='PAID'`.
- `INSERT payments`.
- `INSERT accounting_entries`.
- `UPDATE coupons`.
- `INSERT outbox_messages`.

Đây là **nhiều thay đổi dữ liệu** nhưng có thể chỉ là **một sự kiện nghiệp vụ**: “Đơn hàng X đã được xác nhận thanh toán”.

Ngược lại, một JPA `@PostUpdate` có thể xảy ra khi:

- Nhân viên sửa ghi chú đơn hàng.
- Job sửa `updated_at`.
- Đồng bộ dữ liệu thay đổi một field kỹ thuật.
- Nghiệp vụ thực sự chuyển sang `PAID`.

Do đó, **không suy luận một domain event chỉ từ việc có ORM UPDATE** mà không biết transition và business invariant nào đã xảy ra.

## 4. Ba loại sự kiện qua bảng so sánh

| Đặc điểm | ORM lifecycle event | Domain event | Integration event sau commit |
|---|---|---|---|
| Ví dụ | `PostUpdateEvent`, `@PostPersist` | `OrderPaid`, `StockReserved` | `OrderPaidV1` gửi broker |
| Ngôn ngữ | Entity/SQL/mapping | Ngôn ngữ nghiệp vụ | Hợp đồng giữa systems |
| Tạo khi nào | Theo ORM lifecycle/flush | Khi aggregate thực hiện transition | Sau hoặc cùng lúc tạo bản ghi outbox trong transaction |
| Có nghĩa commit thành công? | **Không** | Chưa chắc, nếu được tạo trong transaction đang mở | Chỉ nên công bố ra ngoài sau dữ liệu commit |
| Có thể bị gọi do thay đổi kỹ thuật? | Có | Không nên | Theo domain event đã được chọn |
| Phạm vi | Persistence provider | Domain/application | Giữa services/processes |
| Độ bền mặc định | Không | Tùy nơi lưu | Phụ thuộc transport/outbox |
| Retry/idempotency mặc định | Không đảm bảo | Không đảm bảo | Phải thiết kế rõ |
| Coupling | Mapping và Hibernate SPI | Aggregate/business language | Event schema và consumer contract |

**Domain event là điều đã xảy ra trong nghiệp vụ**; **integration event là cách truyền một sự thật đã commit tới bên ngoài**. Nhiều hệ thống dùng tên tương tự cho hai loại, nhưng ranh giới transaction và trách nhiệm delivery vẫn khác.

## 5. JPA lifecycle callbacks là gì?

JPA hỗ trợ các callbacks như:

- `@PrePersist`, `@PostPersist`.
- `@PreUpdate`, `@PostUpdate`.
- `@PreRemove`, `@PostRemove`.
- `@PostLoad`.

Ví dụ:

~~~java
@Entity
@Table(name = "orders")
@EntityListeners(OrderAuditListener.class)
public class Order {

    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    // Các thuộc tính, constructor, accessors...
}
~~~

Listener:

~~~java
public class OrderAuditListener {

    @PreUpdate
    public void beforeUpdate(Order order) {
        // Tác vụ nhẹ, đồng bộ với lifecycle persistence.
        // Không gửi HTTP/Kafka ở đây.
    }

    @PostUpdate
    public void afterUpdate(Order order) {
        // SQL UPDATE có thể vừa được thực thi,
        // nhưng transaction chưa chắc đã COMMIT.
    }
}
~~~

`@EntityListeners` là cơ chế chuẩn JPA, trong khi các hook cụ thể của Hibernate SPI thuộc phạm vi vendor-specific.

### Các callback nên làm gì?

Chúng thường phù hợp hơn với các thao tác kỹ thuật **nhẹ, cục bộ, có thể lặp lại được**, ví dụ điền metadata trên entity khi mapping cho phép.

Không nên dùng JPA callback làm điểm gọi service bên ngoài hoặc thực thi query/EntityManager operations tùy ý: lifecycle callback có các hạn chế về persistence operations, phụ thuộc provider và thời điểm flush.

## 6. @PrePersist khác @PostPersist ra sao?

~~~java
@PrePersist
void beforeInsert() {
    createdAt = Instant.now();
}
~~~

`@PrePersist` được kích hoạt trong lifecycle persist/insert phù hợp; thường được dùng để chuẩn bị metadata trước khi dữ liệu được ghi.

~~~java
@PostPersist
void afterInsert() {
    // Đã qua giai đoạn insert theo lifecycle callback.
}
~~~

`@PostPersist` có thể chạy **sau INSERT execution** nhưng **trước transaction commit**. Thời điểm INSERT phụ thuộc identifier generation và flush schedule:

- `IDENTITY` có thể khiến INSERT diễn ra sớm để lấy generated ID.
- `SEQUENCE` có thể cấp ID trước và trì hoãn INSERT đến flush.
- Thời điểm callback theo JPA provider không nhất thiết trùng thời điểm code gọi `save()`.

Không dùng `@PostPersist` làm dấu mốc “dữ liệu chắc chắn durable và người khác có thể đọc được”.

## 7. @PreUpdate và @PostUpdate không phải post-commit

~~~java
@PostUpdate
void afterUpdate() {
    notificationGateway.send(...); // Chống chỉ định cho side effect bên ngoài.
}
~~~

Giả sử:

~~~text
Transaction A:
  UPDATE orders.status = PAID
  @PostUpdate gửi email "Đã thanh toán"
  Sau đó INSERT accounting_entry thất bại
  ROLLBACK

Kết quả:
  Email đã gửi
  Đơn hàng không được commit là PAID
```

Đây là **external side effect trước commit**: transaction database có thể rollback, nhưng email/webhook/Kafka message thường không rollback cùng.

`@PostUpdate` thích hợp cho persistence-related interception, không phải mặc định điểm công bố sự kiện nghiệp vụ đáng tin cậy.

## 8. @PostLoad có nghĩa gì?

`@PostLoad` xảy ra khi provider hoàn tất load entity theo lifecycle, không có nghĩa business event “Đơn hàng được xem” đã xảy ra.

Một entity có thể được load vì:

- REST endpoint đọc.
- Batch job kiểm tra dữ liệu.
- Lazy association initialization.
- Cache miss.
- Dirty-check preconditions.
- Service khác trong transaction.

Nếu dùng `@PostLoad` để tạo notification hoặc gửi Kafka, số lượng thông điệp có thể tăng ngoài ý muốn và không phản ánh domain action.

**Đọc dữ liệu là sự kiện persistence; không tự đồng nghĩa một business command thành công.**

## 9. Hibernate event SPI chi tiết hơn JPA callbacks

Hibernate còn có hệ thống listener nội bộ, ví dụ:

- `PreInsertEventListener` và `PostInsertEventListener`.
- `PreUpdateEventListener` và `PostUpdateEventListener`.
- `PreDeleteEventListener` và `PostDeleteEventListener`.
- `PostLoadEventListener`.
- Các event listeners cho flush, dirty check, collections và operations khác.

Ví dụ listener kỹ thuật:

~~~java
import org.hibernate.event.spi.PreInsertEvent;
import org.hibernate.event.spi.PreInsertEventListener;

public final class ProductPreInsertListener
        implements PreInsertEventListener {

    @Override
    public boolean onPreInsert(PreInsertEvent event) {
        // Có thể kiểm tra metadata/entity state.
        // return true trong API này có thể veto INSERT.
        return false;
    }
}
~~~

Listener SPI được đăng ký thông qua Hibernate event listener registry/Integrator tùy bootstrap. Nó hữu ích cho extension sâu, nhưng coupling với Hibernate version/mapping cao hơn JPA callbacks.

**Dù tên là PostInsertEvent, event đó không tự chứng minh commit.**

## 10. Không nhầm Hibernate post-commit listener với durable event bus

Hibernate có một số SPI listener hỗ trợ xử lý post-commit, ví dụ các interface thuộc nhóm `PostCommit...EventListener` trong những phiên bản hỗ trợ. Cơ chế này có thể callback khi transaction hoàn tất thay vì tại thời điểm SQL operation.

Tuy vậy:

- Đây là **Hibernate-specific**, không phải domain event contract portable.
- Phụ thuộc session/transaction/event integration.
- Không tự lưu một message bền vững.
- Process crash sau commit vẫn có thể làm callback chưa chạy.
- External broker có thể unavailable.
- Không tự cung cấp idempotency, ordering, retry và observability.

Do đó, **Hibernate post-commit event hook không thay thế transactional outbox** khi dữ liệu nghiệp vụ và integration event phải đồng bộ đáng tin cậy.

## 11. Bulk HQL/SQL có thể bỏ qua entity callbacks

Một điểm quan trọng khi dùng lifecycle callbacks cho nghiệp vụ:

~~~java
entityManager.createQuery(
    """
    update Order o
    set o.status = :newStatus
    where o.id in :ids
    """
)
.setParameter("newStatus", OrderStatus.PAID)
.setParameter("ids", ids)
.executeUpdate();
~~~

Đây là **bulk DML**, không phải lặp `order.markPaid()` trên từng managed entity. Bulk HQL/JPQL/SQL không phát các JPA entity lifecycle callbacks theo từng entity như đường ORM entity update thông thường.

Các đường ghi khác cũng có thể không kích hoạt callback như mong đợi:

- Native SQL/JDBC trực tiếp.
- Database triggers.
- Một số StatelessSession operations theo Hibernate lifecycle semantics.
- External ETL process.

Vì vậy **không dùng ORM callback là nguồn duy nhất cho một sự kiện nghiệp vụ quan trọng**. Domain event cần được tạo ở application/domain command path hoặc được suy ra từ một nguồn thay đổi có transaction contract rõ.

## 12. Domain event là ngôn ngữ nghiệp vụ

Một domain event nên nói **điều gì vừa xảy ra**, không nói **Hibernate đã làm gì**.

Tên có ý nghĩa:

- `OrderPaid`.
- `InvoiceIssued`.
- `InventoryReserved`.
- `CustomerEmailChanged`.
- `ShipmentHandedToCarrier`.

Tên quá kỹ thuật:

- `OrderRowUpdated`.
- `HibernatePostFlush`.
- `EntityDirty`.
- `TableRecordInserted`.

Ví dụ:

~~~java
public record OrderPaid(
    UUID orderId,
    UUID customerId,
    long orderVersion,
    Instant occurredAt
) {}
~~~

Các trường không chỉ phục vụ log; chúng giúp consumer nhận biết aggregate nào thay đổi, lúc nào theo domain và sự kiện tương ứng version nào.

**Không dùng entity JPA managed làm event payload** nếu không thật sự cần: nó có thể mang LAZY proxies, object graph lớn, circular references và dữ liệu nhạy cảm không nằm trong hợp đồng sự kiện.

## 13. Aggregate tạo domain event khi transition hợp lệ

Ví dụ aggregate:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    private UUID customerId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;

    protected Order() {}

    public UUID getId() { return id; }
    public UUID getCustomerId() { return customerId; }
    public long getVersion() { return version; }

    public void markPaid() {
        if (status == OrderStatus.PAID) {
            throw new IllegalStateException("Order already paid");
        }
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new IllegalStateException(
                "Only pending orders can become paid"
            );
        }

        status = OrderStatus.PAID;
    }
}
~~~

Trong mô hình này, `markPaid()` biểu diễn business transition. Service quyết định tạo `OrderPaid` **khi domain method hoàn tất**, chứ không đợi xem Hibernate phát UPDATE hay không.

Nếu version của aggregate dùng `@Version`, giá trị sau flush có thể khác giá trị đọc ngay sau khi mutate. Khi xây event payload theo business version, nên quyết định rõ lúc nào lấy version, hoặc dùng business event sequence riêng; không tự cho rằng `getVersion()` trước flush đã là version mới.

## 14. Domain event được tạo trong transaction không có nghĩa đã commit

~~~java
@Transactional
public void markPaid(UUID id) {
    Order order = orders.findById(id).orElseThrow();
    order.markPaid();

    OrderPaid event = new OrderPaid(
        order.getId(),
        order.getCustomerId(),
        order.getVersion(),
        Instant.now()
    );

    publisher.publishEvent(event);
}
~~~

Tại dòng `publishEvent(event)`, transaction thường **chưa commit**. `publishEvent()` là thao tác công bố vào **Spring application event mechanism**, không tự gửi message qua external broker và không tự đợi DB commit.

Nếu method sau đó throw exception, Spring transaction có thể rollback theo rollback rules nhưng event đã được phát vào application event infrastructure.

Vì vậy **loại listener** và **transaction boundary** quyết định tác động bên ngoài.

## 15. @EventListener mặc định không đợi commit

~~~java
@Component
public class OrderNotificationListener {

    @EventListener
    public void handle(OrderPaid event) {
        emailClient.sendReceipt(event.orderId());
    }
}
~~~

Với event multicaster mặc định đồng bộ, `@EventListener` thường được gọi **ngay trong luồng `publishEvent()`**. Nếu transaction còn mở, email có thể gửi trước commit.

Spring có thể được cấu hình asynchronous event multicasting, và `@Async` thay đổi thời gian thực thi, nhưng **async không đồng nghĩa after-commit**: nó chỉ thay đổi thread/scheduling và còn tăng rủi ro transaction context bị mất.

Không dùng `@EventListener` thông thường để công bố irreversible external action mà nghiệp vụ yêu cầu database transaction phải commit thành công trước.

## 16. @TransactionalEventListener gắn xử lý với transaction phase

Spring có:

~~~java
@Component
public class OrderPaidListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPaid(OrderPaid event) {
        emailClient.sendReceipt(event.orderId());
    }
}
~~~

Listener này được gọi khi transaction tương ứng **đã commit**, nếu event được published trong một transaction được Spring transaction synchronization quản lý.

Lợi ích:

- Không gửi email trong trường hợp business transaction rollback.
- Đơn giản cho side effect in-process, không yêu cầu broker.
- Dễ tách business state change và notification action.

Nhưng đây vẫn là **best-effort**: listener nằm trong process ứng dụng, không có durable queue mặc định.

## 17. Các phase của @TransactionalEventListener

| Phase | Thời điểm | Điểm cần lưu ý |
|---|---|---|
| `BEFORE_COMMIT` | Trước commit | Vẫn có thể rollback; không dùng cho side effect không thể hoàn tác. |
| `AFTER_COMMIT` | Sau commit thành công | Phù hợp thông báo best-effort; không bảo đảm delivery khi crash. |
| `AFTER_ROLLBACK` | Sau rollback | Hữu ích cho cleanup/log nghiệp vụ thất bại; không dùng để nói transaction đã commit. |
| `AFTER_COMPLETION` | Sau hoàn tất commit hoặc rollback | Phải phân biệt outcome nếu logic cần biết kết quả. |

Trong Spring hiện đại, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION` được xử lý tương ứng với transaction completion callbacks. Khi listener chạy, một số transaction resources có thể **vẫn đang bound/accessible**, nhưng transaction đã hoàn thành và không có commit tiếp theo cho những thao tác mới vô tình tham gia resource cũ.

**Không đồng nhất “listener chạy sau commit” với “mọi repository.save() trong listener sẽ được commit”.**

## 18. Ví dụ after-commit notification có giới hạn rõ

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public CheckoutService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void markPaid(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.markPaid();

        events.publishEvent(new OrderPaid(
            order.getId(),
            order.getCustomerId(),
            order.getVersion(),
            Instant.now()
        ));
    }
}
~~~

~~~java
@Component
public class ReceiptNotification {

    private final EmailClient emailClient;

    public ReceiptNotification(EmailClient emailClient) {
        this.emailClient = emailClient;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void notifyCustomer(OrderPaid event) {
        emailClient.sendReceipt(event.orderId());
    }
}
~~~

`EmailClient` là interface dịch vụ minh họa. Hành vi mong đợi:

- Transaction **commit**: listener có thể chạy và gửi email.
- Transaction **rollback**: listener `AFTER_COMMIT` không được gọi.
- Process **crash sau commit**: listener có thể không chạy; email bị thiếu.
- Email gateway **timeout sau commit**: dữ liệu đơn đã commit; listener không thể rollback đơn hàng.

Đây là lựa chọn hợp lý nếu **mất một email có thể được khôi phục bằng job khác** hoặc quy trình không đòi delivery bền vững. Nếu email/thông điệp là thành phần bắt buộc của integration, cần outbox.

## 19. Phát sự kiện ngoài transaction: mặc định có thể bị bỏ qua

Một điểm dễ bị bỏ sót:

~~~java
events.publishEvent(new OrderPaid(...));
~~~

Nếu tại thời điểm gọi không có transaction đang được Spring synchronization quản lý, `@TransactionalEventListener` **mặc định không chạy** cho event đó.

Có thể cấu hình:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderPaid event) {
    // ...
}
~~~

`fallbackExecution = true` cho phép listener chạy khi **không có transaction**, nhưng khi đó không có commit để chờ; không còn cùng một bảo đảm hậu commit như trong transaction.

Chỉ bật fallback khi không có transaction cũng là một trường hợp nghiệp vụ được chấp nhận. Không dùng nó để che giấu lỗi thiếu `@Transactional` trong service.

## 20. Vì sao @Transactional không có hiệu lực như tưởng?

Các nguyên nhân thường gặp:

- Self-invocation (`this.method()` không đi qua Spring proxy trong chế độ proxy AOP thông thường).
- Method được gọi từ object không do Spring quản lý.
- Method chạy trên thread khác.
- Transaction manager khác với manager mà repository/database dùng.
- `Propagation.SUPPORTS` khi không có transaction.
- Event được publish ngoài service boundary.
- Exception không kích hoạt rollback theo rollback rules, dẫn tới transaction vẫn commit.

Nếu một `AFTER_COMMIT` listener không được gọi, đừng vội kết luận Spring lỗi: kiểm tra **transaction thực tế**, proxy/interceptor và phase trước.

## 21. REQUIRED và REQUIRES_NEW tác động đến thời điểm commit

Với `Propagation.REQUIRED` (mặc định), method con thường tham gia transaction đã có:

~~~java
@Transactional
public void checkout(UUID id) {
    paymentService.capturePayment(id);
    // Transaction chung commit sau khi checkout() kết thúc.
}
~~~

Nếu `capturePayment()` publish event trong transaction này, `AFTER_COMMIT` listener gắn với **transaction ngoài**, không phải mốc kết thúc method con.

Với `REQUIRES_NEW`, Spring có thể mở transaction riêng và event gắn với commit của transaction mới khi đã được publish bên trong nó.

Điều này đặc biệt quan trọng nếu nghiệp vụ có nhiều aggregate transactions; không được tự giả định một event phát ra là transaction chính đã commit.

## 22. Nested/savepoint rollback là một góc cạnh cần kiểm tra

Một `PROPAGATION_NESTED` transaction dùng savepoint có thể rollback tới savepoint trong khi **outer transaction vẫn tiếp tục và commit**. Transaction synchronizations gắn với outer transaction có behavior riêng theo Spring version.

Nếu event được phát trong logic của một nested scope sau đó rollback về savepoint, không nên mặc định `AFTER_COMMIT` listener sẽ tự biết sự kiện đó cần hủy trong mọi cấu hình.

Khi sử dụng nested/savepoints:

- Kiểm thử commit/rollback của inner và outer.
- Không lấy after-commit listener đơn thuần làm bằng chứng business operation nested còn hợp lệ.
- Cân nhắc lưu domain/integration event trong **cùng transaction** với thay đổi thật bằng outbox; nếu savepoint rollback, outbox row trong scope đó cũng được rollback.
- Phân biệt `NESTED` và `REQUIRES_NEW`: một cái thường dựa trên savepoint, cái kia có transaction độc lập.

## 23. Lỗi quan trọng: Ghi DB trong AFTER_COMMIT listener

Giả sử:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void handle(OrderPaid event) {
    auditRepository.save(
        new AuditEntry("ORDER_PAID", event.orderId())
    );
}
~~~

Có một bẫy: ở phase sau commit, transaction chính đã hoàn tất. Spring transaction resources có thể vẫn accessible; thao tác data access có thể trông như “tham gia” resource cũ nhưng **không còn commit tiếp theo** để bảo đảm write này được lưu.

Nếu cần ghi DB mới **sau commit**, hãy dùng **transaction độc lập**, ví dụ một service khác có propagation `REQUIRES_NEW`:

~~~java
@Service
public class AuditWriter {

    private final AuditRepository audits;

    public AuditWriter(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void recordOrderPaid(UUID orderId) {
        audits.save(new AuditEntry("ORDER_PAID", orderId));
    }
}
~~~

~~~java
@Component
public class OrderPaidAuditListener {

    private final AuditWriter writer;

    public OrderPaidAuditListener(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void handle(OrderPaid event) {
        writer.recordOrderPaid(event.orderId());
    }
}
~~~

`AuditWriter` là bean riêng để call đi qua Spring transaction proxy. Đây vẫn là **hai commits**: order transaction trước và audit transaction sau; audit có thể thất bại, nên không dùng nếu yêu cầu audit row phải atomic với Order update. Trong trường hợp đó, ghi audit/outbox row ngay **trong transaction nghiệp vụ**.

## 24. Exception ở AFTER_COMMIT không rollback dữ liệu đã commit

Nếu listener ném exception sau commit:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void send(OrderPaid event) {
    broker.publish(event); // Có thể timeout hoặc throw.
}
~~~

Transaction database đã hoàn thành. Không có cơ chế magic “undo commit” vì callback thất bại.

Tùy implementation và call path, exception có thể được log, propagate hoặc bị xử lý khác, nhưng **không đảo ngược commit vừa thành công**. Thậm chí API caller có thể thấy lỗi trong khi DB đã commit, dẫn tới retry gây duplicate payment/event.

Giải pháp:

- Định nghĩa idempotency cho command.
- Không dùng kết quả gửi notification làm điều kiện duy nhất để trả kết quả transaction chính.
- Dùng durable outbox khi message phải được gửi lại sau lỗi.
- Có observability, retry và dead-letter policy.

## 25. @Async và AFTER_COMMIT không đồng nghĩa durable delivery

Một listener có thể được kết hợp:

~~~java
@Async
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void process(OrderPaid event) {
    externalClient.call(event);
}
~~~

Điều này có thể tách external call khỏi thread request sau khi transaction hoàn tất, nhưng:

- Scheduled async task vẫn nằm trong memory/process.
- Process crash trước khi worker thực thi có thể mất event.
- Thread pool có thể bị đầy/reject task.
- Exceptions trong async methods có thể không tới caller.
- Không có transaction context tự lan sang thread mới.
- Ordering của tasks có thể thay đổi.

**Async = cách thực thi, không phải độ bền.** Dùng queue/outbox khi cần reliability.

## 26. Spring Data @DomainEvents là cơ chế khác

Spring Data cho phép aggregate công bố domain events từ repository operations, ví dụ:

~~~java
public class OrderAggregate {

    private final List<Object> domainEvents = new ArrayList<>();

    public void markPaid() {
        // Thực thi business rule, thay state.
        domainEvents.add(new OrderPaid(...));
    }

    @DomainEvents
    Collection<Object> events() {
        return Collections.unmodifiableList(domainEvents);
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Đây là ví dụ khái niệm về annotations `org.springframework.data.domain.DomainEvents` và `AfterDomainEventPublication`. Có thể dùng `AbstractAggregateRoot` hỗ trợ register/clear domain events.

Quan trọng:

- Spring Data repository phát events khi những repository methods được interceptor hỗ trợ gọi, ví dụ `save()` hoặc `delete()` theo contracts.
- **Không mặc định mọi Hibernate dirty checking/flush sẽ gọi repository save và tự phát `@DomainEvents`.**
- Domain events có thể được publish **trước transaction commit**; listener type quyết định lúc xử lý.
- `@AfterDomainEventPublication` xóa danh sách event in-memory theo cơ chế Spring Data, **không có nghĩa event đã tới external broker**.
- Khi cần durable integration delivery, vẫn phải thiết kế outbox hoặc reliable mechanism khác.

## 27. Domain event được tạo ở đâu?

Một thiết kế dễ hiểu thường là:

~~~text
API request
   |
Application service @Transactional
   |
Aggregate.validateAndChangeState()
   |
Domain event OrderPaid được tạo
   |
Application service ghi dữ liệu + outbox
   |
Commit
   |
Dispatcher publish integration event
```

Domain event được sinh ra tại **business transition** chứ không gắn với `@PostUpdate`. Có thể:

1. Aggregate trả một domain event hoặc lưu danh sách pending events.
2. Application service tạo event sau khi domain method thành công.
3. Domain service tạo event khi nhiều aggregates phối hợp.

Chọn cơ chế phù hợp kiến trúc; tránh trùng lặp tạo event ở cả entity callback và service.

## 28. Trường hợp nào nên xử lý sự kiện trong cùng transaction?

Không phải mọi domain reaction đều phải sau commit.

Ví dụ: Khi thanh toán thành công, nghiệp vụ phải ghi `accounting_entry` **atomic** với cập nhật Order. Khi đó các thay đổi cần nằm trong **cùng DB transaction**:

~~~java
@Transactional
public void confirmPayment(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.markPaid();

    accountingEntries.save(
        AccountingEntry.forPaidOrder(order)
    );

    // Cả Order và accounting entry commit/rollback cùng nhau.
}
~~~

Có thể tổ chức bằng domain service hoặc local synchronous handler, nhưng phải minh bạch transaction boundary. Không đẩy một invariant bắt buộc sang `AFTER_COMMIT` listener rồi mong dữ liệu vẫn atomic.

Phân biệt:

- **Side effect nội bộ cần atomic:** cùng transaction.
- **Thông báo bên ngoài cần dữ liệu đã durable:** sau commit hoặc outbox.
- **Audit bắt buộc:** thường là một DB row trong cùng transaction, không phải một callback sau commit may rủi.

## 29. Nguy cơ gửi message trước commit

Một anti-pattern:

~~~java
@Transactional
public void markPaid(UUID id) {
    Order order = orders.findById(id).orElseThrow();
    order.markPaid();

    kafkaTemplate.send(
        "order-events",
        id.toString(),
        "ORDER_PAID"
    );

    accountingEntries.save(...); // Có thể throw.
}
~~~

Timeline:

~~~text
T0: BEGIN
T1: Order.status = PAID
T2: Kafka nhận ORDER_PAID
T3: INSERT accounting_entry thất bại
T4: Database ROLLBACK
T5: Consumer đã nhận event "Đã thanh toán"
```

Broker và relational DB thường không chia sẻ một atomic transaction mặc định. Không thể dùng Java try/catch để rollback một message đã được consumer xử lý.

Đây là **dual-write problem**: một business operation ghi hai hệ thống bền vững khác nhau.

## 30. AFTER_COMMIT loại một lỗi nhưng chưa loại crash window

Nếu thay gửi broker trực tiếp bằng:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void publish(OrderPaid event) {
    broker.send(event);
}
~~~

thì trường hợp database **rollback** không còn gửi event qua listener này. Đây là cải thiện quan trọng.

Nhưng vẫn có cửa sổ:

~~~text
DB COMMIT thành công
       |
       | Process crash / container bị kill
       | Broker unavailable
       | JVM out-of-memory
       |
AFTER_COMMIT listener chưa gửi thành công
```

Dữ liệu nghiệp vụ đã durable, nhưng không có bản ghi bền vững nào ghi nhớ rằng event cần gửi. Sau restart, app không biết phải retry event nào chỉ dựa trên bộ nhớ listener cũ.

**Khi integration event bắt buộc phải được công bố**, dùng transactional outbox thay vì chỉ in-process after-commit listener.

## 31. Transactional outbox là gì?

**Transactional outbox** ghi **business state** và **bản ghi sự kiện cần công bố** vào **cùng một database transaction**.

~~~mermaid
flowchart TD
    A["Command: Mark Order Paid"] --> B["BEGIN TRANSACTION"]
    B --> C["UPDATE orders SET status=PAID"]
    C --> D["INSERT outbox_event OrderPaidV1"]
    D --> E{"COMMIT thành công?"}
    E -- "Không" --> F["Rollback cả order và outbox"]
    E -- "Có" --> G["Order và outbox durable cùng nhau"]
    G --> H["Outbox dispatcher / CDC"]
    H --> I["Broker/Webhook"]
    I --> J["Consumer xử lý idempotent"]
~~~

Nếu transaction rollback, **cả Order update và outbox insert rollback**. Nếu transaction commit, outbox row tồn tại ngay cả khi application crash, cho phép một worker khác gửi lại sau restart.

Outbox giải quyết **atomicity giữa business write và ý định gửi event** bằng một DB transaction; nó không tự khiến publish tới broker là exactly-once.

## 32. Bảng outbox gợi ý

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    published_at TIMESTAMPTZ
);

CREATE INDEX ix_outbox_ready
    ON outbox_event (status, available_at, occurred_at);

CREATE INDEX ix_outbox_aggregate
    ON outbox_event (aggregate_type, aggregate_id, aggregate_version);
~~~

Các trường có vai trò:

| Cột | Mục đích |
|---|---|
| `event_id` | Định danh duy nhất để deduplicate. |
| `aggregate_type`, `aggregate_id` | Tìm nguồn và partition key. |
| `aggregate_version` | Giúp xử lý thứ tự updates theo aggregate. |
| `event_type`, `schema_version` | Contract rõ khi evolve message schema. |
| `payload` | Snapshot dữ liệu tối thiểu mà consumer cần. |
| `status` | `PENDING`, `IN_PROGRESS`, `PUBLISHED` hoặc trạng thái policy định nghĩa. |
| `available_at`, `attempts` | Retry/backoff. |
| `occurred_at`, `published_at` | Quan sát thời gian và độ trễ delivery. |

Đây là **schema minh họa**, không phải schema chuẩn bắt buộc. Nếu dùng DBMS không có `JSONB`, chọn representation tương ứng.

## 33. Outbox entity JPA

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    @Column(name = "event_id", nullable = false)
    private UUID eventId;

    @Column(name = "aggregate_type", nullable = false)
    private String aggregateType;

    @Column(name = "aggregate_id", nullable = false)
    private String aggregateId;

    @Column(name = "event_type", nullable = false)
    private String eventType;

    @Column(name = "schema_version", nullable = false)
    private int schemaVersion;

    @Column(name = "payload", nullable = false)
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OutboxStatus status;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "available_at", nullable = false)
    private Instant availableAt;

    @Column(nullable = false)
    private int attempts;

    protected OutboxEvent() {}

    // Factory method/getters được lược bớt.
}
~~~

Ở ví dụ, `payload` là String để làm rõ ý tưởng. **Với PostgreSQL `JSONB`, mapping String mặc định có thể cần JDBC JSON type/cast hoặc mapping Hibernate `@JdbcTypeCode(SqlTypes.JSON)`**, tùy Hibernate version. Nếu không định cấu hình JSON mapping, có thể dùng cột `TEXT` và serialize JSON ở application. Không giả định String tự bind thành JSONB trong mọi dialect.

Nên tạo `event_id` trước khi lưu outbox và dùng cùng ID khi gửi broker để consumer dedupe.

## 34. Ghi aggregate và outbox trong cùng @Transactional

Ví dụ giữ logic tạo payload trong application service, sử dụng repository:

~~~java
@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    public OrderPaymentService(
            OrderRepository orders,
            OutboxRepository outbox,
            ObjectMapper objectMapper) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void markPaid(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        order.markPaid();

        OrderPaidV1 message = new OrderPaidV1(
            UUID.randomUUID(),
            order.getId(),
            order.getCustomerId(),
            Instant.now()
        );

        String payload;
        try {
            payload = objectMapper.writeValueAsString(message);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize OrderPaidV1", ex
            );
        }

        outbox.save(OutboxEvent.pending(
            message.eventId(),
            "Order",
            message.orderId().toString(),
            "OrderPaidV1",
            1,
            payload,
            message.occurredAt()
        ));

        // Transaction commit atomically:
        // Order dirty update + outbox INSERT.
    }
}
~~~

`OrderPaidV1`, `OutboxEvent.pending(...)`, các repositories và mappings là những phần cần định nghĩa trong ứng dụng; code trình bày ranh giới nghiệp vụ và transaction. `ObjectMapper`/`JsonProcessingException` đến từ Jackson nếu dự án dùng Jackson.

Điều quan trọng **không phải** gọi `orders.save(order)` bằng mọi giá: nếu `order` là managed entity, Hibernate dirty checking có thể lưu thay đổi khi flush. Điều quan trọng là **outbox insert và Order update dùng cùng transaction/DB resource và cùng commit boundary**.

Không gọi external broker trong transaction này; để dispatcher xử lý sau.

## 35. Atomicity của outbox chứng minh được những gì?

Giả sử cùng database transaction:

~~~text
BEGIN
  UPDATE orders SET status = 'PAID'
  INSERT outbox_event (event_id, type, payload, status)
COMMIT
~~~

Nếu COMMIT thất bại, cả hai thay đổi transactional đều không được công bố. Nếu COMMIT thành công, cả state và event intent cùng durable trong database.

Lưu ý:

- Nếu outbox được ghi vào **database khác** hoặc một `REQUIRES_NEW` transaction, atomicity đã mất.
- Nếu code save outbox nhưng transaction sau đó rollback, outbox cũng phải rollback.
- Nếu event payload serialization thất bại trước outbox insert, transaction thường rollback theo exception policy.
- Nếu dùng routing datasource, phải đảm bảo aggregate và outbox dùng cùng writer transaction.
- Nếu database có trigger/outbox side effects riêng, phải hiểu transaction semantics của chúng.

Outbox bảo đảm **không quên ý định gửi khi business write commit**, với điều kiện cùng transaction và dispatcher còn chạy được; nó không bảo đảm consumer sẽ xử lý đúng một lần.

## 36. Dispatcher xử lý outbox như thế nào?

Một worker định kỳ có thể:

1. Lấy các rows `PENDING` đến hạn.
2. **Claim** chúng để nhiều workers không cùng xử lý một lượt.
3. Gửi message tới broker/webhook.
4. Sau broker acknowledgement, đánh dấu `PUBLISHED`.
5. Nếu thất bại, tăng `attempts`, đặt `available_at` theo backoff.
6. Quá số lần retry, đưa vào dead-letter/quarantine và cảnh báo.

Pseudocode:

~~~java
for (OutboxEvent event : outboxStore.claimNextBatch(100)) {
    try {
        broker.publish(
            event.aggregateId(),
            event.payload(),
            event.eventId().toString()
        );

        outboxStore.markPublished(event.eventId());
    } catch (Exception ex) {
        outboxStore.scheduleRetry(event.eventId(), ex);
    }
}
~~~

`claimNextBatch`, `markPublished`, `scheduleRetry` là interface minh họa của outbox service. **Không coi toàn bộ vòng lặp là một DB transaction dài giữ row locks trong lúc chờ network.** Trong production, claim/lease, send, acknowledge và retry nên có boundaries rõ.

## 37. Claim outbox an toàn khi có nhiều workers

Một chiến lược PostgreSQL có thể dùng `FOR UPDATE SKIP LOCKED` để phân chia rows giữa workers:

~~~sql
SELECT event_id
FROM outbox_event
WHERE status = 'PENDING'
  AND available_at <= now()
ORDER BY occurred_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Query này cần chạy trong transaction phù hợp. Thiết kế cụ thể thường:

- Claim rows trong transaction ngắn.
- Ghi `IN_PROGRESS`, `lease_owner`, `lease_until` hoặc token tương đương.
- Commit claim.
- Gửi broker ngoài transaction claim để không giữ locks lâu.
- Acknowledge riêng với conditional update.
- Reclaim rows khi lease hết hạn, để crash không làm event kẹt mãi.

Nếu giữ transaction/row locks trong khi broker call chậm, worker có thể làm DB lock contention cao. Nếu không có lease/recovery, worker crash sau khi claim có thể khiến event không bao giờ được gửi lại.

Các DBMS khác có cú pháp row locking khác; không copy PostgreSQL SQL sang mọi dialect.

## 38. Vì sao outbox thường là at-least-once?

Một crash window không thể tránh chỉ bằng outbox:

~~~text
Worker gửi message tới broker
  |
  | Broker đã lưu message và ACK
  |
Worker crash trước khi markPublished trong DB
  |
Worker khác retry outbox row
  |
Consumer nhận cùng event lần nữa
```

Điều này dẫn đến **at-least-once delivery** trong thiết kế phổ biến: một event có thể được gửi nhiều lần.

**Giải pháp không phải tự tin rằng sẽ không bao giờ duplicate**, mà là:

- Mỗi event có stable unique `eventId`.
- Producer retry giữ nguyên `eventId`.
- Consumer xử lý idempotent/deduplicate.
- Broker/consumer có retry và dead-letter policies.
- Nếu nghiệp vụ yêu cầu exactly-once end-to-end, phải thiết kế transaction và deduplication cho cả effect đích, không chỉ source broker.

## 39. Consumer idempotency bằng inbox/deduplication

Ví dụ một consumer cần tạo bản ghi fulfillment khi nhận `OrderPaidV1`.

Bảng:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong **cùng transaction** xử lý business effect:

~~~text
BEGIN
  INSERT processed_message(consumer_name, event_id, processed_at)
  nếu đã tồn tại -> bỏ qua duplicate
  nếu insert thành công -> tạo fulfillment record
COMMIT
```

Nếu hệ thống nhận message trùng, unique constraint trên `(consumer_name, event_id)` cho phép nhận biết đã xử lý.

**Cần atomicity giữa inbox marker và business effect**, không chỉ kiểm tra `if (!exists)` trước rồi insert sau, vì hai consumers có thể race. Có thể dùng `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL) và dựa vào row count trong transaction, hoặc cơ chế tương đương.

Nếu consumer gửi external email/API ngoài DB, phải có chiến lược idempotency riêng với hệ thống đích.

## 40. Thứ tự sự kiện theo aggregate

Ví dụ Order#42 có các transitions:

~~~text
OrderCreated -> OrderPaid -> OrderShipped
```

Nếu dispatcher có nhiều workers, event `OrderShipped` có thể đến consumer trước `OrderPaid` trừ khi có chiến lược ordering.

Các lựa chọn:

- Partition message broker theo `aggregateId`.
- Gán `aggregateVersion` hoặc sequence tăng đơn điệu theo aggregate.
- Sắp xếp/claim per aggregate khi dispatch.
- Consumer kiểm tra expected version hoặc có buffer/retry khi out of order.
- Thiết kế event consumers tolerate reorder khi domain cho phép.

Database `occurred_at` không tự bảo đảm một total order hoàn hảo khi concurrent transactions hoặc clock drift. Nếu yêu cầu strict ordering per aggregate, dùng business sequence/version và kỹ thuật concurrency phù hợp.

Đối với Hibernate `@Version`, phải cân nhắc thời điểm version increment/flush và các updates bypass ORM; không lấy timestamp làm thay thế version mà không có kiểm chứng.

## 41. Thiết kế payload theo contract

Một integration event nên có tối thiểu:

~~~json
{
  "eventId": "2fd96b8f-7427-47f2-9130-746bf9aac19d",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "0bc6cf4a-3643-4fe1-85cc-579c8b9c1d90",
  "occurredAt": "2026-11-15T09:00:00Z",
  "payload": {
    "orderId": "0bc6cf4a-3643-4fe1-85cc-579c8b9c1d90",
    "customerId": "d35d7c10-2a40-4de8-8dbe-ea1f1a427c5a"
  }
}
~~~

JSON trên là ví dụ hợp đồng event, không phải JPA serialization tự động.

Khuyến nghị:

- Chọn tên nghiệp vụ có ngữ nghĩa rõ, không gắn chặt schema bảng.
- Event ID ổn định cho retries.
- Version schema và đặt chính sách tương thích backward/forward.
- Chỉ gửi fields consumer cần; tránh PII/secrets.
- Không serialize nguyên managed entity hoặc Hibernate lazy proxy.
- Dùng timestamp/timezone thống nhất, ví dụ UTC.
- Đặt correlation/causation IDs nếu nhiều workflow cần tracing.
- Đảm bảo consumer biết semantics: sự kiện “đã được thanh toán” khác “đang yêu cầu thanh toán”.

## 42. Domain event và integration event có thể khác nhau

Domain event nội bộ có thể mang dữ liệu và loại Java phục vụ aggregate/local handlers:

~~~java
record OrderPaid(UUID orderId, Money amount) {}
~~~

Integration event phát ngoài service cần schema ổn định hơn:

~~~java
record OrderPaidV1(
    UUID eventId,
    UUID orderId,
    String currency,
    String amount,
    Instant occurredAt
) {}
~~~

Không bắt consumer phụ thuộc class Java, entity mapping, ORM annotation hoặc Hibernate proxies. Việc ánh xạ domain event → integration event có thể diễn ra trong application service khi tạo outbox.

Một domain event có thể sinh nhiều integration messages, hoặc nhiều internal events được gom thành một integration event theo API contract.

## 43. Retry, backoff và poison messages

Không gửi lại lỗi vô hạn với delay cố định và không có quan sát.

Một policy có thể gồm:

- Retry các lỗi tạm thời như broker timeout, 503, rate limiting.
- Exponential backoff với jitter.
- Giới hạn attempts và dead-letter/quarantine.
- Phân loại lỗi không thể tự sửa: schema invalid, unauthorized, bad payload.
- Cảnh báo theo độ tuổi event chưa gửi, không chỉ số lần retry.
- Manual replay sau khi sửa nguyên nhân.

Ví dụ trạng thái:

~~~text
PENDING -> IN_PROGRESS -> PUBLISHED
               |
               +-> PENDING (next available_at)
               |
               +-> DEAD_LETTER (cần xử lý)
```

Nếu worker crash ở `IN_PROGRESS`, lease expiry cho phép recovery; nếu broker đã nhận nhưng DB chưa đánh dấu, duplicate là bình thường và consumer phải idempotent.

## 44. Outbox polling và CDC

Có hai cách đưa committed outbox rows tới broker:

**Polling publisher:** Application/worker query bảng outbox, claim rows, gửi broker, đánh dấu đã gửi. Dễ triển khai nhưng cần polling, concurrency, retry và cleanup.

**Change Data Capture (CDC):** Công cụ đọc transaction log (WAL/binlog/redo, theo DB) và chuyển outbox insert thành message. Ví dụ hệ sinh thái có thể dùng Debezium outbox event router khi đáp ứng môi trường.

CDC có lợi ích giảm polling/query overhead và bám sát transaction log, nhưng vẫn cần:

- Quản lý connector/offset/replication lag.
- Thiết kế event schema.
- Xử lý duplicate và replay.
- Monitoring, access control, retention.
- Kiểm thử ordering và contract.

**CDC không tự loại bỏ idempotency requirement.** Consumer vẫn cần thiết kế khi offset/replay dẫn tới duplicate deliveries.

## 45. Bảo đảm transaction boundary khi dùng outbox

Một anti-pattern là:

~~~java
@Transactional
public void markPaid(UUID id) {
    Order order = orders.findById(id).orElseThrow();
    order.markPaid();

    outboxService.saveWithRequiresNew(...); // Transaction riêng!
}
~~~

Nếu outbox insert commit trong transaction `REQUIRES_NEW` nhưng outer transaction sau đó rollback, outbox báo `OrderPaid` trong khi Order không chuyển trạng thái ở DB.

Ngược lại, nếu Order commit trước nhưng outbox nằm trong transaction khác bị rollback, event sẽ mất.

**Ràng buộc thiết kế:** Business changes và outbox message phải **cùng một database transaction atomic**, tránh `REQUIRES_NEW`/remote database nếu không có distributed transaction hoặc giao thức nhất quán khác.

## 46. Lỗi ORM callback publish message: minh họa đầy đủ

Sai:

~~~java
@Entity
class Order {
    @PostUpdate
    void afterUpdate() {
        kafkaProducer.send(
            "order-events",
            "ORDER_PAID"
        );
    }
}
~~~

Có ít nhất năm vấn đề:

1. `@PostUpdate` không đồng nghĩa transition `PENDING_PAYMENT -> PAID`.
2. Callback có thể chạy trước COMMIT.
3. Transaction có thể rollback sau callback.
4. Callback có thể bị bypass bởi bulk SQL/native DML.
5. Callback gọi network phá vỡ separation of concerns và gây timeout/reentrancy risks.

Đúng hướng:

~~~text
Order.markPaid() thực thi business invariant
    |
Application service tạo OrderPaid
    |
Outbox row được INSERT cùng transaction
    |
DB COMMIT
    |
Dispatcher gửi OrderPaidV1
    |
Consumer idempotent
```

Không nhất thiết tất cả hệ thống cần outbox; nhưng nếu message mang trách nhiệm kinh doanh xuyên service, hãy giải quyết delivery contract thay vì gắn mạng vào entity callback.

## 47. Khi nào có thể dùng @TransactionalEventListener(AFTER_COMMIT) trực tiếp?

Phù hợp tương đối với:

- Invalidate cache **best-effort** có TTL/fallback.
- Gửi một notification có thể tái tạo bằng scheduled reconciliation.
- Trigger một workflow local mà chấp nhận mất callback khi process crash.
- Ghi log/metrics không critical, có hệ thống observability độc lập.
- Khởi động một tác vụ nội bộ có recovery path khác.

Cần outbox hoặc durable mechanism khi:

- Kafka message kích hoạt fulfillment/accounting quan trọng.
- Sự kiện là duy nhất để service khác biết trạng thái mới.
- Webhook phải retry cho tới khi được acknowledge.
- Có yêu cầu audit/integration delivery có thể chứng minh.
- Process restart không được làm mất thông báo.

Một tiêu chí thực tế: **Nếu app crash một giây sau DB commit, có cơ chế tìm và gửi lại sự kiện đó không?** Nếu câu trả lời là không, `AFTER_COMMIT` listener đơn thuần chưa đáp ứng yêu cầu durable delivery.

## 48. Audit là persistence concern hay business event?

Có ít nhất ba loại audit:

1. **ORM change audit:** Entity nào thay đổi cột nào, lúc nào, do ai. Có thể dùng Hibernate Envers, listener kỹ thuật hoặc database CDC/triggers tùy yêu cầu.
2. **Business audit:** “Đơn 42 được duyệt bởi quản lý M vì quy tắc R.” Đây là ý nghĩa nghiệp vụ, không chỉ field diff.
3. **External compliance log:** Một hệ thống khác phải nhận/ghi lại sự kiện, có delivery/audit requirement riêng.

Envers và các cơ chế entity revision không tự tạo một integration event contract gửi broker sau commit. Domain event cũng không tự lưu field-level history.

Nếu audit phải atomic với business mutation, thường lưu audit row trong cùng transaction hoặc dùng outbox. Không đặt compliance audit bắt buộc vào after-commit callback volatile.

## 49. Observability cho event pipeline

Nên đo cả **trước và sau commit**:

- Số domain commands chuyển state thành công.
- Số outbox rows được commit.
- Số events đang `PENDING`/`IN_PROGRESS`/`DEAD_LETTER`.
- Event age/lag từ `occurred_at` đến `published_at`.
- Broker publish attempts và acknowledgements.
- Retry counts, error classes, lease expirations.
- Consumer processing failures và duplicate skips.
- Ordering/version mismatches.
- Backlog growth sau deploy/outage.

Correlation IDs và `eventId` giúp trace:

~~~text
HTTP request / commandId
    -> Order aggregateId
    -> outbox eventId
    -> broker messageId/key
    -> consumer processing log
```

Đừng log payload chứa dữ liệu nhạy cảm nguyên vẹn; log IDs, event type và số liệu đủ để truy tìm.

## 50. Thử nghiệm kỹ thuật các mốc lifecycle

Một integration test hữu ích tạo transaction rồi ép flush:

~~~java
@Transactional
public void changeAndFlush(UUID id) {
    Order order = orders.findById(id).orElseThrow();
    order.markPaid();

    entityManager.flush();

    // ORM @PostUpdate có thể đã chạy.
    // Transaction vẫn có thể rollback sau đây.
    throw new IllegalStateException("Force rollback");
}
~~~

Kết quả mong đợi:

- SQL UPDATE đã có thể được gửi tới DB tại flush.
- JPA `@PostUpdate` có thể đã chạy.
- Transaction rollback nên Order không commit trạng thái PAID.
- Listener `@TransactionalEventListener(AFTER_COMMIT)` không chạy nếu event được phát trong transaction này và transaction rollback.
- Listener `AFTER_ROLLBACK` có thể chạy nếu đã đăng ký.

Đây là cách phân biệt **flush lifecycle** với **transaction commit**. Test cần dùng DB transaction thật và không nhầm kết quả rollback do Spring Test framework với rollback của scenario.

## 51. Test @TransactionalEventListener đúng transaction

Một test gọi service:

~~~java
@Test
void afterCommitRunsOnlyWhenCommandCommits() {
    paymentService.markPaid(orderId);

    // paymentService phải được gọi qua Spring proxy,
    // transaction commit khi method trả về.
    // Có thể kiểm tra spy/mock AFTER_COMMIT listener
    // hoặc kiểm tra side effect có thể quan sát.
}
~~~

Lưu ý: Với `@SpringBootTest` và `@Transactional` **trên test method**, Spring Test thường tạo outer transaction rồi rollback sau test. Trong trường hợp đó, service REQUIRED tham gia transaction test, không commit thật, nên `AFTER_COMMIT` listener **không chạy**.

Có thể:

- Không đặt `@Transactional` trên test khi muốn quan sát service commit.
- Dùng `TransactionTemplate`/test transaction control với commit tường minh.
- Dùng `@Commit` hoặc cấu hình rollback phù hợp có chủ đích.
- Kiểm tra callback bằng spy/latch theo cơ chế sync/async thực tế.

Không kết luận listener hỏng khi test luôn rollback.

## 52. Test crash window và outbox reliability

Một integration test cho outbox cần chứng minh:

1. Command thành công → Order PAID và outbox row cùng xuất hiện.
2. Command ném exception → cả Order update và outbox INSERT rollback.
3. Dispatcher gặp broker timeout → outbox row chưa mất, được retry.
4. Broker ACK rồi worker crash trước `markPublished` → event có thể gửi lại.
5. Consumer nhận duplicate `eventId` → business effect chỉ được thực hiện một lần.
6. Worker A và B cùng claim → không xử lý cùng lease một cách sai.
7. Lease hết hạn → row được reclaim và publish.
8. Event ordering per aggregate được kiểm soát theo contract.
9. Dead-letter và replay có logging/authorization phù hợp.

Đây là các kịch bản quan trọng hơn việc chỉ unit-test `@TransactionalEventListener` có được gọi một lần trong trường hợp lý tưởng hay không.

## 53. Test sự kiện nội bộ Hibernate khác domain event

Một matrix để tránh nhầm:

| Hành động | ORM callback? | Domain event? | External publish? |
|---|---|---|---|
| `entityManager.persist(order)` và flush | Có thể có Pre/PostPersist | Không tự sinh `OrderPaid` | Không nên tự gửi |
| Sửa `Order.description` rồi flush | Có thể PostUpdate | Không phải `OrderPaid` | Không nên gửi `OrderPaid` |
| `order.markPaid()` trong business service | Chưa chắc callback đến khi flush | Có `OrderPaid` nếu transition hợp lệ | Chờ commit hoặc outbox |
| Bulk HQL update trạng thái | Không có lifecycle per entity | Phải tạo riêng nếu contract yêu cầu | Thiết kế rõ |
| Transaction rollback sau flush | ORM callback có thể đã chạy | Event object có thể đã tạo | Không gửi qua AFTER_COMMIT |
| Transaction commit, process crash | ORM lifecycle đã xảy ra | Domain fact durable trong DB | Có thể mất nếu chỉ listener memory |
| Outbox committed + dispatcher retry | Không cần ORM callback | Event intent được lưu | At-least-once; consumer dedupe |

Các trường hợp này giúp team quyết định nơi đặt rule, thay vì dựa vào tên “post” của ORM callback.

## 54. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Gửi Kafka trong `@PostPersist` | Message có thể tới trước commit | Tạo domain event ở service, dùng after-commit hoặc outbox |
| Xem `flush()` như `commit()` | Gửi thông báo cho dữ liệu rollback | Phân biệt SQL execution và transaction commit |
| Dùng `@EventListener` mặc định cho irreversible side effect | Listener chạy ngay trong transaction | Dùng `@TransactionalEventListener(AFTER_COMMIT)` nếu best-effort |
| Coi AFTER_COMMIT là durable queue | Mất event khi crash | Transactional outbox/CDC |
| Ghi DB trong AFTER_COMMIT không tạo transaction mới | Write có thể không được commit như mong đợi | `REQUIRES_NEW` khi thật sự cần post-commit write |
| Dùng REQUIRES_NEW cho outbox | Outbox và business state không atomic | Lưu outbox cùng transaction |
| Quên listener không có transaction | Event bị bỏ qua mặc định | Đảm bảo transaction hoặc fallback có chủ đích |
| Dùng `@Async` để “đảm bảo sau commit” | Scheduling không có commit contract | Kết hợp transaction phase; cần reliability thì outbox |
| Tưởng `@DomainEvents` chạy ở mọi dirty flush | Bỏ sót events | Hiểu repository interceptor semantics |
| Serialize managed JPA entity vào message | LAZY proxies, dữ liệu dư/thông tin nhạy cảm | DTO/versioned payload |
| Không gắn eventId | Không xử lý duplicates được | Stable unique event ID |
| Mark PUBLISHED trước broker ACK | Mất message nếu gửi thất bại | Ack rồi mark; chấp nhận duplicate và idempotency |
| Không có lease recovery | Outbox stuck khi worker crash | Lease expiry/reclaim |
| Phụ thuộc timestamp để order tuyệt đối | Consumer xử lý sai thứ tự | Aggregate version/key/ordering policy |
| Dùng callback cho nghiệp vụ khi có bulk SQL | Event thiếu | Đặt business intent ở command path |

## 55. Lựa chọn giải pháp theo yêu cầu

| Yêu cầu | Lựa chọn nên cân nhắc |
|---|---|
| Điền `createdAt`/metadata kỹ thuật | JPA callback hoặc Spring Data auditing theo mapping |
| Hook rất sâu vào persistence engine | Hibernate EventListener SPI |
| Biểu đạt “Order đã trả tiền” trong domain | Domain event tại aggregate/application layer |
| Local handler không cần chờ commit, phải atomic với dữ liệu | Xử lý trong cùng transaction (cẩn trọng side effects) |
| Sau commit cập nhật cache best-effort | `@TransactionalEventListener(AFTER_COMMIT)` |
| Sau commit gửi email có thể tái tạo bằng reconciliation | AFTER_COMMIT + cơ chế recovery nếu cần |
| Bắt buộc Kafka/Webhook nhận mọi sự kiện đã commit | Transactional outbox + dispatcher/CDC |
| Consumer có thể nhận messages lặp | Idempotent consumer/inbox |
| Cần strict per-aggregate ordering | Partition key + version/sequence + kiểm soát concurrency |
| Compliance audit bắt buộc | Audit/outbox row cùng transaction hoặc DB mechanism phù hợp |

## 56. Checklist trước khi triển khai

**Domain và lifecycle**

- [ ] Event tên theo nghiệp vụ, không theo tên ORM SQL operation?
- [ ] Event được tạo tại business transition hợp lệ?
- [ ] Không dựa `@PostUpdate` như dấu commit?
- [ ] Đường bulk/native/stateless mutations có được xem xét?
- [ ] Nếu invariant phải atomic, xử lý cùng DB transaction?
- [ ] Không serialize JPA entity/proxies ra broker?

**Spring/transaction**

- [ ] `@Transactional` thực sự được proxy intercept?
- [ ] Event được publish trong transaction đúng?
- [ ] Listener dùng đúng phase?
- [ ] Không bật fallbackExecution ngoài ý muốn?
- [ ] Ghi DB sau commit có transaction mới nếu cần?
- [ ] Hiểu nested/savepoint và REQUIRES_NEW?
- [ ] Exceptions ở listener không được coi là rollback business commit?

**Độ bền integration**

- [ ] Nếu process crash sau commit, có event durable để retry?
- [ ] Outbox cùng DB transaction với aggregate?
- [ ] Worker claim/lease/recovery an toàn?
- [ ] Broker ACK trước khi markPublished?
- [ ] Có stable eventId và consumer idempotency?
- [ ] Có ordering/version policy?
- [ ] Có retry/backoff/dead-letter và metrics?
- [ ] Có schema version/PII/correlation policy?

**Testing**

- [ ] Test flush rồi rollback?
- [ ] Test AFTER_COMMIT/AFTER_ROLLBACK?
- [ ] Test không có transaction?
- [ ] Test Spring Test outer rollback?
- [ ] Test dispatcher crash/duplicate/retry?
- [ ] Test multi-worker claim và tenant boundaries?

## 57. Bài tập thực hành

1. Viết một entity có `@PrePersist`, `@PostPersist`, `@PreUpdate` và log thứ tự callback khi gọi `persist`, `flush`, `commit`.
2. Thêm `throw new RuntimeException()` sau `flush()`. Quan sát callback đã chạy nhưng DB transaction rollback.
3. Tạo `Order.markPaid()` và record domain event `OrderPaid`; chỉ tạo khi transition hợp lệ.
4. Viết listener `@EventListener` gửi mock notification, rồi thay bằng `@TransactionalEventListener(AFTER_COMMIT)`; so sánh rollback.
5. Thử publish event không có transaction và quan sát hành vi mặc định/fallbackExecution.
6. Thử gọi nested REQUIRED và REQUIRES_NEW để xem event gắn với transaction nào.
7. Viết một listener `AFTER_COMMIT` ghi audit DB, rồi tách sang service `REQUIRES_NEW`; giải thích tại sao atomicity khác nhau.
8. Thiết kế outbox schema cho `OrderPaidV1` với eventId, aggregateId, schemaVersion, payload và retry fields.
9. Trong một service `@Transactional`, ghi Order PAID và outbox row; cố tình rollback để xác nhận cả hai cùng mất.
10. Tạo dispatcher giả lập broker trả timeout sau khi đã nhận event. Cho worker retry và quan sát duplicate.
11. Thêm consumer inbox với unique `(consumer_name,event_id)` để tránh ghi fulfillment hai lần.
12. Dùng hai workers claim cùng batch outbox, thêm lease/timeout recovery và kiểm tra không kẹt sau crash.
13. Mô tả cách handle event ordering `OrderPaid`/`OrderShipped` theo aggregateVersion.
14. Viết integration test Spring không có `@Transactional` trên test method để quan sát một commit thật và callback AFTER_COMMIT.
15. Xác định một trường hợp domain invariant phải ghi **trong cùng transaction** và một trường hợp external notification chỉ gửi sau commit.

## 58. Sơ đồ quyết định cuối bài

~~~mermaid
flowchart TD
    A["Có một thay đổi/sự kiện"] --> B{"Là hoạt động kỹ thuật ORM?"}
    B -- "Có" --> C["JPA callback / Hibernate event SPI"]
    C --> D["Không dùng callback làm dấu COMMIT"]
    B -- "Không" --> E{"Là transition có ý nghĩa nghiệp vụ?"}
    E -- "Có" --> F["Domain event tại aggregate/application service"]
    E -- "Không" --> G["Đánh giá lại tên/phạm vi event"]
    F --> H{"Phản ứng cần atomic với DB write?"}
    H -- "Có" --> I["Thực hiện trong cùng transaction"]
    H -- "Không" --> J{"Cần durable external delivery?"}
    J -- "Không, best-effort" --> K["@TransactionalEventListener AFTER_COMMIT"]
    J -- "Có" --> L["Outbox row cùng transaction"]
    L --> M["Commit"]
    M --> N["Dispatcher/CDC + retry"]
    N --> O["Broker/consumer idempotent"]
~~~

## 59. Tổng kết

**Sự kiện nội bộ ORM** như `@PostUpdate` và Hibernate `PostInsertEvent` thông báo cho ứng dụng rằng một bước **persistence lifecycle** đã diễn ra. Chúng không nói transaction chắc chắn đã commit, không diễn tả mặc định một **business transition**, và có thể không xuất hiện ở các đường bulk/native SQL.

**Domain event** như `OrderPaid` được tạo bởi nghiệp vụ khi aggregate chuyển trạng thái hợp lệ. Nó có thể được tạo và lưu trong bộ nhớ trong lúc transaction còn mở; **chưa được coi là bằng chứng durable bên ngoài** cho đến khi business transaction commit thành công.

**Công bố sự kiện sau commit** có hai mức cần phân biệt:

- `@TransactionalEventListener(AFTER_COMMIT)` giúp chạy một **in-process best-effort callback** sau commit, tránh gửi cho transaction rollback; nhưng vẫn có crash window và không bảo đảm broker delivery.
- **Transactional outbox** ghi business state và event intent **trong cùng commit**, sau đó dispatcher/CDC chuyển sự kiện đến broker; cần **at-least-once delivery, retry, idempotency và ordering** để triển khai đáng tin cậy.

Quy tắc nhớ nhanh: **ORM event ≠ domain event; flush ≠ commit; AFTER_COMMIT ≠ durable delivery; outbox ≠ exactly-once consumer effect.** Chọn cơ chế đúng theo ranh giới giao dịch và mức độ đảm bảo mà nghiệp vụ yêu cầu.
