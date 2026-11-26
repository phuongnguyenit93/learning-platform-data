# Transaction boundary trong Spring Modulith Application Events

## 1. Transaction boundary là gì và vì sao quan trọng?

Trong Spring Modulith, các application module có thể giao tiếp bằng application events để giảm phụ thuộc trực tiếp. Ví dụ, **Orders** xác nhận đơn hàng, rồi phát `OrderConfirmed`. **Notifications** nghe sự kiện để tạo yêu cầu gửi thông báo; **Fulfillment** có thể nghe cùng sự kiện để chuẩn bị giao hàng.

Vấn đề then chốt là: **khi Orders phát event, dữ liệu đơn hàng đã commit chưa? Nếu listener thất bại, transaction nào sẽ rollback?** Câu trả lời thay đổi tùy loại listener, thời điểm xử lý và chính sách transaction.

**Transaction boundary** (ranh giới giao dịch) là phạm vi mà trong đó các thao tác được quản lý bởi một transaction cụ thể: cùng commit thành công hoặc cùng rollback theo khả năng của transaction manager và các tài nguyên đang tham gia. Nó không đồng nghĩa ranh giới class, module, thread hay tiến trình.

Trong chương **Giao dịch và event** của `SPRING_MODULITH_APPLICATION_EVENTS`, bài học này giúp bạn thiết kế publisher, listener, xử lý sau commit, Event Publication Registry và retry mà không nhầm “event đã được publish” với “business transaction đã commit” hoặc “consumer đã hoàn tất”.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt transaction của publisher với transaction của từng consumer.
- Giải thích thời điểm chạy `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
- Biết khi nào callback chia sẻ transaction và khi nào phải mở `REQUIRES_NEW`.
- Phân tích trường hợp rollback, exception, crash và publication chưa hoàn thành.
- Chọn synchronous call hoặc event bất đồng bộ dựa trên business invariant.
- Thiết kế idempotency, retry và quan sát trạng thái qua các ranh giới transaction.
- Kiểm thử giao dịch bằng commit thực sự và kiểm tra kết quả sau commit.

## 2. Một luồng nghiệp vụ có thể có nhiều transaction

Giả sử hệ thống thương mại điện tử gồm ba module:

- **Orders** sở hữu aggregate `Order` và trạng thái xác nhận đơn.
- **Notifications** sở hữu bảng notification job.
- **Fulfillment** sở hữu yêu cầu chuẩn bị giao hàng.

Orders thực hiện lệnh `confirmOrder(orderId)`. Sau khi xác nhận đơn trong transaction của mình, Orders phát `OrderConfirmed`.

Có hai mô hình quan trọng.

### 2.1. Mô hình đồng bộ trong cùng transaction

~~~mermaid
flowchart LR
    subgraph TX["Transaction T1 (một tài nguyên DB phù hợp)"]
        A["Orders: confirm"] --> B["publish OrderConfirmed"]
        B --> C["@EventListener: Notifications"]
        C --> D["T1 commit hoặc rollback"]
    end
~~~

Với cơ chế multicaster đồng bộ mặc định và các thao tác DB dùng cùng Spring transaction manager, listener `@EventListener` có thể tham gia transaction **đang mở** của publisher. Lỗi runtime không được xử lý phù hợp có thể làm transaction nguồn rollback.

Đây là **liên kết transaction chặt**: Orders và việc listener làm được buộc về cùng giao dịch theo cách triển khai. Điều đó có thể có chủ đích nhưng thường không phù hợp nếu Notifications gọi email API hoặc các tác vụ mất nhiều thời gian.

### 2.2. Mô hình sau commit với transaction mới

~~~mermaid
flowchart LR
    subgraph T1["Transaction T1: Orders"]
        A["Xác nhận Order"] --> B["publish OrderConfirmed"]
        B --> C["COMMIT Orders"]
    end
    C --> E["AFTER_COMMIT dispatch"]
    subgraph T2["Transaction T2: Notifications"]
        E --> N["Tạo notification job"]
        N --> NC["COMMIT / ROLLBACK T2"]
    end
    subgraph T3["Transaction T3: Fulfillment"]
        E --> F["Tạo fulfillment request"]
        F --> FC["COMMIT / ROLLBACK T3"]
    end
~~~

Ở mô hình này, **Orders đã commit trước khi listener bắt đầu công việc sau commit**. Notifications và Fulfillment có transaction riêng. Một listener lỗi không thể tự đảo ngược transaction Orders đã commit.

Cần chấp nhận một khoảng thời gian dữ liệu giữa các module **chưa đồng bộ** (*eventual consistency*), đồng thời có cơ chế theo dõi và khôi phục tác vụ chưa hoàn tất.

## 3. Phân biệt event publication và transaction commit

Giả sử code trong Orders:

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.save(order);
    events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, Instant.now(clock)
    ));
}
~~~

Trong ví dụ, `publishEvent(...)` được gọi **trước thời điểm Spring commit transaction** của phương thức `confirm`. Vì thế:

1. Event object đã được tạo và gửi tới event infrastructure.
2. Listener đồng bộ có thể chạy ngay khi transaction còn mở.
3. Transaction Orders có thể **vẫn rollback** sau lời gọi publish, ví dụ do lỗi khi flush/commit hoặc exception phát sinh tiếp theo.
4. Transactional listener ở phase `AFTER_COMMIT` chỉ được kích hoạt sau một commit thành công.
5. Ngay cả khi callback sau commit chạy, side effect của consumer vẫn có thể thất bại.

**Không được diễn giải `publishEvent` là cam kết event đã được tiêu thụ hoặc state đã commit.** Nó là thao tác công bố trong Spring context; độ bền publication và thời điểm nhận thuộc những cơ chế bổ sung được cấu hình.

### Dòng thời gian cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders Service
    participant DB as Database
    participant P as Publisher
    participant L as Listener AFTER_COMMIT
    Client->>O: confirm(orderId)
    O->>DB: Begin TX T1
    O->>DB: Update Order=CONFIRMED
    O->>P: publish OrderConfirmed
    Note over P,L: Listener AFTER_COMMIT chưa chạy
    O->>DB: COMMIT T1
    P-->>L: Dispatch sau commit
    L->>L: Xử lý theo transaction riêng nếu cấu hình
~~~

Nếu commit T1 thất bại, một listener `AFTER_COMMIT` sẽ không được kích hoạt như một công việc sau commit thành công.

## 4. Transaction boundary khác module boundary

Spring Modulith khuyến khích các module bảo vệ API công khai và không import implementation nội bộ của nhau. Tuy nhiên, module boundary **không tự tạo một database transaction riêng**.

Ví dụ module Orders và Inventory cùng ứng dụng, cùng datasource và cùng transaction manager. Nếu Orders gọi trực tiếp public API của Inventory từ bên trong `@Transactional`, thao tác Inventory dùng propagation `REQUIRED` có thể tham gia cùng transaction T1. Đây là một thiết kế có thể phù hợp khi việc giữ tồn kho là invariant bắt buộc.

Ngược lại, khi Orders phát `OrderConfirmed` cho `@ApplicationModuleListener` của Inventory, listener được thực thi sau commit trong transaction mới; thay đổi Inventory không còn atomic với commit Orders.

| Ranh giới | Bảo vệ điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| Application module | Ownership của model, API và dependency | Tự có transaction riêng |
| Spring transaction | Commit/rollback cho tài nguyên tham gia giao dịch | Tính atomic với mọi API ngoài hoặc broker |
| Thread/executor | Nơi thực thi mã | Tự truyền transaction của thread nguồn |
| JVM/process | Phạm vi Spring event infrastructure mặc định | Giao event qua mạng |
| External broker | Truyền thông điệp giữa tiến trình | DB của publisher và consumer cùng commit atomic |

**Quy tắc thiết kế:** xác định business invariant trước; sau đó chọn transaction boundary, cuối cùng mới chọn event listener và executor.

## 5. Khi nào dùng @EventListener đồng bộ?

Một `@EventListener` thông thường được gọi khi event được publish. Với `SimpleApplicationEventMulticaster` mặc định không được gắn executor tùy chỉnh, lời gọi listener diễn ra **đồng bộ** trên thread publisher.

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class AuditListener {

    private final OrderAuditRepository auditRepository;

    AuditListener(OrderAuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @EventListener
    public void on(OrderConfirmed event) {
        auditRepository.save(
                OrderAudit.confirmed(event.eventId(), event.orderId())
        );
    }
}
~~~

Nếu publisher đang có transaction và repository tham gia cùng transaction manager với propagation phù hợp, thao tác audit có thể nằm trong T1. Điều này có thể chấp nhận được nếu audit record thực sự phải đi cùng thay đổi Order và không kéo dài transaction quá mức.

### Rủi ro của listener đồng bộ

- **Coupling lỗi:** một exception từ listener có thể khiến use case publisher thất bại.
- **Tăng thời gian giữ transaction:** listener làm I/O hoặc thao tác nặng sẽ kéo dài thời gian khóa/giữ connection.
- **Side effect không rollback được:** nếu listener gửi email trước commit, sau đó Orders rollback, email vẫn đã được gửi.
- **Phụ thuộc ngầm vào transaction:** listener giả định có transaction phù hợp, nhưng cùng event cũng có thể được publish ở một nơi khác mà không có transaction.

Không nên sử dụng listener đồng bộ chỉ vì “code chạy được”. Cần quyết định rõ kết quả listener có phải một phần của transaction nghiệp vụ hay không.

### Khi nào gọi API trực tiếp dễ hiểu hơn event đồng bộ?

Nếu Orders cần biết Inventory có giữ hàng thành công **trước khi xác nhận đơn**, gọi một public API đồng bộ của Inventory có thể biểu đạt command và lỗi rõ ràng hơn:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    inventory.reserveForOrder(orderId); // public API đồng bộ, nếu nghiệp vụ cần.
    orders.confirm(orderId);
}
~~~

Ví dụ này chỉ an toàn theo kỳ vọng atomic khi hai thao tác thực sự tham gia cùng transaction manager/tài nguyên thích hợp. Nếu Inventory là dịch vụ ngoài JVM hoặc dùng database khác, phải thiết kế workflow và compensation riêng; một `@Transactional` local không bao trùm mọi hệ thống.

## 6. @TransactionalEventListener và các transaction phase

Spring Framework cung cấp `@TransactionalEventListener` để xử lý event tại những thời điểm liên quan đến vòng đời transaction.

| Phase | Khi nào callback chạy? | Dùng cho tình huống nào? | Cảnh báo |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit | Kiểm tra/bổ sung việc bắt buộc trước commit khi có thiết kế rõ | Exception có thể làm commit không thành công; chưa phải state bền vững |
| `AFTER_COMMIT` | Sau commit thành công; **mặc định** | Phản ứng với sự thật đã được commit | Không thể rollback transaction publisher; cần transaction mới khi ghi state |
| `AFTER_ROLLBACK` | Sau rollback | Cleanup/ghi nhận rollback theo chính sách | Không biến thao tác nguồn thành thành công |
| `AFTER_COMPLETION` | Sau transaction hoàn tất, bất kể commit hay rollback | Cleanup, metrics hoặc quan sát | Phải phân biệt commit/rollback nếu nghiệp vụ cần |

Ví dụ:

~~~java
@Component
public class OrderLifecycleListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderConfirmed event) {
        // Xử lý sau khi Orders commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderConfirmed event) {
        // Minh họa cleanup/observability cho lần publication bị rollback.
    }
}
~~~

Đoạn code giả định có các import `@Component`, `@TransactionalEventListener` và `TransactionPhase`. Không nhất thiết cùng một module nên đăng ký cả hai callback cho mọi event. Đừng phát các sự kiện mang nghĩa “đã xác nhận thành công” rồi dùng `AFTER_ROLLBACK` để làm side effect nghiệp vụ xác nhận.

### 6.1. Trường hợp không có transaction

`@TransactionalEventListener` theo mặc định chỉ xử lý khi event được publish trong một ngữ cảnh transaction phù hợp. Nếu không có transaction, callback thường **không được gọi**; `fallbackExecution = true` cho phép xử lý trong trường hợp không có transaction nhưng làm thay đổi ngữ nghĩa:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void on(OrderConfirmed event) {
    // Nếu không có transaction, có thể được gọi ngay theo fallback.
}
~~~

**Không bật fallback tùy tiện** nếu ý nghĩa event đòi hỏi chỉ phản ứng sau khi một state đã commit. Khi không có transaction, không có mốc commit nguồn tương ứng để chờ.

### 6.2. BEFORE_COMMIT không phải phép kiểm tra nghiệp vụ mặc định

Dùng listener `BEFORE_COMMIT` để ra quyết định nghiệp vụ cốt lõi có thể khiến flow khó đọc: Orders không thể thấy rõ các điều kiện bắt buộc nằm ở listener nào. Với business invariant quan trọng, ưu tiên tổ chức trong domain/application service hoặc public API đồng bộ. Listener trước commit phù hợp khi đã có lý do rõ và có test chứng minh exception/rollback theo kỳ vọng.

## 7. Cạm bẫy AFTER_COMMIT: transaction đã xong nhưng resource có thể còn gắn

Đây là điểm dễ sai trong ứng dụng Spring dùng transaction.

Callback `AFTER_COMMIT` chạy sau khi transaction nguồn đã commit, nhưng một số transaction resources có thể **vẫn còn gắn với thread** trong giai đoạn callback và cleanup. Nếu callback thực hiện truy cập dữ liệu với propagation `REQUIRED` theo cách tham gia vào resource của transaction vừa hoàn tất, các thay đổi có thể **không được commit trong một transaction mới** như người viết mong đợi.

Ví dụ đáng tránh:

~~~java
@Component
public class NotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        notificationRepository.save(
                NotificationJob.forOrder(event.orderId())
        );
    }
}
~~~

Đừng mặc định rằng `save(...)` ở đây chắc chắn mở transaction mới và commit bền vững. Hành vi thực tế phụ thuộc transaction manager, resource và ngữ cảnh gọi.

### Hướng an toàn: REQUIRES_NEW cho dữ liệu của consumer

~~~java
@Service
public class NotificationService {

    private final NotificationJobRepository jobs;

    public NotificationService(NotificationJobRepository jobs) {
        this.jobs = jobs;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void scheduleIfAbsent(UUID eventId, UUID orderId) {
        if (jobs.existsBySourceEventId(eventId)) {
            return;
        }
        jobs.save(NotificationJob.forOrderConfirmed(eventId, orderId));
    }
}
~~~

Listener sau commit gọi service này qua Spring proxy. `REQUIRES_NEW` yêu cầu transaction vật lý mới; từ đó consumer có commit/rollback độc lập.

**Lưu ý:** `existsBySourceEventId` rồi `save` chỉ mô tả ý định; phải có unique constraint ở DB theo `eventId` hoặc business key để xử lý race condition. Trong một số môi trường, thay đổi state và ghi dấu đã xử lý cần nằm cùng transaction của listener.

### Vì sao không chỉ thêm @Transactional vào method cùng class?

Spring transaction AOP thông thường dựa vào proxy. Nếu method của một bean gọi một method khác của chính bean đó bằng `this.method()`, lời gọi có thể **không đi qua proxy** và annotation transaction trên method đích không được áp dụng theo kỳ vọng. Đưa thao tác ghi vào một service riêng được inject giúp ranh giới transaction rõ ràng hơn.

## 8. @ApplicationModuleListener: ranh giới đề xuất giữa các module

Spring Modulith cung cấp `@ApplicationModuleListener` cho giao tiếp module qua event. Annotation này kết hợp các đặc tính:

- `@TransactionalEventListener`: mặc định xử lý sau commit;
- `@Async`: xử lý bất đồng bộ qua Spring async infrastructure;
- `@Transactional(propagation = REQUIRES_NEW)`: mỗi invocation listener có transaction mới phù hợp.

Ví dụ listener trong Notifications:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        notifications.scheduleIfAbsent(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

Giả định Spring async support được bật và executor được cấu hình phù hợp. `@ApplicationModuleListener` không tự biến JVM event bus thành message broker. Nó giúp tách transaction của consumer khỏi publisher để module nhận tự chịu trách nhiệm trạng thái và lỗi của mình.

### Tại sao không dùng @Async + @EventListener đơn thuần?

Nếu kết hợp `@Async` với `@EventListener` thông thường, task có thể được giao cho executor **trước khi transaction publisher commit**. Listener có thể:

- Không thấy dữ liệu mới vì transaction còn chưa commit.
- Đọc một phiên bản state cũ.
- Gây side effect dù transaction Orders về sau rollback.
- Bị chạy trong transaction khác mà publisher không kiểm soát.

Muốn phản ứng khi state nguồn đã commit, hãy dùng callback theo phase `AFTER_COMMIT` (và transaction mới nếu cần ghi state) thay vì chỉ dùng `@Async`.

## 9. Ví dụ xuyên suốt: publisher Orders và listener Notifications

### 9.1. Contract công khai

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

`eventId` giúp consumer nhận biết một lần xảy ra sự kiện khi xử lý lại. `orderId` định danh aggregate nguồn; `occurredAt` là thời điểm phát sinh do publisher ghi nhận. Payload bất biến theo ý nghĩa contract, không chứa JPA entity/lazy association hoặc object quản lý transaction.

### 9.2. Publisher sở hữu transaction T1

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return; // Không phát event mới khi không có chuyển trạng thái.
        }

        order.confirm(); // Domain bảo vệ invariant.
        orders.save(order);

        publisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock)
        ));
    }
}
~~~

Phần mã giả định `Order`, `OrderRepository`, `Clock` được khai báo trong ứng dụng. `@Transactional` bao bọc use case xác nhận. Spring sẽ thực hiện commit khi phương thức kết thúc bình thường nếu transaction manager không phát sinh lỗi.

Cần chú ý **concurrency**: hai request có thể cùng đọc `isConfirmed() == false` rồi cùng gọi `confirm`. Optimistic locking (`@Version`), cơ chế khóa hoặc constraint phải bảo vệ business invariant. Việc thêm event không thay thế kiểm soát đồng thời ở database.

### 9.3. Consumer sở hữu transaction T2

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    private final NotificationService service;

    public OrderNotificationListener(NotificationService service) {
        this.service = service;
    }

    @ApplicationModuleListener
    public void handle(OrderConfirmed event) {
        service.enqueueConfirmationIfAbsent(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

Method `enqueueConfirmationIfAbsent` là phương thức giả định cần triển khai trong Notifications với idempotency và transaction theo nghiệp vụ.

Với `@ApplicationModuleListener`, xử lý được kích hoạt sau commit T1 và được thực thi bất đồng bộ trong transaction riêng. Nếu T2 rollback, **T1 vẫn đã commit**. Vì vậy, Orders có thể đang ở `CONFIRMED` trong khi Notifications chưa có email job.

### 9.4. Phân biệt “lên lịch email” với “đã gửi email”

Ghi một notification job trong T2 là thao tác DB có thể commit/rollback. Gọi trực tiếp email provider lại là side effect ngoài DB, không thể rollback bằng `@Transactional` của Spring.

Một thiết kế chắc chắn thường gồm:

~~~text
Orders T1 commit -> OrderConfirmed
                     |
                     v
Notifications T2 commit -> notification_job(PENDING)
                     |
                     v
Email worker -> gọi provider -> cập nhật SENT/FAILED trong transaction riêng
~~~

Ở đây, công việc nhận event và công việc gửi email tách thành hai bước. Có thể retry job gửi và dùng idempotency key nếu nhà cung cấp hỗ trợ. Cần định nghĩa rõ khi nào trạng thái `SENT` được ghi nhận và cách xử lý trường hợp provider đã gửi nhưng phản hồi bị mất.

## 10. Khi transaction T1 rollback, chuyện gì xảy ra?

Giả sử Orders phát event, rồi một lỗi làm transaction rollback:

~~~java
@Transactional
public void confirmThenFail(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.save(order);

    events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, Instant.now()
    ));

    throw new IllegalStateException("Simulated failure");
}
~~~

Theo quy tắc rollback mặc định thông dụng của Spring, một runtime exception không được xử lý phù hợp làm transaction bị đánh dấu rollback. Với listener `@TransactionalEventListener(AFTER_COMMIT)`, callback **không được chạy cho commit thất bại này**.

Tuy nhiên, nếu listener là `@EventListener` đồng bộ, nó có thể **đã chạy trước khi exception xảy ra**. Nếu nó chỉ ghi DB và tham gia T1, ghi DB sẽ rollback cùng T1; nhưng nếu nó gửi email ra ngoài, email không thể “rollback”.

| Listener / side effect | Sau khi T1 rollback |
| --- | --- |
| `@EventListener` đồng bộ, ghi cùng DB và cùng T1 | Thay đổi DB có thể rollback cùng T1 |
| `@EventListener` đồng bộ, gọi HTTP/email | Side effect ngoài DB có thể đã xảy ra |
| `@TransactionalEventListener(AFTER_COMMIT)` | Không được gọi cho transaction rollback |
| `@ApplicationModuleListener` | Không chạy như xử lý after-commit thành công |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Có thể được gọi để cleanup/quan sát nếu phù hợp |

**Đừng suy ra mọi exception đều làm rollback.** Spring có các quy tắc rollback tùy loại exception, `rollbackFor`, `noRollbackFor` và transaction manager. Khi nghiệp vụ cần rollback với checked exception, phải cấu hình hoặc tổ chức phù hợp và kiểm thử.

## 11. Khi Orders đã commit nhưng listener thất bại

Giả sử:

~~~text
12:00:00.000  Orders: Order CONFIRMED, commit T1
12:00:00.050  Notifications: bắt đầu T2
12:00:00.200  Notifications: database timeout, rollback T2
12:00:00.300  Fulfillment: commit T3 thành công
~~~

Đây là một trạng thái có thể xảy ra bình thường trong hệ thống event-driven. `OrderConfirmed` vẫn là sự thật đã commit trong Orders. Một transaction T2 thất bại **không tự cuộn ngược** T1 hay T3.

Điều này dẫn tới ba yêu cầu:

1. **Mỗi module sở hữu state và xử lý lỗi của mình.** Notifications cần ghi nhận hoặc khôi phục publication chưa hoàn tất.
2. **Không giả định toàn bộ listener hoàn thành khi API trả kết quả.** Nếu API xác nhận đơn trả thành công ngay sau commit Orders, Notifications có thể vẫn chưa gửi thông báo.
3. **Định nghĩa eventual consistency và SLA.** Có thể hiển thị “Đơn đã xác nhận, thông báo đang chờ” thay vì yêu cầu mọi module đồng bộ tức thời.

Nếu nghiệp vụ thật sự yêu cầu “chỉ xác nhận đơn khi Inventory đã giữ hàng”, việc chuyển Inventory thành `@ApplicationModuleListener` sau commit **không bảo toàn invariant đó**. Cần thiết kế một thao tác đồng bộ trước commit hoặc một workflow rõ ràng gồm các trạng thái và compensation.

## 12. Transaction propagation: REQUIRED, REQUIRES_NEW và NESTED

Propagation quyết định một method `@Transactional` tương tác với transaction đang tồn tại thế nào.

| Propagation | Ý nghĩa cơ bản | Phù hợp với bài toán |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction hiện tại nếu có; nếu không có thì tạo mới | Service nội bộ thực thi trong transaction nghiệp vụ bình thường |
| `REQUIRES_NEW` | Tạm tách transaction hiện có và bắt đầu transaction vật lý riêng | Consumer cần commit/rollback độc lập sau commit publisher |
| `NESTED` | Savepoint bên trong transaction hiện có khi transaction manager hỗ trợ | Một số trường hợp JDBC; không được hiểu là transaction độc lập |
| `MANDATORY` | Chỉ chạy nếu đã có transaction | API yêu cầu caller cung cấp transaction |
| `NOT_SUPPORTED` | Thực thi không có transaction | Một số thao tác không nên giữ transaction; phải kiểm soát nhất quán riêng |

### 12.1. REQUIRES_NEW có chi phí

Nếu gọi `REQUIRES_NEW` khi một transaction bên ngoài vẫn đang giữ database connection, transaction mới có thể cần **connection bổ sung**. Trong môi trường tải cao, cấu hình pool connection không phù hợp có thể gây chờ hoặc deadlock do nhiều thread cùng giữ connection nguồn và xin connection mới.

Với listener sau commit chạy async, transaction nguồn đã hoàn tất trước khi consumer bắt đầu, nên hành vi cạnh tranh connection khác với việc gọi `REQUIRES_NEW` đồng bộ khi T1 còn mở. Dù vậy, mỗi consumer vẫn tiêu thụ database connection riêng và cần sizing executor/pool phù hợp.

### 12.2. NESTED không phải transaction tách biệt

`NESTED` có thể dùng savepoint nếu transaction manager và tài nguyên hỗ trợ; rollback về savepoint không có nghĩa child đã commit độc lập khỏi outer transaction. Khi outer transaction rollback, thay đổi ở nested scope vẫn bị rollback. Không dùng `NESTED` như cách thay thế `REQUIRES_NEW` cho listener phải ghi state sau commit.

## 13. Async listener làm thay đổi ranh giới thread và transaction

Một transaction Spring thông thường liên kết với thread thực thi. Khi chuyển tác vụ sang executor bằng `@Async`, worker thread **không tự kế thừa transaction của thread nguồn**. Do đó:

- Không truyền `EntityManager`, connection hoặc một JPA entity lazy đang gắn transaction nguồn vào event.
- Không giả định `SecurityContext`, MDC hoặc HTTP request attributes tự được truyền.
- Nếu consumer cần ghi DB, cần mở transaction riêng trong worker.
- Nếu cần trace/correlation, dùng metadata event bền vững hoặc context propagation phù hợp.

Ví dụ tường minh thay cho `@ApplicationModuleListener` khi muốn chọn executor riêng:

~~~java
@Component
public class ConfirmationListener {

    @Async("moduleEventsExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void on(OrderConfirmed event) {
        // Ghi state Notifications trong transaction riêng.
    }
}
~~~

Cần bật `@EnableAsync`, khai báo executor và bảo đảm proxy/AOP hoạt động. `@ApplicationModuleListener` được dùng khi muốn composition mặc định của Spring Modulith; tổ hợp tường minh giúp xác định executor theo tên.

Không dùng `@Async` như một cách “tăng hiệu năng miễn phí”: quá nhiều listener chạy song song có thể làm quá tải database, làm sai thứ tự event hoặc tăng retry storm. Thread pool, queue, rejection policy và shutdown cần được thiết kế theo SLA thực tế.

## 14. Transaction boundary và Event Publication Registry

Spring application events mặc định hoạt động **trong tiến trình**. Khi Orders commit thành công nhưng JVM dừng trước khi listener hoàn tất, phải có cơ chế để nhận biết publication còn chưa được xử lý.

Spring Modulith cung cấp **Event Publication Registry** cho các transactional event listeners khi đã cấu hình backend lưu trữ phù hợp. Registry giúp theo dõi publication chưa hoàn thành và hỗ trợ khôi phục/republication theo khả năng của phiên bản thư viện và chính sách vận hành.

### 14.1. Ghi nhận publication cùng transaction nguồn

Trong một cấu hình registry có transaction manager và storage phù hợp, publication cần giao cho listener được ghi nhận trong phạm vi transaction của publisher. Mục tiêu là tránh tình huống business state đã commit mà hệ thống hoàn toàn không có dấu vết event cần giao.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders
    participant DB as DB
    participant R as Event Publication Registry
    participant N as Notifications Listener
    O->>DB: T1: cập nhật Order
    O->>R: T1: ghi publication cho listener
    O->>DB: COMMIT T1
    R-->>N: AFTER_COMMIT: xử lý event
    alt T2 thành công
        N-->>R: Đánh dấu publication completed
    else T2 lỗi hoặc process crash
        Note over R: Publication chưa hoàn thành
        R-->>N: Khôi phục/giao lại khi được cấu hình
    end
~~~

Sơ đồ minh họa mục đích bảo toàn publication. Chi tiết SQL, bảng, tên trạng thái, hình thức đánh dấu hoàn tất, việc ghi nhận `FAILED` và quá trình resubmission phụ thuộc vào backend và version Spring Modulith.

### 14.2. Registry không phải transaction phân tán

Registry **không tạo một transaction atomic chung** giữa Orders và database của Notifications, cũng không bao trùm broker hoặc nhà cung cấp email. Nó hỗ trợ theo dõi delivery tới listener và recovery khi xảy ra lỗi. Trạng thái “publication completed” chỉ biểu thị công việc listener đã hoàn tất theo cơ chế đăng ký, không đồng nghĩa mọi hiệu ứng bên ngoài ứng dụng đã xảy ra chính xác một lần.

### 14.3. Retry phải được thiết kế rõ

Không nên giả định “có registry là tự retry mãi mãi”. Tùy cấu hình, cần xác định:

- Cơ chế tìm và xử lý lại incomplete/failed publications.
- Khi nào chạy resubmission (startup, lịch định kỳ hoặc quy trình vận hành).
- Điều kiện backoff, giới hạn lần thử và phân loại lỗi.
- Cách xử lý poison event (payload không thể xử lý).
- Quan sát độ tuổi publication, số lần lỗi và latency theo listener.

Nếu một listener thất bại vĩnh viễn do vi phạm business rule, retry vô hạn sẽ tạo backlog, không làm dữ liệu đúng hơn. Cần quy trình sửa dữ liệu, nâng cấp code hoặc đánh dấu xử lý thủ công có kiểm soát.

## 15. At-least-once delivery và ranh giới idempotency

Một publication có thể được giao lại khi ứng dụng dừng ở điểm xấu:

~~~text
T1 Orders: COMMIT OrderConfirmed
T2 Notifications: tạo notification_job và COMMIT
Crash: chưa kịp ghi nhận publication completed
Restart: registry phát lại OrderConfirmed
T3 Notifications: nhận lại cùng eventId
~~~

Nếu listener tạo thêm một job ở T3, khách hàng có thể nhận hai email. Vì thế, phải thiết kế **idempotency** ở **transaction boundary của consumer**, không chỉ ở publisher.

### 15.1. Tạo khóa dedup bền vững

Một thiết kế đơn giản cho Notifications:

~~~sql
CREATE TABLE notification_job (
    id                  UUID PRIMARY KEY,
    source_event_id     UUID NOT NULL UNIQUE,
    order_id            UUID NOT NULL,
    status              VARCHAR(32) NOT NULL
);
~~~

Mỗi publication `OrderConfirmed` có một `eventId` ổn định. Consumer có thể dùng `source_event_id` làm unique key. Nếu quy tắc nghiệp vụ yêu cầu “mỗi Order chỉ có một email loại confirmation”, có thể thêm unique constraint theo `(order_id, notification_type)`; không nhất thiết chỉ dựa vào event ID.

### 15.2. Ghi kết quả và dấu đã xử lý cùng transaction

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void handle(OrderConfirmed event) {
    if (jobs.existsBySourceEventId(event.eventId())) {
        return;
    }

    jobs.save(NotificationJob.pending(
            event.eventId(), event.orderId()
    ));
}
~~~

Đây là phác thảo cần xử lý race condition với database unique constraint và cách mapping exception/transaction phù hợp. Hai invocation đồng thời đều có thể thấy “chưa tồn tại”; unique key mới là hàng rào cuối cùng. Nếu dùng bảng riêng `processed_events`, việc ghi marker và thay đổi state phải trong cùng transaction, không mark trước rồi thực hiện side effect sau mà thiếu cơ chế phục hồi.

### 15.3. Exactly-once không tự xuất hiện

Event Publication Registry, `REQUIRES_NEW` và unique constraint giúp giảm lỗi nhưng không tự bảo đảm **exactly-once cho mọi side effect**. Nếu email provider đã gửi xong nhưng ứng dụng timeout và không nhận ack, retry có thể gửi lại. Cần idempotency key do provider hỗ trợ, durable job, đối soát hoặc quy tắc chấp nhận/bù trừ nghiệp vụ.

**Ranh giới quan trọng:** transaction database quản lý state trong database, không rollback email đã gửi ra ngoài.

## 16. Bảng tình huống lỗi qua các transaction boundary

| Thời điểm lỗi | Transaction Orders | Transaction Notifications | Kết quả và cách xử lý |
| --- | --- | --- | --- |
| Trước khi Order xác nhận xong | Rollback hoặc chưa commit | Chưa có | Không công bố sự thật xác nhận thành công |
| Sau khi publish nhưng trước commit | Có thể rollback | Với after-commit: chưa chạy | Listener `AFTER_COMMIT` không xử lý nếu T1 rollback |
| Trong listener `@EventListener` đồng bộ | Tùy exception và propagation có thể rollback | Có thể cùng T1 | Xem lại việc listener có thực sự cần atomic với publisher |
| Sau T1 commit, trước khi submit async | Đã commit | Chưa bắt đầu | Registry/outbox cần cho khả năng khôi phục bền vững |
| Sau T1 commit, executor từ chối task | Đã commit | Chưa bắt đầu | Quan sát rejection; tìm publication chưa hoàn thành và resubmit |
| T2 ghi DB rồi rollback | Đã commit | Rollback | Retry listener theo cơ chế phù hợp |
| T2 commit, chưa đánh dấu completed | Đã commit | Đã commit | Có thể redelivery; consumer cần idempotent |
| Broker/email provider đã xử lý, mất ack | Đã commit | Tùy trạng thái DB | Cần idempotency bên ngoài hoặc reconciliation |
| Một listener thành công, listener khác lỗi | Đã commit | Một T thành công, một T lỗi | Khôi phục từng consumer độc lập; không rollback T1 |

Bảng này giả định các listener cần xử lý sau commit đã được cấu hình đúng và có publication storage khi yêu cầu phục hồi sau crash. Không thể dùng bảng như bảo đảm cho một application event thông thường không có registry.

## 17. Eventual consistency, ordering và dữ liệu đến trễ

Khi listener xử lý ở transaction riêng, state các module có thể khác nhau trong một khoảng thời gian:

~~~text
T1: Orders = CONFIRMED           (đã commit)
T2: Fulfillment = PENDING        (chưa tạo yêu cầu)
T3: Notifications = QUEUED       (vừa commit)
T4: Fulfillment = REQUESTED      (commit sau)
~~~

Đó là hệ quả trực tiếp của việc tách transaction boundary. Nếu ứng dụng cần hiển thị trạng thái tổng hợp, UI/API phải thừa nhận “đang xử lý” và không coi trạng thái publisher là bằng chứng tất cả consumer đã hoàn thành.

### 17.1. Event đến không theo thứ tự

Ví dụ:

~~~text
Version 7: OrderConfirmed
Version 8: OrderCancelled

Consumer nhận: OrderCancelled trước, rồi OrderConfirmed do retry.
~~~

Nếu consumer chỉ áp dụng event theo thứ tự nhận, một trạng thái đã hủy có thể bị “xác nhận lại” sai. Có thể bổ sung:

- `aggregateVersion` tăng nhất quán trong aggregate nguồn.
- State-machine guard ngăn chuyển ngược trạng thái terminal.
- Truy vấn state hiện tại qua public API khi business requirement cho phép.
- Cơ chế queue/partition theo aggregate ID khi mở rộng tới broker.

`occurredAt` chỉ là timestamp, không phải cơ chế đảm bảo thứ tự tuyệt đối. Transaction độc lập và xử lý async không bảo đảm các listener luôn hoàn thành cùng thứ tự publish.

### 17.2. Event là sự thật lịch sử

`OrderConfirmed` vẫn đúng nếu sau đó `OrderCancelled` xảy ra. Nhưng consumer nhận lại `OrderConfirmed` sau khi đơn hủy không được suy diễn rằng hiện tại Order vẫn `CONFIRMED`. Cần xác định consumer đang tái hiện lịch sử, xây read model hay thực hiện hành động đòi hỏi trạng thái mới nhất.

## 18. Transaction boundary với integration event và outbox

Giao tiếp giữa các application module trong cùng JVM không tương đương giao tiếp tới dịch vụ bên ngoài. Khi Orders cần gửi sự kiện sang CRM qua Kafka, thêm ranh giới mới:

~~~text
TX Orders commit -> externalization/outbox -> broker -> CRM consumer TX
~~~

Spring Modulith hỗ trợ cơ chế **event externalization** để đưa các event được chọn ra ngoài ứng dụng qua tích hợp messaging. Event Publication Registry có thể hỗ trợ theo dõi publication tới transactional listener/externalization trong cấu hình tương ứng.

Nếu yêu cầu lưu bản ghi cần gửi ra ngoài và relay độc lập, có thể dùng mô hình **transactional outbox**: thay đổi state nghiệp vụ và outbox record được ghi trong cùng transaction của publisher, rồi worker/CDC chuyển message tới broker. Hai cơ chế có mục tiêu liên quan nhưng **không nên coi registry và outbox chuyên dụng là hoàn toàn giống nhau**.

Một database transaction Spring thông thường không tạo giao dịch phân tán atomic giữa database Orders, broker, database CRM và email provider. Vì vậy, ở mỗi biên cần xác định:

- Ai sở hữu state và commit nào thể hiện sự thật nghiệp vụ.
- Khi nào thông điệp được coi là đã được broker chấp nhận.
- Consumer dùng idempotency/ack như thế nào.
- Làm sao khôi phục khi crash giữa commit và acknowledgement.
- Có cần versioning, replay, reconciliation hoặc compensation không.

## 19. Các lỗi thiết kế thường gặp

| Anti-pattern | Vì sao sai? | Hướng thiết kế |
| --- | --- | --- |
| Cho rằng `publishEvent` nghĩa là đã commit | Publication xảy ra khi transaction còn mở | Chọn listener phase theo yêu cầu nhất quán |
| Gửi email trong `@EventListener` đồng bộ rồi rollback Order | Email không thể rollback với DB | Sau commit + durable job/outbox |
| `@TransactionalEventListener(AFTER_COMMIT)` ghi DB nhưng không mở transaction mới phù hợp | Có thể còn resource của transaction đã commit | Dùng `REQUIRES_NEW` khi cần commit độc lập |
| Dùng `@Async @EventListener` rồi cho là đã an toàn sau commit | Async có thể chạy trước commit | Kết hợp transactional phase `AFTER_COMMIT` |
| Cho rằng module boundary tạo transaction mới | Hai module vẫn có thể chia sẻ T1 | Thiết kế transaction rõ ràng theo use case |
| Đưa business invariant bắt buộc sang listener async | Publisher có thể trả thành công quá sớm | Gọi public API đồng bộ hoặc xây workflow |
| Bắt exception rồi im lặng trong listener | Registry có thể đánh dấu publication completed dù nghiệp vụ chưa xong | Để lỗi được báo đúng hoặc lưu trạng thái failure nhất quán |
| Retry không có idempotency | Tạo dữ liệu/side effect trùng | Unique constraint và dedup bền vững |
| Tưởng registry tự retry vô hạn | Publication có thể tồn đọng | Thiết kế resubmission, alert và runbook |
| Tin rằng một transaction local bao trùm broker/API ngoài | Không có atomic cross-system theo mặc định | Outbox/externalization và reconciliation |
| Test `AFTER_COMMIT` trong transaction rollback mặc định | Listener không được gọi như production | Test commit thật và chờ điều kiện |
| Dùng entity JPA làm event payload | Lazy loading, state mutable, rò rỉ nội bộ | Event payload bất biến, chỉ dữ liệu cần thiết |

## 20. Kiểm thử transaction boundary

Kiểm thử cần xác minh **điều gì đã commit** và **điều gì chỉ có thể chạy sau commit**. Không chỉ kiểm tra “publisher gọi `publishEvent`”.

### 20.1. Test publisher phát đúng event

Với Spring Modulith, có thể dùng `@ApplicationModuleTest` và hỗ trợ `PublishedEvents` theo API phiên bản đang dùng để kiểm tra event type và payload. Test phải xác minh cả state đã thay đổi và trường hợp command bị từ chối không phát event thành công.

### 20.2. Test AFTER_COMMIT cần commit thật

Ví dụ kiểm thử tích hợp có `TransactionTemplate`:

~~~java
@SpringBootTest
class OrderEventTransactionTest {

    @Autowired TransactionTemplate transactions;
    @Autowired ApplicationEventPublisher events;
    @Autowired NotificationJobRepository jobs;

    @Test
    void listenerCreatesJobAfterCommit() {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        transactions.executeWithoutResult(status ->
                events.publishEvent(new OrderConfirmed(
                        eventId, orderId, Instant.now()
                ))
        ); // Kết thúc callback -> commit transaction.

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(jobs.existsBySourceEventId(eventId)).isTrue()
        );
    }
}
~~~

Đây là ví dụ có chủ đích dùng API test của Spring Boot, `TransactionTemplate` và Awaitility; giả định các bean/event class và imports đã có. Cần điều chỉnh theo ứng dụng, datasource và chính sách test. Không bọc toàn bộ test trong `@Transactional` mặc định rollback mà vẫn kỳ vọng `AFTER_COMMIT` chạy.

### 20.3. Test rollback không kích hoạt listener after-commit

~~~java
@Test
void rollbackDoesNotTriggerAfterCommitListener() {
    UUID eventId = UUID.randomUUID();
    UUID orderId = UUID.randomUUID();

    assertThatThrownBy(() -> transactions.executeWithoutResult(tx -> {
        events.publishEvent(new OrderConfirmed(
                eventId, orderId, Instant.now()
        ));
        throw new IllegalStateException("force rollback");
    })).isInstanceOf(IllegalStateException.class);

    await().during(Duration.ofMillis(300))
            .atMost(Duration.ofSeconds(2))
            .untilAsserted(() ->
                    assertThat(jobs.existsBySourceEventId(eventId)).isFalse()
            );
}
~~~

Test “không có side effect” khi async thường cần cách kiểm chứng phù hợp để tránh false positive (listener có thể chỉ chưa kịp chạy). Ở đây dùng khung thời gian quan sát minh họa; kiểm thử đáng tin cậy hơn có thể dùng test instrumentation hoặc kiểm soát executor. Không dùng thời gian 300 ms như một guarantee về mọi môi trường.

### 20.4. Kiểm thử lỗi sau commit và retry

| Test | Kỳ vọng |
| --- | --- |
| Listener ném exception khi ghi notification job | Transaction Notifications rollback, Orders không rollback |
| Registry lưu publication khi listener thất bại | Publication được nhìn thấy ở trạng thái chưa hoàn thành theo backend |
| Khôi phục/republication cùng event ID | Tạo đúng một notification job |
| Consumer đã commit, crash trước completion | Retry không tạo side effect trùng |
| Hai event song song cùng business key | DB constraint giữ invariant |
| Event cũ được xử lý sau event mới | State guard/version ngăn áp dụng sai |
| Application restart giữa commit và xử lý | Publication có thể phục hồi khi persistence và resubmission được cấu hình |

### 20.5. Kiểm tra ranh giới module độc lập với transaction

Spring Modulith có thể xác minh dependency:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void verifyDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Architecture test giúp phát hiện việc consumer import type nội bộ của publisher, nhưng không xác minh transaction commit/rollback. Cần cả architecture test lẫn integration test với database và listener thực tế.

## 21. Quan sát transaction và publication trong vận hành

Một hệ thống event đáng tin cậy cần phân biệt nhiều mốc thành công:

1. **Publisher T1 committed:** state nghiệp vụ đã được lưu.
2. **Publication recorded:** có bản ghi giao việc tới transactional listener nếu cấu hình registry phù hợp.
3. **Listener invoked:** callback bắt đầu.
4. **Consumer T2 committed:** dữ liệu module nhận đã cập nhật thành công.
5. **Publication completed:** registry đánh dấu xử lý hoàn thành theo cơ chế của mình.
6. **External side effect confirmed:** nếu có email/API ngoài, kết quả đã được quan sát/đối soát riêng.

| Chỉ số / thuộc tính | Mục đích |
| --- | --- |
| `eventId`, `eventType`, `orderId` | Trace xuyên publisher và consumer |
| `transaction phase`, `listener name` | Xác định callback chạy ở đâu và khi nào |
| Publication pending/failed/completed | Theo dõi delivery theo listener |
| Tuổi publication cũ nhất | Phát hiện backlog bị kẹt |
| Retry count và exception category | Phân biệt lỗi tạm thời với lỗi vĩnh viễn |
| Consumer commit/rollback count | Theo dõi lỗi DB và concurrency |
| End-to-end latency | Đo thời gian từ publisher commit đến consumer completion |
| Duplicate event rate | Đánh giá idempotency/recovery |

Không log toàn bộ payload chứa dữ liệu nhạy cảm. Ghi ID, loại event, correlation ID và trạng thái theo cấu trúc đủ để nối các bản ghi. Một log “event published” không thay thế giám sát consumer completed.

## 22. Bài tập thực hành

### Bài 1 — Vẽ transaction boundary

Cho use case:

~~~text
Orders.confirm()
  -> update Order
  -> publish OrderConfirmed
     -> Notifications.on() tạo email job
     -> Fulfillment.on() tạo packing request
~~~

Hãy vẽ hai phiên bản: `@EventListener` đồng bộ cùng transaction và `@ApplicationModuleListener` sau commit với transaction riêng. Chỉ ra exception nào có thể làm Orders rollback và exception nào không.

### Bài 2 — Sửa lỗi AFTER_COMMIT

Một developer viết:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderConfirmed event) {
    repository.save(NotificationJob.forOrder(event.orderId()));
}
~~~

Hãy giải thích rủi ro của thao tác ghi dữ liệu trong callback after-commit và sửa bằng service có `REQUIRES_NEW` hoặc một `@ApplicationModuleListener` phù hợp. Bổ sung test có commit thật.

### Bài 3 — Phân tích tình huống crash

T1 đã commit; T2 đã tạo notification job và commit; ứng dụng crash trước khi publication completed. Hãy mô tả vì sao registry có thể giao lại event và thiết kế unique constraint theo `eventId` để không tạo hai job.

### Bài 4 — Quyết định giữ hàng

Đơn hàng chỉ được xác nhận nếu Inventory đã giữ đủ số lượng. Bạn có nên để Inventory nhận `OrderConfirmed` bất đồng bộ sau commit không? Nếu không, hãy trình bày phương án public API đồng bộ cùng transaction (khi cùng tài nguyên) hoặc một saga/workflow khi Inventory nằm ngoài ứng dụng.

### Bài 5 — Xử lý event ngoài transaction

Một batch job phát `OrderConfirmed` sau khi đã thực hiện nhiều thao tác không có transaction. Listener có `@TransactionalEventListener` nhưng không chạy. Hãy xác định nguyên nhân, phân tích `fallbackExecution` và đề xuất cách đảm bảo sự thật đã được lưu bền trước khi phát.

## 23. Checklist thiết kế transaction boundary

- [ ] Phân biệt rõ transaction nghiệp vụ của publisher và transaction của mỗi listener.
- [ ] Đã xác định business invariant nào phải được giữ atomic và không chuyển tùy tiện sang after-commit.
- [ ] Đã chọn `@EventListener` hay `@TransactionalEventListener` theo đúng thời điểm cần xử lý.
- [ ] Listener chỉ thực hiện side effect sau commit nếu sự thật nghiệp vụ đòi hỏi state đã commit.
- [ ] Khi cần ghi DB trong callback after-commit, dùng transaction mới phù hợp.
- [ ] `@ApplicationModuleListener` đã được cấu hình async/executor và transaction đúng mục đích.
- [ ] Có cơ chế idempotency bền vững với unique constraint theo event/business key.
- [ ] Không dùng in-memory cache để thay thế dấu đã xử lý qua restart hoặc multi-instance.
- [ ] Có backend Event Publication Registry/outbox nếu cần khôi phục publication sau crash.
- [ ] Đã xác định chính sách retry, poison event, resubmission, logging và alert.
- [ ] Payload không chứa JPA entity mutable, connection hay transaction context.
- [ ] Test có commit thật, rollback, lỗi listener, duplicate, crash và ordering.
- [ ] UI/API phản ánh được eventual consistency khi consumer xử lý sau commit.

## 24. Tổng kết

**Transaction boundary là ranh giới của commit và rollback, không phải ranh giới class hay module.** Một event do Orders phát có thể được listener đồng bộ xử lý trong cùng transaction hoặc được transactional listener nhận sau khi Orders commit. Đây là hai mô hình khác nhau về coupling lỗi, tính nhất quán và khả năng phục hồi.

Trong Spring Modulith, `@ApplicationModuleListener` là lựa chọn thuận tiện cho giao tiếp liên module sau commit, bất đồng bộ và có transaction riêng. Khi transaction publisher đã commit, lỗi consumer không thể tự rollback giao dịch nguồn; hệ thống cần chấp nhận eventual consistency, theo dõi publication và xử lý lại khi cần.

Event Publication Registry hỗ trợ lưu và quản lý publication với cấu hình phù hợp, nhưng không tạo atomic transaction toàn hệ thống hay bảo đảm exactly-once cho email/API bên ngoài. Để giao sự kiện đáng tin cậy, hãy phối hợp **transaction đúng biên + hợp đồng event rõ ràng + idempotency + retry/recovery + kiểm thử và quan sát**.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): listener liên module, Event Publication Registry và khả năng khôi phục.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): các phase, `fallbackExecution` và lưu ý về after-commit.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW` và `NESTED`.

> Ví dụ Java chỉ minh họa những thành phần cốt lõi; cần khai báo imports/dependency, transaction manager, repository, migration/schema và cấu hình asynchronous execution đúng với phiên bản Spring đang dùng. Đây là bài biên soạn STEP 4; kiểm tra chuyên môn chuyên sâu được thực hiện ở bước QA tiếp theo.
