# @DomainEvents và @AfterDomainEventPublication

Trong **Spring Data Relational JDBC**, aggregate root có thể ghi nhận những sự kiện nghiệp vụ phát sinh trong quá trình thay đổi trạng thái. Ví dụ, khi đơn hàng chuyển từ NEW sang PAID, nghiệp vụ có thể tạo sự kiện `OrderPaid` để các thành phần khác gửi thông báo, cập nhật read model hoặc khởi động một quy trình tiếp theo.

Spring Data Commons cung cấp hai annotation để hỗ trợ cách làm này:

- **`@DomainEvents`** đánh dấu phương thức trên aggregate root dùng để cung cấp một hoặc nhiều domain event cho Spring Data publish.
- **`@AfterDomainEventPublication`** đánh dấu phương thức được gọi sau khi các event đó đã được publish. Thường dùng để xóa danh sách event đang chờ phát khỏi aggregate.

Hai annotation giúp aggregate giữ event cùng với thay đổi nghiệp vụ, còn repository infrastructure đảm nhiệm việc publish event khi gọi các repository method phù hợp. Chúng không tự tạo event từ mọi thay đổi property và cũng không đồng nghĩa với việc database đã commit. Cần hiểu rõ ranh giới giữa hành động nghiệp vụ, repository call, application event và transaction.

## 1. Domain event là gì?

Domain event là một đối tượng biểu diễn một sự việc có ý nghĩa trong nghiệp vụ đã xảy ra. Nó thường được đặt tên ở dạng quá khứ, chẳng hạn:

- `OrderPlaced`: đơn hàng đã được tạo.
- `OrderPaid`: đơn hàng đã được thanh toán.
- `InventoryReserved`: hàng tồn kho đã được giữ chỗ.
- `CustomerAddressChanged`: địa chỉ khách hàng đã thay đổi.
- `OrderCancelled`: đơn hàng đã bị hủy.

Một domain event nên trả lời được câu hỏi: **Điều gì đã xảy ra trong domain?**

Ví dụ, thay đổi property `status` từ NEW sang PAID là một thay đổi trạng thái. Sự kiện `OrderPaid` diễn đạt ý nghĩa nghiệp vụ của thay đổi đó.

```java
import java.time.Instant;

public record OrderPaid(
    Long orderId,
    Instant occurredAt
) {}
```

Event record chứa ID của aggregate và thời điểm sự kiện xảy ra. Tùy nghiệp vụ, event có thể chứa thêm dữ liệu cần thiết cho consumer, chẳng hạn payment reference hoặc currency. Nên chỉ đưa vào những thông tin mà consumer cần và có ý nghĩa ổn định.

### 1.1. Domain event khác với entity lifecycle event

Hai khái niệm này không giống nhau:

| Domain event | Lifecycle event |
|---|---|
| Mô tả sự kiện nghiệp vụ | Mô tả một giai đoạn persistence |
| Ví dụ `OrderPaid` | Ví dụ `AfterSaveEvent` |
| Được tạo khi quy tắc nghiệp vụ xảy ra | Được Spring Data phát khi aggregate được lưu, đọc hoặc xóa |
| Có ý nghĩa với các consumer nghiệp vụ | Thường hữu ích cho logging, auditing kỹ thuật hoặc tích hợp lifecycle |
| Không nhất thiết mọi lần save đều tạo event | Gắn với thao tác persistence tương ứng |

Không nên phát `OrderPaid` chỉ vì repository được gọi. Một đơn hàng có thể được lưu khi cập nhật địa chỉ, ghi chú hoặc thông tin giao hàng. Chỉ hành động thanh toán mới tạo event `OrderPaid`.

### 1.2. Domain event không phải message broker

Khi Spring Data publish domain event, nó publish một Spring application event trong application context. Điều đó không tự động gửi message tới Kafka, RabbitMQ hoặc một hệ thống bên ngoài.

Một listener trong cùng ứng dụng có thể nhận event. Nếu cần gửi ra broker, ứng dụng phải triển khai phần tích hợp tương ứng. Nếu việc gửi phải bền vững qua sự cố tiến trình, cần cân nhắc transactional outbox.

## 2. Vai trò của @DomainEvents

`@DomainEvents` nằm trong Spring Data Commons và được dùng trên một phương thức của aggregate root.

Phương thức được đánh dấu:

- Không nhận tham số.
- Có thể trả về một event object.
- Hoặc trả về một collection các event object.

Ví dụ:

```java
class PurchaseOrder {

    private final List<Object> domainEvents = new ArrayList<>();

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }
}
```

Khi repository infrastructure xử lý một repository method có hỗ trợ domain event publication, Spring Data gọi phương thức này để lấy các event đang chờ publish.

`@DomainEvents` không phải annotation đặt trên từng event class. Nó đánh dấu **phương thức cung cấp event của aggregate root**.

### 2.1. Một event hoặc nhiều event

Có thể trả một event:

```java
@DomainEvents
public Object domainEvent() {
    return new OrderPaid(id, Instant.now());
}
```

Hoặc trả nhiều event:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return List.copyOf(events);
}
```

Cách trả collection phù hợp khi một hành động nghiệp vụ tạo ra nhiều sự kiện hoặc aggregate có nhiều event đang chờ publish.

Dùng collection rỗng khi không có event nào cần publish. Không tạo event giả chỉ để phương thức luôn có kết quả.

### 2.2. Event phải được ghi nhận từ hành vi domain

Spring Data không tự suy luận event từ sự thay đổi property. Aggregate cần chủ động ghi nhận event khi một hành vi nghiệp vụ hợp lệ xảy ra.

```java
public void markPaid(Instant occurredAt) {
    if (status != OrderStatus.NEW) {
        throw new IllegalStateException("Only a NEW order can be paid");
    }

    status = OrderStatus.PAID;
    events.add(new OrderPaid(id, occurredAt));
}
```

Ở đây, quy tắc chuyển trạng thái và việc tạo event nằm cạnh nhau. Nếu điều kiện thanh toán không hợp lệ, exception được ném ra trước khi trạng thái và event được thay đổi.

Cách làm này giúp tránh trường hợp application service tự đoán event từ hai lần đọc object rồi vô tình phát sai sự kiện.

## 3. Vai trò của @AfterDomainEventPublication

`@AfterDomainEventPublication` đánh dấu một phương thức trên aggregate root. Spring Data gọi phương thức này sau khi tất cả domain event được cung cấp đã được publish.

Một cách sử dụng phổ biến là xóa danh sách event đang chờ:

```java
@AfterDomainEventPublication
public void clearDomainEvents() {
    events.clear();
}
```

Lý do cần xóa event là aggregate có thể được save nhiều lần trong vòng đời sử dụng của cùng một object. Nếu danh sách không được dọn, một lần save sau có thể publish lại những event cũ.

Ví dụ:

```text
1. Aggregate ghi nhận OrderPaid.
2. Repository save aggregate.
3. Spring Data lấy event và publish.
4. @AfterDomainEventPublication chạy.
5. Danh sách event đang chờ được xóa.
6. Một lần save sau không publish lại OrderPaid cũ.
```

### 3.1. Phương thức callback không phải transaction callback

Tên annotation chỉ nói rằng phương thức được gọi sau khi event đã được publish. Nó **không** có nghĩa là:

- Database transaction đã commit.
- Tất cả listener đã hoàn tất xử lý.
- Message đã được gửi thành công tới broker.
- Consumer bên ngoài đã nhận event.
- Side effect không thể thất bại.

`@AfterDomainEventPublication` là callback dọn dẹp trạng thái event trong aggregate. Nó không thay thế `@TransactionalEventListener` và không phải cơ chế bảo đảm phát event bền vững.

### 3.2. Không xóa event trước khi cung cấp chúng

Nếu phương thức `@DomainEvents` trả về danh sách rỗng vì event đã bị xóa trước repository call, không có gì để publish.

Chỉ dọn event trong phương thức được đánh dấu `@AfterDomainEventPublication` hoặc theo cơ chế có chủ đích khác. Tránh xóa danh sách ngay sau khi gọi phương thức domain tạo event.

## 4. Ví dụ đầy đủ với hai annotation

Giả sử đơn hàng có trạng thái NEW và PAID. Khi thanh toán thành công, aggregate đổi trạng thái và ghi nhận event.

### 4.1. Event object

```java
import java.time.Instant;

public record OrderPaid(
    Long orderId,
    Instant occurredAt
) {}
```

### 4.2. Aggregate root

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.annotation.Transient;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private OrderStatus status;

    @Transient
    private final List<Object> events = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a NEW order can be paid"
            );
        }

        status = OrderStatus.PAID;
        events.add(new OrderPaid(id, Instant.now()));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`@Transient` trên danh sách event rất quan trọng với kiểu triển khai thủ công: danh sách này là trạng thái tạm dùng trong bộ nhớ, không phải dữ liệu cần ánh xạ thành cột hoặc bảng con của aggregate.

Ví dụ giả định ID đã được gán khi tạo aggregate. Nếu database chỉ sinh ID khi insert, event được tạo trước lần save có thể chưa có ID. Trong trường hợp đó, hãy cân nhắc ID do ứng dụng sinh (ví dụ UUID), hoặc thiết kế event không phụ thuộc vào database-generated ID tại thời điểm domain action xảy ra.

### 4.3. Repository

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Không cần viết code publish event trong repository. Spring Data repository infrastructure phát hiện các phương thức được đánh dấu trên aggregate root và publish các event khi gọi repository methods phù hợp.

### 4.4. Application service

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {

    private final PurchaseOrderRepository repository;

    public PaymentService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void pay(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found")
            );

        order.markPaid();

        repository.save(order);
    }
}
```

Luồng xử lý:

1. Service tải aggregate.
2. Aggregate kiểm tra quy tắc nghiệp vụ trong `markPaid`.
3. Aggregate đổi trạng thái và thêm `OrderPaid` vào danh sách event.
4. Service gọi `repository.save`.
5. Spring Data lấy event từ phương thức `domainEvents` và publish.
6. Sau khi publish, Spring Data gọi `clearDomainEvents`.
7. Transaction service hoàn tất theo quy tắc commit/rollback.

Event được tạo bởi hành vi domain; repository chỉ là điểm kích hoạt cơ chế publish.

## 5. Dùng AbstractAggregateRoot thay vì tự viết danh sách event

Spring Data Commons cung cấp lớp tiện ích `AbstractAggregateRoot`. Lớp này đã triển khai cơ chế thu thập và cung cấp event dựa trên `@DomainEvents` và `@AfterDomainEventPublication`.

Thay vì tự khai báo list, getter và phương thức clear, aggregate có thể kế thừa lớp này:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private Long id;

    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a NEW order can be paid"
            );
        }

        status = OrderStatus.PAID;

        registerEvent(
            new OrderPaid(id, Instant.now())
        );
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`registerEvent` là phương thức được cung cấp bởi `AbstractAggregateRoot`. Nó ghi nhận event để repository có thể publish khi gọi save hoặc delete với aggregate instance.

### 5.1. registerEvent và andEvent

Hai phương thức tiện ích chính:

| Phương thức | Giá trị trả về | Cách dùng |
|---|---|---|
| `registerEvent(event)` | Chính event vừa đăng ký | Khi chỉ cần ghi nhận event |
| `andEvent(event)` | Aggregate hiện tại | Khi muốn nối thao tác đăng ký event vào một biểu thức |

Ví dụ:

```java
registerEvent(new OrderPaid(id, Instant.now()));
```

Hoặc:

```java
return andEvent(new OrderPaid(id, Instant.now()));
```

`AbstractAggregateRoot` còn cung cấp `andEventsFrom(aggregate)` để thêm các event đang giữ trong một aggregate khác vào aggregate hiện tại. Dùng các phương thức này khi mô hình nghiệp vụ cần chuyển tiếp event có chủ đích.

### 5.2. Khi nào dùng AbstractAggregateRoot?

Lớp tiện ích phù hợp khi:

- Aggregate root là class có thể kế thừa một lớp cơ sở.
- Muốn dùng cơ chế event buffer có sẵn.
- Muốn tránh lặp lại code quản lý danh sách event.
- Không có yêu cầu đặc biệt về cách lưu hoặc dọn event.

Tự dùng hai annotation phù hợp khi aggregate đã có base class khác, cần kiểm soát cấu trúc event riêng hoặc muốn giữ domain model không phụ thuộc vào lớp tiện ích này.

Không cần vừa kế thừa `AbstractAggregateRoot` vừa tự khai báo một danh sách event và hai annotation tương tự. Hãy chọn một cách triển khai rõ ràng.

## 6. Repository methods nào kích hoạt domain event publication?

Spring Data gắn cơ chế event publication với các repository method nhận aggregate instance. Các phương thức thường gặp là:

| Repository method | Có aggregate instance để lấy event? |
|---|---|
| `save(aggregate)` | Có |
| `saveAll(aggregates)` | Có các aggregate được truyền vào |
| `delete(aggregate)` | Có |
| `deleteAll(aggregates)` | Có các aggregate được truyền vào |
| `deleteById(id)` | Không có aggregate instance được truyền vào |
| `deleteAll()` | Không có danh sách aggregate instance được truyền vào |

Tài liệu Spring Data Commons nêu rõ `deleteById` không thuộc nhóm phương thức publish event theo cơ chế này, vì implementation có thể xóa bằng query và không tải aggregate instance. Các method bulk hoặc method bổ sung có thể khác theo module và phiên bản; hãy kiểm tra contract của phiên bản đang dùng.

### 6.1. Vì sao deleteById không tự phát domain event?

Khi gọi:

```java
repository.deleteById(orderId);
```

Repository chỉ nhận ID. Nó không nhất thiết tải aggregate trước khi xóa. Do đó, không có object aggregate root để gọi phương thức `@DomainEvents`.

Nếu nghiệp vụ cần phát event như `OrderCancelled` hoặc `OrderDeleted` với thông tin từ aggregate:

```java
PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();

order.cancel();

repository.save(order);
repository.delete(order);
```

Đây chỉ là ví dụ minh họa; nghiệp vụ thật cần xác định event nào phù hợp với việc hủy hoặc xóa. Nếu chỉ cần ghi nhận một thao tác xóa theo ID, application service có thể tạo và publish một event riêng sau khi thực hiện quy tắc cần thiết.

### 6.2. Bulk modifying query không tự tạo domain event cho từng aggregate

Một câu SQL bulk như:

```java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = 'EXPIRED'
    WHERE expires_at < :now
    """)
int expireOrders(Instant now);
```

thực hiện trực tiếp trên database. Framework không có từng aggregate instance đã thay đổi để gọi phương thức `@DomainEvents`. Vì vậy, không kỳ vọng query bulk tự phát một domain event cho từng đơn hàng.

Nếu nghiệp vụ cần event cho từng đơn, phải thiết kế quy trình lấy aggregate và xử lý có chủ đích, hoặc ghi event/outbox theo một chiến lược bulk riêng.

## 7. Event được publish như Spring application event

Khi repository infrastructure lấy event từ aggregate, nó publish event qua cơ chế application event của Spring. Listener trong cùng application context có thể nhận event.

Ví dụ:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidLogger {

    @EventListener
    public void onOrderPaid(OrderPaid event) {
        System.out.println(
            "Order paid: " + event.orderId()
        );
    }
}
```

`@EventListener` đánh dấu phương thức listener cho Spring application event. Kiểu tham số giúp Spring xác định event mà listener muốn nhận.

Có thể dùng `ApplicationListener<OrderPaid>` thay cho annotation:

```java
@Component
public class OrderPaidListener
        implements ApplicationListener<OrderPaid> {

    @Override
    public void onApplicationEvent(OrderPaid event) {
        // Xử lý event.
    }
}
```

Chọn cách nào tùy phong cách ứng dụng. Không cần đăng ký listener trong aggregate root; aggregate chỉ tạo và cung cấp event.

### 7.1. Mặc định event listener có thể chạy đồng bộ

Với cấu hình application event multicaster mặc định, listener thường được gọi đồng bộ trong luồng publish. Nếu ứng dụng cấu hình executor bất đồng bộ hoặc listener dùng `@Async`, cách thực thi sẽ khác.

Không nên để listener gửi HTTP hoặc thực hiện tác vụ lâu trong luồng repository save nếu điều đó kéo dài transaction và giữ connection không cần thiết. Nếu listener chỉ nên chạy sau commit, dùng transactional event listener.

## 8. Phân biệt @AfterDomainEventPublication với AFTER_COMMIT

Đây là điểm dễ nhầm nhất.

`@AfterDomainEventPublication` được gọi sau khi Spring Data publish các domain event lấy từ aggregate. `@TransactionalEventListener(phase = AFTER_COMMIT)` được gọi theo transaction synchronization sau khi transaction commit thành công.

| Cơ chế | Điều kiện gọi | Mục đích |
|---|---|---|
| `@AfterDomainEventPublication` | Sau khi các event từ aggregate đã được publish | Dọn event buffer hoặc xử lý trạng thái event nội bộ |
| `@EventListener` | Khi Spring application event được publish | Xử lý event trong application context |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi transaction commit | Chạy side effect chỉ khi dữ liệu đã commit |
| Transactional outbox | Outbox record commit cùng dữ liệu nghiệp vụ | Phát thông điệp bền vững và có thể retry |

Ví dụ một service có transaction:

```java
@Transactional
public void pay(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

    order.markPaid();
    repository.save(order);

    // Transaction có thể vẫn chưa commit tại đây.
}
```

Repository save kích hoạt domain event publication. Phương thức `@AfterDomainEventPublication` có thể đã xóa event buffer, trong khi transaction của service vẫn đang mở.

Nếu một thao tác sau đó thất bại và transaction rollback, việc dọn event buffer không được hoàn tác cùng database. Vì thế, callback này không thể được dùng như bằng chứng rằng nghiệp vụ đã commit.

### 8.1. Chỉ xử lý sau commit

Nếu event cần kích hoạt email hoặc gọi hệ thống khác sau khi đơn hàng đã commit:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPaidNotificationHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendNotification(OrderPaid event) {
        // Gửi thông báo sau khi transaction commit.
    }
}
```

Nếu transaction rollback, listener phase AFTER_COMMIT không được gọi theo mặc định. Event được publish trong transaction có thể được đăng ký với transaction synchronization để xử lý đúng phase.

Nếu không có transaction đang hoạt động, `@TransactionalEventListener` mặc định không xử lý event. Chỉ bật `fallbackExecution` nếu ứng dụng thật sự muốn xử lý event cả khi không có transaction.

### 8.2. Listener AFTER_COMMIT không thể rollback transaction gốc

Khi listener AFTER_COMMIT chạy, transaction đã commit. Nếu gửi email thất bại, database không thể rollback trạng thái PAID chỉ vì email không gửi được.

Nếu cần thử lại, hãy thiết kế retry, idempotency hoặc hàng đợi bền vững. Đừng coi lỗi listener sau commit là lỗi có thể hoàn tác transaction gốc.

## 9. Vấn đề event bị mất và Transactional Outbox

Domain event trong aggregate thường được giữ trong bộ nhớ. Việc Spring publish event vào application context không tự lưu event vào database hay broker.

Có một khoảng thời gian rủi ro:

1. Database commit thành công.
2. Ứng dụng dừng trước khi listener gửi message ra ngoài.
3. Event trong bộ nhớ biến mất khi tiến trình dừng.
4. Consumer bên ngoài không nhận được message.

`@TransactionalEventListener(AFTER_COMMIT)` giải quyết điều kiện thời điểm, nhưng không tạo ra hàng đợi bền vững.

Với tích hợp quan trọng, dùng Transactional Outbox:

1. Aggregate thực hiện hành vi nghiệp vụ và tạo domain event.
2. Service lưu aggregate.
3. Service ghi outbox record trong cùng database transaction.
4. Transaction commit cả dữ liệu aggregate và outbox.
5. Worker đọc các record chưa phát và gửi tới broker.
6. Worker đánh dấu đã phát hoặc retry khi lỗi.

Ví dụ bảng outbox:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

Nếu transaction rollback, cả thay đổi aggregate và outbox record đều rollback. Nếu commit, worker có thể tiếp tục gửi event sau khi ứng dụng khởi động lại.

Outbox thường cung cấp delivery ít nhất một lần (at-least-once), không tự bảo đảm exactly-once. Consumer cần idempotency dựa trên event ID hoặc khóa nghiệp vụ.

## 10. Dùng @DomainEvents khi gọi JdbcAggregateTemplate?

Cơ chế publication được gắn với Spring Data repository proxy. Khi gọi repository method phù hợp, interceptor của repository tìm các event được cung cấp bởi aggregate root rồi publish.

`JdbcAggregateTemplate` là API template trực tiếp, không phải repository proxy. Không nên mặc định rằng gọi:

```java
aggregateTemplate.save(order);
```

sẽ kích hoạt cùng cơ chế `@DomainEvents` và `@AfterDomainEventPublication` như repository save.

Nếu use case dùng trực tiếp template, có thể publish event một cách tường minh bằng `ApplicationEventPublisher` sau khi thao tác template đã chạy trong transaction:

```java
@Transactional
public void pay(Long orderId) {
    PurchaseOrder order = aggregateTemplate.findById(
        orderId,
        PurchaseOrder.class
    );

    order.markPaid();

    PurchaseOrder saved = aggregateTemplate.update(order);

    publisher.publishEvent(
        new OrderPaid(saved.getId(), Instant.now())
    );
}
```

Nếu event phải được xử lý sau commit, listener vẫn nên dùng `@TransactionalEventListener(AFTER_COMMIT)`. Nếu cần delivery bền vững, ghi outbox trong cùng transaction.

Một lựa chọn khác là dùng repository cho use case cần cơ chế event publication tích hợp sẵn. Điều quan trọng là chọn một điểm publish rõ ràng, tránh vừa để repository tự publish vừa tự gọi `publishEvent` cho cùng một event.

## 11. Event buffer và các vấn đề thiết kế

### 11.1. Event buffer không phải dữ liệu persistence

Danh sách event đang chờ là trạng thái tạm của aggregate trong bộ nhớ. Với cách triển khai thủ công, đánh dấu nó `@Transient` để Spring Data JDBC không cố ánh xạ thành property database.

Với `AbstractAggregateRoot`, lớp cơ sở cung cấp cơ chế quản lý event buffer. Nếu tự viết cơ chế riêng, hãy bảo đảm các field phục vụ event không bị mapping như dữ liệu aggregate.

### 11.2. Không giữ event cũ qua nhiều use case

Sau khi event đã được publish, `@AfterDomainEventPublication` nên dọn buffer. Điều đó tránh event cũ bị phát lại ở lần save tiếp theo.

Nếu aggregate bị tái sử dụng trong bộ nhớ qua nhiều hành động, hãy xác định rõ event nào thuộc hành động nào. Thông thường, mỗi aggregate instance chỉ nên được dùng trong một phạm vi use case có kiểm soát.

### 11.3. Không dùng event để thay thế dữ liệu domain

Event là bản ghi về điều đã xảy ra, không phải nguồn thay thế cho trạng thái aggregate hiện tại. Consumer cần trạng thái mới nhất có thể tải aggregate qua repository nếu nghiệp vụ yêu cầu.

Một event tốt thường mang snapshot đủ dùng cho consumer, nhưng không nên nhồi toàn bộ aggregate vào event nếu điều đó tạo phụ thuộc quá chặt.

### 11.4. Đặt tên event ở thì quá khứ

Tên `OrderPaid` diễn đạt một sự việc đã xảy ra. Tên `PayOrder` thường giống command hơn: nó yêu cầu hệ thống thực hiện một hành động.

Phân biệt:

| Command | Domain event |
|---|---|
| `PayOrder` | `OrderPaid` |
| `PlaceOrder` | `OrderPlaced` |
| `CancelOrder` | `OrderCancelled` |
| `ReserveInventory` | `InventoryReserved` |

Command có thể thất bại hoặc bị từ chối. Event chỉ nên được ghi nhận sau khi hành động nghiệp vụ tương ứng thành công trong domain model.

### 11.5. Event nên bất biến

Java record là lựa chọn phù hợp cho nhiều event:

```java
public record OrderPaid(
    Long orderId,
    Instant occurredAt,
    String paymentReference
) {}
```

Sau khi event được publish, consumer không nên sửa event object để ảnh hưởng tới consumer khác. Dữ liệu bất biến giúp event dễ kiểm thử, ghi log và chuyển thành message.

## 12. Xử lý event khi saveAll và delete nhiều aggregate

Một repository method nhận nhiều aggregate có thể kích hoạt event publication cho các aggregate được truyền vào, theo contract của module và phiên bản Spring Data đang sử dụng.

Ví dụ:

```java
repository.saveAll(orders);
```

Nếu mỗi aggregate có event buffer riêng, mỗi aggregate có thể cung cấp event của nó. Spring Data publish những event mà các aggregate cung cấp, sau đó gọi callback dọn event tương ứng.

Với delete theo collection:

```java
repository.deleteAll(orders);
```

Repository nhận aggregate instance nên có thể lấy domain event từ những instance đó theo cơ chế event publication được hỗ trợ.

Ngược lại:

```java
repository.deleteAll();
repository.deleteAllById(ids);
```

không cung cấp danh sách aggregate instance cho cơ chế này. Nếu nghiệp vụ yêu cầu domain event cho từng aggregate bị xóa, cần tải và xử lý các aggregate hoặc thiết kế một event bulk có ý nghĩa nghiệp vụ riêng.

Đối với batch lớn, không nên tải toàn bộ aggregate chỉ để tạo event nếu có cách ghi outbox hoặc xử lý theo batch hiệu quả hơn. Hãy cân nhắc chi phí truy vấn, bộ nhớ và yêu cầu audit/event của nghiệp vụ.

## 13. Kiểm thử @DomainEvents và @AfterDomainEventPublication

Nên kiểm tra ba hành vi:

1. Aggregate chỉ tạo event khi hành vi nghiệp vụ hợp lệ.
2. Repository save/delete method phù hợp làm event được publish.
3. Event buffer được dọn sau khi publication hoàn tất.

### 13.1. Unit test hành vi domain

```java
@Test
void payingOrderRegistersAnEvent() {
    PurchaseOrder order = new PurchaseOrder(
        42L,
        OrderStatus.NEW
    );

    order.markPaid();

    assertThat(order.domainEvents())
        .singleElement()
        .isInstanceOf(OrderPaid.class);
}
```

Nếu dùng `AbstractAggregateRoot`, có thể kiểm tra qua phương thức test/package-private phù hợp hoặc kiểm tra event bằng integration test qua repository.

### 13.2. Kiểm tra repository publication

Một integration test có thể đăng ký listener test để ghi nhận event:

```java
@Component
class TestOrderEventListener {

    private final List<OrderPaid> received = new CopyOnWriteArrayList<>();

    @EventListener
    public void on(OrderPaid event) {
        received.add(event);
    }

    public List<OrderPaid> receivedEvents() {
        return List.copyOf(received);
    }

    public void clear() {
        received.clear();
    }
}
```

Test:

```java
@Test
void repositorySavePublishesAggregateEvents() {
    PurchaseOrder order = repository.findById(42L).orElseThrow();

    order.markPaid();
    repository.save(order);

    assertThat(testListener.receivedEvents())
        .extracting(OrderPaid::orderId)
        .containsExactly(42L);
}
```

Test này minh họa publication qua repository. Fixture database và trạng thái ban đầu phải bảo đảm đơn hàng 42 đang ở trạng thái NEW.

### 13.3. Kiểm tra event buffer được dọn

Với cách triển khai thủ công:

```java
order.markPaid();

assertThat(order.domainEvents()).hasSize(1);

order.clearDomainEvents();

assertThat(order.domainEvents()).isEmpty();
```

Trong integration test, có thể kiểm tra lần save thứ hai trên cùng aggregate instance không publish lại event cũ sau khi callback dọn buffer đã chạy.

### 13.4. Kiểm tra transaction rollback

Đăng ký một `@TransactionalEventListener(AFTER_COMMIT)` và chạy use case trong transaction bị rollback:

- Event có thể đã được publish từ repository.
- Callback `@AfterDomainEventPublication` có thể đã dọn event buffer.
- Listener AFTER_COMMIT không được gọi vì transaction không commit.

Test này chứng minh publication, dọn buffer và commit là ba thời điểm khác nhau.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Save aggregate nhưng không có event | Hành vi domain không đăng ký event hoặc repository method không thuộc nhóm được hỗ trợ | Kiểm tra event buffer và method save/delete |
| Event bị phát lại ở lần save sau | Không dọn event buffer | Dùng `@AfterDomainEventPublication` |
| deleteById không phát event | Chỉ truyền ID, không có aggregate instance | Tải aggregate hoặc publish event tường minh |
| Mỗi lần save đều phát OrderPaid | Tạo event trong getter hoặc callback không đúng chỗ | Đăng ký event trong hành vi domain khi chuyển trạng thái |
| Event listener chạy nhưng transaction rollback | Dùng `@EventListener` thường trong transaction | Dùng `@TransactionalEventListener(AFTER_COMMIT)` cho side effect sau commit |
| Nghĩ @AfterDomainEventPublication chạy sau commit | Nhầm callback publication với transaction phase | Phân biệt callback dọn buffer và AFTER_COMMIT |
| Danh sách event bị lưu xuống database | Event buffer không được đánh dấu transient | Dùng `@Transient` cho field event tự quản lý |
| JdbcAggregateTemplate.save không publish như repository | Template không đi qua repository event interceptor | Publish tường minh hoặc dùng repository |
| Bulk update không có event cho từng row | Query sửa trực tiếp database, không có aggregate instances | Thiết kế event/outbox cho bulk operation |
| Event gửi ra broker bị mất khi app crash | Application event chỉ tồn tại trong tiến trình | Dùng transactional outbox |
| Consumer xử lý trùng message | Retry hoặc delivery nhiều lần | Thiết kế consumer idempotent |
| Event thiếu aggregate ID | ID chỉ được database sinh sau khi insert | Dùng ID ứng dụng hoặc thiết kế event phù hợp thời điểm |
| Domain event chứa toàn bộ aggregate | Event phụ thuộc chặt vào model persistence | Tạo event payload riêng, chỉ chứa dữ liệu cần thiết |

## 15. Bài thực hành

**Bài 1.** `@DomainEvents` được đặt ở đâu?

*Đáp án:* Trên một phương thức của aggregate root. Phương thức không nhận tham số và trả về một event hoặc collection event.

**Bài 2.** `@AfterDomainEventPublication` dùng để làm gì?

*Đáp án:* Đánh dấu phương thức được gọi sau khi các event đã được publish. Thường dùng để xóa event buffer để tránh publish lặp.

**Bài 3.** Khi nào aggregate nên tạo `OrderPaid`?

*Đáp án:* Khi hành vi thanh toán hợp lệ thực sự chuyển đơn hàng sang trạng thái PAID, không phải mỗi khi repository save được gọi.

**Bài 4.** `deleteById` có tự publish domain event từ aggregate không?

*Đáp án:* Không theo cơ chế chuẩn này, vì repository chỉ nhận ID và có thể không tải aggregate instance. Cần tải aggregate hoặc publish event riêng theo nghiệp vụ.

**Bài 5.** `@AfterDomainEventPublication` có nghĩa database đã commit chưa?

*Đáp án:* Không. Nó chỉ được gọi sau publication. Transaction của service có thể vẫn mở và có thể rollback.

**Bài 6.** Listener chỉ được gửi email sau commit nên dùng gì?

*Đáp án:* `@TransactionalEventListener(phase = AFTER_COMMIT)`. Nếu cần đảm bảo message bền vững qua crash, cân nhắc outbox.

**Bài 7.** `AbstractAggregateRoot` hỗ trợ gì?

*Đáp án:* Cung cấp event buffer và các phương thức `registerEvent`, `andEvent`, `andEventsFrom` cùng cơ chế cung cấp và dọn event dựa trên hai annotation.

**Bài 8.** Vì sao event buffer thủ công nên được đánh dấu `@Transient`?

*Đáp án:* Đây là trạng thái tạm trong bộ nhớ, không phải property cần được Spring Data JDBC lưu vào schema.

**Bài 9.** Gọi trực tiếp `JdbcAggregateTemplate.save` có chắc chắn kích hoạt publication qua `@DomainEvents` không?

*Đáp án:* Không nên giả định như vậy. Cơ chế tích hợp dựa trên repository proxy. Khi dùng template trực tiếp, publish event tường minh hoặc dùng outbox.

## 16. Điều cần ghi nhớ

- `@DomainEvents` đánh dấu phương thức aggregate root cung cấp một event hoặc collection event; phương thức không nhận tham số.
- Event phải được ghi nhận từ hành vi nghiệp vụ hợp lệ, không tự phát chỉ vì property thay đổi hoặc repository được save.
- `@AfterDomainEventPublication` chạy sau khi event được publish và thường dùng để xóa event buffer.
- Callback này không phải transaction callback và không chứng minh database đã commit.
- `AbstractAggregateRoot` là lớp tiện ích có sẵn để quản lý event buffer bằng `registerEvent`, `andEvent` và `andEventsFrom`.
- Spring Data publication gắn với repository methods nhận aggregate instance như save/delete; `deleteById` không có aggregate để lấy event.
- Domain event được publish như Spring application event trong application context; nó không tự gửi message ra broker.
- Dùng `@TransactionalEventListener(AFTER_COMMIT)` khi consumer chỉ được xử lý sau commit.
- Với thông điệp cần bảo đảm bền vững, dùng transactional outbox và consumer idempotent.
- Khi tự quản lý event buffer trong aggregate, đánh dấu field bằng `@Transient` để nó không trở thành dữ liệu persistence.
- Khi dùng `JdbcAggregateTemplate` trực tiếp, không mặc định rằng repository event publication interceptor sẽ chạy.

### Tài liệu tham khảo chính thức

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): quy tắc sử dụng `@DomainEvents` và `@AfterDomainEventPublication`.
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AbstractAggregateRoot.html): `registerEvent`, `andEvent`, `andEventsFrom` và event buffer.
- [Spring Data Commons — EventPublishingRepositoryProxyPostProcessor API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.html): cơ chế repository proxy phát event từ aggregate root.
- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): application event publisher và listener trong Spring context.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và các transaction phase.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository và aggregate persistence trong Spring Data JDBC.

Khi triển khai, hãy xác định rõ event được tạo ở hành vi domain nào, repository method nào kích hoạt publication, callback nào dọn buffer và listener nào cần chờ commit. Tách riêng các bước đó giúp tránh phát trùng, xử lý side effect trước commit hoặc mất thông điệp khi ứng dụng gặp sự cố.
