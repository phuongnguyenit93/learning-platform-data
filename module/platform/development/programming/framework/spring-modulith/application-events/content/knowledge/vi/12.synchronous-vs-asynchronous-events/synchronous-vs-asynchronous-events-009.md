# Đánh đổi độ trễ

## 1. Độ trễ của ai được tối ưu?

Khi tổ chức giao tiếp giữa các module bằng **Spring Modulith application events**, một trong những quyết định quan trọng nhất là xử lý **đồng bộ (synchronous)** hay **bất đồng bộ (asynchronous)**. Lựa chọn này không chỉ ảnh hưởng đến thời gian phản hồi của một HTTP request; nó còn tác động đến thời gian hoàn tất quy trình nghiệp vụ, tính nhất quán dữ liệu, mức sử dụng tài nguyên và khả năng phục hồi khi lỗi.

Hãy xét hệ thống đặt hàng gồm bốn module:

- `orders` ghi nhận việc xác nhận đơn.
- `notifications` gửi email xác nhận cho khách.
- `reporting` cập nhật projection phục vụ báo cáo.
- `loyalty` cộng điểm thưởng.

Khi đơn được xác nhận, `orders` phát `OrderConfirmed`. Nếu xử lý ba tác vụ phụ bằng listener đồng bộ, API xác nhận đơn có thể phải chờ chúng. Nếu dùng listener bất đồng bộ sau commit, API có thể trả kết quả sớm hơn, nhưng **email, báo cáo và điểm thưởng chưa chắc đã hoàn tất khi khách nhận phản hồi**.

~~~mermaid
flowchart TB
    subgraph SYNC["Phản ứng đồng bộ"]
        R1["Request"] --> O1["Xác nhận đơn"]
        O1 --> E1["Gửi email"]
        E1 --> A1["Cập nhật báo cáo"]
        A1 --> X1["Response"]
    end
    subgraph ASYNC["Phản ứng bất đồng bộ sau commit"]
        R2["Request"] --> O2["Xác nhận đơn + publish"]
        O2 --> C2["Commit và response"]
        C2 -.-> Q2["Publication / executor"]
        Q2 --> E2["Gửi email"]
        Q2 --> A2["Cập nhật báo cáo"]
    end
~~~

Để phân tích đúng, cần đo **hai loại độ trễ khác nhau**:

1. **Độ trễ phản hồi (response latency):** thời gian từ lúc ứng dụng nhận yêu cầu đến lúc trả câu trả lời. Người dùng cảm nhận loại này trực tiếp.
2. **Độ trễ hoàn tất tác động (event-to-effect latency):** thời gian từ khi sự kiện nghiệp vụ được commit đến khi một listener hoàn tất tác động của nó, ví dụ email được gửi hoặc read model đã cập nhật.

**Chuyển sang async thường có thể giảm response latency nhưng không tự làm giảm event-to-effect latency.** Tổng lượng công việc vẫn cần được thực hiện, đôi khi còn tăng vì thêm hàng đợi, transaction riêng, ghi registry và cơ chế retry.

Mục tiêu của bài học thuộc chương **Đồng bộ và bất đồng bộ** là biết đánh đổi hai loại độ trễ này trong phạm vi `SPRING_MODULITH_APPLICATION_EVENTS` mà vẫn giữ ranh giới module, transaction sau commit và khả năng giao sự kiện đáng tin cậy.

## 2. Phân rã thời gian trên critical path

**Critical path** là chuỗi công việc mà yêu cầu phải chờ trước khi được coi là hoàn tất theo hợp đồng của API. Với xử lý tuần tự đồng bộ:

\[
T_{\mathrm{response}} \approx T_{\mathrm{validate}} + T_{\mathrm{write}} + T_{\mathrm{syncListeners}} + T_{\mathrm{commit}} + T_{\mathrm{framework}}
\]

Nếu các listener đồng bộ được chạy tuần tự, `T_syncListeners` có thể gần bằng tổng thời gian của từng listener. Nếu ứng dụng cấu hình multicaster khác hoặc các công việc thực sự chạy song song, critical path cần xét phần **lâu nhất mà publisher bắt buộc phải chờ**, không đơn giản cộng tất cả.

Với listener bất đồng bộ sau commit:

\[
T_{\mathrm{response}} \approx T_{\mathrm{validate}} + T_{\mathrm{write}} + T_{\mathrm{publication}} + T_{\mathrm{commit}} + T_{\mathrm{dispatchOverhead}}
\]

\[
T_{\mathrm{effect}} \approx T_{\mathrm{commit}} + T_{\mathrm{queueWait}} + T_{\mathrm{listenerWork}} + T_{\mathrm{retryDelay}}
\]

Các biểu thức chỉ giúp suy nghĩ về **những thành phần thời gian**. Chúng không phải công thức đo tuyệt đối cho mọi cấu hình Spring; callback sau commit, đăng ký publication, mức tải và cách cấp thread có thể làm các thành phần chồng lấn.

Ví dụ **số liệu giả định**, không phải benchmark Spring Modulith:

| Thành phần | Thời gian giả định |
| --- | ---: |
| Xác thực và ghi trạng thái đơn | 45 ms |
| Gửi email qua dịch vụ ngoài | 400 ms |
| Cập nhật bảng báo cáo | 120 ms |
| Phần việc còn lại, gồm commit/overhead | 25 ms |

Nếu mọi thứ nằm trên đường xử lý đồng bộ tuần tự, response latency xấp xỉ **590 ms**. Nếu email và báo cáo được chuyển sang các listener bất đồng bộ, response latency có thể giảm đáng kể, nhưng vẫn chịu chi phí ghi publication và commit; không thể kết luận chắc chắn còn đúng **70 ms** khi chưa đo. Thời gian email hoàn tất có thể **lâu hơn 400 ms** nếu phải chờ hàng đợi.

**Nguyên tắc:** luôn hỏi “bước nào thực sự phải hoàn thành trước response?” rồi mới chuyển nó ra khỏi critical path.

## 3. Listener đồng bộ: đơn giản nhưng có thể kéo dài request

Spring Framework cung cấp `ApplicationEventPublisher` và `@EventListener`. Với multicaster mặc định, listener thông thường chạy **đồng bộ trong thread gọi `publishEvent(...)`**.

~~~java
// Module notifications: minh họa listener đồng bộ.
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class SynchronousConfirmationListener {
    private final MailGateway mailGateway;

    SynchronousConfirmationListener(MailGateway mailGateway) {
        this.mailGateway = mailGateway;
    }

    @EventListener
    void on(OrderConfirmed event) {
        mailGateway.sendOrderConfirmation(event.orderId());
    }
}
~~~

Nếu gateway email mất 1 giây, thao tác publish có thể bị giữ lại tương ứng. Nghiêm trọng hơn, nếu publisher đang trong transaction và listener gọi API bên ngoài **trước khi commit**, email có thể gửi thành công rồi transaction đơn hàng rollback. Hệ thống tạo ra một hiệu ứng bên ngoài mà database không thể hoàn tác.

Điểm mạnh của đồng bộ không nên bị bỏ qua:

- Bên gọi có thể nhận exception ngay; hữu ích khi công việc thực sự thuộc **điều kiện chấp nhận yêu cầu**.
- Dễ lần theo lời gọi và debug một luồng xử lý nhỏ.
- Không cần bổ sung hàng đợi nội bộ chỉ để thực hiện một phép kiểm tra nhanh.

Tuy nhiên, `@EventListener` không phải lựa chọn tốt chỉ vì “viết ít code” khi listener làm HTTP call chậm, gửi email, tính toán nặng hoặc tác vụ mà nghiệp vụ **không yêu cầu hoàn tất trước phản hồi**.

Một lưu ý: `@EventListener` có thể được xử lý khác nếu bạn tùy biến `ApplicationEventMulticaster` hoặc gắn thêm cơ chế async. Luôn xác định cấu hình thực tế thay vì giả định mọi listener đều đồng bộ ở mọi ứng dụng.

## 4. Sau commit không đồng nghĩa bất đồng bộ

Một nhầm lẫn phổ biến là nghĩ rằng dùng `@TransactionalEventListener` thì HTTP response chắc chắn không phải chờ listener.

~~~java
import com.example.shop.orders.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AfterCommitAuditListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        // Chạy sau commit thành công, nhưng không tự động async.
    }
}
~~~

`@TransactionalEventListener` mặc định gắn với pha `AFTER_COMMIT`. Trong cách thực thi thông thường, callback pha này có thể vẫn chạy **đồng bộ trên luồng đang hoàn thành transaction**, trước khi lời gọi service/transaction interceptor trở về. Vì vậy một listener chậm **vẫn có thể làm phản hồi chậm**, dù dữ liệu nguồn đã được commit.

Cần phân biệt hai trục quyết định:

| Trục | Câu hỏi | Các ví dụ |
| --- | --- | --- |
| **Transaction phase** | Listener chạy trước hay sau khi nguồn commit? | `@EventListener`, `@TransactionalEventListener(AFTER_COMMIT)` |
| **Execution mode** | Publisher có phải chờ listener không? | Đồng bộ hay thực thi bằng executor bất đồng bộ |

**Sau commit** phục vụ tính đúng đắn: không xử lý một sự thật chưa được commit. **Bất đồng bộ** phục vụ việc tách thời gian chờ: publisher không phải đợi toàn bộ công việc listener. Hai đặc tính bổ sung cho nhau, không thay thế nhau.

Ngoài ra, xử lý sau commit không tự động có transaction ghi mới. Nếu callback sau commit cần ghi dữ liệu, phải hiểu ngữ cảnh transaction; với Spring Modulith, `@ApplicationModuleListener` cung cấp tổ hợp phù hợp cho xử lý module độc lập.

## 5. `@ApplicationModuleListener` và trade-off độ trễ

Spring Modulith cung cấp `@ApplicationModuleListener` cho giao tiếp giữa các module. Annotation này kết hợp listener **sau commit**, **bất đồng bộ** và **transaction mới** theo `REQUIRES_NEW`.

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
        notifications.sendConfirmationOnce(
                event.eventId(), event.orderId());
    }
}
~~~

`NotificationService.sendConfirmationOnce(...)` là một API minh họa, **không có nghĩa annotation tự bảo đảm exactly-once**. Module nhận phải thực thi trạng thái và idempotency đúng theo nghiệp vụ. Cũng cần bật/cấu hình hỗ trợ async, executor và transaction manager phù hợp với ứng dụng.

Tác động tới độ trễ:

- Sau khi nguồn commit, listener có thể được lên lịch ở thread khác; API thường không phải chờ hoàn tất gửi email.
- Người dùng có thể nhận phản hồi **đã xác nhận đơn** trước khi email đến. Đây là hành vi hợp lệ nếu hợp đồng API mô tả đúng.
- Listener có thể phải chờ executor, khóa database hoặc dịch vụ email; tốc độ phản hồi nhanh hơn **không chứng minh tác vụ phụ hoàn tất nhanh hơn**.
- Nếu listener thất bại, transaction xác nhận đơn đã commit không thể bị rollback. Hệ thống cần ghi nhận lỗi và đường khôi phục thay vì giả định “thao tác thành công hoàn toàn”.

Khi có nhiều listener cho cùng một event, mỗi consumer có độ trễ và trạng thái completion riêng. Không có cam kết rằng `notifications` xử lý trước `reporting` hoặc `loyalty` chỉ vì tên lớp hay thứ tự khai báo.

## 6. Ví dụ end-to-end: xác nhận đơn và gửi email sau commit

### 6.1. Hợp đồng event công khai

`orders` định nghĩa một record bất biến trong package công khai:

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

`eventId` nhận diện sự kiện logic để truy vết xử lý; `correlationId` liên kết chuỗi nghiệp vụ nếu có nhiều event. `orderId` là business key. Không truyền `OrderEntity` hay `OrderRepository` nội bộ sang module khác.

### 6.2. Publisher cập nhật nguồn rồi publish trong transaction

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
            return; // Không phát lại event nếu trạng thái không đổi.
        }

        order.confirm(); // Bất biến nghiệp vụ thuộc orders.
        publisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(), correlationId, orderId,
                Instant.now(clock)));
    }
}
~~~

`OrderEntity`, `OrderRepository` và `Clock` là những thành phần giả định đã cấu hình. `order.confirm()` phải xác minh được chuyển trạng thái hợp lệ. Hệ thống có concurrent request cần optimistic locking/unique constraint hoặc cơ chế đồng bộ dữ liệu thích hợp; chỉ kiểm tra `isConfirmed()` chưa chống được mọi race condition.

Vì event được publish **trong transaction nguồn**, một listener `AFTER_COMMIT` không được thực thi như thể đơn đã xác nhận khi transaction rollback. `publishEvent(...)` vẫn chỉ là lời gọi publish, không có nghĩa commit đã xảy ra tại thời điểm đó.

### 6.3. Một luồng request, hai đồng hồ độ trễ

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as orders
    participant DB as Database
    participant R as Publication Registry
    participant N as notifications
    U->>O: POST /orders/{id}/confirm
    O->>DB: Đổi trạng thái (transaction A)
    O->>R: Đăng ký publication (transaction A)
    O->>DB: COMMIT A
    O-->>U: Xác nhận đơn đã commit
    Note over U,O: Kết thúc response latency
    R-->>N: Giao event sau commit
    N->>N: Chờ executor / gửi email
    N->>DB: Ghi trạng thái xử lý (transaction B)
    N-->>R: Completion
    Note over R,N: Kết thúc event-to-effect latency
~~~

Sơ đồ là diễn giải **logic**, không cam kết thứ tự tuyệt đối giữa callback async và thời điểm ghi response trên mạng. Trên thực tế listener có thể bắt đầu trước khi client nhận byte phản hồi. Các bước registry bền vững chỉ có khi implementation và transaction được cấu hình phù hợp.

Nếu client cần biết chính xác email đã gửi, API xác nhận đơn nên **trả trạng thái chính xác** (ví dụ “đơn được xác nhận; thông báo đang xử lý”) và cung cấp nơi tra trạng thái gửi, thay vì trả một kết quả khiến khách hiểu mọi tác vụ đã hoàn tất.

## 7. Độ trễ trung bình không nói hết: p95 và p99

Latency của listener có thể có **đuôi dài** (*tail latency*): đa số email gửi nhanh, nhưng một số ít request gặp DNS chậm, database lock hoặc timeout. Nếu listener nằm trên critical path của HTTP request, các đuôi dài này trực tiếp làm xấu **p95/p99 response latency**.

Các khái niệm:

- **p50**: 50% quan sát có thời gian không vượt mức này (median).
- **p95**: 95% quan sát không vượt mức này; 5% chậm hơn.
- **p99**: 99% quan sát không vượt mức này; 1% chậm hơn.

**Số liệu minh họa hoàn toàn giả định**:

| Chỉ số | Listener email đồng bộ trên request | Listener email bất đồng bộ |
| --- | ---: | ---: |
| HTTP response p50 | 220 ms | 65 ms |
| HTTP response p95 | 900 ms | 130 ms |
| HTTP response p99 | 2.300 ms | 250 ms |
| Email hoàn tất p95 từ lúc commit | Gắn với đường xử lý đồng bộ | 1.700 ms (gồm chờ hàng đợi) |

Bảng không thể dùng làm kết quả benchmark; nó minh họa việc **cải thiện p99 HTTP** và **xấu đi thời gian email hoàn tất** có thể cùng xảy ra. Nếu báo cáo chỉ hiển thị p95 HTTP mà không đo p95 event-to-effect, hệ thống có thể trông nhanh hơn trong khi khách phải đợi email lâu hơn.

Không suy ra p99 tổng bằng cách cộng thẳng p99 của mọi thành phần: percentile của tổng các biến không nhất thiết bằng tổng percentile, đặc biệt khi các thành phần tương quan. Hãy đo **chuỗi xử lý đầu cuối thực tế**.

## 8. Hàng đợi và executor: latency có thể bị chuyển chỗ

Async cần nơi thực thi công việc, chẳng hạn một Spring `TaskExecutor`. Khi lượng event đến vượt khả năng xử lý, thời gian chờ hàng đợi tăng. **Async không tạo thêm năng lực xử lý miễn phí**.

Giả sử trong một cửa sổ tải ổn định:

- 40 event/giây cần gửi thông báo.
- Executor có bốn worker, mỗi worker xử lý trung bình tám event/giây.
- Năng lực xử lý xấp xỉ 32 event/giây, thấp hơn tốc độ đến.

Nếu trạng thái này kéo dài, backlog có xu hướng tăng khoảng **8 event/giây** (ví dụ đơn giản, chưa tính retry và biến động), khiến event-to-effect latency tiếp tục xấu đi. Tăng queue capacity chỉ trì hoãn thời điểm hết chỗ, **không sửa được mất cân bằng throughput**.

Theo **Little's Law** trong hệ ổn định:

\[
L = \lambda W
\]

Trong đó `L` là số công việc trung bình đang trong hệ, `λ` là tốc độ hoàn thành/đến ở trạng thái ổn định và `W` là thời gian lưu lại trung bình. Công thức này giúp thấy mối liên hệ giữa backlog và latency, **không áp dụng như trạng thái ổn định** khi queue vẫn đang tăng vô hạn.

### Ví dụ cấu hình executor có giới hạn

~~~java
package com.example.shop.config;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutionConfig {

    // Ví dụ minh họa: tên bean "taskExecutor" cho @Async mặc định.
    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("module-events-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}
~~~

Các giá trị 4/8/200 **chỉ phục vụ học tập**, không phải khuyến nghị mặc định cho production. `AbortPolicy` làm việc vượt công suất bị từ chối thay vì giữ queue vô hạn. Với listener sau commit, lỗi từ chối thực thi có thể xảy ra **sau khi transaction nguồn đã commit**. Cần cấu hình Event Publication Registry bền vững và đường phục hồi phù hợp, không được kỳ vọng rollback đơn đã được commit.

Trước khi tăng số thread, đo bottleneck thật:

- **CPU-bound:** nhiều thread hơn có thể tăng context switching mà không tăng throughput.
- **I/O-bound:** số thread phù hợp có thể tăng đồng thời, nhưng bị giới hạn bởi connection pool, rate limit và dịch vụ phía ngoài.
- **Database-bound:** executor quá lớn có thể gây tranh chấp lock, tăng số kết nối và kéo dài cả transaction của module nguồn.

Nên cấu hình queue có giới hạn, giới hạn concurrency, timeout và cơ chế backpressure. Khi cần xử lý tải lớn hoặc liên tiến trình, một message broker bên ngoài có thể phù hợp hơn executor trong một JVM; nhưng broker cũng phải được cấu hình capacity, consumer concurrency và chiến lược retry.

## 9. Backpressure: làm gì khi consumer chậm?

Khi publisher tạo event nhanh hơn listener xử lý, hệ thống cần chính sách **backpressure** thay vì chỉ bổ sung thread hoặc heap.

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Queue dài, active threads luôn đạt max | Consumer không theo kịp | Đo bottleneck, tăng năng lực phù hợp hoặc giới hạn tốc độ phát |
| p99 HTTP vẫn tốt nhưng email chậm nhiều phút | Work được dời khỏi critical path nhưng backlog lớn | Đặt SLO delivery riêng, cảnh báo publication age |
| Nhiều timeout từ email API | Dịch vụ ngoài quá tải hoặc rate limit | Timeout, retry có backoff/jitter, giới hạn concurrency |
| Pool kết nối DB cạn | Listener giữ nhiều transaction đồng thời | Giảm concurrency hoặc tối ưu giao dịch/SQL |
| Executor từ chối task | Queue và worker đều đầy | Đường lưu bền/recovery; theo dõi rejection; không mất event âm thầm |
| Registry backlog tăng sau deploy | Listener lỗi hoặc schema không tương thích | Phân loại lỗi, sửa code/config, resubmit có kiểm soát |

Không phải tác vụ nào cũng có thể trì hoãn vô hạn. Với thông báo “đơn đã xác nhận”, gửi sau vài giây có thể chấp nhận. Với cảnh báo gian lận hoặc xử lý vận đơn theo deadline, độ trễ hoàn tất có thể là yêu cầu nghiêm ngặt; khi đó cần đặt giới hạn thời gian và cơ chế ưu tiên thích hợp.

**Đừng chuyển một công việc bắt buộc thành async chỉ để API trông nhanh.** Nếu request trả “thanh toán thành công” trong khi việc thu tiền mới chỉ được enqueue, phản hồi đã sai về mặt nghiệp vụ. Cần dùng trạng thái như `PAYMENT_PENDING` hoặc kết quả đồng bộ được xác minh, tùy mô hình.

## 10. Event Publication Registry: độ tin cậy phải đi kèm hiệu năng

Nếu chỉ sử dụng application events trong bộ nhớ, JVM có thể dừng **sau khi đơn hàng commit nhưng trước khi listener async xử lý**. Khi đó latency không còn là vài giây mà có thể trở thành tác vụ bị mất hẳn.

Spring Modulith cung cấp **Event Publication Registry** để theo dõi các publication dành cho transactional listeners. Khi dùng backend bền vững được cấu hình với transaction thích hợp (ví dụ JDBC/JPA), registry có thể lưu bản ghi publication gắn với transaction nguồn và theo dõi trạng thái hoàn tất của từng listener.

~~~mermaid
flowchart TB
    P["Publish OrderConfirmed"]
    P --> T["Transaction nguồn"]
    T -->|"commit"| D[("Durable publication registry")]
    D --> L["Listener async"]
    L -->|"success"| C["Ghi completion"]
    L -->|"fail"| F["Publication chưa hoàn tất"]
    F --> R["Recovery/resubmit có kiểm soát"]
    R --> L
~~~

Mô hình trên lược bỏ các callback và việc ghi registry trong transaction. **Không phải mọi cấu hình dùng `@ApplicationModuleListener` đều tự có registry bền vững**; cần chọn starter/implementation, schema, transaction manager và chính sách recovery phù hợp với phiên bản Spring Modulith đang sử dụng.

Đánh đổi về độ trễ:

- **Lợi ích:** tác vụ có thể được phát hiện và xử lý lại nếu listener lỗi hoặc tiến trình dừng.
- **Chi phí:** ghi publication trong transaction nguồn có thể tăng I/O và làm commit chậm hơn so với event thuần trong bộ nhớ.
- **Chi phí sau commit:** completion cũng cần được ghi nhận, cộng thêm thao tác database và khả năng contention.
- **Chi phí retry:** event xử lý lại làm tăng tải, có thể gây vòng xoáy backlog khi nguồn lỗi chưa được giải quyết.

Vì vậy, cần đo **response latency với registry đã bật**, không chỉ đo một bản demo event thuần bộ nhớ. Registry cải thiện khả năng phục hồi nhưng không bảo đảm **exactly-once** cho email, API bên ngoài hoặc các side effects khác.

## 11. Retry và idempotency cũng tạo độ trễ

Một listener gọi email gateway có thể timeout. Nên xử lý đúng theo loại lỗi:

1. **Lỗi tạm thời:** network timeout, rate limit; có thể retry với backoff, jitter và giới hạn lần thử.
2. **Lỗi dữ liệu vĩnh viễn:** địa chỉ không hợp lệ, payload không thể deserialize; retry mãi chỉ làm backlog tăng.
3. **Không xác định tác động đã xảy ra chưa:** timeout sau khi gửi request; phía nhận có thể đã thực hiện. Cần idempotency key/đối soát trước khi thử lại.

Ví dụ:

~~~text
10:00:00  OrderConfirmed(E1) commit
10:00:01  Listener thử gửi email lần 1 -> timeout
10:00:06  Listener thử lại lần 2 -> timeout
10:00:20  Listener thử lại lần 3 -> thành công

HTTP response của confirm: đã kết thúc từ lúc nguồn commit
Event-to-effect latency: khoảng 20 giây, không phải 1 giây
~~~

Đây là timeline minh họa. Nếu retry chạy trong chính listener, nó có thể giữ worker trong thời gian chờ; nếu scheduling/resubmit bên ngoài listener, hàng đợi và chính sách vận hành khác đi. Không nên dùng `Thread.sleep(...)` trong listener để thực hiện backoff dài hạn khi cần hệ thống có thể phục hồi qua restart.

Idempotency giúp **retry an toàn**, không nhất thiết làm tác vụ nhanh hơn:

- `eventId` nhận diện một event logic, giữ nguyên khi giao lại cùng event.
- `correlationId` nối các event trong một luồng, không nên dùng làm khóa deduplicate tất cả event.
- Khóa nghiệp vụ như `(orderId, notificationType)` có thể phù hợp khi chỉ gửi một email xác nhận cho mỗi đơn.
- Nếu email đã gửi nhưng tiến trình dừng trước khi registry ghi completion, listener có thể được gọi lại; phải kiểm soát việc gửi trùng ở module nhận hoặc tại dịch vụ bên ngoài.

Chọn retry và dead-letter/manual review dựa trên **độ trễ tối đa chấp nhận được**. Một tác vụ hoàn tất “cuối cùng” sau nhiều giờ không đạt yêu cầu nếu hợp đồng nghiệp vụ đòi hoàn tất trong 30 giây.

## 12. Đánh đổi độ trễ với tính nhất quán

Synchronous và asynchronous còn khác nhau ở **thời điểm dữ liệu của consumer phản ánh nguồn**.

| Câu hỏi | Đồng bộ trong transaction / lời gọi | Bất đồng bộ sau commit |
| --- | --- | --- |
| Client có chờ tác vụ phụ? | Thường có | Thường không |
| Module nguồn đã commit trước consumer? | Không nhất thiết | Có, với listener sau commit |
| Consumer có thể đọc dữ liệu nguồn mới nhất ngay? | Phụ thuộc transaction và isolation | Dữ liệu nguồn đã commit, nhưng có thể tiếp tục thay đổi |
| Kết quả consumer có sẵn khi HTTP trả lời? | Có thể, nếu đường đồng bộ chờ thành công | Không được đảm bảo |
| Thất bại consumer có rollback nguồn đã commit? | Nếu còn trong transaction, có thể ảnh hưởng rollback | Không |
| Cần retry và idempotency riêng? | Tùy side effect; thường vẫn cần với hệ thống ngoài | Rất quan trọng khi delivery có thể lặp |
| Có nguy cơ read model cập nhật trễ? | Ít hơn khi cùng critical path | Có: eventual consistency |

**Không coi async là một phép tối ưu thuần kỹ thuật.** Khi chuyển từ đồng bộ sang xử lý sau commit, hợp đồng nghiệp vụ cần nói rõ người dùng được phép nhìn thấy trạng thái nào trong thời gian consumer chưa hoàn tất.

Ví dụ:

- API xác nhận đơn trả `CONFIRMED` khi transaction `orders` commit.
- Trang “Điểm thưởng” có thể vẫn hiển thị số dư cũ đến khi `loyalty` xử lý `OrderConfirmed`.
- Giao diện có thể hiển thị “đang cập nhật điểm” hoặc cung cấp trạng thái đồng bộ phù hợp, không giả vờ mọi dữ liệu đã nhất quán tức thời.

Nếu một invariant bắt buộc phải được xác nhận trước response, **không đặt nó vào listener async rồi mặc định đã hoàn tất**. Hãy dùng API đồng bộ của module có thẩm quyền hoặc thiết kế quy trình có trạng thái trung gian và xác nhận kết quả sau.

## 13. Thiết kế SLO cho cả response và delivery

Một hệ thống có thể đạt SLO response nhưng lại không đạt mục tiêu giao sự kiện. Cần đặt **SLO độc lập**, đo trên đường đi thực tế.

Ví dụ SLO **mang tính giả định** cho một ứng dụng:

| Mục tiêu | Ví dụ chỉ tiêu | Nơi đo |
| --- | --- | --- |
| Xác nhận đơn | p95 HTTP response ≤ 200 ms | Ingress/API metrics |
| Gửi email xác nhận | p95 từ commit đến gửi thành công ≤ 30 giây | Listener + notification delivery logs |
| Cập nhật projection | p99 từ commit đến read model cập nhật ≤ 10 giây | Reporting projection/consumer |
| Publication chưa hoàn tất | 99,9% được xử lý trong ngưỡng vận hành đã định | Registry monitoring |

Các con số là bài tập thiết kế, **không phải chuẩn mặc định của Spring Modulith**. Với ứng dụng cần phản hồi tức thì hay tác vụ có deadline nghiêm ngặt, ngưỡng khác sẽ phù hợp hơn.

Để đo, nên phân biệt các mốc:

~~~text
requestReceivedAt
domainEventCreatedAt
sourceCommittedAt
listenerStartedAt
sideEffectCompletedAt
publicationCompletedAt
httpResponseSentAt
~~~

`occurredAt` trong event thường là thời điểm nghiệp vụ, không mặc nhiên đúng bằng timestamp commit. Nếu cần đo chính xác `commit-to-listener`, phải có đo đạc phù hợp ở transaction/event publication hoặc hệ observability; không nên lấy một timestamp gần đúng rồi tuyên bố là chính xác tuyệt đối.

Các chỉ số hữu ích gồm:

- HTTP response p50/p95/p99.
- Độ trễ `commit → listener start` (queue wait) và `listener start → effect completed`.
- Tuổi publication chưa hoàn tất lớn nhất; số lượng publication theo listener.
- Pool active count, queue depth, rejected tasks, saturation của DB connection pool.
- Retry count, lỗi theo loại, timeout, số event cần đối soát thủ công.

**Metrics tránh gắn UUID eventId/correlationId làm tag**, vì số giá trị rất lớn. Đặt các ID này trong structured logs/traces; metrics nên dùng tag ít biến thiên như tên module, tên event, listener, kết quả và loại lỗi.

## 14. Kiểm thử thay đổi từ đồng bộ sang bất đồng bộ

Chỉ kiểm thử “publisher đã gọi `publishEvent`” không chứng minh SLO hoặc tính đúng đắn khi xử lý async. Cần tách các lớp kiểm thử.

### 14.1. Unit test publisher

Kiểm tra nghiệp vụ xác nhận đơn chỉ phát event khi thật sự chuyển trạng thái, và event mang `orderId`, `eventId`, `correlationId` hợp lệ. Dùng mock `ApplicationEventPublisher` để capture payload; test này không cần chờ listener và không đo được delivery latency.

~~~java
// Pseudocode trọng tâm điều kiện phát event, không phải test runnable đầy đủ.
order.whenIsUnconfirmed();
service.confirm(orderId, correlationId);
verify(publisher, times(1))
        .publishEvent(isA(OrderConfirmed.class));

order.whenIsAlreadyConfirmed();
service.confirm(orderId, correlationId);
verifyNoMoreInteractions(publisher);
~~~

### 14.2. Integration test transaction và listener

Với Spring context và database kiểm thử phù hợp, cần kiểm tra:

1. **Commit nguồn:** gọi `OrderService.confirm(...)` qua Spring bean, transaction thật sự commit, rồi chờ listener bằng điều kiện với timeout.
2. **Rollback nguồn:** publish trong transaction nhưng gây rollback; listener `AFTER_COMMIT` không xử lý event như thể đơn đã được xác nhận.
3. **Latency separation:** dùng gateway test có thể chặn có kiểm soát; xác nhận API có thể trả sau commit trước khi gateway hoàn tất, thay vì đo bằng `Thread.sleep` khó ổn định.
4. **Một consumer chậm:** kéo dài xử lý notification, xác minh reporting không bị ràng buộc thứ tự nghiệp vụ nếu thực sự độc lập.
5. **Executor saturation:** với giới hạn pool/queue cụ thể, kiểm tra rejection/backpressure và việc publication còn có đường recovery, không mất tác vụ âm thầm.
6. **Retry + idempotency:** cố tình lỗi sau side effect rồi phát lại cùng event; xác minh tác động nghiệp vụ không bị thực hiện hai lần.
7. **Compatibility:** event lưu trong registry trước deploy còn deserialize và xử lý được sau thay đổi contract.

**Lưu ý:** test method `@Transactional` mặc định rollback ở cuối có thể khiến listener `AFTER_COMMIT` không bao giờ chạy. Tổ chức test sao cho transaction nguồn được commit thực sự; listener async cần chờ bằng polling/assertion với timeout.

### 14.3. Kiểm thử hiệu năng và tải

Một kịch bản benchmark cần có ít nhất hai con số:

- **HTTP latency** của xác nhận đơn.
- **Event-to-effect latency** của email/reporting/loyalty.

Tăng dần lưu lượng để thấy điểm bão hòa executor/connection pool; chạy đủ thời gian để backlog bộc lộ; so sánh dưới cùng cấu hình database và registry. Đừng chỉ chạy một lần với tải thấp rồi kết luận async “nhanh hơn X lần”.

Thử cả **failure mode**: email gateway chậm, mất kết nối, app restart, registry nhiều publication pending và resubmit sau khi dịch vụ trở lại. Độ trễ trong trường hợp lỗi thường quan trọng hơn chênh lệch vài millisecond ở điều kiện lý tưởng.

## 15. Ma trận chọn synchronous hay asynchronous

| Tác vụ | Cách thường phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra quyền/điều kiện bắt buộc trước khi xác nhận đơn | API đồng bộ với kết quả rõ | Không thể công bố thành công khi điều kiện chưa biết |
| Gửi email xác nhận sau khi đơn commit | `@ApplicationModuleListener` async sau commit | Email không nên giữ đường request và phải có retry/idempotency |
| Cập nhật báo cáo đọc theo ngày | Event + projection async | Chấp nhận cập nhật trễ để tối ưu đường đọc |
| Cập nhật một invariant cần bảo đảm tức thì | API/transaction đồng bộ hoặc thiết kế lại aggregate | Async không bảo đảm tính nhất quán tức thời |
| Thu tiền qua cổng thanh toán | Quy trình nghiệp vụ có trạng thái, idempotency và kết quả rõ | Không giả định enqueue là đã thu tiền |
| Ghi audit là điều kiện tuân thủ trước phản hồi | Giải pháp ghi bền được thiết kế đồng nhất với giao dịch | Không nên đặt điều kiện bắt buộc vào side effect async không có ràng buộc |
| Công việc nền lâu, có thể chịu độ trễ lớn | Async/queue/broker + cơ chế phục hồi | Tách độ trễ khỏi HTTP nhưng phải có capacity và observability |

Không có một annotation tối ưu cho mọi tình huống. Quyết định đúng cần dựa trên **bất biến nghiệp vụ, hợp đồng API, đặc điểm tải, kỳ vọng của người dùng và khả năng xử lý lỗi**.

## 16. Bài thực hành: tối ưu HTTP p95 mà không làm mất email

Giả sử một ứng dụng đang có:

~~~text
orders.confirm()
  -> update orders
  -> publish OrderConfirmed
  -> @EventListener gửi email đồng bộ qua gateway
  -> @EventListener cập nhật bảng reporting
  -> trả HTTP 200
~~~

Gateway email đôi khi mất hơn hai giây; người dùng than phiền thao tác xác nhận đơn chậm. Hãy thiết kế lại:

1. Vẽ critical path trước và sau khi chuyển email/reporting sang `@ApplicationModuleListener`. Chỉ ra chính xác loại latency nào được cải thiện, loại nào có thể tăng.
2. Đổi publisher để cập nhật đơn và publish event **trong transaction**; consumer chỉ xử lý kết quả sau commit.
3. Cấu hình một executor có queue giới hạn và chính sách rejection; nêu cách phát hiện saturation.
4. Bật Event Publication Registry bền vững phù hợp với ứng dụng, thiết kế đường recovery khi JVM dừng sau commit.
5. Thêm idempotency cho notification theo `(orderId, notificationType)` hoặc khóa nghiệp vụ tương đương; thử nhận lại cùng event.
6. Đặt một SLO cho HTTP response và một SLO khác cho thời gian email hoàn tất. Giải thích p95/p99 phải đo bằng công cụ nào và tại đâu.
7. Giả lập tăng tải sao cho tốc độ event đến lớn hơn throughput listener. Mô tả điều gì xảy ra với backlog, RAM, registry và latency.
8. Viết test commit/rollback, gateway chậm, recovery, rejection và bảo đảm không gửi trùng. Giữ ranh giới module bằng `ApplicationModules.of(ShopApplication.class).verify()`.

**Câu hỏi tự đánh giá:**

- Tại sao `@TransactionalEventListener(AFTER_COMMIT)` không chắc làm response nhanh?
- `@ApplicationModuleListener` giảm thời gian nào, và có làm giảm tổng công việc không?
- Nếu request trả nhanh nhưng publication pending tăng liên tục, hệ thống đã được tối ưu đúng mục tiêu chưa?
- Vì sao queue lớn hơn không giải quyết được producer liên tục nhanh hơn consumer?
- Nếu email đã gửi rồi registry chưa đánh dấu completion, tác động nào cần idempotency?
- Khi nào một bước bắt buộc phải nằm trong critical path thay vì được dời sang async?

## 17. Kết luận

**Đánh đổi độ trễ** giữa đồng bộ và bất đồng bộ là quyết định về **đường thực thi và thời điểm cam kết nghiệp vụ**, không chỉ là gắn `@Async` để HTTP phản hồi nhanh. Listener đồng bộ có thể kéo dài transaction và làm xấu p95/p99 request; listener sau commit bất đồng bộ thường giảm thời gian phải chờ của publisher nhưng thêm queue wait, công việc nền, transaction riêng, sự chậm trễ của projection và trách nhiệm xử lý lỗi.

Trong Spring Modulith, hãy tách rõ **response latency** khỏi **event-to-effect latency**, đo cả hai trong tải và sự cố, giữ event theo hợp đồng công khai, và cấu hình Event Publication Registry bền vững cùng retry/idempotency khi cần giao sự kiện đáng tin cậy. Một phương án tốt không chỉ làm người dùng thấy phản hồi nhanh hơn, mà còn bảo đảm các tác động quan trọng **hoàn tất đúng hạn, không bị mất và có thể đối soát khi xảy ra lỗi**.

**Tài liệu tham khảo chính thức:**

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
