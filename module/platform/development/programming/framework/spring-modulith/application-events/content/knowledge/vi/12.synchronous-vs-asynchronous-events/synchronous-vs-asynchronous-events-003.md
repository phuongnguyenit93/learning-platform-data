# `@Async` cho event trong Spring Modulith

Giả sử khách hàng đặt một đơn hàng. Module `ordering` lưu đơn, sau đó module `notification` gửi email, module `analytics` cập nhật thống kê và module `loyalty` tính điểm thưởng. Nếu cả ba listener cùng thực thi trên luồng xử lý HTTP và gửi email bị chậm, thời gian phản hồi đặt hàng sẽ bị kéo dài. Spring cho phép dùng **`@Async` để listener thực thi công việc trên một luồng của executor**, thay vì bắt buộc chờ toàn bộ tác vụ đó hoàn tất trên luồng phát sự kiện.

Nhưng có ba điều khác nhau cần phân biệt:

- **Bất đồng bộ (`@Async`):** xử lý được chuyển sang luồng khác và bên phát thường không chờ listener hoàn tất.
- **Sau commit (`AFTER_COMMIT`):** listener chỉ được kích hoạt khi transaction phát sự kiện đã commit thành công.
- **Giao sự kiện đáng tin cậy:** nếu ứng dụng dừng hoặc listener lỗi, còn khả năng phát hiện và khôi phục công việc chưa hoàn tất; cần hạ tầng lưu publication, retry và idempotency phù hợp.

`@Async` **không tự động đồng nghĩa** với hai điều còn lại. Đây là điểm trọng tâm của bài trong chương **Đồng bộ và bất đồng bộ**, thuộc module học `SPRING_MODULITH_APPLICATION_EVENTS`: tổ chức giao tiếp giữa các module Spring Modulith bằng application events, giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ, đồng thời thực hành publisher, listener, xử lý sau commit, event publication registry, retry, kiểm thử và quan sát việc giao sự kiện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. So sánh `@EventListener` đồng bộ với `@Async @EventListener` về luồng thực thi, thời gian phản hồi và lan truyền lỗi.
2. Cấu hình `@EnableAsync` và một `ThreadPoolTaskExecutor` chuyên cho listener sự kiện.
3. Phân biệt **đổi luồng** với **đổi transaction**; giải thích vì sao listener bất đồng bộ không dùng chung transaction của publisher.
4. Kết hợp `@Async` với `@TransactionalEventListener(phase = AFTER_COMMIT)` đúng nhu cầu nghiệp vụ.
5. Sử dụng `@ApplicationModuleListener` của Spring Modulith và hiểu các semantics giao dịch/bất đồng bộ của nó.
6. Xác định failure window của async event, chọn retry và idempotency thích hợp.
7. Thiết kế test và metric để kiểm chứng listener có chạy trên executor, xử lý sau commit và không làm mất công việc quan trọng khi gặp lỗi.

## 2. Event đồng bộ mặc định: publisher và listener dùng chung luồng

Spring application events không mặc nhiên chạy bất đồng bộ. Với bộ phát sự kiện và multicaster mặc định thường gặp, `@EventListener` được gọi **đồng bộ trong luồng gọi `publishEvent(...)`**.

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final ConfirmationSender sender;

    OrderNotificationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @EventListener
    public void on(OrderPlaced event) {
        sender.send(event.orderId());
    }
}
~~~

Giả sử `OrderingService` gọi:

~~~java
events.publishEvent(new OrderPlaced(
        UUID.randomUUID(),
        orderId,
        clock.instant()
));
~~~

Với dispatcher đồng bộ, luồng gọi có thể phải đợi `sender.send(...)` chạy xong mới tiếp tục. Nếu handler ném một exception chưa được xử lý, exception có thể lan ngược về publisher và ảnh hưởng luồng xử lý hiện tại; khi transaction vẫn mở, điều này có thể ảnh hưởng quyết định commit/rollback.

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant O as ordering
    participant P as Spring event publisher
    participant N as notification listener
    C->>O: placeOrder()
    O->>P: publish OrderPlaced
    P->>N: on(event)
    N->>N: Gửi email (chậm)
    N-->>P: Hoàn tất
    P-->>O: publishEvent() trả về
    O-->>C: Kết quả đặt hàng
~~~

Sơ đồ phản ánh **trường hợp listener đồng bộ**. Cấu hình multicaster, listener và executor của ứng dụng có thể thay đổi hành vi thực tế; không nên suy luận từ tên “event” rằng sự kiện luôn được xử lý sau hoặc ngoài luồng chính.

## 3. Thêm `@Async`: thay đổi điều gì?

Nếu method listener được gắn `@Async`, Spring có thể lập lịch phần xử lý lên một executor:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
class AsyncOrderNotificationListener {

    private final ConfirmationSender sender;

    AsyncOrderNotificationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @Async("eventExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        sender.send(event.orderId());
    }
}
~~~

Khi async support được bật và `eventExecutor` tồn tại, lệnh publish thường chỉ phải **lên lịch** cho handler; nó không phải chờ `sender.send(...)` hoàn tất. Method `on(...)` ở ví dụ này không trả về kết quả mà publisher cần dùng.

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant O as ordering
    participant P as Spring event publisher
    participant X as eventExecutor
    participant N as async listener
    C->>O: placeOrder()
    O->>P: publish OrderPlaced
    P->>X: Submit task
    X-->>P: Đã nhận task
    P-->>O: publishEvent() trả về
    O-->>C: Kết quả đặt hàng
    X->>N: on(event) trên worker thread
    N->>N: Gửi email
~~~

**Chú ý:** đây là minh họa khả năng chạy xen kẽ, không khẳng định email luôn diễn ra sau khi HTTP response đã gửi. Worker thread có thể bắt đầu rất sớm, thậm chí trước khi publisher kết thúc transaction.

| Tính chất | `@EventListener` đồng bộ điển hình | `@Async @EventListener` |
| --- | --- | --- |
| Luồng xử lý | Thường cùng luồng publisher | Luồng của executor |
| Publisher chờ listener hoàn tất? | Thường có | Thường không |
| Exception trong handler | Có thể lan ngược về luồng publish | Không lan ngược theo cách đồng bộ; cần giám sát/xử lý riêng |
| Transaction context của publisher | Handler đồng bộ có thể chạy khi transaction nguồn còn hoạt động | Không tự truyền qua worker thread |
| Thời điểm so với commit | Có thể trước commit | **Vẫn có thể trước commit** |
| Sau crash còn công việc? | Tùy kiến trúc | Task in-memory có thể mất nếu không có hạ tầng bền vững |
| Thứ tự giữa các event | Phụ thuộc dispatcher và logic | Không nên mặc định giữ thứ tự khi nhiều worker |

### Phân biệt async listener với async multicaster

Có hai hướng tạo xử lý bất đồng bộ ở Spring: đánh dấu từng listener bằng `@Async` hoặc cấu hình executor cho `ApplicationEventMulticaster`. Bài này tập trung **`@Async` trên listener**, vì cách đó thể hiện rõ handler nào được chạy bất đồng bộ.

Không nên đổi multicaster toàn cục chỉ để giải quyết một listener chậm nếu chưa xem xét các listener khác, đặc biệt listener giao dịch cần được gọi đúng ngữ cảnh transaction. Spring cũng có cơ chế để một số listener chỉ ra rằng chúng **không hỗ trợ** thực thi bất đồng bộ do multicaster tự lựa chọn; việc ép async toàn cục có thể gây hành vi không như mong đợi.

## 4. Kích hoạt async và cấp executor riêng

`@Async` cần hạ tầng xử lý bất đồng bộ của Spring. Trong cấu hình thông thường, khai báo `@EnableAsync` và một executor có tên dùng cho event:

~~~java
package com.example.shop.config;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class EventAsyncConfiguration {

    @Bean(name = "eventExecutor")
    Executor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("modulith-events-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        executor.initialize();
        return executor;
    }
}
~~~

Khi dùng `@Async("eventExecutor")`, Spring chọn executor được khai báo với qualifier tương ứng. Các con số trên là **ví dụ**, không phải cấu hình khuyến nghị cho mọi hệ thống. Phải điều chỉnh theo độ trễ I/O, CPU, số lượng event, memory, khả năng chịu tải và giới hạn của dịch vụ bên ngoài.

### Vì sao nên có executor riêng?

- **Cô lập tài nguyên:** email hoặc báo cáo chậm không làm chiếm hết pool dùng cho công việc khác.
- **Đặt giới hạn rõ:** cấu hình số worker và queue thay vì để lượng việc tăng vô hạn.
- **Quan sát dễ hơn:** thread name, số task chờ và mức sử dụng pool có thể theo dõi riêng.
- **Vận hành có chủ đích:** lựa chọn cách phản ứng khi queue đầy và lúc shutdown.

### Không bỏ qua trường hợp queue đầy

Khi số task đang chạy đạt giới hạn và queue đã đầy, executor có thể **từ chối task mới**. Tùy executor và cấu hình rejection policy, lỗi lên lịch có thể xuất hiện ngay ở luồng publish hoặc tác vụ bị xử lý theo chính sách khác. `@Async` không bảo đảm một task bất kỳ luôn được tiếp nhận.

Vì vậy, cần xác định:

1. Mức concurrency tối đa mà database và dịch vụ bên ngoài chịu được.
2. Queue tối đa và thời gian chờ chấp nhận được.
3. Chính sách từ chối, cảnh báo và khả năng khôi phục.
4. Khi ứng dụng dừng, công việc nào phải hoàn tất, công việc nào cần lưu bền để xử lý sau.

`setWaitForTasksToCompleteOnShutdown(true)` có thể giúp xử lý phần việc đang nằm trong executor trong quá trình shutdown thông thường, nhưng **không bảo vệ khỏi process crash, mất điện hoặc bị kill cưỡng bức**.

## 5. Ví dụ package module: publisher và async subscriber

Trong Spring Modulith, nên phân biệt **module phát hợp đồng** với **module sở hữu tác vụ async**:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/
│   ├── OrderFacade.java
│   ├── events/
│   │   ├── package-info.java      # Named interface "events"
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── OrderingService.java   # Publisher
│       └── OrderRepository.java
├── notification/
│   ├── package-info.java
│   └── internal/
│       ├── AsyncOrderNotificationListener.java
│       └── ConfirmationSender.java
└── analytics/
    └── internal/
        └── OrderAnalyticsListener.java
~~~

Event contract:

~~~java
// com/example/shop/ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

Nếu hợp đồng ở subpackage `ordering.events`, công bố nó thành named interface:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Module `notification` chỉ cần API events có thể giới hạn phụ thuộc:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

Publisher:

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderingService(
            OrderRepository repository,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(OrderDraft draft) {
        UUID orderId = repository.create(draft);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));

        return orderId;
    }
}
~~~

`OrderDraft`, `OrderRepository` và bean `Clock` là các thành phần giả định của ứng dụng minh họa. Ví dụ cho thấy publisher **không biết** listener của `notification` và `analytics`; các consumer chỉ import contract đã công bố.

Nhưng nếu `notification` dùng `@Async @EventListener` như mục 3, nó có thể bắt đầu xử lý `OrderPlaced` **trước khi transaction tạo đơn commit**. Nếu thao tác gửi email phải phụ thuộc vào việc đơn đã lưu thành công, cần thay đổi cơ chế kích hoạt như phần tiếp theo.

## 6. `@Async` không chờ commit: race condition quan trọng

Xét tiến trình:

~~~text
T0  Thread HTTP mở transaction tạo đơn
T1  Ghi OrderEntity (chưa commit)
T2  publish OrderPlaced
T3  @Async @EventListener được executor nhận task
T4  Thread async chạy, tra orderId ở kết nối DB khác
T5  Transaction nguồn commit hoặc rollback
~~~

T4 có thể đến **trước** T5. Nếu async listener tra database, nó có thể chưa nhìn thấy đơn hàng chưa commit theo isolation level thông thường. Tệ hơn, nếu gửi email ở T4 nhưng transaction rollback ở T5, người dùng có thể nhận xác nhận về đơn hàng chưa được chấp nhận.

~~~mermaid
sequenceDiagram
    participant O as ordering transaction
    participant DB as Database
    participant X as Executor
    participant N as notification
    O->>DB: INSERT Order (chưa commit)
    O->>X: publish -> schedule async listener
    par Hai luồng chạy độc lập
        X->>N: on(OrderPlaced)
        N->>DB: SELECT Order
    and
        O->>DB: Commit hoặc rollback
    end
    Note over N,DB: Listener có thể đọc trước khi commit
~~~

**Giải pháp đúng về thứ tự nghiệp vụ:** nếu consumer chỉ được phản ứng với đơn hàng đã commit, dùng listener theo transaction phase `AFTER_COMMIT`, có thể kết hợp với `@Async`. Đừng cố khắc phục bằng `Thread.sleep(...)`; sleep không tạo bảo đảm thứ tự hay tính bền vững.

## 7. Kết hợp `@Async` với `@TransactionalEventListener(AFTER_COMMIT)`

Đối với email sau khi đơn hàng đã được lưu thành công, listener có thể viết:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderCommittedNotificationListener {

    private final ConfirmationService confirmations;

    OrderCommittedNotificationListener(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @Async("eventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        confirmations.processCommittedOrder(event);
    }
}
~~~

Ý nghĩa:

1. `@TransactionalEventListener` gắn xử lý với **commit của transaction phát event**.
2. `@Async("eventExecutor")` chuyển phần xử lý sang worker thread.
3. `ConfirmationService` chịu trách nhiệm nghiệp vụ notification và trạng thái xử lý của nó.

`@TransactionalEventListener` có phase mặc định là `AFTER_COMMIT`; khai báo tường minh để dễ học. Nếu publisher phát sự kiện **ngoài một transaction đang hoạt động**, listener kiểu này sẽ **không chạy theo mặc định**, trừ khi chủ động bật `fallbackExecution = true`.

### 7.1. Thread async không có transaction nguồn

Transaction Spring phổ biến dựa trên **context gắn với thread**. Khi chuyển sang một worker thread, transaction context của publisher **không tự được truyền qua**. Đây là điều mong muốn với xử lý độc lập, nhưng cũng có nghĩa consumer muốn ghi database cần transaction riêng.

Ví dụ dùng một service bean khác để mở transaction:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class ConfirmationService {

    private final NotificationRepository notifications;

    ConfirmationService(NotificationRepository notifications) {
        this.notifications = notifications;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void processCommittedOrder(OrderPlaced event) {
        notifications.createPendingConfirmationIfAbsent(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

`NotificationRepository` và `createPendingConfirmationIfAbsent(...)` là các abstraction minh họa. Tên method không tự bảo đảm idempotency; dự án thật cần unique constraint/transaction phù hợp.

Đặt `@Transactional` trên **một bean riêng** giúp lời gọi đi qua Spring transaction proxy, tránh nhầm lẫn với self-invocation (`this.someTransactionalMethod()`) trong cùng class. Phần gửi email bên ngoài database có thể là bước tiếp theo và cần chính sách retry riêng.

### 7.2. Khi không cần async

Không phải listener sau commit nào cũng cần `@Async`. Nếu phản ứng rất nhỏ, có yêu cầu thứ tự rõ hoặc muốn đơn giản hóa vận hành, `@TransactionalEventListener(AFTER_COMMIT)` đồng bộ có thể phù hợp. Chọn async dựa trên độ trễ, tài nguyên, cô lập lỗi và khả năng chấp nhận xử lý muộn.

## 8. `@ApplicationModuleListener` của Spring Modulith

Spring Modulith có annotation `@ApplicationModuleListener` để đơn giản hóa mô hình **listener module độc lập**. Theo semantics của annotation này, nó kết hợp listener giao dịch sau commit, `@Async` và transaction mới (`REQUIRES_NEW`):

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationModuleListener {

    private final ConfirmationService confirmations;

    OrderNotificationModuleListener(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.processCommittedOrder(event);
    }
}
~~~

`@ApplicationModuleListener` giúp biểu đạt ý đồ: module `notification` phản ứng với một sự thật đã commit ở module `ordering` mà không ràng buộc transaction nguồn. Với ví dụ này, nếu `ConfirmationService` đã mở transaction `REQUIRES_NEW`, cần xem xét có thực sự cần annotation transaction ở cả lớp xử lý và lớp listener hay không; ứng dụng thật nên chọn ranh giới transaction đơn giản, nhất quán.

**Không dùng đồng thời cả hai listener ở mục 7 và mục 8 cho cùng side effect** nếu không chủ động muốn xử lý hai lần. Đây là **hai phương án thay thế** để minh họa, không phải cấu hình nên triển khai cùng lúc.

### Phân biệt Spring `@Async` và Spring Modulith

| Thành phần | Vai trò |
| --- | --- |
| `@Async` | Chuyển thực thi method sang executor của Spring theo cấu hình |
| `@EventListener` | Đăng ký method phản ứng với application event |
| `@TransactionalEventListener` | Đăng ký phản ứng gắn với pha transaction của event |
| `@ApplicationModuleListener` | Kết hợp các semantics phù hợp cho phản ứng giữa application modules |
| **Event Publication Registry** | Theo dõi publication hoàn tất/chưa hoàn tất theo hạ tầng persistence được cấu hình |

Đừng suy ra chỉ gắn `@ApplicationModuleListener` là đã có mọi dependency lưu trạng thái publication, retry policy hoặc exactly-once. Khả năng này phải được cấu hình và kiểm chứng ở ứng dụng đang dùng.

## 9. Event contract và ownership vẫn quan trọng khi async

Khi chuyển sang executor, listener có thể chạy **sau khi code publisher đã thoát khỏi method**, thậm chí sau khi request context kết thúc. Vì vậy payload cần **đủ ổn định và không phụ thuộc tài nguyên sống của thread nguồn**.

Nên:

- Dùng record/DTO hoặc value object không thay đổi sau publish.
- Đưa `eventId`, `orderId` và timestamp có ý nghĩa để hỗ trợ khử trùng lặp và truy vết.
- Giữ event contract ở API công khai hoặc named interface của module phát.
- Để module nhận sở hữu cách xử lý side effect, thay vì đặt implementation listener trong package module phát.

Nên tránh:

~~~java
// Không nên truyền trực tiếp entity JPA có lazy relationship
// hoặc tham chiếu tới request/thread-specific state:
public record OrderPlaced(OrderEntity entity, HttpServletRequest request) {}
~~~

Đây là ví dụ **thiết kế cần tránh**, không phải event contract thực tế. Một async listener không nên kỳ vọng persistence context nguồn vẫn mở hoặc request thread state vẫn tồn tại. Nếu cần dữ liệu bổ sung, dùng contract snapshot thích hợp hoặc truy vấn qua API đã công bố sau commit.

### Thread-local context không tự động “đi theo” `@Async`

`SecurityContextHolder`, MDC logging, request context và nhiều transaction context có thể dựa trên `ThreadLocal`. Khi đổi thread:

- Không mặc định có cùng identity, trace ID hoặc MDC của thread HTTP.
- Không copy tùy tiện toàn bộ security context nếu worker không cần.
- Nếu cần correlation, hãy đưa định danh an toàn vào event hoặc cấu hình task decorator/context propagation đã được kiểm soát.
- Với yêu cầu phân quyền ở listener, lấy và xác minh dữ liệu/identity theo policy phù hợp; không coi chuỗi `userId` trong payload là bằng chứng authorization.

**Async không phải ranh giới bảo mật.** Các module cùng JVM vẫn chia sẻ môi trường runtime; `@Async` chỉ thay đổi cách lập lịch và thread thực thi.

## 10. Lỗi khi listener bất đồng bộ: ai nhìn thấy?

Với listener đồng bộ, exception có thể được ném trên luồng publisher. Với listener async trả về `void`, lỗi xảy ra trong worker thread thường **không thể ném trực tiếp trở lại nơi đã gọi `publishEvent(...)`** theo cùng cách.

~~~java
@Async("eventExecutor")
@EventListener
public void on(OrderPlaced event) {
    emailClient.send(event.orderId()); // Có thể ném exception.
}
~~~

Nếu `emailClient.send(...)` ném exception sau khi task đã được lên lịch, request đặt hàng có thể đã trả kết quả bình thường. Điều này không có nghĩa email đã gửi thành công.

### 10.1. Cách xử lý exception

- Ghi log có `eventId` và tên listener; không log payload chứa dữ liệu nhạy cảm.
- Với `@Async` trả về `void`, cấu hình `AsyncUncaughtExceptionHandler` nếu muốn xử lý lỗi không được bắt theo một cách có chủ đích.
- Phân biệt **lỗi tạm thời** (timeout, dịch vụ đích quá tải) với **lỗi không thể retry vô hạn** (vi phạm nghiệp vụ, schema không hợp lệ).
- Không nuốt exception rồi coi công việc đã hoàn tất khi hạ tầng publication/retry phụ thuộc vào việc listener báo thất bại.

Ví dụ cấu hình handler cho method async trả về `void`:

~~~java
package com.example.shop.config;

import java.lang.reflect.Method;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class EventAsyncErrorHandling implements AsyncConfigurer {

    private static final Logger log =
            LoggerFactory.getLogger(EventAsyncErrorHandling.class);

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (Throwable error, Method method, Object... parameters) ->
                log.error("Async listener failed: {}", method.getName(), error);
    }
}
~~~

Đây là ví dụ **tùy chọn về quan sát lỗi**; nó không tạo retry tự động. Nếu dự án có nhiều `AsyncConfigurer` hoặc cấu hình executor mặc định khác, phải hợp nhất thành một cấu hình nhất quán. Không nên tự log toàn bộ `parameters` vì có thể chứa thông tin cá nhân.

### 10.2. Lỗi lập lịch khác lỗi xử lý

Nếu `eventExecutor` từ chối task vì quá tải, lỗi có thể xảy ra **ngay khi submit**, trước khi handler bắt đầu. Nếu task đã được nhận nhưng handler thất bại, lỗi xảy ra trong worker thread. Hai loại lỗi này có thời điểm và cách quan sát khác nhau, nên không được xử lý giống hệt nhau.

Một ứng dụng có yêu cầu độ bền cao không nên chỉ dựa vào in-memory executor queue làm nơi giữ công việc quan trọng. `@Async` là cơ chế concurrency, không phải hàng đợi sự kiện bền vững.

## 11. Retry, Event Publication Registry và idempotency

Mục tiêu async thường là tách một phản ứng chậm khỏi đường đi chính. Với tác vụ quan trọng, cần bổ sung câu hỏi: **nếu listener không hoàn thành thì ai nhận ra và chạy lại?**

Spring Modulith cung cấp **Event Publication Registry** để theo dõi các publication tới listener được hỗ trợ khi có persistence và cơ chế tích hợp thích hợp. Registry có thể giúp ghi nhận publication còn dang dở và hỗ trợ chiến lược khôi phục hoặc chạy lại. Đây là lớp trách nhiệm khác với `@Async`.

~~~mermaid
flowchart TD
    O["ordering<br/>Commit đơn hàng"] --> E["OrderPlaced"]
    E --> R["Registry publication<br/>khi được cấu hình"]
    R --> N["Async module listener"]
    N --> Q{"Xử lý thành công?"}
    Q -->|Có| C["Ghi nhận completion"]
    Q -->|Không| F["Publication chưa hoàn tất"]
    F --> T["Recovery / retry theo chính sách"]
    T --> N
~~~

Sơ đồ minh họa một kiến trúc dùng registry, **không mô tả một cấu hình tự động xuất hiện chỉ nhờ `@Async`**. Mức độ giao nhận và thời điểm ghi publication phụ thuộc setup Spring Modulith, transaction và storage cụ thể.

### 11.1. Vì sao retry có thể làm xử lý trùng?

Giả sử listener gửi email thành công, nhưng ứng dụng dừng trước khi trạng thái “đã hoàn tất” được ghi nhận. Khi publication được xử lý lại, email có thể gửi lần nữa.

Do đó, consumer cần cơ chế **idempotency**:

- Dùng cùng `eventId` khi retry **cùng một sự kiện**.
- Với database local, ghi dấu `(consumer, eventId)` và cập nhật dữ liệu trong cùng transaction thích hợp.
- Với dịch vụ ngoài, ưu tiên idempotency key được API đích hỗ trợ; nếu không có, phải thừa nhận cửa sổ lỗi có thể tạo side effect trùng.
- Không đánh đồng `orderId` với `eventId`: một đơn có thể có nhiều sự kiện hợp lệ.

### 11.2. Không phải lỗi nào cũng nên retry

| Loại lỗi | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Tạm thời | Email provider trả lỗi quá tải | Retry có giới hạn, backoff và jitter |
| Quá tải executor | Queue đầy, task bị từ chối | Cảnh báo, backpressure và recovery bền vững nếu cần |
| Contract không hợp lệ | Thiếu trường bắt buộc | Không retry vô hạn; kiểm tra và sửa nguồn dữ liệu |
| Vi phạm quyền | Không được phép gửi tới địa chỉ này | Từ chối, audit và xử lý quy tắc bảo mật |
| Event đã được xử lý | Event ID trùng | Bỏ qua an toàn theo chính sách consumer |

**Không bao giờ** giả định `@Async` hoặc `@ApplicationModuleListener` tự cấp bảo đảm exactly-once. Muốn hệ thống đáng tin cậy phải thiết kế persistence, failure recovery, idempotency và observability có bằng chứng.

## 12. Khả năng mở rộng và sức ép tải

Async cải thiện thời gian phản hồi của publisher nhưng không làm tác vụ biến mất: thời gian CPU/I/O của listener vẫn phải được chi trả ở worker thread. Khi tốc độ event đến lớn hơn tốc độ xử lý lâu dài, queue sẽ tăng, độ trễ tích lũy và cuối cùng có thể bị từ chối task.

Ví dụ giả định:

| Tham số | Giá trị minh họa |
| --- | --- |
| Số event đến trung bình | 100 event/giây |
| Thời gian xử lý trung bình một event | 200 ms |
| Số worker thread | 8 |
| Thông lượng tối đa lý tưởng khi mỗi worker chạy tuần tự | Khoảng 40 event/giây |

Với giả định không có bottleneck hoặc batch khác, thông lượng xử lý chỉ khoảng `8 / 0,2 = 40` event/giây, thấp hơn 100 event/giây đầu vào. Queue sẽ tiếp tục tăng; `@Async` không cứu được hệ thống khỏi quá tải nếu không có cơ chế giới hạn hoặc mở rộng thông lượng.

Con số trên chỉ dùng để **minh họa tư duy capacity planning**. Thực tế còn phụ thuộc thời gian chờ I/O, thread scheduling, giới hạn kết nối database, email provider và sự biến thiên của workload.

### Giám sát executor

Các chỉ số nên có:

1. Số worker đang hoạt động và kích thước pool.
2. Queue depth, thời gian chờ trước khi bắt đầu task và số task bị từ chối.
3. Thời gian xử lý theo loại event/listener.
4. Tỷ lệ thành công/thất bại; số lần retry và publication đang tồn đọng.
5. Thời gian từ `occurredAt`/commit đến completion của từng consumer.

Không nên dùng mỗi “HTTP trả lời nhanh hơn” làm thước đo thành công. Nếu báo cáo nhanh nhưng hàng nghìn email bị tồn đọng hoặc thất bại không ai biết, thiết kế không đạt mục tiêu nghiệp vụ.

## 13. Thứ tự, cạnh tranh và tính nhất quán

Khi nhiều worker có thể xử lý cùng lúc, `OrderPlaced` và `OrderCancelled` của cùng đơn có thể được nhận hoặc hoàn thành **khác thứ tự**. Ví dụ:

~~~text
T0: publish OrderPlaced(orderId=O1)
T1: publish OrderCancelled(orderId=O1)
T2: worker B hoàn tất OrderCancelled
T3: worker A mới hoàn tất OrderPlaced
~~~

Nếu consumer chỉ cập nhật trạng thái theo “event nào xử lý cuối” mà không xét thứ tự nghiệp vụ, nó có thể quay đơn đã hủy về trạng thái đã đặt.

Các cách xử lý:

- Thiết kế trạng thái/chuyển trạng thái hợp lệ ở consumer.
- Dùng version của aggregate, sequence number hoặc thời điểm có ngữ nghĩa rõ nếu cần kiểm soát thứ tự.
- Bố trí phân vùng/serial execution theo aggregate khi công nghệ cho phép.
- Không đưa các bất biến bắt buộc có thứ tự vào nhiều listener async độc lập mà không có cơ chế điều phối.

**Một executor nhiều thread không bảo đảm thứ tự xử lý/hoàn tất**, và thứ tự publish cũng không mặc định tạo bảo đảm thứ tự cho các side effect sau commit. Đây là quyết định kiến trúc cần làm rõ trước khi mở rộng concurrency.

## 14. Kiểm thử `@Async` cho event

Nên chia test theo **mục tiêu cần chứng minh**, tránh dùng một test đơn lẻ để kết luận tất cả hoạt động.

| Mục tiêu | Cách kiểm tra | Giới hạn |
| --- | --- | --- |
| Publisher phát đúng event | `@ApplicationModuleTest` và `PublishedEvents` | Không chứng minh listener đã xong |
| Listener chuyển công việc đúng | Unit test gọi trực tiếp `on(event)` với mock service | Không kiểm tra Spring async proxy |
| Method thật sự chạy qua executor | Integration test với Spring context và quan sát thread/task | Không chứng minh giao nhận bền vững |
| Side effect chỉ sau commit | Test transaction commit và rollback tách biệt | Cần bảo đảm transaction thực sự commit |
| Lỗi được nhận biết | Mô phỏng exception và kiểm tra log/handler/registry | Cần test với hạ tầng được cấu hình |
| Retry không làm trùng side effect | Xử lý lại cùng `eventId` và kiểm tra state | Không đủ nếu side effect bên ngoài chưa có cơ chế idempotency |
| Hệ thống chịu được quá tải | Load test executor/queue, quan sát rejected task | Phụ thuộc cấu hình và tài nguyên thực tế |

### 14.1. Test phát sự kiện bằng `PublishedEvents`

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderingEventTest {

    @Autowired
    OrderFacade orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID orderId = orders.placeOrder(validRequest());

        assertThat(events.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(orderId);
    }

    private PlaceOrderRequest validRequest() {
        // Bổ sung fixture đúng với nghiệp vụ và dữ liệu kiểm thử.
        throw new UnsupportedOperationException("Implement project fixture");
    }
}
~~~

`OrderFacade`, `PlaceOrderRequest` và `validRequest()` là thành phần minh họa cần cài đặt trong dự án thực. Test trên chứng minh việc **publish**, không chứng minh email đã gửi hoặc listener chạy trên executor.

### 14.2. Integration test cho side effect async

Một cách kiểm thử bất đồng bộ là gọi nghiệp vụ qua Spring-managed bean, rồi dùng công cụ chờ **điều kiện kết quả** có thời hạn, thay vì `Thread.sleep(...)` với thời gian cố định.

~~~java
// Pseudocode sử dụng thư viện Awaitility và mock/stub phù hợp.
UUID orderId = orderFacade.placeOrder(validOrderRequest());

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        verify(confirmationSender).send(orderId)
    );
~~~

Đây là ví dụ **ý tưởng test**, cần dependency Awaitility, fixture và cách mock/spy đúng với ngữ cảnh Spring test của ứng dụng. Nếu phương thức gửi còn nhận event ID, assertion phải kiểm tra cả event ID phù hợp.

Để test transaction `AFTER_COMMIT`, chú ý:

- Test được gắn `@Transactional` có thể **rollback vào cuối test**, khiến listener sau commit không chạy.
- Cần dùng service transaction thật, `TransactionTemplate` hoặc cơ chế test transaction phù hợp để tạo **commit** khi kiểm tra after-commit.
- Để kiểm tra rollback, cố ý tạo lỗi làm transaction nguồn rollback và xác nhận side effect không xảy ra.
- Với async listener, đợi kết quả/bằng chứng theo cách có timeout; không giả định listener hoàn tất ngay khi `placeOrder()` trả về.

### 14.3. Kiểm tra module boundary

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này bảo vệ hướng phụ thuộc giữa `ordering` và `notification`. Nó không chứng minh executor có đủ thread, transaction commit trước khi handler chạy hay event registry được cấu hình đúng.

## 15. Khi nào nên dùng `@Async`?

**Nên cân nhắc** với các phản ứng có thể xử lý muộn và không quyết định trực tiếp kết quả nghiệp vụ đang trả về:

| Tình huống | Có thể dùng async? | Điều kiện cần |
| --- | --- | --- |
| Gửi email sau khi đơn commit | Có | Listener sau commit, idempotency và cơ chế phát hiện lỗi |
| Cập nhật thống kê không cần realtime tuyệt đối | Có | Chấp nhận độ trễ, xử lý trùng/thứ tự |
| Phát integration message cho bên thứ ba | Có, nhưng chưa đủ | Adapter, hạ tầng broker, publication persistence/retry khi cần |
| Kiểm tra hạn mức bắt buộc trước khi chấp nhận đơn | Thường không nên fire-and-forget | Phải biết kết quả trước khi quyết định |
| Giữ hàng bắt buộc trước khi xác nhận bán | Không thể chỉ dùng listener async không điều phối | Thiết kế workflow/state machine hoặc lời gọi đồng bộ |
| Ghi dữ liệu có quan hệ nhất quán chặt với transaction nguồn | Cân nhắc kỹ | Cần transaction boundary và bất biến được chứng minh |

Một quy tắc thực dụng: **nếu nghiệp vụ chính không thể được coi là thành công khi tác vụ phụ chưa hoàn tất**, đừng chỉ chuyển tác vụ đó sang `@Async` rồi trả thành công. Cần hợp đồng, trạng thái hoặc cơ chế điều phối phù hợp với điều kiện nghiệp vụ.

## 16. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `@Async` mặc nhiên chạy sau commit | Consumer có thể đọc dữ liệu chưa commit hoặc phản ứng với transaction rollback | Dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc `@ApplicationModuleListener` phù hợp |
| Không bật hạ tầng async | Handler có thể không chạy bất đồng bộ như kỳ vọng | Cấu hình `@EnableAsync`/executor và test runtime |
| Dùng chung một executor cho mọi tác vụ chậm | Tác vụ email chiếm tài nguyên của luồng khác | Cô lập pool và đặt giới hạn rõ |
| Không theo dõi rejected task | Công việc bị bỏ sót khi quá tải | Giám sát queue/rejection và xây dựng recovery |
| Truyền JPA entity hoặc request object vào event | Lazy loading lỗi, dữ liệu thay đổi hoặc context đã đóng | Dùng immutable event contract và dữ liệu cần thiết |
| Chờ transaction của publisher trong worker thread | Worker không tự kế thừa transaction nguồn | Dùng transaction mới trong service consumer |
| Nuốt exception của listener | Registry/giám sát có thể coi sai trạng thái thành công | Báo lỗi rõ và theo dõi thất bại |
| Nghĩ async là message queue bền vững | Mất công việc nếu process crash | Dùng publication persistence/outbox/broker phù hợp |
| Giả định một event chỉ được xử lý một lần | Retry có thể gửi email/cộng chỉ số trùng | Stable event ID và idempotency |
| Giả định thứ tự event được giữ bởi thread pool | Trạng thái bị cập nhật ngược | Version/state machine/ordering strategy |
| Dùng `Thread.sleep` để “đợi commit” | Lỗi race vẫn có thể xảy ra | Kích hoạt theo transaction phase |
| Test chỉ dùng `PublishedEvents` | Không phát hiện listener không chạy hoặc async lỗi | Bổ sung integration test/metrics |

## 17. Bài thực hành: chuyển từ listener đồng bộ sang async an toàn

**Bối cảnh:** ứng dụng có `ordering`, `notification` và `analytics`. Khi đặt hàng thành công, module `ordering` phát `OrderPlaced`; hai module còn lại phản ứng sau commit.

### Phần A — Khảo sát hành vi ban đầu

1. Viết một listener `@EventListener` đồng bộ gửi email giả lập chậm.
2. Ghi lại thời gian `placeOrder()` trả kết quả khi email chậm hoặc ném exception.
3. Xác định email chạy trên thread nào và transaction đặt hàng có thể đang ở trạng thái nào.
4. Giải thích vì sao tăng độ trễ email lại ảnh hưởng thời gian HTTP trong cấu hình đồng bộ.

### Phần B — Chuyển sang `@Async`

1. Bật `@EnableAsync`, định nghĩa `eventExecutor` với pool/queue hữu hạn.
2. Gắn `@Async("eventExecutor")` vào `@EventListener` của module `notification`.
3. Quan sát thread name và thời điểm listener bắt đầu so với transaction commit.
4. Tạo một giao dịch cố tình rollback sau khi publish. Ghi lại nguy cơ nếu async listener đã gửi xác nhận.

### Phần C — Sửa điều kiện sau commit

1. Thay listener bằng `@Async @TransactionalEventListener(AFTER_COMMIT)` **hoặc** `@ApplicationModuleListener`; không đăng ký hai listener cùng gửi một email.
2. Bảo đảm consumer ghi trạng thái bằng transaction riêng thích hợp.
3. Lặp lại kịch bản rollback và xác minh email không được gửi.
4. Cho email sender ném lỗi sau commit; ghi nhận lỗi, không coi việc đặt hàng đã commit là có thể rollback ngược.

### Phần D — Đánh giá độ tin cậy

1. Cấu hình Event Publication Registry và storage cần thiết theo phiên bản Spring Modulith của dự án nếu tác vụ cần khả năng khôi phục.
2. Mô phỏng listener lỗi; kiểm tra trạng thái publication và chính sách xử lý lại.
3. Phát lại cùng `eventId` để kiểm chứng idempotency.
4. Tăng tốc độ publish đến gần hoặc vượt năng lực xử lý, theo dõi queue depth và rejected task.
5. Kiểm tra `ApplicationModules.verify()` để bảo đảm `notification` chỉ phụ thuộc API sự kiện đã được công bố của `ordering`.

### Checklist nghiệm thu

| Yêu cầu | Bằng chứng |
| --- | --- |
| Async thật sự dùng executor đã cấu hình | Thread/metric của `eventExecutor` hoặc integration test |
| Publisher không phụ thuộc implementation consumer | Test ranh giới module PASS |
| Listener không gửi email khi đơn rollback | Test transaction rollback PASS |
| Sau commit listener ghi dữ liệu trong transaction hợp lệ | Kiểm tra trạng thái database sau xử lý |
| Lỗi listener được quan sát | Log/metric/publication trạng thái phù hợp |
| Có thể xử lý lại an toàn | Cùng `eventId` không tạo side effect trùng |
| Hệ thống có chính sách khi queue đầy | Thử tải và quan sát rejection/backpressure |

## 18. Câu hỏi tự kiểm tra

**Câu 1. Chỉ thêm `@Async` vào một `@EventListener` đã đủ để bảo đảm email chạy sau khi đơn commit chưa?**

Chưa. `@Async` chỉ thay đổi luồng và cách lập lịch; listener vẫn có thể bắt đầu trước commit. Muốn phản ứng sau commit cần `@TransactionalEventListener(AFTER_COMMIT)` hoặc cơ chế tương đương.

**Câu 2. Vì sao async listener thường không dùng chung transaction với publisher?**

Vì transaction context của Spring thường được gắn với thread hiện tại. Worker thread không tự kế thừa transaction nguồn; nếu cần cập nhật database, consumer nên dùng transaction mới thích hợp.

**Câu 3. `@ApplicationModuleListener` khác `@Async @EventListener` ở điểm nào quan trọng?**

`@ApplicationModuleListener` biểu đạt một listener module gắn với pha sau commit và transaction mới, đồng thời thực thi bất đồng bộ theo cấu hình. `@Async @EventListener` thông thường không có bảo đảm đợi commit.

**Câu 4. Nếu handler `void` được gắn `@Async` ném exception thì caller `publishEvent(...)` có nhận trực tiếp exception đó không?**

Không theo cơ chế lan truyền đồng bộ thông thường nếu exception xảy ra trong worker. Cần quan sát exception handler, log, trạng thái publication và cơ chế recovery. Lỗi khi **lên lịch** task là trường hợp riêng có thể xuất hiện ngay khi publish.

**Câu 5. Pool có tám worker, mỗi event mất khoảng 200 ms; 100 event/giây có xử lý kịp không?**

Trong phép tính lý tưởng đơn giản, thông lượng khoảng 40 event/giây. Nếu đầu vào duy trì 100 event/giây, backlog sẽ tăng. Phải đo thực tế và điều chỉnh capacity/backpressure, không chỉ tăng queue vô hạn.

**Câu 6. Có Event Publication Registry thì consumer có còn phải idempotent không?**

Có. Publication có thể được chạy lại sau một cửa sổ lỗi mà side effect đã diễn ra nhưng completion chưa ghi nhận. Idempotency giúp ngăn lặp kết quả nghiệp vụ.

**Câu 7. Thêm `@Async` có làm `OrderPlaced` tự động thành message trên Kafka hay RabbitMQ không?**

Không. Spring application event và `@Async` có thể hoạt động hoàn toàn trong cùng JVM. Externalization và broker là trách nhiệm khác.

## 19. Kết luận

**`@Async` cho event là công cụ tách thời gian và tài nguyên xử lý listener khỏi luồng phát sự kiện**, không phải một cơ chế tự động bảo đảm transaction, durability hay delivery exactly-once. Khi publisher cần trả lời nhanh còn consumer có thể xử lý muộn, async có thể giảm độ trễ và hỗ trợ phân tách trách nhiệm giữa các module Spring Modulith.

Để áp dụng an toàn, hãy xác định rõ **sự kiện được phát ở thời điểm nào**, **listener có phải đợi commit không**, **executor có bao nhiêu tài nguyên**, **lỗi và task bị từ chối được phát hiện thế nào**, và **retry có gây trùng hay không**. Với các phản ứng liên module sau commit, `@TransactionalEventListener` kết hợp `@Async` hoặc `@ApplicationModuleListener` là những hướng triển khai phù hợp khi đã cấu hình và kiểm thử đúng.

Trong hệ thống cần giao sự kiện đáng tin cậy, tiếp tục bổ sung **Event Publication Registry/persistence**, recovery, idempotency và observability theo yêu cầu. Cách tiếp cận này vừa bảo vệ ranh giới nghiệp vụ, vừa tránh đánh đổi tính nhất quán và khả năng phục hồi chỉ để có thời gian phản hồi nhanh hơn.
