# Publish event

## 1. Publish event nằm ở đâu trong chu kỳ phát hành?

Trong một **modular monolith**, các module cùng chạy trong một ứng dụng Spring Boot nhưng có trách nhiệm nghiệp vụ riêng. Module `orders` xử lý đơn hàng; `inventory` quản lý tồn kho; `notifications` gửi thông báo; `reporting` xây dựng báo cáo. Khi đơn hàng được xác nhận, các module khác cần biết **sự kiện đã xảy ra** để thực hiện công việc của chúng.

Thay vì để `orders` lần lượt gọi các service của mọi module nhận, nó có thể **publish** (phát hành) một *application event*, ví dụ `OrderConfirmed`. Những module quan tâm tự khai báo listener:

~~~mermaid
flowchart LR
    API["HTTP / Application service"] --> O["orders<br/>Xác nhận đơn"]
    O --> P["ApplicationEventPublisher<br/>publishEvent(OrderConfirmed)"]
    P --> N["notifications<br/>Gửi thông báo"]
    P --> R["reporting<br/>Cập nhật báo cáo"]
    P --> L["loyalty<br/>Tích điểm"]
~~~

**Publish event** là thao tác module nguồn **công bố một sự thật nghiệp vụ** thông qua cơ chế application events của Spring. Việc gọi `publishEvent(...)` chỉ khởi động quá trình phân phối event theo cơ chế đã cấu hình; nó **không đồng nghĩa** dữ liệu nguồn đã commit, mọi listener đã xử lý xong hoặc event đã được lưu bền.

Trong học phần **SPRING_MODULITH_APPLICATION_EVENTS**, cần hiểu thao tác publish ở cả hai góc độ:

- **Kiến trúc:** module phát chỉ biết hợp đồng event do chính nó công bố; nó không cần import listener hoặc service của module nhận.
- **Vòng đời kỹ thuật:** event được tạo, phát vào bộ phân phối của Spring, có thể được đăng ký trong Event Publication Registry, chờ transaction commit, giao đến listener và đánh dấu hoàn tất hoặc giữ lại để phục hồi.

Sau bài này, bạn có thể tự viết publisher, giải thích chính xác điều gì xảy ra khi commit/rollback, chọn loại listener phù hợp, và xác minh event được giao đáng tin cậy khi ứng dụng gặp lỗi.

## 2. Event là một sự thật đã xảy ra, không phải lời ra lệnh

Trước khi gọi `publishEvent`, module nguồn phải quyết định **sự kiện nào đáng để công bố**:

| Kiểu thông điệp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Domain/application event | `OrderConfirmed` | Đơn hàng **đã được xác nhận** |
| Command | `ConfirmOrder` | Hãy thực hiện việc xác nhận đơn |
| Query | `FindOrderSummary` | Hãy trả về thông tin hiện tại của đơn |

Nếu `orders` cần hệ thống tồn kho trả lời **còn đủ hàng hay không** trước khi chấp nhận đơn, thông thường nó cần API truy vấn/command có kết quả rõ ràng. Nếu đơn đã được xác nhận và việc gửi email chỉ là tác động phụ, `OrderConfirmed` là lựa chọn phù hợp.

Một event tốt thường có các đặc điểm:

1. **Tên ở thì đã xảy ra:** `OrderConfirmed`, `PaymentCaptured`, `StockReserved`.
2. **Dữ liệu cần thiết, bất biến:** ID thực thể, thời điểm, thông tin cốt lõi cho consumer; không truyền entity JPA managed hoặc repository nội bộ.
3. **Được công khai ở ranh giới module:** consumer chỉ import kiểu event trong API hợp lệ của module phát.
4. **Có định danh phục vụ truy vết:** `eventId` xác định event logic; `correlationId` liên kết các event thuộc cùng một quy trình nếu cần.
5. **Chỉ phát khi nghiệp vụ thực sự đổi trạng thái:** không phát `OrderConfirmed` một lần nữa khi lệnh xác nhận chỉ trả về “đã xác nhận từ trước”, trừ khi hợp đồng nghiệp vụ quy định một sự kiện khác.

Ví dụ về event bất biến với Java 17+:

~~~java
// com/example/shop/orders/OrderConfirmed.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID correlationId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderConfirmed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(correlationId, "correlationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

`OrderConfirmed` không chứa `OrderEntity` hoặc trạng thái của Hibernate session. Module `notifications` có thể sử dụng event ngay cả sau khi transaction nguồn đã kết thúc. `eventId` nên giữ nguyên nếu **cùng event** được phát lại; một lần xác nhận hợp lệ mới phát event mới với ID mới.

## 3. ApplicationEventPublisher trong Spring

Spring Framework cung cấp interface `org.springframework.context.ApplicationEventPublisher`. Đây là API cơ bản mà Spring Modulith sử dụng làm nền tảng tổ chức giao tiếp giữa các module:

~~~java
import org.springframework.context.ApplicationEventPublisher;

// Trong một Spring bean:
publisher.publishEvent(new OrderConfirmed(
        eventId, correlationId, orderId, occurredAt));
~~~

Bạn không cần kế thừa `ApplicationEvent` cho event kiểu record. Spring hỗ trợ publish đối tượng thông thường (POJO event). Khi publish, Spring chuyển event đến các listener phù hợp theo bộ phân phối `ApplicationEventMulticaster` được cấu hình.

Mặc định phổ biến, listener `@EventListener` chạy **đồng bộ** trên thread của publisher. Vì vậy:

~~~java
publisher.publishEvent(event);
// Đến đây listener @EventListener đồng bộ thường đã chạy.
// Nhưng listener AFTER_COMMIT/async có thể CHƯA chạy.
~~~

**Không suy luận rằng `publishEvent` luôn trả về ngay và không bao giờ ném lỗi.** Một `@EventListener` đồng bộ có thể ném exception ngay trong lời gọi publish; nếu lệnh đang ở transaction, lỗi có thể khiến transaction nguồn rollback. Khi một `ApplicationEventMulticaster` được tùy biến để chạy bất đồng bộ, hành vi phân phối khác mặc định; cần kiểm tra cấu hình thực tế.

**Cũng không suy luận rằng `publishEvent` là gửi message đến Kafka/RabbitMQ.** Spring application event cơ bản chỉ chạy bên trong cùng ứng dụng. Nếu cần truyền sang tiến trình khác phải thiết kế externalization/message broker riêng.

## 4. Triển khai publisher trong module sở hữu nghiệp vụ

Giả sử `orders` sở hữu trạng thái xác nhận đơn. Thao tác xác nhận được thực hiện trong transaction và publish event sau khi nghiệp vụ đã chuyển trạng thái trong persistence context:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderConfirmed.java             # Event công khai
│   └── internal/
│       ├── OrderEntity.java
│       ├── OrderRepository.java
│       └── OrderService.java           # Nơi phát event
├── notifications/
│   └── internal/
│       └── ConfirmationListener.java   # Consumer
└── reporting/
    └── internal/
        └── OrderProjectionListener.java
~~~

~~~java
// com/example/shop/orders/internal/OrderService.java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher,
                        Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId, UUID correlationId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();

        if (order.isConfirmed()) {
            return; // Không tạo event mới khi không có chuyển trạng thái.
        }

        order.confirm(); // Kiểm tra quy tắc nghiệp vụ của orders.

        publisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                correlationId,
                order.getId(),
                Instant.now(clock)));
    }
}
~~~

`OrderRepository`, `OrderEntity` và `Clock` là các thành phần minh họa, cần được hiện thực/cấu hình trong ứng dụng. Nếu hai request xác nhận đồng thời, việc kiểm tra `isConfirmed()` **chưa đủ** để chống race condition: phải có optimistic locking, khóa database hoặc ràng buộc trạng thái phù hợp.

Vị trí publish nằm trong transaction do Spring quản lý:

1. `orders` đọc và kiểm tra đơn hàng.
2. `orders` cập nhật trạng thái của entity.
3. `orders` publish `OrderConfirmed` mô tả chuyển trạng thái ấy.
4. Transaction nguồn **commit hoặc rollback** khi phương thức hoàn thành.

**Lưu ý:** transaction chỉ được Spring áp dụng khi lời gọi đi qua cơ chế proxy/transaction phù hợp. Nếu gọi trực tiếp một phương thức `@Transactional` từ một phương thức khác trong cùng bean (*self-invocation*), transaction mong muốn có thể không được kích hoạt. Khi đó listener `AFTER_COMMIT` mặc định có thể không nhận event vì không có transaction đang hoạt động.

Không nên dùng `publishEvent(...)` để “ra lệnh” cho module khác sửa trực tiếp trạng thái do `orders` sở hữu. Module nguồn phải tự bảo đảm bất biến nghiệp vụ trước khi phát event.

## 5. Dòng thời gian: publish, commit, dispatch, completion

Lỗi thường gặp là xem publish như một lời gọi đồng nghĩa với “đã giao và xử lý xong”. Thực tế vòng đời gồm nhiều mốc:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as orders
    participant S as Spring Events
    participant DB as Database
    participant R as Publication Registry
    participant N as notifications
    C->>O: confirm(orderId)
    O->>DB: Đổi trạng thái đơn (transaction A)
    O->>S: publishEvent(OrderConfirmed)
    S->>R: Đăng ký publication theo listener (A)
    Note over O,R: Lúc publish, transaction A chưa commit
    O->>DB: COMMIT A
    DB-->>S: Sau commit thành công
    S-->>N: Giao event cho listener AFTER_COMMIT
    N->>DB: Ghi việc xử lý (transaction B)
    N-->>R: Xử lý thành công / ghi nhận completion
~~~

Sơ đồ là **mô hình khái niệm** khi đã cấu hình registry bền vững và listener sau commit. Cơ chế callback, lưu publication và ghi completion cụ thể phụ thuộc phiên bản Spring Modulith, backend registry và cấu hình. Nếu không có registry phù hợp, bước “đăng ký publication” không đồng nghĩa đã có một bản ghi bền vững.

| Thời điểm | Điều đã chắc chắn | Điều chưa chắc chắn |
| --- | --- | --- |
| Tạo `new OrderConfirmed(...)` | Có đối tượng event trong bộ nhớ | Event chưa được publish |
| Gọi `publishEvent(event)` | Spring bắt đầu phân phối theo cấu hình; listener đồng bộ có thể chạy | Dữ liệu nguồn chưa chắc commit, listener sau commit chưa chắc chạy |
| Transaction A commit | Trạng thái của module nguồn được commit | Listener async có thể còn chờ |
| Listener nhận event sau commit | Consumer được gọi với payload event | Side effect của consumer chưa chắc thành công |
| Listener hoàn tất | Có thể ghi nhận publication đã hoàn tất | Side effect bên ngoài chưa chắc đúng một lần nếu thiếu idempotency |
| Listener thất bại | Cần quan sát và có đường phục hồi | Không nên giả định tự retry vô hạn |

**Giao event thành công** cần được định nghĩa theo từng mục tiêu: publisher đã gọi `publishEvent`, dữ liệu nguồn đã commit, listener đã nhận, hay tác động nghiệp vụ đã hoàn tất. Những mức ấy khác nhau.

## 6. Đồng bộ và sau commit là hai lựa chọn có tác động khác nhau

### 6.1. Listener đồng bộ: `@EventListener`

~~~java
import com.example.shop.orders.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class SynchronousAuditListener {
    @EventListener
    void on(OrderConfirmed event) {
        // Thường chạy ngay khi publisher gọi publishEvent(...).
        // Có thể đang ở trong transaction nguồn.
    }
}
~~~

Theo cấu hình mặc định, exception từ listener đồng bộ có thể lan ngược tới publisher. Nếu listener làm tác động bên ngoài như gửi email ngay lúc này, rồi transaction nguồn rollback, email có thể đã được gửi **cho một đơn chưa commit**. Đó là lý do những tác vụ chỉ có ý nghĩa sau khi nghiệp vụ hoàn tất thường không nên chạy bằng listener đồng bộ trong transaction nguồn.

Listener đồng bộ vẫn có chỗ dùng: kiểm tra hoặc phản ứng **phải chạy cùng lời gọi hiện tại**, với ngữ nghĩa transaction và xử lý lỗi được thiết kế rõ ràng. Không biến mỗi công việc phụ thành listener đồng bộ chỉ vì dễ triển khai.

### 6.2. Listener theo transaction: `@TransactionalEventListener`

~~~java
import com.example.shop.orders.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AfterCommitAuditListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        // Chỉ chạy khi transaction nguồn đã commit thành công.
    }
}
~~~

Giá trị mặc định của `phase` cũng là `AFTER_COMMIT`. Khi transaction nguồn rollback, listener `AFTER_COMMIT` **không** chạy. Khi publish ngoài transaction, listener `@TransactionalEventListener` mặc định bị bỏ qua, trừ khi đặt `fallbackExecution = true`.

**`AFTER_COMMIT` không đồng nghĩa có transaction ghi mới.** Transaction nguồn đã hoàn tất nhưng tài nguyên có thể còn được giữ trong callback; các thao tác ghi cần transaction mới nếu phải commit độc lập. Và `@TransactionalEventListener` tự nó **không làm listener bất đồng bộ**.

### 6.3. Spring Modulith: `@ApplicationModuleListener`

~~~java
// com/example/shop/notifications/internal/ConfirmationListener.java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ConfirmationListener {
    private final NotificationService notifications;

    ConfirmationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.sendConfirmationOnce(event.orderId());
    }
}
~~~

Spring Modulith cung cấp `@ApplicationModuleListener` như tổ hợp xử lý **sau commit**, **bất đồng bộ** và **transaction mới** (`REQUIRES_NEW`). Cần bật/configure hỗ trợ async phù hợp với ứng dụng (chẳng hạn `@EnableAsync`, executor và giới hạn hàng chờ), đồng thời có các dependency Spring Modulith cần thiết.

Với thiết kế này, `orders` không cần biết `notifications`. Sau khi đơn đã commit, module nhận tự quản lý trạng thái gửi thông báo. Nếu việc gửi lỗi, đơn hàng vẫn giữ trạng thái đã commit. Muốn xử lý lỗi đáng tin cậy phải có registry và chiến lược khôi phục thích hợp.

| Loại listener | Mốc xử lý thông thường | Lỗi có thể rollback nguồn? | Tự tạo transaction mới? |
| --- | --- | --- | --- |
| `@EventListener` | Ngay khi publish (mặc định đồng bộ) | Có thể, nếu cùng transaction và exception lan ra | Không |
| `@TransactionalEventListener` | Sau commit theo mặc định | Không, vì nguồn đã commit | Không |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ | Không | Có, theo `REQUIRES_NEW` |

## 7. Rollback: event được publish nhưng nghiệp vụ chưa thành công

Hãy xét:

~~~java
@Transactional
public void confirmThenFail(UUID orderId, UUID correlationId) {
    confirmWithinSameTransaction(orderId, correlationId);
    throw new IllegalStateException("Không thể hoàn tất tác vụ");
}
~~~

Giả sử `confirmWithinSameTransaction(...)` cập nhật đơn và publish event trong **transaction đang hoạt động**:

- Event có thể đã được **phân phối tới `@EventListener` đồng bộ**, vì listener này chạy lúc publish.
- Thay đổi database sẽ rollback khi exception khiến transaction rollback.
- Các `@TransactionalEventListener(AFTER_COMMIT)` và `@ApplicationModuleListener` sẽ **không được thực thi theo pha sau commit**.
- Với Event Publication Registry được ghi trong cùng transaction và cấu hình đúng, bản ghi publication của transaction này cũng rollback, không tồn tại một publication đã commit để phục hồi.

Vì vậy đừng xem `publishEvent` như xác nhận “đơn đã được đặt thành công”. Với listener đồng bộ, cần tránh side effect bên ngoài không thể rollback, hoặc cần thiết kế một cơ chế nhất quán khác.

Một trường hợp khác: phương thức publisher được gọi **ngoài transaction**. Spring vẫn có thể giao event tới `@EventListener` thường, nhưng listener sau commit mặc định không chạy. Nếu nghiệp vụ cần tính nhất quán giữa việc thay đổi dữ liệu nguồn và publication, hãy bảo đảm transaction ở đúng **application service** sở hữu việc cập nhật.

## 8. Event Publication Registry bắt đầu tham gia khi nào?

Một hệ thống chỉ dùng Spring application events thông thường không có cơ chế đảm bảo bền vững rằng một listener sẽ hoàn tất sau khi nguồn commit. Ví dụ: transaction đơn hàng commit, nhưng JVM dừng đột ngột trước khi listener bất đồng bộ kịp xử lý. Event chỉ nằm trong bộ nhớ có thể mất.

**Event Publication Registry** của Spring Modulith giải quyết một phần quan trọng của khoảng trống này:

1. **Đăng ký publication:** khi một event được publish, registry ghi nhận các publication dành cho các transactional listener phù hợp. Với implementation transaction-aware/bền vững được cấu hình đúng, việc đăng ký gắn với **transaction nguồn**.
2. **Commit nguồn:** thay đổi nghiệp vụ và các bản ghi publication được commit nhất quán; nếu transaction rollback, chúng rollback cùng nhau.
3. **Dispatch sau commit:** các listener được gọi sau commit theo loại/pha đã khai báo.
4. **Hoàn tất:** khi listener thành công, registry ghi nhận publication đã hoàn tất theo cơ chế completion của implementation/cấu hình.
5. **Chưa hoàn tất / lỗi:** nếu listener thất bại hoặc ứng dụng dừng, còn dữ liệu publication để quan sát và thực hiện resubmit/recovery theo cơ chế đã thiết lập.

Điều kiện quan trọng là **phải dùng một backend registry thực sự phù hợp**, chẳng hạn implementation dựa trên JDBC hoặc JPA với database/schema/transaction được cấu hình. Chỉ thêm `@ApplicationModuleListener` **không tự tạo kho event bền vững**.

Registry theo dõi việc giao event cho listener; nó không nhất thiết là **event store** lưu mọi event cho mục đích event sourcing và không thay thế audit nghiệp vụ dài hạn nếu có yêu cầu đó.

**Đừng mặc định retry tự động vô hạn.** Tùy phiên bản Spring Modulith và cấu hình, ứng dụng có thể cần kích hoạt cơ chế resubmit khi restart, gọi API quản trị phục hồi hoặc xây dựng job vận hành riêng. Phải theo dõi những publication chưa hoàn tất và có quy trình xử lý lỗi dữ liệu vĩnh viễn.

## 9. Thất bại ở từng giai đoạn và cách phản ứng

| Giai đoạn | Ví dụ lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- | --- |
| Trước publish | Kiểm tra đơn không hợp lệ | Không nên tạo event `OrderConfirmed` | Trả lỗi nghiệp vụ; không phát sự thật chưa xảy ra |
| Khi publish trong transaction | Listener đồng bộ ném exception | Có thể khiến transaction nguồn rollback | Xác định listener có cần đồng bộ không; xử lý exception hợp lý |
| Trước commit | Database từ chối ghi, deadlock, constraint | Transaction rollback | Không xử lý after-commit cho trạng thái chưa thành công |
| Sau commit, trước dispatch | JVM dừng | Dữ liệu nguồn đã commit nhưng listener chưa chạy | Registry bền vững + khôi phục publication |
| Listener đang thực thi | Timeout gọi email/API | Nguồn vẫn commit; listener có thể chưa hoàn tất | Retry có kiểm soát và idempotency |
| Sau side effect, trước completion | Email đã gửi, JVM dừng | Phục hồi có thể xử lý lại cùng event | Chống gửi trùng hoặc idempotency key downstream |
| Đọc lại event cũ | Payload không còn deserialize được | Publication tồn nhưng không xử lý được | Chiến lược tương thích schema/version |

**Exactly-once cho side effect bên ngoài không đến chỉ từ registry.** Ví dụ gửi email thành công, rồi tiến trình dừng trước khi đánh dấu publication hoàn tất. Khi phục hồi, cùng event có thể được giao lại. Listener phải có cơ chế phát hiện xử lý trùng, và nếu đối tác hỗ trợ idempotency key thì nên truyền khóa ổn định.

Khóa idempotency tùy nghiệp vụ:

- Với một đơn chỉ được gửi đúng một email xác nhận: khóa `(orderId, notificationType)`.
- Với mỗi event có thể tạo một side effect độc lập: khóa `(eventId, consumerName)`.
- Với một khoản thưởng cho mỗi đơn: ràng buộc unique `(orderId, rewardType)`.

Không dùng `correlationId` làm khóa deduplicate toàn bộ event: nhiều event hợp lệ có thể cùng thuộc một correlation ID.

## 10. Không phát event hai lần chỉ vì listener chưa hoàn tất

Giả sử nguồn đã xác nhận đơn, phát `OrderConfirmed(E1)` và transaction commit. Listener email gặp lỗi. Nếu người vận hành **gọi lại phương thức xác nhận đơn** để “thử lại event”, có hai vấn đề:

1. Lời gọi có thể không phát event vì đơn đã được xác nhận; listener vẫn chưa được phục hồi.
2. Nếu code sai và cố phát `OrderConfirmed(E2)` mới, event mới có thể tạo thêm publication, thêm lần gửi email và sai lịch sử nghiệp vụ.

Đường đúng là phân biệt hai tác vụ:

**Lặp lại thao tác nghiệp vụ** (`confirmOrder`) là một command mới hoặc lệnh được retry, cần kiểm tra idempotency của command và trạng thái đơn.

**Phát lại publication của một event đã xảy ra** (`OrderConfirmed(E1)`) là khôi phục việc giao cho listener chưa hoàn tất. Nó phải giữ ngữ nghĩa và ID của event gốc, sử dụng registry hoặc cơ chế phục hồi được thiết kế.

Một command mới hợp lệ làm phát sinh **sự kiện nghiệp vụ mới** thì có thể tạo event ID mới. Nhưng lỗi giao event cũ **không có nghĩa** nghiệp vụ cũ đã xảy ra lần thứ hai.

## 11. Kiểm thử publisher, transaction và delivery

Cần kiểm tra nhiều lớp khác nhau vì một test chỉ xác minh `publishEvent` được gọi chưa chứng minh event sẽ được giao đáng tin cậy.

### 11.1. Unit test: publisher phát đúng event

Đây là ví dụ unit test dùng JUnit 5, Mockito và AssertJ, giả định các lớp `OrderRepository` và `OrderEntity` đã được định nghĩa trong module:

~~~java
package com.example.shop.orders.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class OrderServiceTest {

    @Test
    void publishesOrderConfirmedWithExpectedIds() {
        OrderRepository orders = mock(OrderRepository.class);
        OrderEntity order = mock(OrderEntity.class);
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-10T08:30:00Z"), ZoneOffset.UTC);

        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();
        when(orders.findById(orderId))
                .thenReturn(java.util.Optional.of(order));
        when(order.isConfirmed()).thenReturn(false);
        when(order.getId()).thenReturn(orderId);

        new OrderService(orders, publisher, clock)
                .confirm(orderId, correlationId);

        ArgumentCaptor<OrderConfirmed> captured =
                ArgumentCaptor.forClass(OrderConfirmed.class);
        verify(publisher).publishEvent(captured.capture());
        verify(order).confirm();

        OrderConfirmed event = captured.getValue();
        assertThat(event.orderId()).isEqualTo(orderId);
        assertThat(event.correlationId()).isEqualTo(correlationId);
        assertThat(event.eventId()).isNotNull();
        assertThat(event.occurredAt())
                .isEqualTo(Instant.parse("2026-01-10T08:30:00Z"));
    }
}
~~~

Unit test gọi trực tiếp đối tượng service, **không kích hoạt transaction proxy của Spring**; test này chỉ xác minh rằng code publisher phát event đúng theo điều kiện nghiệp vụ. Một test khác cần kiểm tra nhánh `order.isConfirmed() == true` để chắc chắn không phát event mới khi trạng thái không đổi.

### 11.2. Integration test: chỉ xử lý sau commit

Với Spring Boot test và một database kiểm thử tương thích, kiểm tra:

1. **Commit thành công:** tạo đơn, gọi `OrderService.confirm(...)` đi qua Spring bean để mở transaction, commit; chờ listener async với timeout rồi xác minh trạng thái bên nhận.
2. **Rollback nguồn:** sau khi publish trong transaction, gây exception làm rollback; xác minh listener `AFTER_COMMIT` không thực hiện side effect.
3. **Không có transaction:** publish event thử nghiệm ngoài transaction và xác nhận listener transaction mặc định không thực thi, trong khi `@EventListener` đồng bộ có thể thực thi.
4. **Lỗi listener:** cố tình ném exception trong listener; xác minh publication chưa hoàn tất theo registry backend đang dùng.
5. **Phục hồi:** kích hoạt đường recovery/resubmit đã cấu hình và xác minh listener có thể xử lý lại **cùng event**.
6. **Idempotency:** gây lỗi sau side effect rồi thử lại, xác minh kết quả nghiệp vụ không bị nhân đôi.

Không đánh dấu toàn bộ bài test `@Transactional` nếu transaction test mặc định rollback và bạn cần kiểm tra `AFTER_COMMIT`: listener sau commit có thể không được gọi. Cần tổ chức test thực sự commit transaction nguồn, và dùng cơ chế chờ có timeout thay vì assert ngay sau `publishEvent(...)` khi listener bất đồng bộ.

### 11.3. Kiểm tra ranh giới module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {
    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện các phụ thuộc module không hợp lệ do Spring Modulith nhận diện, nhưng **không thay thế** kiểm thử transaction, delivery hay SQL truy cập trực tiếp dữ liệu module khác.

## 12. Quan sát vòng đời publish event trong vận hành

Một hệ thống đáng tin cậy phải quan sát được **mốc nào đã xảy ra và mốc nào đang chờ**. Có thể theo dõi:

| Chỉ số/log | Ý nghĩa | Hành động khi bất thường |
| --- | --- | --- |
| Số event được publish theo loại | Tần suất phát sự kiện nghiệp vụ | Xem lại publisher hoặc lưu lượng yêu cầu |
| Publication chưa hoàn tất | Listener nào chưa có completion | Kiểm tra lỗi và quy trình phục hồi |
| Tuổi publication lâu nhất | Event đã chờ bao lâu | Điều tra listener bị lỗi hoặc hàng đợi nghẽn |
| Tỉ lệ/độ trễ xử lý listener | Consumer xử lý nhanh hay chậm | Kiểm tra executor, database, phụ thuộc bên ngoài |
| Số lần resubmit và lỗi | Xu hướng retry lặp lại | Tách lỗi tạm thời và lỗi dữ liệu vĩnh viễn |
| ID trên log | Nối event gốc với lần xử lý và retry | Tra theo `eventId`, `correlationId`, `orderId` |

Ví dụ logging ở publisher:

~~~java
log.info("Publishing OrderConfirmed eventId={} correlationId={} orderId={}",
        event.eventId(), event.correlationId(), event.orderId());
publisher.publishEvent(event);
~~~

Đặt log tại vị trí này chỉ chứng minh **đã bắt đầu publish**. Không được diễn giải dòng log thành “đã commit và toàn bộ listener đã thành công”. Hãy ghi nhận log/metric completion ở listener hoặc registry theo cơ chế phù hợp.

Với listener async, `MDC` hoặc `ThreadLocal` của HTTP thread gốc không tự động được đảm bảo giữ nguyên. Nếu cần truy vết lâu dài qua retry và restart, đặt `correlationId` trong event rồi tái tạo context log ở listener. Không dùng UUID event/correlation làm tag metrics có cardinality rất cao; giữ ID chi tiết trong log/trace.

## 13. Bài thực hành: publish một event đáng tin cậy

Tạo hai module `orders` và `notifications` trong cùng Spring Boot application. `orders` có API `confirm(orderId, correlationId)`, chỉ xác nhận đơn hợp lệ; `notifications` gửi thông báo sau commit.

Yêu cầu thực hành:

1. Tạo record `OrderConfirmed` công khai với `eventId`, `orderId`, `correlationId` và `occurredAt`.
2. Inject `ApplicationEventPublisher` vào service nội bộ của `orders`; gọi `publishEvent(...)` **một lần** sau khi chuyển trạng thái hợp lệ, trong transaction của service.
3. Viết `@ApplicationModuleListener` ở `notifications`; tự quản lý dữ liệu và trạng thái gửi thông báo, không import `OrderRepository`.
4. Cấu hình backend Event Publication Registry bền vững phù hợp với persistence của ứng dụng; xác định cách kiểm tra publication chưa hoàn tất và cách recovery theo phiên bản đang dùng.
5. Cho listener thất bại một lần, kiểm tra trạng thái đơn vẫn commit và publication còn được theo dõi; sau đó thử khôi phục.
6. Dùng khóa idempotency để xử lý tình huống listener gửi thành công nhưng publication chưa kịp đánh dấu hoàn tất.
7. Viết test cho ba đường: commit thành công, rollback nguồn và phát lại publication. Kiểm tra cấu trúc module với `ApplicationModules.verify()`.

**Câu hỏi tự đánh giá:**

- Sau `publishEvent(...)`, điều kiện nào khiến `@EventListener` đã chạy nhưng `@ApplicationModuleListener` chưa chạy?
- Khi transaction nguồn rollback, listener `AFTER_COMMIT` và bản ghi publication có trạng thái thế nào nếu registry được đăng ký cùng transaction?
- Nếu JVM dừng sau commit nhưng trước dispatch, cơ chế nào giúp biết listener chưa hoàn tất?
- Nếu email đã gửi nhưng ghi nhận completion lỗi, chỉ retry publication có đủ để tránh gửi email lần hai không?
- Vì sao không nên gọi lại `confirmOrder` để sửa lỗi listener?

## 14. Ghi nhớ

**Publish event** bằng `ApplicationEventPublisher.publishEvent(...)` là hành động **công bố sự thật nghiệp vụ** vào cơ chế application events của Spring; nó **không phải một cam kết đã commit, đã giao bền vững hay đã xử lý xong**. Các mốc tạo event, publish, đăng ký publication, commit, listener xử lý, ghi completion và phục hồi phải được phân biệt khi thiết kế.

Trong Spring Modulith, kết hợp event thuộc API công khai, transaction đúng nơi sở hữu nghiệp vụ, `@ApplicationModuleListener` sau commit, **Event Publication Registry có lưu trữ bền vững**, idempotency và giám sát publication để giảm phụ thuộc giữa module mà vẫn có đường khôi phục khi lỗi. Mỗi listener giữ trách nhiệm về tác động nghiệp vụ của mình; publish thành công chỉ là **một bước** của chu kỳ giao sự kiện đáng tin cậy.

**Tài liệu tham khảo chính thức:**

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
