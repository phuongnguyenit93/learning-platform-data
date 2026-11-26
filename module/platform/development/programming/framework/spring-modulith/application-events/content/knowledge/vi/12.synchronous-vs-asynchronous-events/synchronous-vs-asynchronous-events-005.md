# Thread context khi xử lý event đồng bộ và bất đồng bộ trong Spring Modulith

## 1. Thread context là gì và vì sao quan trọng?

Trong Spring, **thread context** là tập thông tin gắn với luồng thực thi hiện tại, thường được truy cập qua `ThreadLocal` hoặc các cơ chế tương tự: transaction đang hoạt động, thông tin người dùng đăng nhập, trace/correlation ID, MDC dùng cho log, locale, request attributes hoặc tenant hiện hành.

Khi xử lý application event **đồng bộ** trên cùng thread, listener thường nhìn thấy một số context của publisher. Khi xử lý event **bất đồng bộ** trên thread khác, những giá trị đó **không tự động đi theo**. Nếu giả định sai, listener có thể gặp lỗi thiếu transaction, mất trace, thiếu principal, truy vấn sai tenant hoặc đọc một JPA entity đã detached.

Ví dụ, một request HTTP xác nhận đơn hàng:

~~~text
HTTP thread: http-nio-8080-exec-7
  SecurityContext: user-42
  MDC: traceId=abc123
  Transaction: xác nhận đơn hàng
      |
      +-- publishEvent(OrderConfirmed)
             |
             +-- @EventListener (đồng bộ, mặc định):
             |      chạy ngay trên HTTP thread
             |
             +-- @ApplicationModuleListener (bất đồng bộ):
                    worker thread khác
                    không tự có transaction/request/MDC/security của HTTP thread
~~~

Trong phạm vi module học `SPRING_MODULITH_APPLICATION_EVENTS`, mục tiêu là giao tiếp giữa các module Spring Modulith bằng application events, giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ. Hiểu thread context là điều kiện quan trọng để thực hành publisher, listener sau commit, event publication registry, retry, kiểm thử và quan sát luồng event đáng tin cậy.

> **Quy tắc cốt lõi:** Context của thread là **môi trường thực thi tạm thời**, không phải một phần của sự thật nghiệp vụ được bảo đảm tồn tại khi event bị trì hoãn, retry hoặc xử lý sau khi ứng dụng khởi động lại.

### 1.1. Phân biệt ba loại thông tin

| Loại | Ví dụ | Chiến lược khi xử lý bất đồng bộ |
| --- | --- | --- |
| **Dữ liệu nghiệp vụ của event** | `eventId`, `orderId`, `occurredAt`, `actorId` | Lưu trong event hoặc hợp đồng công khai, nếu được phép và cần thiết |
| **Context quan sát thực thi** | Trace/correlation ID, MDC log keys | Propagate bằng cơ chế hỗ trợ hoặc thiết lập lại trong listener rồi dọn sạch |
| **Context tài nguyên/thread-bound** | Transaction, JPA persistence context, HTTP request | Không sao chép như object; thiết lập tài nguyên/transaction mới tại nơi xử lý |

Không phải mọi thông tin cần được truyền. **Nguyên tắc tối thiểu hóa:** chỉ đưa vào event/context những giá trị consumer thật sự cần; tránh chép token, session, địa chỉ IP hoặc toàn bộ request khi không có nhu cầu rõ ràng.

## 2. Những context thường gặp trong Spring

| Context | Cơ chế phổ biến | Có tự theo sang thread mới không? | Lưu ý |
| --- | --- | --- | --- |
| **Transaction** | `TransactionSynchronizationManager` và transaction manager | Không | Transaction imperative thông thường gắn với thread; listener khác thread cần transaction riêng |
| **Security** | `SecurityContextHolder` | Không theo mặc định | Có thể dùng wrappers/`TaskExecutor` tích hợp security khi thực sự cần |
| **Logging MDC** | SLF4J `MDC` | Không bảo đảm | Cần capture/restore hoặc context-propagation; luôn cleanup khi dùng thread pool |
| **HTTP request attributes** | `RequestContextHolder` | Không đáng tin cậy | Request có thể đã kết thúc trước khi listener async chạy |
| **Locale** | `LocaleContextHolder` | Không được giả định | Nếu cần ngôn ngữ người dùng để gửi email, đưa locale phù hợp vào event |
| **Tracing** | Micrometer Tracing / OpenTelemetry context | Phụ thuộc tích hợp/configuration | Truyền trace context theo cơ chế được hỗ trợ; không tự dựng trace ID thay thế span |
| **Tenant context tùy biến** | `ThreadLocal<TenantId>` của ứng dụng | Không | Chọn tenant từ event đã xác thực rồi mở context mới có cleanup |
| **Persistence context** | JPA `EntityManager` trong transaction | Không | Truyền ID/immutable snapshot, không dựa vào lazy-loaded entity |

Một số API hỗ trợ `InheritableThreadLocal`, nhưng **không nên xem đó là giải pháp mặc định cho async executor**. Thread trong pool được tái sử dụng; thread con không phải lúc nào cũng được tạo mới vào thời điểm submit task. Kế thừa hoặc giữ context không đúng cách có thể gây lộ thông tin giữa các request.

### 2.1. Bốn thời điểm khác nhau

Khi đọc một event listener, phải hỏi rõ:

1. **Khi phát event:** publisher đang chạy trên thread nào, có transaction không?
2. **Khi đăng ký callback:** listener được Spring gọi ngay hay chờ một pha transaction?
3. **Khi thực thi công việc:** chạy cùng thread hay thông qua executor?
4. **Khi hoàn tất hoặc retry:** những context nào còn tồn tại, những context nào cần dựng lại?

Sự kiện được phát trong một HTTP request **không có nghĩa** listener sẽ chạy khi HTTP request còn tồn tại.

## 3. Listener đồng bộ: vì sao context thường còn nguyên?

`ApplicationEventPublisher` của Spring Framework phối hợp với `ApplicationEventMulticaster` để tìm các listener. Trong cấu hình thường dùng, multicaster mặc định gọi `@EventListener` **đồng bộ**; listener có thể chạy cùng thread với nơi gọi `publishEvent(...)`.

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
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher events,
                    Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();
        order.requireCanConfirm();
        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
~~~

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    private final OrderAuditWriter audits;

    OrderAuditListener(OrderAuditWriter audits) {
        this.audits = audits;
    }

    @EventListener
    void on(OrderConfirmed event) {
        audits.append(event.orderId(), event.occurredAt());
    }
}
~~~

`OrderRepository`, aggregate `Order` và `OrderAuditWriter` do dự án tự triển khai; các đoạn mã chỉ minh họa luồng. Nếu listener đồng bộ thực sự chạy trên thread transaction của publisher, thao tác database dùng transaction manager phù hợp có thể tham gia transaction đó.

### 3.1. Lợi ích và rủi ro khi cùng thread

**Lợi ích:** listener có thể nhìn thấy MDC, security context và transaction đang có; dễ debug luồng gọi tuần tự; exception có thể truyền ngược về publisher.

**Rủi ro:** listener làm tăng độ trễ API, có thể gây rollback toàn transaction nếu lỗi không được xử lý; tác vụ ngoài database (gửi email, gọi HTTP) không thể được rollback theo thay đổi DB; listener vô tình phụ thuộc request/session context sẽ khó chuyển sang xử lý bất đồng bộ.

**Quan trọng:** sự có mặt của transaction trong cùng thread là **đặc tính thực thi tại thời điểm đó**, không phải contract của event. Nếu sau này chuyển sang `@Async` hoặc thay multicaster, những giả định đó có thể không còn đúng.

### 3.2. Context đang thấy không nhất thiết nên được dùng

Ví dụ, listener đồng bộ có thể đọc `SecurityContextHolder.getContext().getAuthentication()`. Nhưng event `OrderConfirmed` là một sự thật nghiệp vụ, có thể được phát từ HTTP request, scheduled job, consumer khác hoặc chương trình backfill. Nếu logic bắt buộc có HTTP principal, cùng một sự kiện sẽ hành xử khác nhau tùy đường gọi.

Nếu ai xác nhận đơn là dữ liệu nghiệp vụ cần audit, hãy truyền **định danh actor đã được kiểm tra** theo một contract phù hợp thay vì dùng trạng thái thread ngầm ở listener.

## 4. @Async tạo một ranh giới thread mới

`@Async` cho phép Spring thực hiện method được hỗ trợ trên một executor khác, thường là thread trong pool. Khi áp dụng cho listener, việc dispatch sang executor có thể diễn ra nhanh còn **công việc thực** diễn ra sau.

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class NotificationListener {

    private final NotificationService notifications;

    NotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @Async("domainEventExecutor")
    @EventListener
    void on(OrderConfirmed event) {
        notifications.sendOrderConfirmed(event.orderId());
    }
}
~~~

Ứng dụng cần bật và cấu hình async execution (chẳng hạn `@EnableAsync` và bean executor có tên tương ứng); `NotificationService` do module `notifications` định nghĩa. Đoạn code **chưa** thể hiện yêu cầu chạy sau commit: `@Async` chỉ chỉ định cách thực thi, không tự biến listener thành transactional after-commit listener.

### 4.1. Một luồng thực thi minh họa

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant Req as HTTP request thread
    participant Exec as Async executor
    participant Worker as Worker thread

    Client->>Req: POST /orders/{id}/confirm
    Req->>Req: Begin transaction
    Req->>Req: publishEvent(OrderConfirmed)
    Req->>Exec: Submit listener task
    Exec-->>Worker: Chạy listener
    par Các luồng có thể chạy song song
        Worker->>Worker: Gọi notification provider
    and Transaction nguồn còn đang diễn ra
        Req->>Req: Commit hoặc rollback
    end
    Req-->>Client: Response theo contract nghiệp vụ
~~~

**Nguy cơ:** worker có thể bắt đầu chạy **trước khi transaction nguồn commit**. Nếu nguồn rollback, email có thể đã gửi nhầm. Vì vậy, với thông báo chỉ hợp lệ sau commit, thường cần kết hợp **transactional event semantics** và async.

### 4.2. Những giả định không an toàn

Không được mặc định rằng trong listener `@Async`:

- `TransactionSynchronizationManager.isActualTransactionActive()` trả về true vì publisher có `@Transactional`.
- `SecurityContextHolder.getContext().getAuthentication()` vẫn là người dùng gửi HTTP request.
- `MDC.get("traceId")` vẫn bằng giá trị bên publisher.
- `RequestContextHolder.currentRequestAttributes()` còn truy cập được.
- JPA entity truyền từ publisher vẫn ở trong cùng persistence context.

Một số ứng dụng có custom context propagation khiến **một vài** giá trị tồn tại; điều đó vẫn không bảo đảm transaction nguồn đi theo và không nên xem là đặc tả nghiệp vụ.

### 4.3. Exception trong async listener

Exception ở thread khác không tự được ném ngược vào lời gọi `publishEvent(...)` trong HTTP thread. Với async method trả về `void`, cơ chế xử lý lỗi thường gắn với `AsyncUncaughtExceptionHandler` hoặc quản lý của framework; với `Future`/`CompletionStage`, kết quả lỗi có thể nằm trong đối tượng kết quả.

Muốn tác vụ quan trọng không bị thất lạc, cần **cơ chế theo dõi publication và phục hồi** thích hợp, không chỉ ghi log lỗi trong executor. Không nên cho rằng đổi `@EventListener` sang `@Async` mặc nhiên tạo một hàng đợi bền vững.

## 5. @TransactionalEventListener: pha transaction khác với thread

`@TransactionalEventListener` của Spring xử lý application event theo **pha transaction**:

| Pha | Khi nào chạy | Điều cần nhớ |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit nguồn | Có thể tác động quyết định commit; không phải tác vụ “đã chắc chắn commit” |
| `AFTER_COMMIT` (mặc định) | Sau commit thành công | Phù hợp để tránh tác dụng phụ của transaction bị rollback |
| `AFTER_ROLLBACK` | Sau rollback nguồn | Dùng cho cleanup/quan sát thất bại đúng ngữ nghĩa |
| `AFTER_COMPLETION` | Khi transaction kết thúc | Bao gồm cả commit lẫn rollback |

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AfterCommitNotificationListener {

    private final NotificationService notifications;

    AfterCommitNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        notifications.sendOrderConfirmed(event.orderId());
    }
}
~~~

**After commit không đồng nghĩa async.** Nếu không kết hợp cơ chế bất đồng bộ, callback transaction có thể được gọi trên thread của transaction nguồn trong quá trình hoàn tất giao dịch. Trong trường hợp đó, một số ThreadLocal còn khả dụng tại thời điểm callback; tuy nhiên tài nguyên giao dịch nguồn đã ở pha hoàn tất, và không thể dựa vào đó để thực hiện một **commit mới**.

### 5.1. AFTER_COMMIT vẫn cần transaction mới nếu ghi database

Spring lưu ý rằng tài nguyên transaction cũ có thể vẫn còn liên kết với thread lúc callback `AFTER_COMMIT` chạy. Lời gọi repository từ callback **không tự bảo đảm** có transaction commit mới.

Đưa việc ghi dữ liệu sang một bean riêng:

~~~java
package com.example.shop.reporting.internal;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class ReportingProjectionWriter {
    private final SalesProjectionRepository projections;

    ReportingProjectionWriter(SalesProjectionRepository projections) {
        this.projections = projections;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(UUID orderId, UUID eventId) {
        projections.applyIdempotently(eventId, orderId);
    }
}
~~~

`applyIdempotently(...)` là method do ứng dụng tự thiết kế, không phải method mặc định của Spring Data. Listener gọi **bean khác** để `@Transactional` đi qua Spring proxy theo cấu hình thông thường; gọi một method cùng bean bằng `this.method()` có thể bỏ qua transaction interceptor.

### 5.2. Fallback khi không có transaction

Theo mặc định, `@TransactionalEventListener` không xử lý event nếu phát bên ngoài một transaction tương ứng, trừ khi đặt `fallbackExecution = true`. Tùy chọn fallback cho phép callback chạy dù không có transaction, nhưng ngữ nghĩa “sau commit” lúc đó **không tồn tại**.

Do đó, test và các luồng gọi thực tế phải xác nhận publisher có transaction như kỳ vọng. Đừng bật fallback chỉ để “listener luôn chạy” mà không xét đến sự thật nghiệp vụ.

## 6. @ApplicationModuleListener của Spring Modulith

Spring Modulith cung cấp `@ApplicationModuleListener`, một annotation tiện dụng để xây dựng listener giữa các application module. Về ý định sử dụng, nó kết hợp **xử lý theo transaction sau commit**, **bất đồng bộ** và **transaction xử lý riêng** cho listener.

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderReportingListener {

    private final ReportingProjectionWriter writer;

    OrderReportingListener(ReportingProjectionWriter writer) {
        this.writer = writer;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        writer.apply(event.orderId(), event.eventId());
    }
}
~~~

Trong ví dụ, `orders.events.OrderConfirmed` phải là **contract được module `orders` công bố** (package API hoặc named interface) để `reporting` được phép tham chiếu. Code ứng dụng cần cấu hình transaction manager, async executor và registry/backend tương ứng theo phiên bản đang dùng.

### 6.1. Sơ đồ context với Spring Modulith

~~~mermaid
sequenceDiagram
    participant API as HTTP request
    participant Orders as orders / source transaction
    participant Registry as Publication registry
    participant Worker as Async worker
    participant Reporting as reporting / new transaction

    API->>Orders: confirm(orderId)
    Orders->>Orders: Đổi trạng thái hợp lệ
    Orders->>Orders: publishEvent(OrderConfirmed)
    Orders->>Registry: Ghi publication (khi cấu hình)
    Orders->>Orders: Commit
    Orders-->>Worker: Xử lý sau commit
    Note over Worker: Thread khác, không mang transaction nguồn
    Worker->>Reporting: Mở transaction xử lý riêng
    Reporting->>Reporting: Ghi projection theo event
    Reporting-->>Worker: Hoàn tất / lỗi
    Worker->>Registry: Hoàn tất publication nếu xử lý thành công
~~~

Đây là luồng **logic**, không phải mô tả cứng mọi bước bên trong framework. Thời điểm đánh dấu completed, lệnh retry và cách lưu registry phụ thuộc backend/phiên bản.

### 6.2. Vì sao context ở request không đáng tin cậy?

Giả sử `OrderReportingListener` gọi `CurrentUser.getId()` từ `SecurityContextHolder`:

- Khi xử lý trên một worker thread, giá trị có thể trống.
- Khi registry resubmit publication sau khi restart, **HTTP request ban đầu không còn**.
- Nếu executor tái sử dụng thread mà context không được dọn, giá trị có thể **thuộc một request khác**.

Sự kiện phải chứa dữ liệu cần thiết hoặc listener phải lấy dữ liệu qua một API có quyền sở hữu rõ ràng. **Không có lý do để “phục hồi nguyên request” chỉ vì event cần actor ID.**

### 6.3. Context propagation không giải quyết độ tin cậy

Dù chuyển được MDC, trace hay security context, listener vẫn có thể lỗi sau khi transaction nguồn commit. Muốn thực sự khôi phục công việc cần:

- Event publication registry bền vững khi tính năng đó được sử dụng.
- Chiến lược retry/resubmit theo cấu hình.
- Event payload có thể deserialize sau restart/nâng cấp.
- Idempotency để thực thi lại không gây tác dụng phụ trùng.
- Observability cho từng listener/publication.

Context propagation giúp **quan sát và tính đúng ngữ cảnh**, không biến xử lý trong bộ nhớ thành một hàng đợi bền vững.

## 7. Transaction context không được sao chép qua thread

Đây là ngộ nhận nguy hiểm nhất. Với transaction imperative thông thường, Spring gắn trạng thái giao dịch với thread thông qua cơ chế như `TransactionSynchronizationManager`. Thread khác không thể an toàn “nhận nguyên transaction” bằng cách copy một map `ThreadLocal`.

~~~mermaid
flowchart TD
    A[HTTP thread: transaction orders] --> B[Đổi trạng thái đơn]
    B --> C[Commit transaction nguồn]
    C --> D[Async worker]
    D --> E[Transaction reporting mới]
    E --> F[Commit projection độc lập]
~~~

### 7.1. Vì sao không thể chuyển transaction bằng TaskDecorator?

Transaction chứa nhiều tài nguyên gắn với vòng đời và thread, ví dụ connection, persistence context, trạng thái synchronization và quy tắc commit/rollback. Nếu gắn chúng sang thread khác bằng cơ chế tùy biến, ứng dụng có thể gặp sử dụng connection đồng thời, session không thread-safe hoặc trạng thái commit không nhất quán.

**TaskDecorator dùng cho MDC/quan sát, không phải cơ chế hợp lệ để truyền transaction nguồn.** Listener cần tạo hoặc tham gia transaction của chính nó theo thiết kế.

### 7.2. Không chuyển JPA entity đang managed

**Không nên:**

~~~java
// Ví dụ phản diện: event mang entity mutable.
public record OrderConfirmed(OrderJpaEntity order) {}
~~~

Listener chạy async có thể gặp:

- `LazyInitializationException` do persistence context của publisher đã đóng.
- Trạng thái entity bị thay đổi sau thời điểm phát event.
- Hành vi không an toàn khi nhiều thread truy cập cùng một object mutable.
- Việc consumer phụ thuộc vào model JPA nội bộ của module `orders`.

**Nên dùng:**

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Nếu cần dữ liệu cố định tại thời điểm xảy ra event, cân nhắc **snapshot bất biến đã chọn lọc** trong payload thay vì truy vấn lại state hiện tại. Nếu cần đọc dữ liệu mới nhất, listener có thể truy vấn qua API/module boundary và transaction riêng; hai phương án có semantics khác nhau.

### 7.3. Giao dịch reactive là trường hợp khác

Trong ứng dụng Reactive, context của transaction thường gắn với **Reactor Context**, không phải ThreadLocal theo mô hình imperative. Spring Framework các phiên bản hiện đại hỗ trợ xử lý transactional events trong trường hợp reactive qua cơ chế tương ứng, với yêu cầu gắn transaction context vào nguồn event khi cần.

Không nên áp dụng trực tiếp giải pháp “copy ThreadLocal sang executor” vào pipeline Reactor. Khi làm việc với reactive event publication, cần dùng API và context propagation dành cho reactive của phiên bản Spring hiện hành, kiểm thử theo đúng scheduler và transaction manager.

## 8. MDC và correlation ID: quan sát qua ranh giới thread

MDC (Mapped Diagnostic Context) thường lưu `traceId`, `correlationId`, `orderId` hoặc các khóa log khác để những dòng log cùng một yêu cầu có thể tìm được. SLF4J MDC thường dựa trên context gắn với thread; chuyển sang worker thread có thể khiến các khóa đó biến mất.

Ví dụ log không có propagation:

~~~text
10:00:00 http-nio-8080-exec-7 traceId=abc123 Confirming order 123
10:00:00 task-3                traceId=       Processing OrderConfirmed
~~~

### 8.1. Hướng an toàn nhất khi event có thể retry

Đưa **mã tương quan ổn định, không nhạy cảm** vào event khi có nhu cầu:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    String correlationId
) {}
~~~

Listener tự bổ sung MDC cho khoảng xử lý:

~~~java
import org.slf4j.MDC;

@ApplicationModuleListener
void on(OrderConfirmed event) {
    try (MDC.MDCCloseable eventLog = MDC.putCloseable(
            "eventId", event.eventId().toString());
         MDC.MDCCloseable correlationLog = MDC.putCloseable(
            "correlationId", event.correlationId())) {

        writer.apply(event.orderId(), event.eventId());
    }
}
~~~

Ví dụ giả định `event.correlationId()` không null và hợp lệ; nếu không có correlation ID, hãy xử lý trường hợp thiếu trước khi gọi `MDC.putCloseable(...)`. Cơ chế `try-with-resources` giúp phục hồi/xóa **hai khóa** của MDC khi thoát; nếu nhiều thư viện dùng chung MDC, cần kiểm tra semantics restore theo implementation.

**Lưu ý:** correlation ID trong event là metadata phục vụ liên kết log, **không thay thế trace/span context chuẩn**. Nếu event được ghi bền vững và replay sau nhiều giờ, việc tái dùng context của request cũ như một span đang hoạt động có thể không phù hợp với mô hình tracing; cần cân nhắc tạo span mới có liên kết đúng.

### 8.2. TaskDecorator để truyền MDC cho các task trực tiếp

Nếu tác vụ chỉ chạy qua executor nội bộ và cần giữ MDC ở thời điểm **submit task**, Spring cho phép dùng `TaskDecorator`:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcCopyingTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submitted = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (submitted == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submitted);
                }
                task.run();
            } finally {
                // Khôi phục context của worker trước khi task bắt đầu.
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Ví dụ cấu hình executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class DomainEventAsyncConfig {

    @Bean("domainEventExecutor")
    ThreadPoolTaskExecutor domainEventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("domain-event-");
        executor.setTaskDecorator(new MdcCopyingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Listener sử dụng `@Async("domainEventExecutor")` mới chắc chắn yêu cầu executor được đặt tên đó. Với `@ApplicationModuleListener`, cấu hình async executor được chọn theo quy tắc của Spring và cách annotation cấu hình trong phiên bản dùng; **không nên giả định mọi listener sẽ tự động sử dụng bean trên nếu chưa cấu hình và kiểm thử**.

### 8.3. Hạn chế của TaskDecorator

- Nó chỉ truyền context **tại thời điểm task được submit**.
- Không bảo tồn context qua **restart hoặc resubmission từ registry**.
- Không biến context thành một phần có thể deserialize của event.
- Không bảo đảm truyền SecurityContext, transaction, request hay Reactor context.
- Có thể xung đột với cơ chế tracing propagation do framework đã cấu hình; cần chọn chiến lược phối hợp, tránh ghi đè decorator hiện hành.
- Mỗi task phải được **dọn context** để không ảnh hưởng task tiếp theo của thread pool.

Với event quan trọng có thể phát lại, các định danh nghiệp vụ/correlation thiết yếu nên nằm trong contract event thay vì chỉ trông chờ MDC của request nguồn.

## 9. SecurityContext: danh tính người dùng không tự đi theo event

Spring Security thường dùng `SecurityContextHolder` để truy cập người dùng đang xác thực. Với mode mặc định, context gắn với thread thực thi yêu cầu.

Giả sử người dùng `user-42` xác nhận đơn. Listener `loyalty` bất đồng bộ muốn ghi audit “ai kích hoạt nghiệp vụ”:

**Thiết kế mong manh:**

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    var authentication =
        SecurityContextHolder.getContext().getAuthentication();
    String username = authentication.getName(); // Có thể null / sai context.
    audits.record(event.orderId(), username);
}
~~~

### 9.1. Nếu actor là dữ liệu nghiệp vụ: truyền định danh rõ ràng

Tại ranh giới HTTP/application service, xác thực và kiểm tra quyền **trước khi** tạo event. Sau đó đưa định danh cần thiết, được phép chia sẻ, vào event:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    String actorId,
    Instant occurredAt
) {}
~~~

Listener:

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    audits.recordConfirmedBy(
        event.orderId(),
        event.actorId(),
        event.occurredAt()
    );
}
~~~

`actorId` phải được lấy từ nguồn đã được xác thực hoặc một service principal hợp lệ; **không tin trực tiếp** giá trị tùy ý mà client tự gửi. Nếu actor không phải thông tin cần audit, đừng thêm nó vào event chỉ để truy cập security context. Cần cân nhắc quyền riêng tư và retention của payload.

### 9.2. Khi thật sự cần propagate SecurityContext

Spring Security có các wrapper hỗ trợ chạy task dưới một security context cụ thể, ví dụ `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextAsyncTaskExecutor`. Chúng hữu ích cho tác vụ **ngắn hạn trong cùng tiến trình** khi nghiệp vụ cần thực thi theo security identity phù hợp.

Tuy nhiên:

- Không nên tự copy `SecurityContextHolder` bằng cách lưu một reference mutable vào thread pool.
- Không được làm mất bước authorization ở ranh giới module/service nhận.
- Không lưu nguyên access token, session hoặc credentials vào event registry để phục hồi.
- Một background handler hoặc event replay thường phù hợp hơn với **service identity + dữ liệu actor phục vụ audit**.
- Việc ủy quyền theo người dùng hiện tại có thể hết hiệu lực khi request đã kết thúc; cần mô hình phân quyền minh bạch cho job nền.

**Không phải mọi listener phải chạy dưới quyền của HTTP caller.** Việc module `reporting` xử lý một event đã commit có thể là công việc hệ thống, không phải request trực tiếp của người dùng.

## 10. Request, locale và tenant context

### 10.1. RequestContextHolder chỉ có ý nghĩa trong vòng đời request

Ở HTTP controller hoặc service sync, có thể truy cập request attributes thông qua `RequestContextHolder`. Nhưng listener chạy sau commit/bất đồng bộ có thể hoàn tất **sau khi request đã đóng**. Gọi `currentRequestAttributes()` có thể ném exception vì không có request context trên worker thread.

Không nên đưa `HttpServletRequest` vào event hoặc cố giữ toàn bộ request object trong thread pool; request/session có vòng đời và chi phí không phù hợp cho xử lý dài hạn.

Nếu listener cần một thông tin cụ thể như nguồn yêu cầu, kênh bán hàng hoặc ngôn ngữ hiển thị, **trích xuất và xác thực trước**, rồi đưa dữ liệu tối thiểu vào event hoặc một hợp đồng chứa metadata rõ ràng.

### 10.2. Locale trong tác vụ hậu commit

Một email xác nhận đơn phải dùng ngôn ngữ người dùng đã chọn. Nếu listener chỉ đọc `LocaleContextHolder.getLocale()`, nó có thể nhận locale mặc định của worker thay vì locale của khách hàng.

Thiết kế tốt hơn:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    String notificationLocale,
    Instant occurredAt
) {}
~~~

Ví dụ `notificationLocale` có thể là thẻ BCP 47 như `vi-VN` hoặc `en-US`. Module `notifications` phải validate/fallback theo các locale được hỗ trợ. Nếu ngôn ngữ thông báo có thể thay đổi sau khi đặt hàng, cần chọn rõ dùng **snapshot lúc xác nhận** hay **sở thích mới nhất khi gửi**; đây là quyết định nghiệp vụ.

### 10.3. Tenant context: ngăn lỗi truy cập chéo tenant

Trong ứng dụng multi-tenant, một custom `TenantContext` thường dùng `ThreadLocal` để chọn schema/datasource/filter. Nếu listener async không có tenant context, nó có thể truy vấn sai tenant hoặc rơi vào default tenant.

Quy trình an toàn:

1. Xác định `tenantId` ở ranh giới đã được xác thực và kiểm tra quyền.
2. Ghi `tenantId` như dữ liệu nghiệp vụ/event metadata được phép dùng.
3. Tại listener, kiểm tra event thuộc tenant hợp lệ theo chính sách.
4. Mở một **tenant execution scope** mới trên worker thread.
5. Thực hiện transaction dữ liệu đúng tenant.
6. Dọn tenant context bằng `finally` hoặc một scope tự đóng.

~~~java
// Pseudocode minh họa; TenantScope là kiểu do ứng dụng tự xây dựng.
@ApplicationModuleListener
void on(OrderConfirmed event) {
    TenantId tenant = tenants.requireValid(event.tenantId());

    try (TenantScope ignored = tenantContext.open(tenant)) {
        projectionService.apply(event);
    }
}
~~~

Trong ví dụ này, event phải định nghĩa `tenantId()` khi có yêu cầu multi-tenant. `TenantScope` và `tenantContext` **không phải API chuẩn của Spring Modulith**. Việc chuyển tenant hoặc chọn datasource phải diễn ra **trước khi mở transaction** phù hợp. Không thiết lập lại tenant của một transaction đã gắn với connection khác.

**Cảnh báo:** Nếu worker thread tái sử dụng mà không xóa tenant context, event của tenant B có thể bị xử lý dưới tenant A. Đây là lỗi cô lập dữ liệu nghiêm trọng; nên có test sử dụng cùng executor cho các event thuộc hai tenant.

## 11. Micrometer Context Propagation và tracing

Trong các ứng dụng Spring Boot hiện đại, Micrometer Tracing/OpenTelemetry có thể tạo trace/span để quan sát đường đi giữa HTTP request, event publisher và listener. Spring/Micrometer cung cấp các khả năng **context propagation** giúp chuyển một số context được đăng ký qua async/reactive boundaries.

### 11.1. ContextSnapshot không tự hiểu mọi ThreadLocal

Micrometer Context Propagation cung cấp khái niệm `ContextSnapshot` và các `ThreadLocalAccessor` được đăng ký trong `ContextRegistry` để capture/restore những context cụ thể.

Ý tưởng chung:

~~~text
publisher thread:
    tạo/capture snapshot của context có accessor được đăng ký
    submit task + snapshot

worker thread:
    mở scope từ snapshot
    chạy công việc
    đóng scope / restore context cũ
~~~

Điều này **không có nghĩa** framework tự truyền tất cả custom ThreadLocal, toàn bộ Spring Security context hoặc transaction. Cần xác minh dependency, accessor và configuration mà phiên bản Spring Boot/Micrometer dự án đang sử dụng.

### 11.2. Tracing xuyên sự kiện khác với correlation ID

| Thông tin | Công dụng | Lưu ý |
| --- | --- | --- |
| `traceId` | Nhóm các span cùng một trace | Dùng framework tracing để tạo/tiếp nối span chính xác |
| `spanId` | Nhận diện một span | Không tự sao chép cố định sang mọi công việc mới |
| `correlationId` | Liên kết log/workflow nghiệp vụ | Có thể được thiết kế như metadata event, nếu phù hợp |
| `eventId` | Nhận diện một event nghiệp vụ | Dùng cho idempotency, debug và điều tra publication |
| `orderId` | Nhận diện aggregate | Không được dùng thay thế eventId khi có nhiều event của cùng đơn |

Với sự kiện **đã lưu bền vững và retry sau nhiều giờ**, không nên kỳ vọng trace span của HTTP request cũ vẫn đang sống. Có thể tạo span xử lý mới có thuộc tính `eventId`/`correlationId` hoặc dùng span link theo công cụ tracing phù hợp. Mục tiêu là quan sát luồng đúng nghĩa, không tạo một request “bất tử”.

### 11.3. Không trộn nhiều cơ chế propagation một cách mù quáng

Nếu ứng dụng đã dùng tracing integration hoặc context-propagating decorator, việc tự thêm `MdcCopyingTaskDecorator` có thể ghi đè decorator khác hay tạo context không nhất quán. Cần một phương án thống nhất, có test xác nhận:

- Trace của request được liên kết với listener như mong đợi.
- MDC có event/correlation ID đúng.
- Không mang dữ liệu user/tenant sai sang task khác.
- Context được dọn khi task ném exception.
- Retry sau restart vẫn có đủ metadata từ event để điều tra.

## 12. Thread pool và tải hệ thống ảnh hưởng thế nào?

Ngay cả khi context đã đúng, executor cần cấu hình để không làm hệ thống quá tải. `@Async` không miễn phí: nó chuyển công việc sang queue và worker threads.

### 12.1. Các tham số cần có chủ đích

| Cấu hình | Tác động |
| --- | --- |
| `corePoolSize` | Số worker nền tảng |
| `maxPoolSize` | Mức song song tối đa của pool trong điều kiện cấu hình queue |
| `queueCapacity` | Số task được chờ; queue lớn có thể che backlog/độ trễ |
| `threadNamePrefix` | Giúp đọc log và phân biệt thread |
| Rejection policy | Quyết định khi pool/queue không còn nhận task |
| Shutdown policy | Ảnh hưởng task đang chạy hoặc đang chờ khi ứng dụng dừng |

Trong `ThreadPoolTaskExecutor`, cách tăng số worker đến `maxPoolSize` phụ thuộc tình trạng queue. Một queue quá lớn có thể khiến pool ít khi mở rộng vượt `corePoolSize` nhưng độ trễ task tăng. Cần đo workload I/O/CPU và chọn cấu hình phù hợp.

### 12.2. Thread pool được tái sử dụng

~~~text
request A (tenant=A, trace=A) -> worker-1 -> return
request B (tenant=B, trace=B) -> worker-1 -> return
~~~

Nếu worker-1 còn giữ `ThreadLocal` của request A sau khi task kết thúc, task B có thể đọc thông tin sai. Vì thế **cleanup bằng finally hoặc scope tự đóng là bắt buộc** với custom context, đặc biệt là tenant, security và MDC.

### 12.3. Virtual threads không giải quyết bài toán context

Java virtual threads thay đổi mô hình thực thi và chi phí tạo thread, nhưng **không tự chuyển** security, request hoặc transaction từ thread nguồn sang thread khác. ThreadLocal vẫn có ngữ nghĩa riêng và việc lưu dữ liệu lớn/nguy hiểm trong context vẫn cần tránh.

Đừng chọn virtual threads như một cách thay thế event publication registry, transaction mới hay idempotency. Tính đúng đắn của listener vẫn phụ thuộc contract, thời điểm commit và xử lý lỗi.

## 13. Ví dụ hoàn chỉnh: truyền dữ liệu cần thiết vào event

Giả sử module `orders` phát sự kiện sau khi một đơn được xác nhận. Module `notifications` cần:

- `orderId` để tạo nội dung email.
- `eventId` để deduplicate các lần retry.
- `actorId` để ghi audit của hành động xác nhận.
- `locale` để chọn ngôn ngữ thông báo.
- `correlationId` để tra cứu log.

Không cần chuyển nguyên `SecurityContext`, `HttpServletRequest` hoặc entity JPA.

### 13.1. Contract được công bố bởi module sở hữu

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    String actorId,
    String localeTag,
    String correlationId,
    Instant occurredAt
) {}
~~~

Event nằm trong package `orders.events`. Nếu đây là subpackage cần được module khác import, có thể công bố qua named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Mỗi trường thêm vào phải có lý do nghiệp vụ/bảo mật. Đoạn record là ví dụ yêu cầu cụ thể; **không phải mẫu bắt buộc cho mọi ứng dụng**. Nếu sử dụng registry có lưu serialized payload, cần xem xét schema compatibility khi thay đổi record.

### 13.2. Publisher trích xuất metadata tại ranh giới đã xác thực

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
    public void confirm(UUID orderId, ConfirmContext context) {
        var order = orders.findById(orderId).orElseThrow();
        order.requireCanConfirm(context.actorId());
        order.confirm();

        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            context.actorId(),
            context.localeTag(),
            context.correlationId(),
            clock.instant()
        ));
    }
}
~~~

`ConfirmContext` là **value object của ứng dụng** chứa metadata đã được xác thực tại entry point (controller, background process hoặc integration adapter). Không được lấy `actorId` từ một request parameter chưa kiểm tra. Chính sách authorization vẫn phải được áp dụng phù hợp; chỉ truyền actor ID không tự cấp quyền.

### 13.3. Listener dùng context bền vững từ event

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.slf4j.MDC;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationHandler {

    private final ConfirmationDeliveryService delivery;

    OrderConfirmationHandler(ConfirmationDeliveryService delivery) {
        this.delivery = delivery;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        try (var eventLog = MDC.putCloseable(
                "eventId", event.eventId().toString());
             var correlationLog = MDC.putCloseable(
                "correlationId", event.correlationId())) {

            delivery.sendOnce(
                event.eventId(),
                event.orderId(),
                event.actorId(),
                event.localeTag()
            );
        }
    }
}
~~~

`ConfirmationDeliveryService.sendOnce(...)` do module `notifications` định nghĩa và cần thực hiện idempotency trên dữ liệu do module sở hữu hoặc phối hợp provider có idempotency key. Giả định các ID và correlation string hợp lệ; thực tế phải validate những input bắt buộc.

Listener **không hỏi lại HTTP context**. Vì vậy nó vẫn có đủ thông tin khi:

- Chạy ở worker thread khác.
- Event được xử lý vài giây sau transaction nguồn.
- Publication bị retry sau khi executor khởi động lại.
- API gọi event đến từ scheduled job thay vì một HTTP request.

### 13.4. Khi nào cần đọc state hiện tại thay vì snapshot?

Nếu nội dung thông báo phải phản ánh **tên hiển thị mới nhất của khách hàng**, có thể đọc qua API truy vấn phù hợp tại thời điểm gửi. Nếu phải phản ánh **đúng dữ liệu tại thời điểm xác nhận**, cần snapshot giá trị bất biến. Không có đáp án chung: phải nêu rõ contract nghiệp vụ và lựa chọn nhất quán.

## 14. Lỗi, retry và context sau khi ứng dụng restart

Trong Spring Modulith, event publication registry giúp theo dõi publication cho những transactional listeners phù hợp khi backend lưu trữ đã được cấu hình. Một listener có thể được gọi lại sau khi xử lý trước đó thất bại.

### 14.1. Tại sao TaskDecorator không đủ cho replay?

Giả sử request `traceId=abc123` phát `OrderConfirmed` và application server crash. Sau restart, registry resubmit publication:

~~~text
HTTP thread ban đầu: đã biến mất
SecurityContext cũ: không còn
MDC cũ: không còn
RequestContext cũ: không còn
Transaction nguồn: đã commit trong quá khứ
Event payload lưu bền: còn nếu registry/backend ghi đúng
~~~

TaskDecorator chỉ có thể capture context của thread **đang submit công việc mới**; nó không thể phục hồi ngẫu nhiên HTTP context của nhiều giờ trước. Vì vậy, `eventId`, `tenantId`, `actorId`, `localeTag` hoặc `correlationId` nếu thực sự cần phải xuất hiện trong event/metadata bền vững.

### 14.2. Thứ tự xử lý và thời điểm hoàn tất

Thứ tự event được phát **không luôn bằng** thứ tự hoàn tất các async listeners. Một listener xử lý lâu có thể kết thúc sau listener được dispatch sau, và event cũ có thể được resubmit sau event mới.

Nếu consumer cần thứ tự theo aggregate:

- Cân nhắc `aggregateVersion` hoặc sequence ổn định.
- Chọn chiến lược state machine, optimistic locking hoặc buffer event.
- Không dùng timestamp hoặc thread ID làm thứ tự nghiệp vụ tuyệt đối.
- Khi dùng broker, hiểu phạm vi ordering theo partition/key và giới hạn của cơ chế retry.

### 14.3. Completion không đồng nghĩa exactly-once

Một listener có thể ghi database thành công rồi crash trước khi publication được đánh dấu hoàn tất. Khi retry, event được xử lý lại. Cần áp dụng **idempotency**:

~~~sql
CREATE TABLE processed_order_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

~~~text
handle(event):
    BEGIN local transaction
       INSERT eventId vào processed_order_events (unique)
       nếu trùng: không thực hiện tác dụng phụ lần nữa
       nếu mới: cập nhật dữ liệu do module nhận sở hữu
    COMMIT
    listener trả về thành công
~~~

Việc ghi dấu và cập nhật dữ liệu cần phối hợp transaction và unique constraint thích hợp để bảo vệ concurrency. Với email hoặc HTTP provider ngoài, cần chiến lược idempotency/đối soát riêng; database local không thể tự bảo đảm atomicity với mọi tác dụng phụ ngoại vi.

### 14.4. Không nuốt exception của listener quan trọng

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        delivery.sendOnce(
            event.eventId(), event.orderId(),
            event.actorId(), event.localeTag()
        );
    } catch (RuntimeException error) {
        log.error("Notification failed, eventId={}",
                event.eventId(), error);
        throw error; // Không báo hoàn tất giả cho tác vụ cần retry.
    }
}
~~~

Nếu bắt exception rồi trả về như thành công, cơ chế theo dõi publication có thể **đánh dấu completed dù công việc chưa xong**. Chỉ nuốt lỗi khi chính contract của listener cho phép bỏ qua và đã có cơ chế ghi nhận quyết định rõ ràng.

## 15. Kiểm thử thread context và ranh giới transaction

Unit test method listener không đủ chứng minh việc context có bị mất khi Spring dispatch sang executor hay callback có đợi commit hay không. Cần kết hợp **test logic, Spring integration test và fault injection**.

### 15.1. Ma trận kiểm thử

| Ca kiểm thử | Kết quả cần xác minh |
| --- | --- |
| Listener `@EventListener` đồng bộ | Cùng thread với publisher khi dùng multicaster đồng bộ chuẩn |
| Listener `@Async` | Công việc thực có thể chạy ở thread khác; không dựa vào transaction nguồn |
| Listener `AFTER_COMMIT` | Chỉ chạy sau commit thành công; không chạy cho transaction rollback |
| Listener `@ApplicationModuleListener` | Tác vụ hậu commit có transaction riêng phù hợp |
| MDC có decorator | Đúng correlation keys trên worker, không còn sau khi task kết thúc |
| Hai request dùng cùng worker | Task B không thấy dữ liệu MDC/tenant của task A |
| Security context không propagate | Handler không crash do null principal; dùng actor từ event nếu cần |
| Tenant A và B | Mỗi event chọn đúng tenant, không truy cập chéo |
| Request kết thúc trước listener | Không gọi `RequestContextHolder` của request cũ |
| Publication được replay sau restart | Metadata cần thiết vẫn lấy từ event/registry |
| Listener retry cùng `eventId` | Không gửi/trừ/tăng điểm trùng |
| Worker exception | Context được cleanup trong finally; lỗi được ghi nhận |

### 15.2. Test định tính thread-hop

Với Spring integration test, dùng một listener thử nghiệm ghi `Thread.currentThread().getName()` và tín hiệu hoàn tất vào một đối tượng đồng bộ trong test. Gọi service publisher, chờ kết quả bằng `CountDownLatch` hoặc công cụ chờ điều kiện có timeout. So sánh tên/ID thread **trong đúng cấu hình executor đang thử**.

Không cần mặc định các thread tên gì. Quan trọng là xác định:

1. Listener thực sự đi qua async executor.
2. Không phụ thuộc transaction/request của publisher.
3. Context được truyền hoặc tái lập đúng với contract.

Một unit test gọi trực tiếp `listener.on(event)` **không thực hiện thread hop**, vì vậy không chứng minh `@Async`, `@TransactionalEventListener` hoặc registry đã hoạt động.

### 15.3. Test sự rò rỉ context trong thread pool

Cấu hình test executor có một worker để cố ý tái sử dụng thread:

~~~text
Task A:
    MDC tenant=A, trace=A
    xử lý xong

Task B:
    MDC tenant=B, trace=B
    phải KHÔNG nhìn thấy tenant=A hoặc trace=A

Task C:
    không có context
    phải KHÔNG nhận lại context của A/B
~~~

Chạy trường hợp A ném exception để chắc chắn `finally` vẫn dọn MDC/custom ThreadLocal. Kiểm tra cả task không có context nguồn, vì lỗi rò rỉ thường bị phát hiện khi thread chạy lại một task **trống context**.

### 15.4. Test transaction cần commit thật

Nhiều Spring test có `@Transactional` sẽ rollback mặc định khi test kết thúc, khiến listener `AFTER_COMMIT` không chạy. Muốn kiểm tra hậu commit, cần **cho transaction nguồn commit thật** hoặc điều khiển test transaction theo API tương ứng.

Khi listener async, chờ trạng thái cuối cùng bằng điều kiện có timeout, không dùng `Thread.sleep(...)` cố định. Đọc lại database của module nhận trong transaction độc lập để kiểm tra dữ liệu thực sự commit, không chỉ kiểm tra event đã được publish.

### 15.5. Test sai lỗi thực tế

Mô phỏng:

- Request đã kết thúc trước khi handler truy cập locale.
- SecurityContext trống hoặc service principal khác HTTP caller.
- Thread pool bận, task chờ trong queue; request đã được giải phóng.
- Registry replay event cũ sau restart.
- External provider bị timeout rồi thành công trước lần retry.
- Listener bắt và nuốt exception khiến publication bị ghi hoàn tất giả.
- Worker bị interrupt hoặc executor bị shutdown khi đang chạy.

Kiểm tra hành vi theo **sự thật nghiệp vụ, độ bền công việc và cách khôi phục**, không chỉ dựa trên việc log có xuất hiện một traceId.

## 16. Những sai lầm thường gặp

### “@Async nghĩa là sẽ chạy sau commit”

Sai. `@Async` quyết định **executor/thread**, không quyết định pha transaction. Một listener `@EventListener` được đánh dấu `@Async` có thể bắt đầu trước khi transaction publisher commit. Muốn xử lý hậu commit, cần dùng đúng cơ chế transactional event.

### “@Transactional trên publisher sẽ đi sang worker”

Sai với transaction imperative thông thường. Worker không chia sẻ transaction của HTTP thread. Nếu listener cần ghi database, cần transaction riêng theo thiết kế.

### “@TransactionalEventListener(AFTER_COMMIT) tự chạy background”

Sai. After-commit là **điều kiện thời điểm**, không tự có thread mới. Muốn async cần cơ chế async phù hợp hoặc `@ApplicationModuleListener` với hạ tầng cấu hình đúng.

### “Chỉ cần copy SecurityContext và HttpServletRequest là xong”

Sai. Request có vòng đời riêng; security context có thông tin nhạy cảm và có thể hết hiệu lực. Với công việc bền vững, hãy truyền dữ liệu nghiệp vụ tối thiểu và thực hiện authorization phù hợp tại nơi xử lý.

### “TaskDecorator chuyển được mọi ThreadLocal và transaction”

Sai. Decorator chỉ xử lý những context được viết để capture/restore, và không thể sao chép transaction nguồn một cách hợp lệ. Context qua restart/replay phải được thiết kế khác.

### “MDC không cần dọn vì thread sẽ kết thúc”

Sai với thread pool. Worker được tái sử dụng, gây rò rỉ trace, tenant hoặc dữ liệu người dùng giữa các tác vụ nếu không cleanup.

### “Virtual threads tự bảo toàn context của request”

Sai. Dù virtual threads có đặc điểm quản lý thread khác, context của thread này không tự trở thành context của thread khác. Transaction, request và security identity vẫn cần thiết kế tường minh.

### “Có traceId trong log là event đã được xử lý đúng”

Sai. Trace giúp quan sát, nhưng listener có thể thất bại, publication chưa completed hoặc tác dụng phụ bị xử lý trùng. Cần cả registry/retry, idempotency và kiểm thử.

## 17. Bài tập thực hành: sửa lỗi context trong notification listener

**Bối cảnh:** Một ứng dụng Spring Modulith có `orders` và `notifications`. Người dùng xác nhận đơn qua HTTP. Code hiện tại:

~~~java
@Async
@EventListener
void on(OrderConfirmed event) {
    String user = SecurityContextHolder.getContext()
        .getAuthentication().getName();
    Locale locale = LocaleContextHolder.getLocale();
    String traceId = MDC.get("traceId");

    emailSender.send(event.orderId(), user, locale, traceId);
}
~~~

Các lỗi quan sát được: đôi lúc `NullPointerException` vì authentication trống; một số email dùng locale mặc định; trace ID biến mất; email đôi khi được gửi dù transaction xác nhận đơn rollback.

### 17.1. Yêu cầu sửa

1. Giữ quyền quyết định xác nhận đơn trong `orders`.
2. Phát `OrderConfirmed` chỉ khi trạng thái nghiệp vụ được xác lập hợp lệ.
3. Chỉ gửi email khi transaction nguồn commit thành công.
4. Không yêu cầu listener phải nhìn thấy HTTP SecurityContext hoặc request còn sống.
5. Bảo toàn `actorId`, `localeTag`, `correlationId` khi thực sự cần qua retry/restart.
6. Giới hạn context quan sát trong một lượt xử lý và cleanup khi hoàn tất.
7. Bảo vệ duplicate khi listener được xử lý lại.
8. Có test rollback, request không có principal trên worker, MDC leakage và registry replay.

### 17.2. Phương án đề xuất

~~~mermaid
flowchart TD
    HTTP[HTTP request / auth] --> Validate[Validate actor, locale, correlation]
    Validate --> Orders[orders: confirm trong transaction]
    Orders --> Ev[OrderConfirmed chứa metadata cần thiết]
    Ev --> Commit{Source commit?}
    Commit -->|Rollback| NoEmail[Không chạy tác vụ hậu commit]
    Commit -->|Commit| Async[Async module listener]
    Async --> NewTx[notifications: transaction / scope riêng]
    NewTx --> Send[sendOnce với idempotency key]
    Send --> Done[Completion / registry theo cấu hình]
~~~

Không cần đưa toàn bộ authentication vào event. Module `notifications` chỉ nhận những trường đã được chọn lọc và có quyền xử lý. Nếu phải gọi nhà cung cấp email ngoài database, cần áp dụng retry và idempotency/đối soát riêng cho provider đó.

### 17.3. Các bước triển khai

- **Bước 1:** Bổ sung metadata nghiệp vụ cần thiết vào contract `OrderConfirmed`.
- **Bước 2:** Trích xuất và xác minh metadata tại controller/application boundary; không dùng request parameter không tin cậy để giả mạo actor.
- **Bước 3:** Dùng `@TransactionalEventListener(AFTER_COMMIT)` kết hợp async phù hợp, hoặc `@ApplicationModuleListener` nếu đáp ứng hạ tầng và mức độ tin cậy mong muốn.
- **Bước 4:** Ghi event/publication bền vững nếu tác vụ gửi thông báo cần phục hồi sau process restart.
- **Bước 5:** Trong listener, lấy actor/locale/correlation từ event, thêm MDC bằng scope ngắn, xử lý thông báo với idempotency.
- **Bước 6:** Dọn custom `ThreadLocal` trong `finally` hoặc scope tự đóng, kể cả khi throw exception.
- **Bước 7:** Kiểm thử cùng executor xử lý event từ hai tenant/người dùng khác nhau mà không lộ context.
- **Bước 8:** Giả lập transaction rollback, worker lỗi, service restart và gửi lại cùng event ID.

### 17.4. Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Không gửi email sau rollback | Integration test cho source transaction rollback |
| Không lệ thuộc HTTP context | Listener xử lý được event khi request đã đóng |
| Đúng actor và locale | Dữ liệu event đã xác thực được dùng ở listener |
| Không rò rỉ MDC/tenant | Hai task liên tiếp trên cùng worker không dùng nhầm context |
| Có khả năng phục hồi | Publication chưa hoàn tất vẫn được quan sát và resubmit theo chính sách |
| Không gửi lặp ngoài ý muốn | Cùng `eventId` được xử lý lại an toàn |
| Đọc log đúng luồng | Có event ID/correlation ID phù hợp, không lộ token hoặc dữ liệu nhạy cảm |

## 18. Checklist và câu hỏi tự kiểm tra

### Checklist

- [ ] Đã xác định listener chạy đồng bộ hay bất đồng bộ, và có thuộc pha transaction nào không.
- [ ] Không coi `@Async` là tương đương `AFTER_COMMIT`.
- [ ] Không sao chép transaction/JPA persistence context từ publisher sang worker.
- [ ] Listener hậu commit ghi DB có transaction riêng với commit rõ ràng.
- [ ] Dữ liệu nghiệp vụ cần cho retry/restart được đưa vào event hoặc contract bền vững phù hợp.
- [ ] Không dùng `HttpServletRequest`/session cũ trong listener chạy nền.
- [ ] Security identity ở nơi xử lý được thiết kế đúng: actor audit khác service authorization.
- [ ] Locale, tenant và correlation được chuyển hoặc tái lập rõ ràng, có validation.
- [ ] MDC và custom ThreadLocal được cleanup dù task thất bại.
- [ ] Không phụ thuộc vào `InheritableThreadLocal` để giải quyết thread pool.
- [ ] Không tự coi context propagation là cơ chế giao event đáng tin cậy.
- [ ] Async executor có kích thước queue/pool và rejection policy phù hợp.
- [ ] Registry, resubmission, idempotency và error handling được kiểm thử khi cần.
- [ ] Test có transaction nguồn commit thật và kiểm chứng listener async qua timeout.
- [ ] Có kiểm thử context leakage trên cùng một worker thread được tái sử dụng.

### Câu hỏi

1. Vì sao `SecurityContextHolder` có thể đọc được trong listener đồng bộ mà lại trống ở listener `@Async`?
2. `@TransactionalEventListener(AFTER_COMMIT)` có tự tạo worker thread mới không?
3. Vì sao `@Async` trên `@EventListener` có thể khiến tác vụ chạy trước transaction nguồn commit?
4. Khi một callback `AFTER_COMMIT` cần ghi database, vì sao phải cân nhắc transaction mới?
5. Vì sao TaskDecorator truyền MDC nhưng không thể truyền transaction nguồn?
6. Khi registry replay event sau restart, cần lấy `actorId`, `tenantId` hoặc `correlationId` từ đâu?
7. Lỗi gì xảy ra khi không dọn custom `TenantContext` trên thread pool?
8. Khi nào nên dùng `DelegatingSecurityContextAsyncTaskExecutor`, khi nào nên dùng actor ID trong event?
9. `traceId` và `eventId` phục vụ những mục đích khác nhau nào?
10. Vì sao unit test gọi thẳng method listener không chứng minh `@Async` thực sự chạy trên thread khác?
11. Khi source transaction rollback, listener kiểu nào không nên thực hiện tác vụ hậu commit?
12. Vì sao listener báo completed vẫn có thể tạo tác dụng phụ lặp sau resubmission?

**Ghi nhớ:** Thread context là một tiện ích gắn với **luồng thực thi**, trong khi application event biểu diễn **sự thật nghiệp vụ có thể được xử lý ở thời điểm và thread khác**. Muốn giao tiếp module đáng tin cậy với Spring Modulith, hãy bảo vệ ranh giới transaction, truyền metadata nghiệp vụ cần thiết một cách tường minh, dùng propagation cho quan sát đúng phạm vi, dọn context khi dùng executor, và kiểm thử cả async, rollback, retry lẫn restart.
