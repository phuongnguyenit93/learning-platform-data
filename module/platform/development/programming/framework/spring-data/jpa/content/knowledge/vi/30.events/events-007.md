# Hành vi của sự kiện khi rollback, khi không có giao dịch và khi dùng @Async

Trong Spring Data JPA, sự kiện miền (domain event) thường được phát ra khi một aggregate root thay đổi trạng thái. Spring có thể chuyển sự kiện đến listener ngay khi publish hoặc gắn listener với một giai đoạn của transaction. Kết quả phụ thuộc vào thời điểm publish, trạng thái transaction và việc listener chạy đồng bộ hay bất đồng bộ.

Cần phân biệt ba việc:

- **Publish event:** đưa sự kiện vào Spring ApplicationEventPublisher.
- **Handle event:** listener thực thi logic xử lý sự kiện.
- **Commit transaction:** dữ liệu nghiệp vụ được xác nhận trong cơ sở dữ liệu.

Ba việc này không nhất thiết xảy ra cùng thời điểm. Một event có thể đã được publish và listener đồng bộ đã chạy, nhưng transaction sau đó vẫn rollback. Ngược lại, listener gắn với AFTER_COMMIT chỉ chạy sau khi transaction commit thành công.

## 1. Publish event và listener thông thường

Spring cho phép publish event bằng `ApplicationEventPublisher`:

```java
public record OrderPlacedEvent(Long orderId) {
}
```

Service phát sự kiện sau khi lưu đơn hàng:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);

        events.publishEvent(
                new OrderPlacedEvent(saved.getId())
        );

        return saved.getId();
    }
}
```

Mặc định, Spring xử lý `@EventListener` đồng bộ ngay trong lúc `publishEvent()` được gọi:

```java
@Component
public class OrderEventListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "Received order " + event.orderId()
        );
    }
}
```

Nếu sự kiện được publish bên trong một transaction, listener thông thường vẫn chạy trước khi transaction đó commit. Nếu phần xử lý sau đó ném exception và transaction rollback, listener đã chạy rồi. Spring không tự hoàn tác email, HTTP request, message gửi sang hệ thống khác hoặc các tác dụng phụ bên ngoài mà listener đã thực hiện.

Nếu listener đồng bộ ghi dữ liệu qua cùng transaction manager và tham gia transaction hiện tại, thao tác ghi đó có thể rollback cùng transaction. Tuy nhiên, không thể dùng rollback cơ sở dữ liệu để hoàn tác một hành động bên ngoài như gửi email hoặc gọi API.

Vì vậy, `@EventListener` phù hợp khi cần phản ứng ngay với event và chấp nhận xử lý trong thời điểm publish. Khi nghiệp vụ chỉ được thực hiện sau khi dữ liệu đã commit, hãy dùng `@TransactionalEventListener`.

## 2. @TransactionalEventListener và các giai đoạn transaction

`@TransactionalEventListener` cho phép gắn việc xử lý event với một giai đoạn của transaction:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderTransactionListener {

    @TransactionalEventListener
    public void afterCommit(OrderPlacedEvent event) {
        System.out.println(
                "Order committed: " + event.orderId()
        );
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
    )
    public void afterRollback(OrderPlacedEvent event) {
        System.out.println(
                "Order rolled back: " + event.orderId()
        );
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderPlacedEvent event) {
        System.out.println(
                "Transaction completed: " + event.orderId()
        );
    }
}
```

Nếu không khai báo phase, Spring dùng `TransactionPhase.AFTER_COMMIT`. Các phase có ý nghĩa:

| Phase | Thời điểm listener chạy | Khi transaction rollback |
|---|---|---|
| `BEFORE_COMMIT` | Ngay trước khi transaction commit | Có thể đã chạy dù transaction sau đó rollback |
| `AFTER_COMMIT` | Sau khi commit thành công | Không chạy |
| `AFTER_ROLLBACK` | Sau khi rollback | Chạy |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc | Chạy cả khi commit và rollback |

### Khi transaction commit

Nếu service publish event trong transaction và transaction commit thành công:

1. Event được publish.
2. Spring đăng ký listener transaction-bound với transaction hiện tại.
3. Transaction commit.
4. Listener `AFTER_COMMIT` được gọi.
5. Listener `AFTER_ROLLBACK` không được gọi.
6. Listener `AFTER_COMPLETION` cũng được gọi vì transaction đã hoàn tất.

### Khi transaction rollback

Ví dụ:

```java
@Transactional
public void placeOrder(Order order) {
    Order saved = orders.save(order);
    events.publishEvent(
            new OrderPlacedEvent(saved.getId())
    );

    throw new IllegalStateException("Payment rejected");
}
```

Nếu exception làm transaction rollback:

- Listener `@EventListener` thông thường đã chạy ngay khi event được publish.
- Listener `AFTER_COMMIT` không chạy vì transaction không commit.
- Listener `AFTER_ROLLBACK` chạy để xử lý tình huống rollback.
- Listener `AFTER_COMPLETION` chạy sau khi rollback hoàn tất.
- Dữ liệu ghi trong cùng transaction bị rollback theo quy tắc transaction.

Có thể dùng `AFTER_ROLLBACK` để ghi log nghiệp vụ, cập nhật metric, giải phóng tài nguyên hoặc thực hiện một hành động bù trừ. Không nên gửi thông báo "đơn hàng đã tạo thành công" từ listener thông thường trước khi transaction commit.

`BEFORE_COMMIT` không có nghĩa là chắc chắn sẽ commit. Listener phase này chạy trước commit, nhưng một listener khác, lỗi flush hoặc lỗi commit vẫn có thể khiến transaction rollback.

## 3. Khi publish event mà không có transaction

`@EventListener` thông thường không yêu cầu transaction. Nếu không có transaction, listener vẫn chạy ngay khi event được publish.

Với `@TransactionalEventListener`, mặc định `fallbackExecution = false`. Nếu event được publish khi không có transaction đang hoạt động, listener sẽ không được thực thi vì Spring không có transaction phase để đăng ký.

Ví dụ:

```java
@Component
public class NoTransactionListener {

    @EventListener
    public void onRegularEvent(OrderPlacedEvent event) {
        // Vẫn chạy khi không có transaction.
    }

    @TransactionalEventListener
    public void onTransactionalEvent(OrderPlacedEvent event) {
        // Bỏ qua nếu event được publish ngoài transaction.
    }
}
```

Nếu muốn listener vẫn chạy khi không có transaction, có thể bật fallback:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onOrderPlaced(OrderPlacedEvent event) {
    // Chạy sau commit nếu có transaction.
    // Nếu không có transaction, chạy ngay theo fallback.
}
```

Cần hiểu rõ giới hạn: `fallbackExecution = true` không tạo transaction mới và không giả lập một lần commit. Khi không có transaction, listener chạy ngay trong chế độ fallback; ứng dụng không có bảo đảm AFTER_COMMIT như khi event được publish trong một transaction thực sự.

Nếu listener cần ghi dữ liệu, hãy mở transaction riêng bằng một service có `@Transactional`. Nếu nghiệp vụ cần xác nhận dữ liệu nguồn đã commit trước khi xử lý, hãy bảo đảm event được publish trong transaction nghiệp vụ và không dựa vào fallback.

Với Spring Data domain event, hãy đặt lời gọi repository trong một service method có `@Transactional` khi cần listener gắn với cùng transaction nghiệp vụ. Điều này làm rõ thời điểm publish và giúp `@TransactionalEventListener` nhận được transaction mà nó cần.

## 4. Spring Data @DomainEvents và thời điểm transaction

Spring Data cho phép aggregate root công bố sự kiện qua `@DomainEvents` và dọn danh sách event sau khi publish bằng `@AfterDomainEventPublication`.

Ví dụ aggregate:

```java
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @Transient
    private final List<Object> events = new ArrayList<>();

    public void place() {
        // Thay đổi trạng thái nghiệp vụ của đơn hàng.
        events.add(new OrderPlacedEvent(id));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        events.clear();
    }
}
```

Spring Data gọi các method này khi những repository operation được hỗ trợ được thực thi với aggregate root, chẳng hạn `save()`, `saveAll()`, `delete()` và `deleteAll()`. Các phiên bản Spring Data hiện hành còn hỗ trợ một số phương thức batch delete nhận aggregate root. `deleteById()` không có aggregate instance làm đối số nên không thể dựa vào cơ chế này để lấy event từ entity đã xóa.

Quy trình cơ bản:

1. Aggregate thay đổi trạng thái và ghi nhận event vào danh sách nội bộ.
2. Ứng dụng gọi repository để lưu hoặc xóa aggregate.
3. Spring Data lấy event từ method `@DomainEvents` và publish vào Spring ApplicationContext.
4. Sau khi các event được publish, method `@AfterDomainEventPublication` được gọi để dọn danh sách event.
5. Listener thông thường xử lý ngay; listener transaction-bound chờ phase tương ứng nếu event được publish trong transaction.

`@AfterDomainEventPublication` có nghĩa là event đã được publish vào ApplicationContext. Nó không có nghĩa transaction cơ sở dữ liệu đã commit. Nếu transaction bên ngoài rollback sau đó, danh sách event trong aggregate có thể đã được dọn, trong khi listener `AFTER_COMMIT` không được chạy. Vì thế, danh sách event trong bộ nhớ không phải một hàng đợi bền vững và không nên được dùng làm cơ chế retry sau rollback.

Hãy dùng event payload bất biến, thường chứa ID và dữ liệu cần thiết, thay vì truyền cả entity JPA đang được quản lý sang xử lý bất đồng bộ. Entity có thể detached hoặc thay đổi sau khi event được publish.

## 5. Dùng @Async với event listener

`@Async` chuyển việc thực thi method sang một task được gửi đến Spring `TaskExecutor`. Caller có thể tiếp tục mà không cần chờ listener hoàn tất.

Bật hỗ trợ async:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfig {
}
```

Listener bất đồng bộ thông thường:

```java
@Component
public class OrderNotificationListener {

    @Async
    @EventListener
    public void sendNotification(OrderPlacedEvent event) {
        // Gửi email hoặc gọi dịch vụ thông báo.
    }
}
```

Với `@EventListener` kết hợp `@Async`, công việc được gửi sang executor ngay khi event được publish. Nếu event được publish trong transaction, listener bất đồng bộ có thể bắt đầu trước khi transaction commit. Nó có thể đọc dữ liệu khi dữ liệu chưa được commit hoặc thực hiện tác dụng phụ dù transaction nguồn sau đó rollback.

Nếu chỉ muốn xử lý sau khi dữ liệu đã commit, kết hợp `@Async` với `@TransactionalEventListener(phase = AFTER_COMMIT)`:

```java
@Component
public class OrderNotificationListener {

    private final NotificationService notifications;

    public OrderNotificationListener(
            NotificationService notifications) {
        this.notifications = notifications;
    }

    @Async("eventExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendNotification(OrderPlacedEvent event) {
        notifications.sendOrderConfirmation(event.orderId());
    }
}
```

Trong ví dụ này, listener chỉ được kích hoạt sau khi transaction commit thành công, rồi việc xử lý được chuyển sang executor tên `eventExecutor`. Nếu transaction rollback, listener không được gửi công việc vào executor.

Cần khai báo bean executor có tên tương ứng nếu ứng dụng muốn dùng executor riêng. Nếu không chỉ định tên, Spring dùng executor mặc định được cấu hình cho async support.

## 6. Transaction không tự truyền sang thread @Async

Transaction imperative của Spring thường gắn với thread hiện tại thông qua thread-bound context. Khi `@Async` chuyển công việc sang thread khác, transaction của thread gọi không tự truyền sang thread thực thi.

Ví dụ:

```java
@Transactional
public void createOrder() {
    orders.save(new Order());
    events.publishEvent(new OrderPlacedEvent(123L));
}
```

Nếu listener chạy bằng `@Async`, thread xử lý listener không tham gia transaction của `createOrder()`. Việc listener chạy sau commit nhờ `AFTER_COMMIT` chỉ bảo đảm dữ liệu nguồn đã commit trước khi listener được kích hoạt; nó không chuyển transaction cũ sang thread mới.

Nếu listener cần ghi database, hãy gọi một service có `@Transactional` từ thread async:

```java
@Service
public class NotificationService {

    @Transactional
    public void saveNotification(Long orderId) {
        // Ghi notification trong transaction riêng.
    }
}
```

Khi method này được gọi từ thread async không có transaction, propagation mặc định `REQUIRED` sẽ tạo transaction mới. Không dựa vào transaction của thread publish event.

Có một trường hợp cần phân biệt: listener `AFTER_COMMIT` chạy đồng bộ trên thread transaction ban đầu. Khi callback được gọi, transaction đã commit nhưng tài nguyên transaction có thể vẫn còn được gắn tạm thời. Nếu listener thực hiện thao tác ghi và tham gia transaction cũ bằng `REQUIRED`, thay đổi có thể không được commit thêm lần nữa. Với thao tác ghi database trong listener AFTER_COMMIT đồng bộ, hãy dùng một service transaction riêng với `Propagation.REQUIRES_NEW`.

## 7. Xử lý exception trong @Async listener

Với listener đồng bộ, exception từ listener có thể truyền ngược về nơi publish event và ảnh hưởng đến luồng gọi. Với listener `@Async`, exception xảy ra trong thread executor nên không truyền trực tiếp về caller đã publish event.

Nếu method async trả về `void`, exception không có kết quả trả về để caller quan sát; mặc định Spring ghi log. Có thể cấu hình `AsyncUncaughtExceptionHandler` để xử lý exception của method void.

Nếu cần quan sát kết quả và lỗi, method async có thể trả về `CompletableFuture`:

```java
@Async("eventExecutor")
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public CompletableFuture<Void> process(OrderPlacedEvent event) {
    notificationService.sendOrderConfirmation(event.orderId());

    return CompletableFuture.completedFuture(null);
}
```

Caller publish event không nhận trực tiếp Future này vì Spring gọi listener sau transaction phase. Muốn theo dõi trạng thái xử lý, cần cơ chế giám sát riêng như log có correlation ID, bảng trạng thái job, metric hoặc message broker.

Cũng cần cấu hình executor hợp lý: số thread, queue capacity, chính sách từ chối task, thời gian shutdown và cách xử lý khi hệ thống quá tải. Không nên dùng một executor không giới hạn khiến số task tăng liên tục khi listener chậm hơn tốc độ publish event.

`@Async` hoạt động thông qua Spring proxy. Lời gọi nội bộ trong cùng bean như `this.process(...)` không đi qua proxy nên có thể không kích hoạt async advice. Hãy gọi method từ một Spring bean khác hoặc tách xử lý async thành component riêng.

## 8. Rollback và @Async: các tình huống thường gặp

| Cách khai báo listener | Transaction commit | Transaction rollback | Không có transaction |
|---|---|---|---|
| `@EventListener` | Chạy ngay lúc publish | Đã chạy trước khi rollback | Chạy ngay |
| `@TransactionalEventListener(AFTER_COMMIT)` | Chạy sau commit | Không chạy | Bỏ qua mặc định |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Không chạy | Chạy sau rollback | Bỏ qua mặc định |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Chạy sau khi hoàn tất | Chạy sau khi hoàn tất | Bỏ qua mặc định |
| `@TransactionalEventListener(fallbackExecution = true)` | Theo phase đã chọn | Theo phase đã chọn | Chạy ngay theo fallback |
| `@Async @EventListener` | Được gửi executor lúc publish | Vẫn có thể đã được gửi executor trước rollback | Được gửi executor |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Chỉ gửi executor sau commit | Không gửi executor | Bỏ qua mặc định |

Bảng giả định event được publish đúng lúc listener đăng ký và có transaction imperative đang hoạt động khi cần transaction phase. Nếu cấu hình một ApplicationEventMulticaster dùng executor chung hoặc reactive transaction, cần xét thêm cơ chế context tương ứng.

## 9. Event sau commit có bảo đảm được xử lý không?

`@TransactionalEventListener(AFTER_COMMIT)` giải quyết vấn đề thời điểm: listener chỉ chạy khi transaction đã commit. Tuy nhiên, event của Spring ApplicationContext là cơ chế trong bộ nhớ của tiến trình. Nó không tự lưu event bền vững vào database hoặc broker.

Ví dụ, transaction đã commit đơn hàng nhưng ứng dụng bị dừng trước khi task async xử lý event. Dữ liệu đơn hàng vẫn tồn tại, nhưng việc gửi thông báo hoặc đồng bộ sang hệ thống khác có thể chưa xảy ra. `@Async` cũng không tự cung cấp retry hoặc bảo đảm delivery.

Nếu nghiệp vụ yêu cầu không được mất event sau khi transaction commit, hãy cân nhắc transactional outbox:

1. Trong cùng transaction tạo/cập nhật dữ liệu nghiệp vụ, ghi thêm một bản ghi vào bảng outbox.
2. Commit một lần để cả dữ liệu nghiệp vụ và outbox cùng tồn tại hoặc cùng rollback.
3. Một worker đọc các bản ghi outbox chưa xử lý và gửi đến message broker hoặc dịch vụ đích.
4. Đánh dấu đã xử lý sau khi gửi thành công; retry khi gặp lỗi tạm thời.
5. Listener phía nhận phải idempotent vì retry có thể tạo thông điệp trùng.

Outbox làm cho ý định phát event được lưu bền vững cùng transaction nghiệp vụ. Đây là lựa chọn phù hợp hơn khi không thể chấp nhận mất thông báo do process crash. Với yêu cầu đơn giản, `@TransactionalEventListener` kết hợp `@Async` vẫn hữu ích, nhưng cần hiểu rằng nó không phải message queue bền vững.

## 10. Lỗi thường gặp và cách khắc phục

**Dùng @EventListener rồi gửi email trước commit.** Nếu transaction rollback, email vẫn đã được gửi. Hãy dùng `@TransactionalEventListener(AFTER_COMMIT)` khi thông báo chỉ có ý nghĩa sau khi lưu thành công.

**Dùng @TransactionalEventListener nhưng không có transaction.** Listener mặc định bị bỏ qua. Hãy publish trong service transaction hoặc bật `fallbackExecution = true` nếu thực sự chấp nhận chạy ngay khi không có transaction.

**Cho rằng @Async kế thừa transaction của caller.** Thread executor không tự nhận transaction context của thread publish. Hãy mở transaction riêng trong service được gọi từ async listener khi cần ghi database.

**Cho rằng AFTER_COMMIT listener có thể ghi vào transaction vừa commit.** Transaction đã hoàn tất; các thao tác ghi cần transaction mới. Với listener đồng bộ, dùng `REQUIRES_NEW`; với listener async, service `@Transactional` chạy trên thread worker sẽ mở transaction mới nếu chưa có.

**Cho rằng async listener đã chạy nghĩa là tác vụ đã thành công.** Caller chỉ gửi task đến executor. Listener có thể thất bại sau đó. Hãy theo dõi lỗi, metric, retry và trạng thái xử lý.

**Dùng event trong bộ nhớ như hàng đợi bền vững.** Process crash có thể làm mất công việc sau commit. Dùng outbox hoặc broker có cơ chế lưu bền vững khi cần bảo đảm delivery.

**Xóa danh sách event quá sớm rồi kỳ vọng rollback tự khôi phục event.** `@AfterDomainEventPublication` được gọi sau khi publish vào ApplicationContext, không đợi transaction commit. Hãy dùng outbox nếu cần khôi phục và gửi lại event một cách đáng tin cậy.

**Đặt @Async và @Transactional trên cùng bean rồi gọi nội bộ.** Self-invocation có thể bỏ qua proxy. Tách method xử lý sang bean riêng để proxy async và transaction hoạt động đúng.

## 11. Quy trình thiết kế listener theo nghiệp vụ

1. Xác định event có được phép xử lý trước commit hay phải chờ dữ liệu commit thành công.
2. Nếu cần xử lý theo transaction outcome, dùng `@TransactionalEventListener` và chọn phase rõ ràng.
3. Bảo đảm event được publish trong transaction nghiệp vụ nếu cần AFTER_COMMIT hoặc AFTER_ROLLBACK.
4. Chỉ bật `fallbackExecution` khi có định nghĩa rõ hành vi lúc không có transaction.
5. Dùng `@Async` cho tác vụ chậm hoặc độc lập, và cấu hình executor có giới hạn.
6. Mở transaction mới cho thao tác ghi database trong async worker; với listener AFTER_COMMIT đồng bộ, dùng `REQUIRES_NEW` khi cần ghi.
7. Xử lý exception và giám sát kết quả async thay vì giả định publish thành công đồng nghĩa xử lý thành công.
8. Dùng transactional outbox khi event phải được giao bền vững sau commit.
9. Kiểm thử riêng ba tình huống: commit, rollback và không có transaction; kiểm thử thêm listener async, executor quá tải và lỗi xử lý.

## Kết luận

`@EventListener` chạy khi event được publish, nên có thể xử lý trước khi transaction commit. `@TransactionalEventListener` gắn xử lý với AFTER_COMMIT, AFTER_ROLLBACK hoặc các phase khác; mặc định không chạy nếu không có transaction. `@Async` chuyển listener sang thread khác và không truyền transaction của thread publish. Hãy kết hợp AFTER_COMMIT với async khi cần xử lý nền sau khi dữ liệu đã commit, mở transaction riêng cho thao tác ghi của worker và dùng transactional outbox nếu yêu cầu nghiệp vụ cần bảo đảm event không bị mất.