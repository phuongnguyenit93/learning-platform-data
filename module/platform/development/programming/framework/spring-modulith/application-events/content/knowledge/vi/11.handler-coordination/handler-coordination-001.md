# Thứ tự xử lý handler trong Spring Modulith

## 1. Thứ tự xử lý handler là vấn đề gì?

Trong ứng dụng sử dụng **Spring Modulith application events**, một sự kiện có thể có nhiều handler (listener) cùng phản ứng. Ví dụ, khi module `orders` xác nhận đơn hàng và phát `OrderConfirmed`, các module `notifications`, `reporting`, `loyalty` có thể cùng đăng ký xử lý. Câu hỏi tự nhiên là: **handler nào chạy trước, handler nào chạy sau và điều gì bảo đảm thứ tự đó?**

Đây là nội dung **Thứ tự xử lý handler** thuộc chương **Điều phối handler** của module học `SPRING_MODULITH_APPLICATION_EVENTS`. Việc thiết kế giao tiếp module bằng events giúp giảm phụ thuộc và bảo vệ boundary, nhưng cũng đòi hỏi hiểu rõ publisher, listener, transaction sau commit, event publication registry, retry, kiểm thử và quan sát.

Không nên coi “các handler được khai báo theo thứ tự trong code” là một hợp đồng thứ tự. Thứ tự có thể chịu tác động của Spring event multicaster, annotation `@Order`, loại listener, transaction phase, executor bất đồng bộ, lỗi, retry và thời điểm khôi phục publication.

### 1.1. Bốn loại thứ tự thường bị đánh đồng

| Loại thứ tự | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Thứ tự phát event** | Publisher gọi `publishEvent(A)` và `publishEvent(B)` theo trình tự nào? | `OrderCreated` trước `OrderConfirmed` |
| **Thứ tự gọi handler** | Với một event, Spring bắt đầu gọi listener nào trước? | `AuditListener` trước `MetricsListener` |
| **Thứ tự kết thúc/commit** | Handler nào thực sự ghi dữ liệu và hoàn thành trước? | Listener B trả về trước listener A vì A chạy async lâu hơn |
| **Thứ tự nghiệp vụ** | Bước nào bắt buộc hoàn tất trước khi bước tiếp theo được phép xảy ra? | Chỉ giao hàng khi đơn đạt điều kiện `READY_FOR_SHIPMENT` |

Các loại thứ tự này **không tương đương**. Ví dụ, Spring có thể lần lượt **giao** event cho hai handler, nhưng hai handler chạy ở thread khác nhau nên cái được giao sau hoàn tất trước.

~~~mermaid
flowchart TD
    P[orders phát OrderConfirmed] --> D[Spring dispatch event]
    D --> A[notifications handler]
    D --> B[reporting handler]
    D --> C[loyalty handler]
    A --> AR[Gửi thông báo]
    B --> BR[Cập nhật projection]
    C --> CR[Ghi điểm thưởng]
    Note[Không có phụ thuộc nghiệp vụ trực tiếp giữa A, B và C]
~~~

Nếu ba phản ứng **độc lập**, việc chúng hoàn tất theo thứ tự nào thường không quan trọng. Nếu bước B **phụ thuộc dữ liệu** do A tạo, vấn đề thực sự không phải “chỉnh số `@Order`” mà là **thiết kế luồng điều phối** và điều kiện thành công giữa các bước.

## 2. Mô hình mặc định của Spring event dispatch

Spring Framework cung cấp `ApplicationEventPublisher` để phát sự kiện và `@EventListener` để tiếp nhận. Với cấu hình mặc định thường dùng, Spring sử dụng event multicaster đồng bộ; lời gọi listener được thực hiện trong đường gọi phát event.

Ví dụ:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Service phát event:

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher publisher,
                    Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();
        order.requireCanConfirm();
        order.confirm();

        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
~~~

Các kiểu `OrderRepository` và aggregate `Order` do ứng dụng tự định nghĩa; ví dụ minh họa cách phát event trong một transaction, không phải project chạy độc lập. Đối với persistence có quản lý entity, việc ghi lưu cần tuân theo cơ chế repository/JPA thực tế.

Trong trường hợp sử dụng multicaster mặc định **đồng bộ**:

1. Publisher gọi `publishEvent(...)`.
2. Spring tìm các listener phù hợp với loại event.
3. Listener được gọi theo cơ chế sắp thứ tự của multicaster.
4. Khi các listener đồng bộ hoàn thành, lời gọi publish kết thúc.
5. Nếu một listener ném exception và không có xử lý lỗi phù hợp, exception có thể truyền ngược về publisher.

Điều này **không còn đúng nguyên vẹn** nếu ứng dụng thay multicaster bằng executor bất đồng bộ hoặc listener sử dụng `@Async`. Đồng thời, `@TransactionalEventListener` có ngữ nghĩa đăng ký callback theo pha transaction, không phải “làm mọi thứ ngay tại publish”.

### 2.1. Không cấu hình thứ tự thì có thể dựa vào đâu?

Không nên phụ thuộc vào:

- Thứ tự lớp Java xuất hiện trong mã nguồn.
- Thứ tự Spring scan package hoặc tạo bean.
- Tên class, tên method hay thứ tự import.
- Việc một listener “thường chạy trước” trong những lần debug thủ công.

Nếu thứ tự **thật sự cần thiết** cho các listener đồng bộ, Spring cung cấp `@Order` hoặc giao diện ordering phù hợp. Nhưng cần hỏi trước liệu thứ tự đó có biểu đạt một **quy tắc nghiệp vụ bắt buộc** hay chỉ phục vụ một cách triển khai cụ thể.

## 3. Sử dụng @Order với handler đồng bộ

Annotation `@Order` cho phép chỉ định **độ ưu tiên tương đối** giữa các listener mà Spring sắp xếp trong cùng quá trình dispatch.

Giá trị nhỏ hơn có **độ ưu tiên cao hơn**; ví dụ `@Order(10)` được ưu tiên trước `@Order(20)` trong cùng ngữ cảnh sắp thứ tự. Đây là thứ tự sắp xếp **lời gọi listener** khi chạy đồng bộ, không phải một hệ thống workflow phụ thuộc nghiệp vụ.

### 3.1. Ví dụ hai handler cùng nhận OrderConfirmed

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {
    private final AuditWriter audit;

    OrderAuditListener(AuditWriter audit) {
        this.audit = audit;
    }

    @Order(10)
    @EventListener
    void on(OrderConfirmed event) {
        audit.appendConfirmation(event.orderId());
    }
}
~~~

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
class OrderMetricsListener {
    private final OrderMetrics metrics;

    OrderMetricsListener(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    @Order(20)
    @EventListener
    void on(OrderConfirmed event) {
        metrics.incrementConfirmedOrders();
    }
}
~~~

Với multicaster đồng bộ mặc định và khi cả hai đều thực sự được gọi cho event, `OrderAuditListener` được sắp trước `OrderMetricsListener`. Tên `AuditWriter` và `OrderMetrics` là dependency minh họa.

**Không nên áp dụng ví dụ này máy móc** cho mọi nghiệp vụ:

- Nếu audit là điều kiện bắt buộc để transaction commit, cân nhắc **gọi trực tiếp** method ghi audit trong use case để thể hiện bất biến rõ ràng.
- Nếu metric chỉ phản ánh **đơn đã commit**, `@EventListener` đồng bộ trước commit có nguy cơ đếm cả những transaction sau đó rollback; cân nhắc instrumentation hoặc listener sau commit.
- Nếu listener đầu tiên ném exception, listener thứ hai có thể **không được gọi** trong luồng mặc định, tùy error handler/multicaster và cấu hình.

### 3.2. @Order sắp thứ tự ở phạm vi nào?

| Tình huống | Có nên dựa vào `@Order` để bảo đảm? |
| --- | --- |
| Hai `@EventListener` đồng bộ trong một multicaster theo cấu hình mặc định | Có thể dùng để kiểm soát thứ tự lời gọi |
| Hai listener có cùng giá trị `@Order` | Không dựa vào thứ tự tương đối giữa chúng |
| Một handler đồng bộ và một handler `@Async` | Không bảo đảm thứ tự **hoàn thành** |
| Hai `@ApplicationModuleListener` async | Không bảo đảm thứ tự **hoàn thành/commit** |
| Hai handler ở transaction phase khác nhau | Phase chi phối thời điểm, `@Order` không đảo được mốc transaction |
| Hai event khác nhau được xử lý qua executor | Không suy ra thứ tự hoàn thành toàn hệ thống từ thứ tự publish |
| Hai hệ thống ngoài ứng dụng nhận message qua broker | Cần cơ chế ordering của transport và consumer, `@Order` trong Spring không áp dụng xuyên mạng |

Trong cùng một pha transaction, `@Order` có thể tham gia sắp thứ tự các transactional listener callback theo cơ chế Spring. Nhưng không nên dựa vào nó để cam kết thành công của bước trước trong trường hợp có async, retry hoặc tác dụng phụ bên ngoài.

### 3.3. Không dùng số thứ tự để che một phụ thuộc cứng

Ví dụ: một handler tạo hóa đơn, handler khác gửi email hóa đơn. Nếu chỉ viết:

~~~java
@EventListener
@Order(10)
void createInvoice(OrderConfirmed event) { /* ... */ }

@EventListener
@Order(20)
void emailInvoice(OrderConfirmed event) { /* ... */ }
~~~

thì khi đổi sang listener bất đồng bộ hoặc khi bước tạo hóa đơn lỗi, handler gửi email không có **hợp đồng dữ liệu** bảo đảm hóa đơn đã tồn tại. `@Order` chỉ giải quyết lịch gọi trong một cấu hình cụ thể, không định nghĩa kết quả nghiệp vụ.

Một lựa chọn rõ hơn là:

~~~text
OrderConfirmed
    -> invoice module xử lý tạo Invoice
    -> khi Invoice được lưu hợp lệ: phát InvoiceIssued
    -> email module phản ứng với InvoiceIssued
~~~

Điều này biến “đã tạo hóa đơn” thành một mốc nghiệp vụ được định danh, thay vì giả định một method đã chạy vì số thứ tự nhỏ hơn.

## 4. Transaction phase quyết định mốc xử lý

`@TransactionalEventListener` hỗ trợ đăng ký listener theo các pha transaction. Các pha có ý nghĩa quan trọng hơn việc thay đổi thứ tự đơn giản giữa hai method.

| Phase | Mốc xử lý | Điểm cần hiểu |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction hoàn tất commit | Lỗi có thể ảnh hưởng commit; chỉ phù hợp công việc cần chạy tại thời điểm này |
| `AFTER_COMMIT` | Sau khi commit thành công | Dùng cho tác vụ chỉ nên xảy ra nếu dữ liệu nguồn đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Dùng cho cleanup/quan sát theo kết quả thất bại |
| `AFTER_COMPLETION` | Khi transaction kết thúc dù thành công hay thất bại | Không tự phân biệt một outcome là thành công nếu không kiểm tra |

Giả sử hệ thống có:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validateAuditReady(OrderConfirmed event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void rebuildReadModel(OrderConfirmed event) { /* ... */ }
~~~

Với event được phát trong transaction hợp lệ, callback `BEFORE_COMMIT` thuộc mốc trước khi commit, còn `AFTER_COMMIT` chỉ thuộc nhánh transaction **đã commit**. Dù đặt một `@Order` nhỏ hơn lên listener `AFTER_COMMIT`, nó cũng **không thể được dùng để buộc chạy trước một công việc BEFORE_COMMIT** theo ý nghĩa nghiệp vụ.

### 4.1. Trong cùng phase, @Order có thể hữu ích

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(10)
void updateCache(OrderConfirmed event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Order(20)
void writeMetric(OrderConfirmed event) { /* ... */ }
~~~

Spring có cơ chế ordering khi kích hoạt callback cùng pha transaction. Tuy vậy, nếu các handler thực hiện tác vụ cần **giao dịch ghi mới**, phải thiết kế transaction riêng cho kết quả, và nếu có async thì thứ tự callback **không đồng nghĩa với thứ tự commit**.

### 4.2. Khi không có transaction nguồn

`@TransactionalEventListener` mặc định chỉ xử lý event khi có transaction tương ứng; phát event **không có transaction** thường khiến callback bị bỏ qua, trừ khi cấu hình `fallbackExecution = true`.

Nếu bật fallback, handler có thể được gọi ngoài mô hình commit/rollback mong đợi. Do đó không nên coi annotation này là một cách xếp thứ tự chung cho tất cả event ở mọi nơi, độc lập transaction.

### 4.3. AFTER_COMMIT và transaction ghi dữ liệu mới

Callback `AFTER_COMMIT` có thể chạy khi resource transaction gốc vẫn còn gắn với thread. Nếu handler cần **ghi DB và commit một thay đổi mới**, có thể chuyển sang một bean riêng sử dụng `REQUIRES_NEW`:

~~~java
@Service
class SalesProjectionWriter {
    private final SalesProjectionRepository repository;

    SalesProjectionWriter(SalesProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(OrderConfirmed event) {
        repository.applyIdempotently(event.eventId(), event.orderId());
    }
}
~~~

`SalesProjectionRepository.applyIdempotently(...)` là method ứng dụng tự xây dựng, không phải method Spring Data tự cung cấp. Listener nên gọi method trên **một Spring bean khác** để transaction interceptor hoạt động khi dự án dùng proxy thông thường; gọi nội bộ kiểu `this.apply(...)` có thể bỏ qua proxy.

## 5. @ApplicationModuleListener và bất đồng bộ: dispatch khác completion

Spring Modulith có annotation `@ApplicationModuleListener` giúp tổ chức listener theo transaction, bất đồng bộ và transaction xử lý riêng. Đây là cơ chế hữu ích để module nhận xử lý event hậu commit mà module phát không cần chờ kết quả trong luồng nghiệp vụ chính.

Ví dụ:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ReportingHandler {
    private final SalesProjectionService projections;

    ReportingHandler(SalesProjectionService projections) {
        this.projections = projections;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.recordConfirmedOrder(event.eventId(), event.orderId());
    }
}
~~~

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotificationHandler {
    private final NotificationService notifications;

    NotificationHandler(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.sendConfirmation(event.eventId(), event.orderId());
    }
}
~~~

`SalesProjectionService` và `NotificationService` thuộc module nhận và phải được ứng dụng định nghĩa. Listener cần hạ tầng Spring, async executor, transaction và registry phù hợp.

Giả sử lần lượt dispatch `ReportingHandler` rồi `NotificationHandler`, nhưng executor có nhiều thread:

~~~mermaid
sequenceDiagram
    participant TX as Transaction nguồn
    participant Events as Event infrastructure
    participant R as ReportingHandler
    participant N as NotificationHandler

    TX-->>Events: Commit OrderConfirmed
    Events-->>R: Giao cho executor (tác vụ R)
    Events-->>N: Giao cho executor (tác vụ N)
    N->>N: Gửi thông báo nhanh
    N-->>Events: N hoàn tất
    R->>R: Truy vấn và ghi projection chậm
    R-->>Events: R hoàn tất sau
~~~

**Ý nghĩa:** thứ tự **submit** vào executor không bảo đảm thứ tự bắt đầu, thực thi hay kết thúc. Ngay cả với executor một thread, retry sau lỗi hoặc khi restart ứng dụng vẫn có thể làm thay đổi thứ tự quan sát được ở cấp nghiệp vụ.

### 5.1. Có nên đặt @Order cho hai @ApplicationModuleListener?

Có thể có lý do để khai báo thứ tự dispatch/callback tương đối, nhưng **không được dùng giá trị `@Order` làm điều kiện bảo đảm** “handler A đã commit xong rồi B mới làm”. Nếu B cần kết quả của A, hãy biểu diễn phụ thuộc bằng một **event phản ánh mốc A hoàn tất**, hoặc điều phối bằng một service/workflow có trạng thái.

### 5.2. Không đặt @Async rồi mong transaction context được kế thừa

`@Async` đổi nơi chạy handler. Transaction ở thread nguồn **không tự truyền nguyên vẹn** sang thread xử lý. Muốn xử lý hậu commit, dùng đúng transactional event semantics; muốn cập nhật DB đích, bảo đảm có transaction độc lập và lỗi được quan sát.

### 5.3. Nếu multicaster được cấu hình bất đồng bộ?

Spring cho phép cấu hình event multicaster và executor; việc thay đổi đó ảnh hưởng cách dispatch và các listener có thể dùng async. Transactional listeners có những ràng buộc riêng với transaction synchronization, do đó không được suy diễn rằng mọi loại listener sẽ đồng loạt chạy trên executor tùy biến.

Khi yêu cầu **thứ tự chính xác**, luôn kiểm thử dưới đúng phiên bản Spring và cấu hình multicaster/executor của dự án, không dựa trên lời mô tả tổng quát về thread.

## 6. Handler độc lập và handler phụ thuộc nhau

Đây là bước quan trọng nhất khi điều phối: phải xác định các listener là **fan-out độc lập** hay các bước của **một quy trình có phụ thuộc**.

### 6.1. Fan-out độc lập: không cần thứ tự

~~~mermaid
flowchart TD
    E[OrderConfirmed] --> N[notifications: gửi email]
    E --> R[reporting: cập nhật số liệu]
    E --> L[loyalty: tính điểm]
    N --> NA[Độc lập]
    R --> RA[Độc lập]
    L --> LA[Độc lập]
~~~

Nếu email gửi chậm, báo cáo vẫn có thể hoàn tất. Nếu `loyalty` lỗi, `orders` vẫn có trạng thái đơn đã được xác nhận đúng quy tắc. Các listener chỉ cần **event contract rõ ràng**, retry/idempotency và giám sát riêng.

Trong trường hợp này, thêm `@Order(1)`, `@Order(2)`, `@Order(3)` thường không mang lợi ích nghiệp vụ; thậm chí có thể tạo hiểu nhầm rằng một công việc phụ thuộc vào công việc trước đó.

### 6.2. Phụ thuộc chặt, bắt buộc thành công trước khi trả về

Ví dụ: quy tắc nghiệp vụ yêu cầu kiểm tra và giữ đủ hàng **trước khi** xác nhận đơn. Khi đó, luồng đồng bộ phải biểu diễn quyết định:

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.requireCanConfirm();

    ReservationResult reservation =
        inventoryOperations.reserve(orderId, order.items());
    if (!reservation.success()) {
        throw new InsufficientStockException();
    }

    order.confirm();
    publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(), orderId, clock.instant()
    ));
}
~~~

`InventoryOperations` là API công khai của module `inventory`, còn `ReservationResult`, `InsufficientStockException` và các domain methods là kiểu minh họa của ứng dụng. Việc tham gia transaction chung chỉ khả thi nếu persistence, transaction manager và ranh giới dữ liệu cho phép; với tài nguyên ngoài tiến trình cần mô hình phối hợp khác.

Điểm chính: **không giao yêu cầu giữ hàng bắt buộc qua một listener hậu commit rồi coi đơn đã xác nhận**. Nếu reservation thất bại, exception/result phải được dùng để từ chối hoặc chuyển sang trạng thái chờ theo hợp đồng nghiệp vụ.

### 6.3. Phụ thuộc qua nhiều transaction: orchestration hoặc state machine

Khi một quy trình có thanh toán từ bên thứ ba, callback bất đồng bộ, tạo vận đơn và gửi email, không thể giữ một transaction DB cho toàn bộ các bước. Có thể dùng **process manager**, workflow hoặc state machine:

~~~mermaid
stateDiagram-v2
    [*] --> AwaitingPayment: OrderPlaced
    AwaitingPayment --> Paid: PaymentCaptured
    AwaitingPayment --> Cancelled: PaymentFailed / timeout policy
    Paid --> ReadyForShipment: InventoryAndPackingReady
    ReadyForShipment --> Shipped: ShipmentAccepted
    Cancelled --> [*]
    Shipped --> [*]
~~~

Trong kiến trúc này, event cung cấp **sự thật về mốc hoàn thành**, còn state machine quyết định bước tiếp theo có được phép diễn ra không. Cần định nghĩa rõ module nào **sở hữu trạng thái quy trình**, xử lý timeout/compensation, duplicate, event đến trễ và điều kiện chuyển trạng thái.

Không nên dùng handler A với `@Order(10)` và handler B với `@Order(20)` để giả lập một workflow bền vững chạy qua nhiều transaction.

## 7. Event chaining khi thực sự có thứ tự nghiệp vụ

**Event chaining** là mô hình một bước nghiệp vụ thành công phát ra một event mới, làm điều kiện cho bước sau.

Ví dụ phát hành hóa đơn:

~~~text
OrderConfirmed
    |
    v
Billing module: tạo hóa đơn
    |
    v
InvoiceIssued(invoiceId, orderId)
    |
    v
Notification module: gửi email hóa đơn
~~~

Điểm khác với `@Order`:

- `InvoiceIssued` chỉ được phát khi module `billing` xác lập hóa đơn hợp lệ.
- Listener gửi email không cần biết method tạo hóa đơn được gọi trước nó theo thứ tự bao nhiêu.
- Module `notifications` nhận một contract **nói rằng hóa đơn đã được phát hành**, không nhận tín hiệu mơ hồ “đơn đã xác nhận” rồi đoán hóa đơn có sẵn.
- Mỗi bước có thể có publication, trạng thái khôi phục và idempotency riêng.

### 7.1. Giới hạn của event chaining

Chaining cũng không tự bảo đảm một workflow hoàn chỉnh:

- Nếu bước tạo hóa đơn lỗi, cần biết ai theo dõi và retry.
- Nếu `InvoiceIssued` được phát rồi process chết trước khi publication được ghi bền vững, cần cơ chế giao sự kiện đáng tin cậy.
- Nếu có nhiều event hoặc nhiều consumer, cần nhận diện chuỗi bằng `correlationId`/`orderId` và kiểm soát phiên bản.
- Nếu quy trình cần rollback bù trừ, phải định nghĩa **compensation** và điều kiện dừng.
- Tránh event loop: A phát B, B phát A vô hạn do thiếu kiểm tra state.

Khi quy trình nhiều bước có tính chất quan trọng, việc đặt trạng thái điều phối ở một process manager có thể dễ quan sát hơn mạng lưới event chaining không có chủ sở hữu rõ.

## 8. Thứ tự giữa hai event khác nhau

Giả sử service phát liên tiếp:

~~~java
publisher.publishEvent(new OrderConfirmed(event1, orderId, now));
publisher.publishEvent(new OrderCancelled(event2, orderId, later));
~~~

Việc gọi `publishEvent(...)` theo thứ tự trong cùng thread **không đủ** để cam kết mọi listener xử lý hai event theo cùng thứ tự, đặc biệt khi:

- Listener dùng `@Async` hoặc `@ApplicationModuleListener`.
- Executor có nhiều worker thread.
- Có retry/resubmit của một publication trước đó.
- Bên nhận xử lý message broker theo nhiều partition/consumer.
- Một transaction rollback hoặc mốc nghiệp vụ chưa thực sự xảy ra.

Nếu hai event phản ánh trạng thái cùng aggregate, nên có chiến lược về **thứ tự nghiệp vụ**.

### 8.1. Aggregate version

Event có thể mang:

~~~java
public record OrderStatusChanged(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    String newStatus,
    Instant occurredAt
) {}
~~~

Nếu aggregate sinh `aggregateVersion` tăng nhất quán theo các lần chuyển trạng thái, consumer có thể so sánh với version cuối đã áp dụng. Tuy nhiên:

- `aggregateVersion` phải là giá trị do nguồn **đảm bảo đúng**, không phải timestamp tùy ý.
- Với một số quy trình, nhận version `5` trước version `4` không có nghĩa có thể bỏ qua `4`; cần quyết định **buffer/đợi/truy vấn lại** hay chỉ giữ trạng thái mới nhất.
- Nếu các event thuộc nhiều aggregate, không có một version toàn cục để sắp thứ tự tất cả.
- Cần optimistic locking hoặc so sánh cập nhật atomic để hai consumer đồng thời không ghi đè sai.

### 8.2. Đơn giản hóa: projection từ trạng thái nguồn

Nếu listener chỉ duy trì một read model có thể dựng lại, đôi khi an toàn hơn khi nó truy vấn **trạng thái hiện tại của aggregate qua API đọc phù hợp**, rồi cập nhật projection idempotently. Cách này giảm phụ thuộc vào thứ tự mọi event trung gian, nhưng không phù hợp khi consumer phải tính toán từ **toàn bộ lịch sử biến cố**.

## 9. Failure, retry và publication registry phá vỡ giả định thứ tự

Spring Modulith hỗ trợ **event publication registry** để ghi nhận publication cho transactional listeners khi có backend lưu trữ phù hợp. Một event có nhiều listener có thể dẫn đến nhiều publication độc lập. Listener thành công có thể được ghi hoàn tất; listener lỗi có thể để lại publication chưa hoàn tất cần resubmit.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant Reg as Publication Registry
    participant N as notifications
    participant R as reporting

    O->>Reg: OrderConfirmed / publications
    O-->>N: Event sau commit
    O-->>R: Event sau commit
    N-->>Reg: Được ghi hoàn tất
    R-->>Reg: Lỗi / chưa hoàn tất
    Note over O,R: Các event mới có thể tiếp tục xuất hiện
    O->>Reg: OrderCancelled / publications
    Reg-->>R: Resubmit OrderConfirmed cũ sau khôi phục
~~~

Nếu reporting nhận `OrderCancelled` mới trước khi `OrderConfirmed` cũ được resubmit, nó cần xử lý **event đến không theo thứ tự mong đợi**. Registry theo dõi hoàn tất và phục hồi, **không mặc nhiên biến tất cả handler thành hàng đợi FIFO theo aggregate**.

### 9.1. Đừng suy ra thứ tự từ timestamp publication

Timestamp giúp quan sát thời điểm tạo publication, nhưng không đủ để bảo đảm:

- Công việc A đã commit dữ liệu trước công việc B.
- A sẽ luôn được retry trước B.
- Hai replica chỉ có một worker xử lý cùng loại event.
- Consumer ngoài nhận message theo đúng thứ tự tuyệt đối.

Nếu thứ tự là một bất biến nghiệp vụ, phải có chiến lược về sequence/state machine, cơ chế điều phối hoặc dispatch tuần tự theo khóa với mức bảo đảm đã kiểm chứng.

### 9.2. Đánh dấu completed chỉ nói lên trách nhiệm của listener

Publication completed ở `notifications` không chứng minh `reporting` hoàn tất. Với externalization, completion ở producer có thể chỉ tương ứng việc broker chấp nhận message, **không chứng minh consumer bên ngoài đã xử lý xong**.

Điều phối các bước dựa trên việc “event đã gửi” là lỗi thiết kế nếu bước sau thực sự đòi **kết quả nghiệp vụ** của bước trước. Khi cần kết quả đó, phải có contract riêng thông báo trạng thái thật hoặc query/command có phản hồi rõ.

### 9.3. Retry và idempotency

Một listener có thể đã cập nhật dữ liệu thành công nhưng process chết trước khi registry ghi completed. Khi resubmit, cùng event có thể được xử lý lại.

Đối với listener tăng số điểm thưởng, phải tránh cập nhật hai lần:

~~~sql
CREATE TABLE loyalty_processed_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

~~~text
on OrderConfirmed(event):
    begin transaction
        insert eventId vào bảng processed_events (unique)
        nếu eventId đã tồn tại:
            không cộng điểm lần nữa
        nếu mới:
            cộng điểm theo quy tắc loyalty
    commit
~~~

Việc ghi dấu và cập nhật điểm cần phối hợp atomic trong transaction của module nhận, và unique constraint bảo vệ các lần xử lý đồng thời. Với nhà cung cấp ngoài, có thể cần idempotency key phía đối tác hoặc cơ chế đối soát vì tác dụng phụ ngoài DB không tự rollback.

## 10. Những sai lầm phổ biến khi cố điều phối bằng handler order

### Sai lầm 1 — Dùng @Order để bảo đảm nghiệp vụ xuyên module

~~~java
@Order(10)
@ApplicationModuleListener
void reserveStock(OrderConfirmed e) { /* ... */ }

@Order(20)
@ApplicationModuleListener
void shipOrder(OrderConfirmed e) { /* ... */ }
~~~

Hai listener bất đồng bộ không có bảo đảm **reserveStock đã hoàn thành** khi `shipOrder` bắt đầu. Thứ tự annotation không thay thế điều kiện “chỉ giao sau khi giữ hàng thành công”.

### Sai lầm 2 — Dùng @Order nhỏ hơn như một cách ưu tiên transaction phase

`@Order(0)` trên listener `AFTER_COMMIT` không khiến nó chạy trước listener `BEFORE_COMMIT` của cùng transaction theo ngữ nghĩa phase. Cần phân biệt mốc transaction và thứ tự callback trong từng pha.

### Sai lầm 3 — Bỏ qua exception rồi vẫn coi bước trước đã hoàn tất

~~~java
@ApplicationModuleListener
void createInvoice(OrderConfirmed event) {
    try {
        invoiceService.issue(event.orderId());
    } catch (RuntimeException ex) {
        log.error("Issuing invoice failed", ex);
        // Trả về bình thường: publication có thể bị đánh dấu completed.
    }
}
~~~

Nếu bước thất bại cần retry, việc bắt rồi nuốt exception có thể dẫn tới **false completion**. Hãy ghi nhận lỗi có ngữ cảnh và để cơ chế theo dõi biết kết quả thực, hoặc chuyển lỗi không thể tự phục hồi vào workflow xử lý có trạng thái rõ ràng.

### Sai lầm 4 — Bắt đầu một task khác rồi return ngay

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    CompletableFuture.runAsync(() ->
        invoiceService.issue(event.orderId())
    );
}
~~~

Method listener kết thúc trước task thực sự. Nếu task lỗi, publisher/registry có thể coi listener thành công trong khi hóa đơn chưa tồn tại. Nếu cần tách thêm công việc, hãy **ghi job bền vững** và định nghĩa completion ở mức enqueue, hoặc chờ công việc hoàn tất theo contract mà framework có thể quan sát.

### Sai lầm 5 — Một listener viết dữ liệu nội bộ của module khác

Nếu `notifications` tự cập nhật `orders.internal.OrderRepository` để “báo đã gửi email”, ranh giới sở hữu bị phá vỡ. Notification giữ trạng thái giao của mình; nếu `orders` thật sự cần biết kết quả, `notifications` công bố một event trạng thái có contract phù hợp.

### Sai lầm 6 — Quá nhiều listener có thứ tự phụ thuộc ngầm

Một event có hàng chục handler đánh số `@Order(1)..@Order(50)` thường là dấu hiệu luồng nghiệp vụ bị chia vụn. Cần xem lại nơi đặt logic cốt lõi, tạo các event mang mốc nghiệp vụ rõ, hoặc chuyển sang workflow/orchestrator để dễ kiểm soát hơn.

## 11. Phương án điều phối phù hợp cho từng yêu cầu

| Yêu cầu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Hai tác vụ độc lập sau khi đơn đã commit | Các transactional listeners độc lập | Không cần phụ thuộc vào thứ tự |
| Hai `@EventListener` đồng bộ chỉ cần thứ tự gọi ổn định | `@Order` rõ ràng, test trên cấu hình mặc định | Spring có cơ chế sắp xếp invocation |
| Bước B phải dùng kết quả A trong cùng use case/transaction | Service orchestration hoặc method trực tiếp | Result/error/rollback được biểu diễn tường minh |
| B chỉ chạy khi A đã commit trong transaction khác | A phát event hoàn tất, B lắng nghe event đó | Contract thể hiện điều kiện nghiệp vụ thực sự |
| Quy trình đa bước kéo dài nhiều giờ | State machine/process manager | Có trạng thái, timeout, retry và compensation |
| Consumer cần nhận các thay đổi theo thứ tự aggregate | Version/sequence, routing theo khóa, state machine | Chịu được reorder, retry và concurrency |
| Nhiều listener phải retry độc lập | Registry, idempotency và observability | Theo dõi completion theo từng listener |
| Phát ra broker tới hệ thống ngoài | Externalization, partition key và consumer policy | `@Order` của Spring không điều khiển delivery xuyên mạng |

### 11.1. Chi phí của việc buộc tuần tự hóa

Tuần tự hóa tất cả listener có thể giảm throughput, tăng latency và tạo điểm nghẽn nếu một listener chậm. Vì vậy chỉ bắt buộc ordering khi **nghiệp vụ cần**. Những tác vụ độc lập có thể phát triển và phục hồi riêng, đem lại đúng lợi ích giảm phụ thuộc của application events.

## 12. Kiểm thử thứ tự handler: test điều gì?

Thứ tự cần được kiểm thử theo **mức cam kết** của thiết kế. Không nên viết test mong đợi mọi listener “chạy lần lượt” khi chúng thực chất bất đồng bộ.

### 12.1. Test thứ tự gọi đồng bộ với @Order

Ví dụ Spring Test giới hạn ngữ cảnh vào hai listener và một `CallTrace`. Đây là ví dụ test **cấu hình synchronous**; không bật `@Async` cho các listener.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(HandlerOrderingTest.Config.class)
class HandlerOrderingTest {

    record TestEvent() {}

    static class CallTrace {
        private final List<String> calls = new ArrayList<>();
        void add(String value) { calls.add(value); }
        List<String> snapshot() { return List.copyOf(calls); }
    }

    static class OrderedHandlers {
        private final CallTrace trace;
        OrderedHandlers(CallTrace trace) { this.trace = trace; }

        @EventListener
        @Order(10)
        void first(TestEvent event) { trace.add("first"); }

        @EventListener
        @Order(20)
        void second(TestEvent event) { trace.add("second"); }
    }

    @Configuration
    static class Config {
        @Bean CallTrace trace() { return new CallTrace(); }
        @Bean OrderedHandlers handlers(CallTrace trace) {
            return new OrderedHandlers(trace);
        }
    }

    @Autowired ApplicationEventPublisher publisher;
    @Autowired CallTrace trace;

    @Test
    void followsSynchronousListenerOrder() {
        publisher.publishEvent(new TestEvent());
        assertThat(trace.snapshot()).containsExactly("first", "second");
    }
}
~~~

Test này kiểm tra một tính chất hẹp: hai listener đồng bộ nhận cùng event trong một Spring context có ordering rõ ràng. Nó **không chứng minh** rằng các listener async sẽ commit theo đúng thứ tự, hay broker/consumer sẽ nhận event tương tự.

### 12.2. Test listener sau commit

Với `@TransactionalEventListener` hoặc `@ApplicationModuleListener`:

1. Tạo dữ liệu nghiệp vụ hợp lệ trong một transaction nguồn.
2. Phát event và **commit thật**.
3. Xác minh listener hậu commit xử lý theo contract.
4. Với listener ghi DB, xác minh transaction riêng commit.
5. Với listener async, chờ bằng điều kiện có timeout (ví dụ Awaitility), không dùng sleep cố định.
6. Tạo kịch bản rollback và xác nhận listener hậu commit không thực hiện side effect cho kết quả chưa xảy ra.

**Bẫy kiểm thử:** Test Spring có `@Transactional` thường rollback khi kết thúc nên `AFTER_COMMIT` có thể không chạy. Dùng transaction được kết thúc/commit có kiểm soát trong test thay vì kết luận annotation bị lỗi.

### 12.3. Test phụ thuộc nghiệp vụ, không test thứ tự tình cờ

Nếu yêu cầu là “chỉ gửi email khi hóa đơn đã phát hành”, test phải khẳng định:

- `InvoiceIssued` chỉ xuất hiện khi invoice đã commit hợp lệ.
- Listener gửi email được kích hoạt từ `InvoiceIssued`, không từ `OrderConfirmed` theo phỏng đoán.
- Khi phát hành invoice lỗi, không có email bảo “hóa đơn đã phát hành”.
- Khi publication được retry, không gửi lặp gây tác dụng phụ sai.

Test chỉ đếm rằng `InvoiceHandler` được gọi trước `EmailHandler` là **không đủ**, vì kết quả nghiệp vụ có thể thất bại hoặc được commit ở thời điểm khác.

### 12.4. Test reorder, retry và concurrency

| Tình huống | Điều nên khẳng định |
| --- | --- |
| Listener A chậm, B nhanh | Không có giả định B phải chờ A nếu độc lập |
| Listener A lỗi trong khi B thành công | B không bị xử lý lại vô ích; publication của A có thể khôi phục |
| Event phiên bản cũ đến sau event mới | Projection/state machine không quay về trạng thái sai |
| Cùng event được resubmit hai lần | Idempotency ngăn tác dụng phụ lặp |
| Hai worker cùng xử lý một aggregate | Lock/version/unique constraint bảo vệ dữ liệu |
| Application restart khi publication chưa hoàn tất | Có thể quan sát và khôi phục công việc với chính sách đã định nghĩa |
| Broker có nhiều partition | Chỉ kết luận thứ tự trong phạm vi bảo đảm của transport và routing |

Để kiểm tra phụ thuộc kiến trúc Spring Modulith, dùng `ApplicationModules.of(...).verify()`. Đó là kiểm tra **cấu trúc module**, không thay thế kiểm thử transaction, ordering, retry hoặc side effect.

## 13. Quan sát thứ tự thực tế và dấu hiệu bất thường

Khi một sự cố được mô tả là “handler chạy sai thứ tự”, cần quan sát ít nhất:

- `eventId`, `eventType`, `aggregateId` và nếu có `aggregateVersion`.
- Thời điểm event được phát, transaction nguồn commit.
- Listener nào được gọi và trên thread/executor nào.
- Thời gian bắt đầu, thời gian xử lý, thời điểm kết thúc.
- Kết quả transaction module nhận, exception, retry count.
- Publication nào hoàn tất, publication nào còn tồn đọng.
- Với broker, routing key, partition, offset và consumer group nếu có.

Ví dụ log do ứng dụng chủ động thiết kế:

~~~json
{
  "eventId": "d101fbea-5f7b-4dbb-a71c-878eb189caf0",
  "eventType": "OrderConfirmed",
  "aggregateId": "4ca03563-3144-4e8e-904e-79d3b39e7681",
  "listener": "ReportingHandler",
  "phase": "AFTER_COMMIT",
  "attempt": 2,
  "status": "processing",
  "aggregateVersion": 7
}
~~~

Tên trường và `status` là **schema log minh họa**, không phải log format mặc định của Spring Modulith. Không nên suy thứ tự từ timestamp của log nếu đồng hồ, thread, batching hay transaction khác nhau; dùng sequence/offset/correlation và dữ liệu nghiệp vụ đáng tin cậy khi yêu cầu tính đúng đắn.

## 14. Bài tập thực hành: ba handler cần phối hợp

**Bối cảnh:** Ứng dụng modular monolith có các module `orders`, `billing`, `notifications` và `reporting`. Sau khi `OrderConfirmed`, hệ thống cần:

1. Cập nhật báo cáo bán hàng.
2. Tạo hóa đơn.
3. Gửi email có đính kèm thông tin hóa đơn.

Lập trình viên ban đầu sử dụng ba handler cùng nghe `OrderConfirmed`:

~~~java
@ApplicationModuleListener
@Order(1)
void reporting(OrderConfirmed event) { /* update report */ }

@ApplicationModuleListener
@Order(2)
void billing(OrderConfirmed event) { /* issue invoice */ }

@ApplicationModuleListener
@Order(3)
void email(OrderConfirmed event) { /* attach invoice */ }
~~~

### 14.1. Phân tích

- **Báo cáo:** độc lập với tạo hóa đơn và gửi email, nếu business rules cho phép.
- **Tạo hóa đơn:** có thể xử lý hậu commit, có transaction riêng và cần ghi nhận thành công.
- **Gửi email hóa đơn:** phụ thuộc vào sự thật “hóa đơn đã phát hành”, **không được suy từ thứ tự @Order**.
- Cả ba listener đều có thể gặp lỗi/được retry. Đường gọi async không có bảo đảm tuần tự hóa hoàn thành.

### 14.2. Phương án cấu trúc lại

~~~mermaid
flowchart TD
    E[OrderConfirmed] --> R[reporting: cập nhật projection]
    E --> I[billing: phát hành Invoice]
    I -->|Commit thành công| II[InvoiceIssued]
    II --> M[notifications: gửi email hóa đơn]
    I -->|Thất bại| Err[Publication cần retry / điều tra]
~~~

Phương án này thể hiện **phụ thuộc nghiệp vụ rõ ràng** giữa billing và email, đồng thời để reporting chạy độc lập. Nếu phát hành hóa đơn phải là bước đồng bộ để hoàn tất đơn thì cần xem lại thời điểm `OrderConfirmed` và thiết kế transaction/use case, không giữ nguyên sơ đồ chỉ vì event nghe tiện.

### 14.3. Thiết kế thêm để chạy tin cậy

1. Định nghĩa `OrderConfirmed` và `InvoiceIssued` thành event contract do module sở hữu phát.
2. Đảm bảo `InvoiceIssued` chỉ được tạo khi billing thật sự xác lập invoice hợp lệ.
3. Dùng listener hậu commit và transaction riêng nếu bước không bắt buộc đồng bộ trước commit nguồn.
4. Cấu hình registry bền vững hoặc cơ chế quản lý publication phù hợp với yêu cầu khôi phục.
5. Dùng `eventId` và khóa nghiệp vụ để tránh tạo hai hóa đơn hoặc gửi hai email khi retry.
6. Thử tình huống billing thất bại, email provider lỗi, event gửi lặp và event đến muộn.
7. Theo dõi thời gian từ `OrderConfirmed` tới `InvoiceIssued` và trạng thái publication ở từng module.

### 14.4. Tình huống mở rộng

Hệ thống giao vận bên ngoài muốn chỉ nhận đơn đã có hóa đơn. Nên externalize event phù hợp với ngữ nghĩa đó, ví dụ `InvoiceIssued` hoặc một event `OrderReadyForShipment` sau khi những điều kiện vận chuyển đã thỏa, thay vì dựa vào `@Order` trên các handler của Spring trong ứng dụng nguồn. Broker có mức bảo đảm ordering và retry riêng; consumer vẫn cần state machine/idempotency.

## 15. Checklist trước khi đặt thứ tự handler

- [ ] Đã xác định thứ tự cần là **lời gọi**, **hoàn tất**, **transaction commit** hay **phụ thuộc nghiệp vụ**.
- [ ] Listener độc lập thì không tạo ràng buộc tuần tự không cần thiết.
- [ ] Với `@EventListener` đồng bộ, chỉ dùng `@Order` khi có lý do rõ ràng và kiểm thử phù hợp.
- [ ] Không dùng `@Order` để hứa thứ tự hoàn tất của `@Async` hoặc `@ApplicationModuleListener`.
- [ ] Transaction phase và thời điểm commit được mô tả rõ, không dùng `@Order` thay thế phase.
- [ ] Tác vụ bắt buộc thành công trước khi trả kết quả được tổ chức bằng method/API hoặc quy trình có kết quả rõ.
- [ ] Bước phụ thuộc vào kết quả bước trước có contract/mốc event thể hiện việc đó.
- [ ] Quy trình dài có state machine/process manager, timeout và phương án khôi phục khi cần.
- [ ] Listener hậu commit ghi dữ liệu trong transaction riêng thích hợp.
- [ ] Registry theo dõi publication cho từng listener, không bị hiểu là FIFO workflow engine.
- [ ] Có chiến lược idempotency cho duplicate do retry/resubmit.
- [ ] Event của cùng aggregate có version hoặc cách kiểm soát thứ tự nếu cần.
- [ ] Có test commit/rollback, async completion, failure/retry và event reorder.
- [ ] Log/metric đủ quan sát từng handler và publication, không ghi dữ liệu nhạy cảm.

## 16. Câu hỏi tự kiểm tra

1. `@Order(10)` và `@Order(20)` bảo đảm điều gì trong hai `@EventListener` đồng bộ?
2. Vì sao hai listener `@ApplicationModuleListener` không thể dùng `@Order` để bảo đảm thứ tự commit?
3. Khác biệt giữa transaction phase `BEFORE_COMMIT` và `AFTER_COMMIT` là gì?
4. Nếu service cần kết quả giữ hàng trước khi xác nhận đơn, vì sao event hậu commit không phù hợp?
5. Khi nào nên dùng `InvoiceIssued` thay cho hai handler cùng nghe `OrderConfirmed` và dựa vào `@Order`?
6. Tại sao publication registry không tự bảo đảm thứ tự FIFO giữa mọi event?
7. Một event cũ được resubmit sau khi consumer nhận event mới có thể gây hậu quả gì?
8. Vai trò của `eventId` và `aggregateVersion` khác nhau thế nào?
9. Khi một handler bắt exception rồi return, thứ tự của các handler khác có giúp phục hồi bước thất bại không?
10. Kiểm thử nào chứng minh yêu cầu “email hóa đơn chỉ được gửi sau khi invoice commit” tốt hơn việc kiểm đếm thứ tự gọi method?

**Ghi nhớ:** Thứ tự xử lý handler là vấn đề **ngữ nghĩa và ranh giới trách nhiệm**, không chỉ là giá trị của `@Order`. Spring có thể sắp thứ tự lời gọi đồng bộ; Spring Modulith giúp tổ chức listener hậu commit và theo dõi publication. Nhưng khi một bước **phụ thuộc vào việc bước khác thực sự thành công**, hãy biểu diễn phụ thuộc đó bằng API đồng bộ, event mốc nghiệp vụ hoặc workflow có trạng thái, đồng thời thiết kế retry, idempotency, ordering và kiểm thử tương ứng.
