# Event sau khi rollback trong Spring Modulith

Khi một transaction đặt hàng thất bại, dữ liệu vừa thay đổi trong database có thể được hoàn tác. Tuy nhiên, application event đã được gọi bằng `publishEvent(...)` trước thời điểm thất bại **không tự biến mất khỏi mọi listener**, và một thao tác bên ngoài như gửi email hoặc gọi API không tự được hoàn tác cùng database. Chính vì vậy, cần hiểu rõ **event sau khi rollback**: listener nào được chạy, lúc nào được chạy, nó nhìn thấy dữ liệu gì, và có thể làm gì một cách an toàn.

Trong chương **Giao dịch và event** của `SPRING_MODULITH_APPLICATION_EVENTS`, chúng ta nghiên cứu cơ chế `@TransactionalEventListener(phase = AFTER_ROLLBACK)` của Spring và cách vận dụng vào các module Spring Modulith. Mục tiêu rộng hơn của module học là giao tiếp giữa các module bằng application events để giảm phụ thuộc, giữ ranh giới nghiệp vụ, đồng thời quản lý publisher, listener, xử lý sau commit, Event Publication Registry, retry, kiểm thử và quan sát việc giao sự kiện đáng tin cậy.

> **Ý chính:** `AFTER_ROLLBACK` là **điều kiện kích hoạt callback khi transaction nguồn rollback**, không phải cơ chế tự tạo durable failure event, không phải lời hứa rằng side effect trong transaction đã được khôi phục, và cũng không tự cung cấp retry.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả điểm khác nhau giữa `@EventListener` thường và `@TransactionalEventListener` theo pha transaction.
2. Giải thích điều kiện để listener `AFTER_ROLLBACK` được gọi và những trường hợp nó không được gọi.
3. Thiết kế event đủ nghĩa để phân biệt **ý định/thử thực hiện** với **sự thật nghiệp vụ đã commit**.
4. Dùng `REQUIRES_NEW` ở một service độc lập để ghi audit/metric sau rollback nếu ứng dụng thực sự cần lưu dữ liệu đó.
5. Phân biệt rollback của transaction nguồn với transaction mới hoặc side effect bên ngoài.
6. Nhận diện các tình huống khó: rollback-only, checked exception, lời gọi nội bộ không qua proxy, transaction không tồn tại, `NESTED` và `REQUIRES_NEW`.
7. Viết integration test kiểm tra callback sau rollback mà không bị cấu hình rollback của Spring Test làm sai kết quả.
8. Đánh giá khi nào cần outbox, registry, retry hoặc workflow bền vững thay vì chỉ dựa vào callback sau rollback.

## 2. Bối cảnh: đơn hàng bị từ chối sau khi đã publish event

Giả sử module `ordering` thực hiện luồng:

1. Tạo đơn hàng ở trạng thái tạm.
2. Publish một event biểu thị **một lần thử xử lý đơn**.
3. Kiểm tra thêm điều kiện nghiệp vụ như chống gian lận.
4. Nếu kiểm tra thất bại, ném exception để transaction rollback.

Module `operations` muốn tăng số lượt thử đặt hàng bị rollback, còn module `notification` chỉ được gửi email xác nhận khi đơn hàng **đã commit**. Hai consumer quan tâm đến **hai kết quả transaction khác nhau**.

~~~mermaid
flowchart TD
    A["ordering: mở transaction"] --> B["Lưu đơn tạm"]
    B --> C["publish OrderPlacementAttempted"]
    C --> D{"Kiểm tra nghiệp vụ"}
    D -->|Đạt| E["Commit"]
    D -->|Thất bại| F["Rollback"]
    E --> G["Listener AFTER_COMMIT<br/>Thông báo đặt hàng"]
    F --> H["Listener AFTER_ROLLBACK<br/>Theo dõi lượt thử thất bại"]
~~~

Trong mô hình này, event `OrderPlacementAttempted` **được publish trước khi biết kết quả transaction**. Hai listener quyết định phản ứng theo kết quả commit hoặc rollback. Không nên đặt tên event ấy là `OrderPlacementRolledBack` ngay tại thời điểm publish, vì lúc đó transaction chưa thực sự rollback.

## 3. Bảng pha transaction của listener

`@TransactionalEventListener` của Spring cho phép method listener gắn với một pha của transaction phát event.

| Phase | Khi nào được kích hoạt? | Ứng dụng thường gặp |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction nguồn thực hiện commit theo cơ chế synchronization | Kiểm tra/bổ sung tác vụ trong giai đoạn chuẩn bị commit; không dùng cho side effect không thể hoàn tác |
| `AFTER_COMMIT` | Sau khi transaction nguồn commit thành công | Gửi thông báo, cập nhật hệ thống đọc, phản ứng sau sự thật đã lưu |
| `AFTER_ROLLBACK` | Sau khi transaction nguồn thực sự rollback | Thu thập tín hiệu thất bại, cleanup hoặc audit theo thiết kế |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback | Giải phóng tài nguyên, đo thời gian hoàn tất không phân biệt kết quả |

Mặc định của `@TransactionalEventListener` là `AFTER_COMMIT`. Muốn nhận callback khi rollback phải khai báo **rõ** `phase = TransactionPhase.AFTER_ROLLBACK`:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void afterRollback(OrderPlacementAttempted event) {
    // Chỉ chạy sau rollback của transaction chứa publishEvent(...).
}
~~~

Khác với callback này, một `@EventListener` đồng bộ thông thường có thể chạy **ngay khi publisher gọi `publishEvent(...)`** và do đó có thể chạy trước khi transaction commit hoặc rollback. Không được mặc định mọi listener đều biết kết quả cuối cùng của transaction.

### Không có transaction thì sao?

Theo cấu hình mặc định, `@TransactionalEventListener` **không được gọi** khi publish không nằm trong transaction đang hoạt động. Có thể bật `fallbackExecution = true` để xử lý khi không có transaction, nhưng lựa chọn này **không tạo ra một sự kiện rollback thật**. Nếu nghiệp vụ yêu cầu “chỉ khi rollback”, nên để mặc định `fallbackExecution = false` và kiểm soát transaction boundary rõ ràng.

## 4. Những điều rollback có và không có nghĩa

Rollback của một transaction database có thể hủy các thay đổi dữ liệu tham gia vào transaction đó. Nó **không nhất thiết**:

- Hủy email đã gửi từ `@EventListener` trước commit.
- Hủy HTTP request đã gửi đến một đối tác.
- Hủy transaction `REQUIRES_NEW` đã commit riêng.
- Xóa log, metric hoặc dữ liệu được ghi bởi công cụ không tham gia transaction nguồn.
- Xóa một message đã kịp gửi tới broker bên ngoài.
- Đảm bảo mọi callback `AFTER_ROLLBACK` sẽ chạy nếu tiến trình bị dừng đột ngột.

Sự phân biệt này quan trọng trong Spring Modulith vì module phát và các module nhận thường có trách nhiệm riêng. Nếu module `notification` gửi email ngay khi `OrderPlacementAttempted` được publish, rồi đơn hàng rollback, email **không thể tự thu hồi** chỉ bằng `@Transactional` của `ordering`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as ordering
    participant DB as Database
    participant E as Spring events
    participant L as AFTER_ROLLBACK listener
    C->>O: placeOrder()
    O->>DB: INSERT tạm trong transaction
    O->>E: publish OrderPlacementAttempted
    Note over E,L: Đăng ký callback theo phase
    O->>O: Validation exception
    O->>DB: Rollback
    DB-->>O: Hoàn tác dữ liệu
    E-->>L: Callback AFTER_ROLLBACK
    L->>L: Theo dõi / dọn dẹp nếu phù hợp
    O-->>C: Báo thất bại
~~~

Thứ tự minh họa giả định listener rollback chạy trên luồng transaction như cấu hình thông thường. Nếu handler dùng `@Async`, nội dung handler có thể chạy muộn trên worker thread; không được suy ra callback đã hoàn thành trước khi caller nhận lỗi.

## 5. Event contract cho một lần thử đặt hàng

Để minh họa an toàn, ta dùng một event biểu thị **lần thử**, không khẳng định đơn hàng đã được commit:

~~~java
// com/example/shop/ordering/events/OrderPlacementAttempted.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlacementAttempted(
        UUID attemptId,
        UUID orderId,
        Instant attemptedAt
) {
    public OrderPlacementAttempted {
        Objects.requireNonNull(attemptId, "attemptId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(attemptedAt, "attemptedAt");
    }
}
~~~

Ba trường mang ý nghĩa:

| Trường | Ý nghĩa | Lưu ý cho consumer |
| --- | --- | --- |
| `attemptId` | Định danh lần thử nghiệp vụ | Có thể dùng làm idempotency key cho việc ghi nhận lần thử |
| `orderId` | Định danh đơn được thử tạo | Đơn này **có thể không tồn tại trong DB sau rollback** |
| `attemptedAt` | Thời điểm ghi nhận lần thử | Không phải thời điểm commit/rollback |

Với cấu trúc module mặc định, package con `ordering.events` nên được công bố qua named interface để module khác dùng hợp đồng:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Giả sử module `operations` chỉ cần nhóm event này:

~~~java
// com/example/shop/operations/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.operations;
~~~

`operations` được phép dùng contract từ `ordering::events`, nhưng không cần import `ordering.internal.OrderRepository`. Ranh giới module giúp kiểm soát phụ thuộc mã nguồn; nó không tự chứng minh callback đã được phát hoặc side effect đã lưu thành công.

## 6. Publisher phát event khi transaction còn hoạt động

Một service giả định của module `ordering`:

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCreationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderCreationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID tryPlaceOrder(OrderDraft draft, boolean simulateFailure) {
        UUID orderId = orders.insertDraft(draft);

        events.publishEvent(new OrderPlacementAttempted(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));

        if (simulateFailure) {
            throw new IllegalStateException("Order validation failed");
        }

        orders.markAccepted(orderId);
        return orderId;
    }
}
~~~

**Phạm vi ví dụ:** `OrderDraft`, `OrderRepository`, bean `Clock` và các method repository là thành phần minh họa, phải được ứng dụng triển khai. Tham số `simulateFailure` dùng để làm rõ cơ chế, không phải API production nên cho caller tự quyết định kết quả kiểm tra nghiệp vụ.

Khi `tryPlaceOrder(...)` được gọi qua Spring-managed bean và transaction manager thích hợp:

1. Transaction bắt đầu.
2. Event được publish **khi transaction còn hoạt động**.
3. Listener giao dịch được đăng ký theo transaction synchronization.
4. Nếu ném `IllegalStateException` ra khỏi phương thức transactional, Spring thường đánh dấu rollback và transaction bị rollback theo quy tắc mặc định dành cho unchecked exceptions.
5. Listener `AFTER_ROLLBACK` có thể được kích hoạt; listener `AFTER_COMMIT` không được kích hoạt cho transaction này.

**Giới hạn quan trọng:** nếu code ném exception **trước câu lệnh publish**, không có event được gửi vào Spring event infrastructure để listener trên nhận. Nếu transaction nguồn thật sự commit dù trước đó có một lỗi đã được bắt và nuốt, listener rollback cũng sẽ không chạy.

## 7. Listener chỉ phản ứng khi rollback

Một module vận hành có thể muốn ghi metric về các lần thử đặt hàng bị rollback:

~~~java
package com.example.shop.operations.internal;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderRollbackMetricsListener {

    private final OrderAttemptMetrics metrics;

    OrderRollbackMetricsListener(OrderAttemptMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    void on(OrderPlacementAttempted event) {
        metrics.recordRollback(event.attemptId());
    }
}
~~~

`OrderAttemptMetrics` là abstraction do module `operations` sở hữu, ví dụ có thể cập nhật bộ đếm trong hệ thống metrics. Với metric không giao dịch và chỉ mang mục tiêu quan sát, hãy xác định liệu việc bỏ sót một lần ghi nhận khi crash có chấp nhận được hay không.

### Vì sao metric khác audit pháp lý?

Một bộ đếm best-effort có thể chấp nhận **không hoàn toàn chính xác** nếu tiến trình bị dừng ngay sau rollback. Một bản ghi audit có yêu cầu pháp lý hoặc một event thất bại buộc hệ thống bên ngoài phải biết **không thể** dựa duy nhất vào callback `AFTER_ROLLBACK` trong bộ nhớ mà tuyên bố “không bao giờ mất”.

Để có bằng chứng bền vững, cần quyết định thời điểm ghi, transaction độc lập, cơ chế recovery, cùng khả năng khôi phục khi crash. Nếu cần chứng minh ngay cả lần thử thất bại trước khi bắt đầu transaction, phải ghi nhận ở lớp bên ngoài phù hợp, chứ không chỉ trông chờ event được publish trong transaction.

## 8. Ghi audit sau rollback: phải mở transaction mới

Một bẫy quan trọng: callback `AFTER_ROLLBACK` chạy **sau khi transaction nguồn đã kết thúc**, nhưng tài nguyên giao dịch (ví dụ kết nối/session) có thể vẫn được ràng buộc trong giai đoạn callback hoàn tất. Nếu gọi repository ghi dữ liệu mà không có một transaction mới rõ ràng, không nên mong đợi thay đổi ấy sẽ được commit.

Giải pháp thường gặp là để listener gọi **một bean service độc lập**, phương thức ghi audit mở transaction mới:

~~~java
// com/example/shop/operations/internal/RollbackAuditService.java
package com.example.shop.operations.internal;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class RollbackAuditService {

    private final RollbackAuditRepository repository;

    RollbackAuditService(RollbackAuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(OrderPlacementAttempted event) {
        repository.insertIfAbsent(
                event.attemptId(),
                event.orderId(),
                event.attemptedAt()
        );
    }
}
~~~

~~~java
// com/example/shop/operations/internal/OrderRollbackAuditListener.java
package com.example.shop.operations.internal;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderRollbackAuditListener {

    private final RollbackAuditService audit;

    OrderRollbackAuditListener(RollbackAuditService audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    void on(OrderPlacementAttempted event) {
        audit.record(event);
    }
}
~~~

Những điểm cần hiểu:

- `RollbackAuditService.record(...)` dùng `REQUIRES_NEW` để tạo transaction độc lập với transaction đặt hàng đã rollback.
- Lời gọi từ listener đến **bean khác** đi qua Spring proxy, tránh lỗi self-invocation thường gặp với `@Transactional` trên phương thức được gọi nội bộ qua `this`.
- `insertIfAbsent(...)` chỉ là method ví dụ. Muốn tránh ghi trùng cần unique constraint theo `attemptId` và xử lý xung đột trong transaction thích hợp.
- Không nên để audit ghi thành công được hiểu là transaction đặt hàng cũng đã commit; hai giao dịch có kết quả độc lập.

**Đừng suy diễn mức bảo đảm:** ngay cả với `REQUIRES_NEW`, nếu process bị kill trước hoặc trong callback, record audit vẫn có thể chưa được ghi. Muốn bảo đảm chặt hơn, cần một thiết kế bền vững cho cả **lần thử** và **kết quả thất bại**, chẳng hạn ghi nhận yêu cầu ở transaction độc lập trước khi bắt đầu bước có thể rollback rồi cập nhật trạng thái qua workflow.

## 9. `AFTER_ROLLBACK`, `AFTER_COMMIT` và `AFTER_COMPLETION` cùng nhận một event

Một event `OrderPlacementAttempted` có thể được nhiều listener quan tâm:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void onAccepted(OrderPlacementAttempted event) {
    // Chỉ khi transaction chứa lần thử đã commit.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
void onRolledBack(OrderPlacementAttempted event) {
    // Chỉ khi transaction chứa lần thử rollback.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void onCompleted(OrderPlacementAttempted event) {
    // Khi transaction đã hoàn tất, bất kể commit hay rollback.
}
~~~

Các method trên là minh họa về pha, không phải ba listener phải dùng trong mọi ứng dụng. `AFTER_COMPLETION` không tự truyền vào method một biến cho biết commit hay rollback; nếu cần phân biệt kết quả, ưu tiên listener theo phase hoặc cơ chế quan sát transaction riêng được thiết kế rõ.

| Kết quả transaction | AFTER_COMMIT | AFTER_ROLLBACK | AFTER_COMPLETION |
| --- | --- | --- | --- |
| Commit thành công | Có | Không | Có |
| Rollback thực sự | Không | Có | Có |
| Không có transaction, fallback mặc định | Không | Không | Không |
| Publish trước lúc lỗi nhưng exception không làm rollback và vẫn commit | Có | Không | Có |

Điều kiện thực tế phụ thuộc transaction manager, cách transaction được tạo và event có được publish **trong transaction đang hoạt động** hay không.

## 10. `@ApplicationModuleListener` không phải listener rollback

Spring Modulith có `@ApplicationModuleListener` để tổ chức giao tiếp giữa các application modules. Annotation này hỗ trợ mô hình listener **sau commit**, chạy bất đồng bộ và dùng transaction mới theo cấu hình thực thi phù hợp.

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {

    private final OrderConfirmationService confirmations;

    OrderConfirmationListener(OrderConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlacementAttempted event) {
        confirmations.prepareConfirmation(event.orderId());
    }
}
~~~

Trong ví dụ này, `notification` chỉ nên xác nhận đơn khi **transaction nguồn commit**. Vì vậy:

- Khi transaction đơn hàng **commit**, listener `@ApplicationModuleListener` có thể được kích hoạt và xử lý theo hạ tầng async/transaction của ứng dụng.
- Khi transaction đơn hàng **rollback**, listener kiểu sau commit **không phải listener báo rollback** và không nên được dùng để ghi nhận thất bại.
- Nếu cần xử lý riêng khi rollback, dùng `@TransactionalEventListener(phase = AFTER_ROLLBACK)` hoặc một workflow thất bại bền vững được thiết kế rõ.

Khi dùng event contract `OrderPlacementAttempted` cho nhiều pha, nên ghi rõ ngữ nghĩa của từng handler. Trong thiết kế domain có yêu cầu mạnh, có thể chọn công bố `OrderPlaced` chỉ sau khi dữ liệu được xác nhận thành công thay vì dùng cùng event “attempt” cho mọi mục đích.

### Event Publication Registry có xử lý event rollback tự động không?

**Không nên giả định như vậy.** Event Publication Registry của Spring Modulith tập trung theo dõi publication tới các listener/hạ tầng được hỗ trợ theo cơ chế và persistence đã cấu hình. Nếu việc ghi publication tham gia transaction nguồn và transaction đó rollback, bản ghi publication liên quan cũng có thể bị hoàn tác.

Do đó, việc thêm registry **không tự biến mọi callback AFTER_ROLLBACK thành một thông điệp thất bại bền vững**. Cần kiểm chứng đường đi thực tế theo phiên bản Spring Modulith, cách listener được đăng ký, transaction manager và storage. Với sự kiện thất bại bắt buộc được lưu/giao, hãy thiết kế transaction độc lập hoặc workflow có trạng thái bền vững thay vì chỉ dựa vào event được phát bên trong transaction sắp rollback.

## 11. Khi nào không nên công bố “OrderFailed” ngay trong transaction sắp rollback?

Giả sử code:

~~~java
@Transactional
public void placeOrder(PlaceOrderRequest request) {
    events.publishEvent(new OrderFailed(request.requestId()));
    throw new IllegalStateException("Cannot place order");
}
~~~

Cách viết này có vấn đề ngữ nghĩa và vận hành:

1. Tại thời điểm publish, kết quả rollback chưa hoàn tất, nên tên `OrderFailed` có thể mô tả một sự thật **chưa được xác nhận**.
2. `@EventListener` đồng bộ có thể nhận `OrderFailed` ngay lập tức, trước rollback.
3. `@TransactionalEventListener(AFTER_COMMIT)` sẽ không phản ứng nếu transaction rollback.
4. Nếu bản ghi publication được ghi trong cùng transaction, nó có thể bị rollback cùng dữ liệu.
5. Một side effect bên ngoài được thực hiện trước rollback không tự được hoàn tác.

Nếu nghiệp vụ cần phát sự kiện **một đơn đã thất bại và thất bại ấy phải được lưu bền**, một hướng thường rõ hơn là có **service điều phối ở ngoài transaction đặt hàng**:

~~~text
OrderRequestCoordinator (không nằm trong transaction đặt hàng)
    |
    +-- gọi OrderCreationTx.placeOrder(...) qua Spring bean
    |       |
    |       +-- COMMIT -> trả orderId
    |       +-- ROLLBACK -> ném lỗi về coordinator
    |
    +-- Coordinator nhận kết quả thất bại
            |
            +-- gọi FailureRecordingService.record(...) bằng transaction MỚI
                    |
                    +-- persist failure + outbox message (nếu cần)
~~~

Ở đây `OrderCreationTx` là bean transaction riêng; coordinator chỉ bắt exception **sau khi transaction bên trong đã được Spring hoàn tất**. `FailureRecordingService` ghi trạng thái thất bại bằng transaction khác, có thể kết hợp outbox nếu cần externalization.

Vẫn có **cửa sổ lỗi**: process có thể chết sau rollback nhưng trước khi coordinator ghi failure. Nếu cần bảo đảm mọi yêu cầu đã tiếp nhận đều được theo dõi, phải lưu **bản ghi yêu cầu/lần thử bền vững trước bước có thể thất bại**, sau đó dùng state machine/recovery để xác định kết quả cuối. Một callback trong bộ nhớ không thể thay thế cơ chế này.

## 12. Những trường hợp rollback dễ bị hiểu nhầm

### 12.1. Checked exception có thể không kích hoạt rollback mặc định

Với cấu hình `@Transactional` phổ biến, Spring mặc định rollback khi ném `RuntimeException` hoặc `Error`, nhưng không nhất thiết rollback cho mọi checked exception.

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() throws BusinessCheckedException {
    // Khi checked exception này thoát ra, transaction được chỉ định rollback.
    throw new BusinessCheckedException("Invalid request");
}
~~~

`BusinessCheckedException` là class minh họa cần được định nghĩa trong dự án thực. Nếu không cấu hình `rollbackFor` hoặc chính sách rollback tương đương, transaction có thể commit mặc dù caller nhận một checked exception. Khi đó `AFTER_ROLLBACK` **không phải** callback được chọn.

Điểm cần kiểm tra luôn là **kết quả thực tế của transaction**, không chỉ việc method có ném exception hay không.

### 12.2. Bắt rồi nuốt exception có thể khiến transaction commit

~~~java
@Transactional
public void process() {
    try {
        callBusinessRule();
    } catch (IllegalStateException exception) {
        // Chỉ log rồi tiếp tục mà không đánh dấu rollback.
    }
}
~~~

Nếu transaction chưa bị đánh dấu rollback-only từ tầng khác, method hoàn tất bình thường có thể commit. Muốn rollback phải thiết kế cách báo lỗi/đánh dấu rollback rõ, tránh dùng exception như tín hiệu mà transaction manager không nhìn thấy.

### 12.3. Transaction được đánh dấu rollback-only

Một thành phần tham gia transaction có thể gọi `setRollbackOnly()` hoặc làm transaction bị đánh dấu rollback-only. Dù phương thức bên ngoài có vẻ hoàn thành bình thường, commit cuối cùng có thể dẫn tới rollback và một exception như `UnexpectedRollbackException`.

Khi có event đã đăng ký, `AFTER_ROLLBACK` theo kết quả **rollback thực tế** có thể được gọi; không nên dự đoán pha chỉ từ giá trị trả về của một method bên trong.

### 12.4. Lời gọi nội bộ không qua Spring proxy

~~~java
@Service
class OrderFacadeImpl {

    public void handle() {
        createTransactional(); // Self-invocation trong cùng object.
    }

    @Transactional
    public void createTransactional() {
        // Có thể KHÔNG mở transaction qua proxy theo cách gọi trên.
    }
}
~~~

Khi ứng dụng dùng Spring AOP proxy mode thông thường, `this.createTransactional()` không đi qua proxy của Spring và advice `@Transactional` trên method được gọi có thể không được áp dụng. Nếu publisher phát event trong khi **không có transaction**, listener `AFTER_ROLLBACK` mặc định không chạy.

Hãy bố trí ranh giới transaction ở bean public service được gọi qua Spring-managed proxy hoặc dùng một transaction boundary tường minh phù hợp.

### 12.5. `REQUIRES_NEW` của service con

Nếu một service con chạy transaction `REQUIRES_NEW` và **commit thành công**, sau đó transaction bên ngoài rollback:

- Thay đổi của transaction con vẫn có thể đã commit.
- Event đăng ký trong transaction con gắn với kết quả của **transaction con**, không tự động gắn với kết quả transaction bên ngoài.
- Listener `AFTER_ROLLBACK` được đăng ký vào transaction con **không được gọi** chỉ vì transaction bên ngoài rollback sau đó.

Do đó, cần xác định **transaction nào chứa lời gọi `publishEvent(...)`** thay vì chỉ nói “toàn bộ request thất bại”.

### 12.6. `NESTED` và rollback tới savepoint

`Propagation.NESTED` có thể dùng savepoint trong một transaction vật lý nếu transaction manager/hạ tầng hỗ trợ. Rollback tới savepoint **không nhất thiết tương đương rollback toàn bộ transaction ngoài**. `@TransactionalEventListener(AFTER_ROLLBACK)` thường gắn với việc hoàn tất transaction được Spring quản lý, nên không được mặc định callback này sẽ được gọi ngay mỗi lần quay về savepoint.

Nếu ứng dụng dựa vào nested transaction, cần kiểm thử cụ thể với transaction manager và cấu trúc propagation thực tế.

## 13. `@Async` và rollback: hai vấn đề độc lập

Nếu listener được gắn đồng thời:

~~~java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderPlacementAttempted event) {
    rollbackReportingService.report(event);
}
~~~

Ý tưởng là **sau khi transaction rollback**, Spring lên lịch công việc để xử lý bằng executor. Tuy nhiên:

- Bất đồng bộ giúp luồng nguồn không phải chờ hết tác vụ; nó **không làm callback bền vững** khi process crash.
- Transaction nguồn **không tự được chuyển sang** worker thread. Nếu consumer ghi DB, cần transaction riêng.
- Queue đầy có thể làm việc lên lịch bị từ chối; exception từ worker thread không lan ngược như lời gọi đồng bộ.
- Nếu event cần được báo cáo chắc chắn, phải có storage/recovery, không dùng `@Async` như giải pháp thay thế.

Ngược lại, `@Async @EventListener` **không có phase AFTER_ROLLBACK** nên có thể bắt đầu ngay lúc publish, trước khi biết transaction rollback hay commit. Không thay `@TransactionalEventListener(AFTER_ROLLBACK)` bằng tổ hợp ấy khi cần chỉ phản ứng với rollback.

## 14. Kiểm thử: phải có rollback thật của transaction nguồn

Một unit test gọi trực tiếp:

~~~java
listener.on(event);
~~~

chỉ chứng minh logic của method, **không chứng minh Spring kích hoạt nó ở pha rollback**. Muốn xác minh lifecycle cần integration test dùng transaction manager thật và Spring event dispatch.

### 14.1. Thiết kế probe để quan sát callback

Ví dụ sau dùng một probe test-only ghi lại những `orderId` đã được listener rollback nhận. Bài test chủ động dùng `TransactionTemplate` để tạo transaction rồi commit hoặc rollback. Ứng dụng test cần có một `PlatformTransactionManager` phù hợp và hạ tầng Spring Boot đã được cấu hình.

~~~java
package com.example.shop.ordering.internal;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlacementAttempted;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@Import(RollbackEventIntegrationTest.RollbackProbe.class)
class RollbackEventIntegrationTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired TransactionTemplate transactions;
    @Autowired RollbackProbe probe;

    @BeforeEach
    void clearProbe() {
        probe.orderIds.clear();
    }

    @Test
    void notifiesRollbackListenerForFailedTransaction() {
        UUID orderId = UUID.randomUUID();
        OrderPlacementAttempted event = new OrderPlacementAttempted(
                UUID.randomUUID(), orderId, Instant.now()
        );

        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(event);
            status.setRollbackOnly();
        });

        assertThat(probe.orderIds).contains(orderId);
    }

    @Test
    void doesNotNotifyRollbackListenerAfterCommit() {
        OrderPlacementAttempted event = new OrderPlacementAttempted(
                UUID.randomUUID(), UUID.randomUUID(), Instant.now()
        );

        transactions.executeWithoutResult(status ->
                publisher.publishEvent(event)
        );

        assertThat(probe.orderIds).isEmpty();
    }

    @TestConfiguration
    static class RollbackProbe {

        final List<UUID> orderIds = new CopyOnWriteArrayList<>();

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        void onRollback(OrderPlacementAttempted event) {
            orderIds.add(event.orderId());
        }
    }
}
~~~

Đây là integration test dành cho ứng dụng có Spring transaction manager; test không cần dữ liệu đơn hàng vì chỉ chứng minh **sự kiện được phát trong transaction và callback chạy ở pha phù hợp**. Để chứng minh toàn bộ nghiệp vụ tạo đơn cũng rollback đúng, cần thêm test riêng gọi `OrderCreationService`, kiểm tra trạng thái database và event được publish trên nhánh thất bại.

Điểm quan trọng là method test **không tự bọc `@Transactional`**, vì Spring Test thường rollback transaction của test vào cuối. Nếu test đã mở transaction ngoài, kết quả rollback/commit do service tự thực hiện có thể không còn đúng như bạn tưởng; hãy kiểm soát rõ ranh giới transaction trong test.

### 14.2. Test với `TransactionTemplate`

Một cách khác là tạo transaction và ép rollback tường minh:

~~~java
@Autowired TransactionTemplate transactionTemplate;
@Autowired ApplicationEventPublisher publisher;

@Test
void onlyRunsAfterRollback() {
    OrderPlacementAttempted event = createAttemptEvent();

    transactionTemplate.executeWithoutResult(status -> {
        publisher.publishEvent(event);
        status.setRollbackOnly();
    });

    // Assertion trên một probe/listener AFTER_ROLLBACK đồng bộ.
    assertThat(rollbackProbe.received(event.attemptId())).isTrue();
}
~~~

`createAttemptEvent()` và `rollbackProbe` là test fixture giả định cần triển khai. Với callback `AFTER_ROLLBACK` **đồng bộ**, kết thúc `executeWithoutResult(...)` giúp tạo điểm quan sát rõ ràng. Nếu listener dùng `@Async`, phải chờ điều kiện kết quả có timeout thay vì assert ngay; không dùng `Thread.sleep(...)` cố định để giả lập commit/rollback.

### 14.3. Ma trận test tối thiểu

| Tình huống | Kỳ vọng đối với AFTER_ROLLBACK | Điều cần kiểm chứng thêm |
| --- | --- | --- |
| Commit thành công | Không gọi | AFTER_COMMIT nếu có chạy đúng |
| Rollback sau khi publish | Gọi | Không có bản ghi đơn bị rollback còn tồn tại |
| Lỗi phát sinh trước khi publish | Không có callback cho event chưa publish | Cơ chế theo dõi yêu cầu lỗi riêng nếu cần |
| Publish ngoài transaction | Không gọi theo mặc định | Cách ứng dụng xử lý ngoài transaction |
| Checked exception không cấu hình rollback và transaction vẫn commit | Không gọi | Quy tắc `rollbackFor` |
| Transaction bị đánh dấu rollback-only | Có thể gọi khi rollback thực tế | Có/không `UnexpectedRollbackException` |
| Listener ghi audit bằng REQUIRES_NEW | Audit có thể commit độc lập | Transaction/bảng/unique constraint |
| Process crash trước callback | Có thể bỏ lỡ | Cơ chế durability/recovery độc lập |
| Nhiều lần xử lý lại cùng attempt ID | Không tạo audit/side effect trùng | Idempotency và ràng buộc dữ liệu |

## 15. Kiểm tra ranh giới module khi xử lý rollback

Một listener thuộc module vận hành hoặc giám sát có thể nhận event từ `ordering`, nhưng không nên đọc thẳng repository/entity của `ordering` để tìm “đơn đã bị rollback”: sau rollback, bản ghi đó có thể không tồn tại và việc import implementation còn phá ranh giới module.

Giữ API công khai:

~~~text
com.example.shop
├── ordering/
│   ├── events/
│   │   ├── package-info.java
│   │   └── OrderPlacementAttempted.java
│   └── internal/
│       ├── OrderCreationService.java
│       └── OrderRepository.java
└── operations/
    ├── package-info.java
    └── internal/
        ├── OrderRollbackAuditListener.java
        ├── RollbackAuditService.java
        └── RollbackAuditRepository.java
~~~

Kết hợp bài test kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test xác minh phụ thuộc và named interface theo quy tắc Spring Modulith hiện hành. **Nó không chứng minh callback rollback đã chạy**, do đó cần kết hợp test transaction ở mục trước.

### Vì sao không nên coi event payload là dữ liệu đã commit?

`OrderPlacementAttempted` có thể chứa `orderId` vừa được cấp trong transaction sắp rollback. Consumer chỉ được hiểu rằng **một lần thử với ID đó đã xảy ra trong luồng xử lý**, không được suy rằng DB hiện có một `OrderEntity` tương ứng.

Nếu một consumer cần lookup trạng thái sau rollback, hãy sử dụng một dữ liệu/trạng thái **đã được ghi độc lập, có ý nghĩa riêng** hoặc hợp đồng thất bại có thông tin cần thiết; không bắt consumer dựa vào entity đã rollback.

## 16. Reliability: thất bại nghiệp vụ không đồng nghĩa publication đã được lưu

Trong Spring Modulith, application event có thể được publish hoàn toàn trong cùng JVM. Độ tin cậy giao sự kiện cần được xem xét trên ít nhất ba lớp:

| Lớp | Câu hỏi | Kiểm soát tương ứng |
| --- | --- | --- |
| **Transaction nguồn** | Event được publish trước/ngoài/sau commit? Transaction nào rollback? | `@Transactional`, phase listener, transaction manager |
| **Publication và callback** | Có bản ghi công việc chưa hoàn tất để khôi phục khi crash không? | Registry/persistence/outbox theo cơ chế cấu hình |
| **Side effect của consumer** | Gửi lại có tạo dữ liệu/email trùng không? | Idempotency, transaction riêng, API đích hỗ trợ khóa |

Khi transaction nguồn rollback, một publication **ghi trong chính transaction đó** thường không phải dấu vết bền vững để tái xử lý. Nếu nghiệp vụ thật sự cần lưu và gửi **sự kiện thất bại**, phải có nơi ghi nhận độc lập với transaction thất bại.

### Những lựa chọn theo yêu cầu thực tế

| Nhu cầu | Thiết kế cân nhắc |
| --- | --- |
| Chỉ cần tăng metric best-effort khi rollback | `AFTER_ROLLBACK` listener |
| Ghi audit có thể chấp nhận mất trong trường hợp process crash đúng cửa sổ lỗi | `AFTER_ROLLBACK` gọi service `REQUIRES_NEW`, có test/idempotency |
| Không được mất dấu yêu cầu thất bại | Persist request/attempt **trước** bước có thể rollback trong transaction độc lập, workflow cập nhật kết quả |
| Gửi failure event tới hệ thống ngoài | Record failure/outbox trong transaction độc lập, externalization/recovery và consumer idempotent |
| Điều phối các bước bắt buộc khi có lỗi | Workflow/saga có state và bù trừ, không dựa đơn thuần vào callback rollback |

**Không coi retry là giải pháp khôi phục một event chưa từng được lưu.** Retry chỉ có thể làm lại công việc mà hệ thống còn có bằng chứng hoặc trạng thái để tìm lại.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Gọi `publishEvent(OrderFailed)` rồi mặc định đơn đã rollback | Event có thể được nhận trước rollback, hoặc transaction vẫn commit | Dùng event biểu thị attempt; phân biệt phase và kết quả thật |
| Dùng `@EventListener` để gửi email trong transaction | Gửi email cho đơn rollback | Listener `AFTER_COMMIT` cho side effect chỉ khi thành công |
| Nghĩ `@ApplicationModuleListener` tự báo rollback | Listener sau commit không phải listener rollback | Dùng `AFTER_ROLLBACK` hoặc workflow failure riêng |
| Ghi audit trong callback rollback mà không mở transaction mới | Ghi DB có thể không commit đúng kỳ vọng | Bean `REQUIRES_NEW` với transaction rõ ràng |
| Coi exception bất kỳ là rollback | Checked exception có thể không rollback | Xác định chính sách `rollbackFor` và kết quả thật |
| Bắt exception rồi tiếp tục không rollback | Transaction commit, listener rollback không chạy | Quản lý lỗi và đánh dấu rollback đúng cách |
| Mong savepoint rollback kích hoạt mọi listener AFTER_ROLLBACK | NESTED không nhất thiết là full rollback | Test theo transaction manager/propagation |
| Dùng `@Async` rồi nghĩ callback đã bền vững | Crash có thể làm mất task | Lưu trạng thái yêu cầu/outbox/registry khi thực sự cần |
| Dùng registry để “lưu mọi event đã bị rollback” | Publication trong tx nguồn có thể bị rollback | Thiết kế nguồn failure event độc lập |
| Test chỉ gọi trực tiếp listener method | Không test lifecycle transaction | Integration test với transaction thật |
| Đặt `@Transactional` lên test rồi chờ AFTER_COMMIT | Test rollback mặc định nên AFTER_COMMIT không chạy | Tạo commit thật và xác minh phase |
| Tra `OrderRepository` sau rollback để lấy bản ghi tạm | Bản ghi có thể không còn tồn tại; vi phạm module | Dùng event contract hoặc trạng thái thất bại đã lưu riêng |

## 18. Bài thực hành: quan sát và ghi nhận rollback

**Bối cảnh:** Ứng dụng có module `ordering` và `operations`. Một số lần tạo đơn không vượt qua kiểm tra cuối và transaction phải rollback. `operations` muốn thống kê số lần thất bại; `notification` chỉ gửi xác nhận cho đơn thực sự được commit.

### Phần A — Cấu trúc và event contract

1. Tạo module `ordering` và `operations` theo package Spring Modulith.
2. Công bố `OrderPlacementAttempted(UUID attemptId, UUID orderId, Instant attemptedAt)` ở `ordering.events` qua `@NamedInterface("events")`.
3. Giới hạn `operations` phụ thuộc vào `ordering::events`; không import repository của module đặt hàng.
4. Viết `ApplicationModules.of(ShopApplication.class).verify()` để phát hiện phụ thuộc nội bộ/vòng.

### Phần B — Hai listener khác phase

1. Tạo publisher phát `OrderPlacementAttempted` trong transaction tạo đơn.
2. Tạo listener `AFTER_ROLLBACK` ghi một metric trong `operations`.
3. Tạo listener `AFTER_COMMIT` minh họa một phản ứng khi đơn thành công.
4. Chạy trường hợp commit, trường hợp rollback và so sánh listener nào được gọi.
5. Thử tạo lỗi **trước khi publish** và giải thích vì sao callback rollback cho event đó không được gọi.

### Phần C — Ghi audit vào transaction mới

1. Tạo `RollbackAuditService` với `@Transactional(propagation = REQUIRES_NEW)`.
2. Cho listener rollback gọi service và ghi `attemptId` vào bảng có unique constraint.
3. Xác minh bản ghi đơn hàng đã rollback không tồn tại nhưng bản ghi audit độc lập có thể tồn tại.
4. Xử lý lại cùng `attemptId` để xác nhận không tạo audit trùng.
5. Mô tả failure window giữa rollback và lúc audit được commit. Nêu yêu cầu cần thêm nếu audit tuyệt đối không được mất.

### Phần D — Câu hỏi vận hành

- Nếu hệ thống dừng ngay sau rollback, metric/audit có chắc được ghi không?
- Nếu publisher không mở transaction vì self-invocation, listener rollback có chạy không?
- Nếu transaction con `REQUIRES_NEW` commit còn transaction ngoài rollback, event trong transaction con gắn với pha nào?
- Nếu gửi failure event ra broker, bạn sẽ ghi durable outbox ở đâu để không bị rollback cùng đơn hàng?

### Checklist nghiệm thu

| Tiêu chí | Bằng chứng mong đợi |
| --- | --- |
| API sự kiện không lộ internal package | Spring Modulith verification PASS |
| Rollback thật sau publish | AFTER_ROLLBACK được gọi; AFTER_COMMIT không gọi |
| Commit thành công | AFTER_COMMIT được gọi; AFTER_ROLLBACK không gọi |
| Listener ghi audit riêng | Bản ghi audit commit bằng transaction mới |
| Không có dữ liệu đơn tạm sau rollback | Assertion database sau transaction |
| Xử lý lặp an toàn | Unique constraint/kiểm tra theo attempt ID |
| Hiểu giới hạn độ bền | Phân biệt callback in-memory và workflow/outbox bền vững |

## 19. Câu hỏi tự kiểm tra

**Câu 1. `@TransactionalEventListener(AFTER_ROLLBACK)` có nghĩa event chỉ được tạo sau rollback không?**

Không. Event thường được publish **khi transaction còn hoạt động** và listener được gắn với pha rollback. Handler chỉ được kích hoạt sau khi transaction nguồn rollback thành công theo cơ chế synchronization.

**Câu 2. Nếu `publishEvent(...)` được gọi ngoài transaction thì listener rollback có chạy không?**

Theo mặc định không, vì không có transaction để đăng ký pha rollback. Không nên bật fallback chỉ để mô phỏng một kết quả rollback không tồn tại.

**Câu 3. Nếu dùng `@ApplicationModuleListener` để nhận `OrderPlacementAttempted`, transaction rollback có làm nó chạy không?**

Không. `@ApplicationModuleListener` được thiết kế cho phản ứng sau commit, không phải listener thông báo rollback.

**Câu 4. Vì sao ghi database trong listener sau rollback cần `REQUIRES_NEW`?**

Vì transaction nguồn đã hoàn tất và tài nguyên có thể còn ràng buộc trong callback; cần một transaction mới thực sự được commit để lưu audit độc lập.

**Câu 5. Ném một checked exception có luôn khiến listener rollback chạy không?**

Không. Điều đó phụ thuộc quy tắc rollback của Spring và cấu hình ứng dụng. Chỉ khi transaction **thực sự rollback** thì callback `AFTER_ROLLBACK` mới phù hợp.

**Câu 6. Registry có tự bảo đảm một failure event được publish trong transaction rollback sẽ tồn tại sau crash không?**

Không. Publication ghi trong transaction bị rollback có thể cũng bị hủy. Nếu phải ghi nhận thất bại bền vững, cần transaction độc lập hoặc workflow có trạng thái được lưu theo thiết kế.

**Câu 7. Listener AFTER_ROLLBACK có thể “undo” email đã gửi trước commit không?**

Không. Email là side effect bên ngoài database transaction. Cách phòng tránh là không gửi xác nhận trước khi nguồn commit; nếu đã gửi, có thể cần quy trình đính chính hoặc bù trừ.

## 20. Tổng kết

**Event sau khi rollback** trong Spring chủ yếu là **callback được kích hoạt khi transaction chứa lời gọi publish event hoàn tất bằng rollback**, thông qua `@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)`. Nó hữu ích để đo lường, cleanup hoặc ghi nhận thất bại theo chính sách, nhưng không tự tạo một durable failure event và không đảo ngược side effect bên ngoài.

Khi áp dụng trong Spring Modulith, hãy giữ hợp đồng ở API được công bố, đặt listener trong module sở hữu phản ứng, xác định **transaction nào chứa event**, dùng `REQUIRES_NEW` nếu callback cần ghi dữ liệu độc lập, và kiểm thử bằng rollback thật. Với yêu cầu không được mất sự kiện thất bại, cần một thiết kế lưu trạng thái hoặc outbox/workflow bền vững hơn, kèm recovery, idempotency và observability. Chỉ khi hiểu rõ khác biệt giữa **rollback callback**, **commit event** và **giao sự kiện đáng tin cậy**, các module mới có thể trao đổi bằng events mà không phá vỡ ranh giới hoặc đưa ra kết luận sai về tính nhất quán.
