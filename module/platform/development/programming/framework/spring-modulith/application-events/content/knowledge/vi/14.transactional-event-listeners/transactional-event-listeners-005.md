# Pha AFTER_COMPLETION trong transactional event listener

## 1. Vì sao cần AFTER_COMPLETION?

Khi một module **Orders** xử lý yêu cầu xác nhận đơn, transaction có thể **commit** hoặc **rollback**. Module **Notifications** chỉ nên gửi thông báo xác nhận sau commit; nhưng một thành phần quan sát có thể muốn biết **lần xử lý transaction đã kết thúc**, bất kể kết quả. Spring Framework cung cấp `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)` để biểu đạt loại công việc thứ hai.

Trong kiến trúc **SPRING_MODULITH_APPLICATION_EVENTS**, giao tiếp giữa các module bằng application events giảm phụ thuộc trực tiếp, nhưng không làm mất các quy tắc transaction. Người thiết kế phải trả lời: *event được publish lúc nào, transaction nguồn đã kết thúc chưa, callback có chạy khi rollback không, listener có transaction ghi riêng không?*

**Định nghĩa:** `AFTER_COMPLETION` là pha thực thi transactional event listener **sau khi transaction đã hoàn tất**, không giới hạn ở nhánh commit thành công. Đây không phải tên gọi khác của `AFTER_COMMIT`, cũng không tự cung cấp tham số outcome cho method listener.

Bài thuộc chương **Transactional listener**, tập trung vào pha `AFTER_COMPLETION`, cách áp dụng đúng và mối liên hệ với `@ApplicationModuleListener`, registry, retry, kiểm thử cùng quan sát sự kiện.

### Kết quả học tập

Sau bài này, bạn có thể:

- Giải thích khi nào `AFTER_COMPLETION` được kích hoạt và vì sao callback cũng chạy khi rollback.
- Phân biệt `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Nhận biết những side effect **không được** đặt trong callback cho mọi outcome.
- Phân biệt callback sau completion với API `TransactionSynchronization.afterCompletion(int status)` có thông tin outcome.
- Ghi dữ liệu trong transaction mới khi cần, tránh cạm bẫy tài nguyên transaction đã commit.
- Thiết kế công việc cleanup, audit, metrics, idempotency và recovery phù hợp.
- Viết kiểm thử commit/rollback/no-transaction và kiểm tra listener được cấu hình đúng.

## 2. Bảng đối chiếu bốn phase

| Phase | Thời điểm | Có chạy khi rollback? | Mục đích phổ biến |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước bước commit | Không phải callback sau rollback | Kiểm tra/bổ sung thao tác cần hoàn tất trước commit |
| `AFTER_COMMIT` | Sau commit thành công | **Không** | Phản ứng với sự thật nghiệp vụ đã được commit |
| `AFTER_ROLLBACK` | Sau rollback | **Có** | Cleanup hoặc quan sát việc rollback |
| **`AFTER_COMPLETION`** | **Sau khi transaction kết thúc** | **Có**; cũng chạy khi commit | Cleanup/quan sát không cần phân biệt outcome |

`@TransactionalEventListener` mặc định chọn **`AFTER_COMMIT`** nếu không khai báo `phase`.

~~~mermaid
flowchart TD
    A["Publisher publish event trong T1"] --> B{"Transaction T1 kết thúc thế nào?"}
    B -->|Commit| C["AFTER_COMMIT"]
    B -->|Rollback| D["AFTER_ROLLBACK"]
    C --> E["AFTER_COMPLETION"]
    D --> E
~~~

Hình trên mô tả các pha có thể được kích hoạt tùy outcome. Không nên dùng thứ tự các ô trên hình để suy ra mọi callback thực thi theo một thứ tự cố định giữa các listener có `@Order` khác nhau. Một listener đăng ký `AFTER_COMPLETION` nhận callback **một lần khi transaction liên quan hoàn tất**, không phải một lần cho mỗi nhánh.

### Điều dễ nhầm nhất

Ví dụ service publish `OrderConfirmed` trước khi commit. Dù tên event mang nghĩa “đã xác nhận”, transaction vẫn **có thể thất bại** sau lúc publish. Một listener `AFTER_COMPLETION` sẽ nhận callback cả khi Order bị rollback về trạng thái cũ. Do đó, không dùng pha này để gửi email “đơn đã được xác nhận” hoặc cộng điểm cho đơn đã thanh toán.

Nên phân biệt **event thể hiện một lần thử xử lý** (ví dụ `OrderConfirmationAttempted`) với **event thể hiện business fact đã commit** (ví dụ `OrderConfirmed` được listener `AFTER_COMMIT` tiêu thụ).

## 3. Dòng thời gian từ publish đến completion

Một service minh họa:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.save(order);

    publisher.publishEvent(new OrderConfirmationAttempted(
            UUID.randomUUID(), orderId, Instant.now(clock)
    ));
}
~~~

`OrderConfirmationAttempted` chỉ khẳng định có một lần thử xác nhận được phát trong transaction, không khẳng định transaction thành công. Đoạn mã giả định domain và repository đã được định nghĩa.

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders
    participant DB as Database
    participant P as Event Publisher
    participant L as AFTER_COMPLETION listener
    Client->>O: confirmOrder(orderId)
    O->>DB: BEGIN T1
    O->>DB: update Order
    O->>P: publish OrderConfirmationAttempted
    alt Commit thành công
        O->>DB: COMMIT T1
    else Rollback
        O->>DB: ROLLBACK T1
    end
    P-->>L: after completion callback
    L->>L: Cleanup hoặc metric
~~~

**Mốc completion** là mốc transaction thực sự hoàn tất, không phải khi Java method publish event được gọi, cũng không phải khi mọi consumer đã xử lý xong.

Trong workflow gồm nhiều module và nhiều transaction, completion của transaction Orders không đảm bảo transaction Notifications hay Reporting đã hoàn tất.

## 4. Khai báo AFTER_COMPLETION trong Java

Một ví dụ tập trung vào cleanup:

~~~java
package com.acme.shop.observability;

import com.acme.shop.orders.OrderConfirmationAttempted;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ConfirmationCleanupListener {

    private final AttemptContextRegistry contexts;

    public ConfirmationCleanupListener(AttemptContextRegistry contexts) {
        this.contexts = contexts;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void on(OrderConfirmationAttempted event) {
        contexts.removeIfPresent(event.attemptId());
    }
}
~~~

`AttemptContextRegistry` là một abstraction minh họa cho dữ liệu tạm theo `attemptId`. Điều kiện nghiệp vụ ở đây: *dù transaction thành công hay thất bại, context của lần thử không còn cần thiết sau completion*.

Tính chất của callback:

- Nó được đăng ký như một **Spring event listener**, nên class phải là Spring bean.
- Với transaction thông thường có synchronization, framework trì hoãn xử lý tới phase `AFTER_COMPLETION`.
- Nếu không có transaction, listener mặc định không nhận event trừ khi chủ động bật `fallbackExecution`.
- Annotation này **không tự tạo asynchronous execution**.
- Method không nhận `TransactionStatus` hay một đối số `boolean committed` từ annotation.

Nên để thao tác cleanup ngắn, idempotent và có giới hạn tài nguyên. Nếu resource cần giải phóng kể cả khi JVM dừng đột ngột, callback chỉ là một phần của giải pháp; cần TTL, lease hoặc reconciliation.

## 5. AFTER_COMPLETION không cung cấp outcome cho method

Đây là điểm rất quan trọng:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void on(OrderConfirmationAttempted event) {
    // Chỉ có event payload, không có tham số COMMITTED/ROLLED_BACK.
}
~~~

`TransactionPhase` quyết định **khi nào gọi**. Không thể thêm tham số `int completionStatus` vào method và kỳ vọng Spring tự truyền mã outcome.

Nếu consumer cần phân biệt commit và rollback, có ba cách:

| Nhu cầu | Giải pháp |
| --- | --- |
| Chỉ chạy nếu commit | `@TransactionalEventListener(phase = AFTER_COMMIT)` |
| Chỉ chạy nếu rollback | `@TransactionalEventListener(phase = AFTER_ROLLBACK)` |
| Một callback duy nhất cần mã kết quả | `TransactionSynchronization.afterCompletion(int status)` |

Không nên query database tại callback rồi suy đoán trạng thái transaction cũ dựa trên state hiện tại: có thể đã có transaction khác cập nhật dữ liệu hoặc business state không ánh xạ 1-1 với outcome của transaction.

## 6. Hai listener chuyên biệt thay vì suy đoán kết quả

Ví dụ đội phát triển muốn đếm số lần xử lý thành công và số lần rollback:

~~~java
@Component
public class ConfirmationOutcomeListener {

    private final ConfirmationMetrics metrics;

    public ConfirmationOutcomeListener(ConfirmationMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void committed(OrderConfirmationAttempted event) {
        metrics.confirmationCommitted();
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void rolledBack(OrderConfirmationAttempted event) {
        metrics.confirmationRolledBack();
    }
}
~~~

Với một transaction có kết quả xác định, chỉ một trong hai nhánh outcome phù hợp được gọi cho event đó. Cách này rõ hơn việc gắn một listener `AFTER_COMPLETION` rồi dùng một flag trong event được tạo **trước commit** để đoán kết quả.

Nếu cần đo chung số lần kết thúc transaction, có thể thêm listener `AFTER_COMPLETION` đếm `attempt_finished_total`, nhưng **không đặt tên metric là `orders_confirmed_total`** vì metric đó sẽ bao gồm rollback.

### Có phải mọi rollback đều cần phát domain event?

Không. Rollback chỉ là sự kiện về kết quả transaction kỹ thuật. Một nghiệp vụ từ chối yêu cầu do không đủ điều kiện có thể trả về validation error thay vì tạo domain event. Chỉ công bố một event riêng như `OrderRejected` nếu đó là một **sự thật nghiệp vụ cần được lưu và chia sẻ** với ranh giới transaction được thiết kế rõ ràng.

## 7. TransactionSynchronization.afterCompletion có gì khác?

Spring cung cấp interface `TransactionSynchronization`. Callback:

~~~java
void afterCompletion(int status)
~~~

nhận mã kết quả hoàn tất của transaction.

| Status | Ý nghĩa |
| --- | --- |
| `STATUS_COMMITTED` | Transaction được báo đã commit |
| `STATUS_ROLLED_BACK` | Transaction được báo đã rollback |
| `STATUS_UNKNOWN` | Trạng thái transaction không thể xác định chắc |

Một ví dụ observer:

~~~java
package com.acme.shop.orders.internal;

import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class ConfirmationOutcomeObserver {

    private final ConfirmationMetrics metrics;

    public ConfirmationOutcomeObserver(ConfirmationMetrics metrics) {
        this.metrics = metrics;
    }

    public void register() {
        if (!TransactionSynchronizationManager.isSynchronizationActive()
                || !TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("No active transaction");
        }

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCompletion(int status) {
                        if (status == STATUS_COMMITTED) {
                            metrics.confirmationCommitted();
                        } else if (status == STATUS_ROLLED_BACK) {
                            metrics.confirmationRolledBack();
                        } else {
                            metrics.confirmationOutcomeUnknown();
                        }
                    }
                }
        );
    }
}
~~~

Trong một use case `@Transactional`, gọi `observer.register()` **khi transaction đang hoạt động**. Callback này được gắn với transaction hiện hành, không tự áp dụng cho mọi transaction khác hoặc mọi JVM.

### Khi nào nên dùng synchronization trực tiếp?

- Khi một callback cần **status chính xác**, kể cả `UNKNOWN`.
- Khi tạo instrumentation bám sát transaction manager.
- Khi callback gắn với transaction cụ thể hơn là một domain event được phát rộng rãi.

Nếu chỉ cần phản ứng với một business event commit thành công, `@TransactionalEventListener(AFTER_COMMIT)` đơn giản và diễn đạt tốt hơn. Không dùng callback status thấp tầng chỉ để thay thế mọi event listener trong modular monolith.

## 8. Tài nguyên transaction có thể vẫn còn sau completion

Một giả định sai là: “Đã AFTER_COMPLETION thì mọi persistence context đã biến mất; gọi repository luôn tạo transaction mới.”

Theo semantics Spring transaction synchronization, sau commit hoặc completion, một số transaction resource có thể **vẫn tạm gắn với thread trong lúc callbacks/cleanup**. Nếu callback thực hiện truy cập DB với `REQUIRED`, nó có thể tham gia vào resource transaction đã kết thúc mà không có commit mới cho dữ liệu vừa thay đổi.

Đoạn code dưới đây có nguy cơ:

~~~java
@Component
public class AuditListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void on(OrderConfirmationAttempted event) {
        auditRepository.save(AttemptAudit.finished(event.attemptId()));
    }
}
~~~

Không mặc định `save(...)` sẽ tạo bản ghi bền vững. Kết quả phụ thuộc transaction manager, resource và cách service/repository quản lý transaction.

### Dùng REQUIRES_NEW khi cần ghi state riêng

~~~java
@Service
public class AttemptAuditService {

    private final AttemptAuditRepository audits;

    public AttemptAuditService(AttemptAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFinished(UUID attemptId) {
        audits.save(AttemptAudit.finished(attemptId));
    }
}
~~~

Sau đó listener gọi `auditService.recordFinished(event.attemptId())` **qua Spring bean/proxy**, tạo transaction mới độc lập với transaction đã hoàn tất.

**Lưu ý:** `REQUIRES_NEW` giải quyết ranh giới **ghi dữ liệu**, không bảo đảm callback chắc chắn được chạy sau một cú crash của JVM. Nếu việc ghi audit mọi lần thử là bắt buộc, cần thiết kế nguồn log/outbox/đối soát bền vững thay vì chỉ dựa vào callback trong bộ nhớ.

## 9. AFTER_COMPLETION không có quyền rollback transaction nguồn

Xét tình huống:

~~~text
T1 Orders: COMMIT Order
T1 completion: gọi cleanup
cleanup: ném exception
~~~

Ở thời điểm cleanup ném lỗi, T1 **đã commit**. Không thể dùng exception này để quay ngược commit. Với nhánh rollback, transaction nguồn cũng đã rollback rồi.

Framework xử lý exception ở các callback after-completion theo cơ chế transaction synchronization/transaction manager; không nên giả định nó luôn được truyền ngược như exception của một lời gọi `@EventListener` đồng bộ trước commit. Đặc biệt, không dùng “throw exception trong AFTER_COMPLETION” làm công cụ điều khiển việc transaction nghiệp vụ thành công hay thất bại.

### Thiết kế cleanup an toàn

- Làm việc ngắn, tránh network call không có timeout.
- Xử lý lặp không gây lỗi (idempotent cleanup).
- Ghi log/metric khi cleanup thất bại.
- Nếu tài nguyên cần giải phóng dù process dừng, dùng TTL/lease/reconciliation hoặc nguồn dữ liệu phục hồi được.
- Không lưu vô hạn dữ liệu tạm trong field singleton rồi tin mọi callback sẽ luôn chạy.

Nếu chỉ cần giải phóng tài nguyên trong cùng call stack không gắn với transaction, `try/finally` thường dễ kiểm soát hơn `AFTER_COMPLETION`.

## 10. Tại sao không gửi email sau AFTER_COMPLETION?

Đây là lỗi kiến trúc điển hình:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void on(OrderConfirmed event) {
    emailClient.sendConfirmation(event.orderId());
}
~~~

Nếu Orders publish `OrderConfirmed` trước commit rồi transaction rollback, callback **vẫn chạy** và có thể gửi email sai sự thật: khách nhận thông báo xác nhận cho một đơn chưa bao giờ được commit ở trạng thái `CONFIRMED`.

Cách phù hợp hơn:

~~~java
@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        notifications.enqueueIfAbsent(event.eventId(), event.orderId());
    }
}
~~~

Với `@ApplicationModuleListener` của Spring Modulith, listener được thiết kế cho giao tiếp **sau commit**, bất đồng bộ, trong transaction riêng. `enqueueIfAbsent` nên ghi một notification job idempotent; worker khác gửi email ngoài transaction nguồn theo quy tắc phù hợp.

**Không đánh đồng** `@ApplicationModuleListener` với `@TransactionalEventListener(AFTER_COMPLETION)`. Shortcut của Modulith hướng tới hậu commit, không phải mọi kết quả transaction.

## 11. AFTER_COMPLETION có tự bất đồng bộ không?

**Không.** Khai báo `@TransactionalEventListener(phase = AFTER_COMPLETION)` không tự tạo thread khác. Trong tình huống transaction thông thường dựa trên thread local, callback thường được gọi khi transaction manager hoàn tất, và công việc nặng có thể làm tăng latency của request.

Đối với cleanup/metric nhẹ, listener đồng bộ có thể thích hợp. Nếu thật sự cần chuyển sang executor:

~~~java
@Component
public class AsyncCleanupListener {

    @Async("lifecycleExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void on(OrderConfirmationAttempted event) {
        cleanupService.cleanup(event.attemptId());
    }
}
~~~

Điều kiện:

1. Bật `@EnableAsync`.
2. Có executor tên `lifecycleExecutor` được đăng ký trong Spring context.
3. Listener class/method được Spring proxy/interceptor xử lý.
4. Event chứa dữ liệu bất biến, không truyền `EntityManager`, HTTP request hoặc JDBC connection.
5. Có queue capacity, rejection policy, timeout và shutdown policy phù hợp.

Khi callback completion submit task, phần xử lý thực có thể chạy **muộn hơn**, không còn cùng thread/transaction context. Queue executor trong RAM không phải hàng đợi bền vững để khôi phục sau process crash.

### Kết hợp async với transaction mới

Nếu callback phải ghi DB:

~~~java
@Component
public class AsyncAttemptAuditListener {

    @Async("lifecycleExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void on(OrderConfirmationAttempted event) {
        auditRepository.save(AttemptAudit.finished(event.attemptId()));
    }
}
~~~

Đây là tổ hợp minh họa cần kiểm chứng AOP proxy/transaction và executor. Đừng dùng nó cho những side effect khẳng định commit đã thành công; `AFTER_COMPLETION` vẫn gọi ở cả nhánh rollback.

## 12. Khi không có transaction: fallbackExecution

Với code:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void on(OrderConfirmationAttempted event) {
    cleanupService.release(event.attemptId());
}
~~~

Nếu publisher phát event **ngoài một transaction phù hợp**, listener mặc định **không được gọi**. Đây là khác biệt so với `@EventListener` thông thường.

Spring hỗ trợ thuộc tính:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION,
        fallbackExecution = true
)
public void on(OrderConfirmationAttempted event) {
    cleanupService.release(event.attemptId());
}
~~~

Khi không có transaction, fallback cho phép xử lý theo chính sách của listener. Nhưng việc callback chạy **không chứng minh** có transaction đã commit hoặc rollback: đơn giản là không có transaction để chờ.

Nên tránh bật fallback nếu ý nghĩa callback là “chỉ sau khi một transaction thực sự kết thúc”. Nếu có nguồn phát event từ scheduler/batch không có transaction, hãy xác định rõ kiến trúc: cần tạo transaction cho use case hay cần một listener thường/tác vụ cleanup độc lập?

## 13. Rollback-only và checked exception

Một transaction có thể rollback ngay cả khi method nghiệp vụ không ném exception rõ ràng tới caller. Ví dụ:

~~~java
@Transactional
public void confirm(UUID orderId) {
    publisher.publishEvent(new OrderConfirmationAttempted(
            UUID.randomUUID(), orderId, Instant.now()
    ));

    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
~~~

Trong trường hợp này, callback `AFTER_COMPLETION` vẫn được gọi khi transaction kết thúc bằng rollback. Không nên dùng “method đã return” như bằng chứng cho commit thành công.

Quy tắc rollback của `@Transactional` phụ thuộc loại exception và cấu hình: mặc định phổ biến là rollback cho `RuntimeException` và `Error`; với checked exception, cần đánh giá `rollbackFor`, `noRollbackFor` hoặc cấu hình transaction của ứng dụng. **Outcome thực tế** quan trọng hơn việc đoán dựa trên một nhánh catch.

Một sự kiện được publish ở bước đầu có thể là sự thật về “lần thử xử lý”, nhưng chưa phải sự thật “đơn đã xác nhận” cho consumer hậu commit.

## 14. Transaction propagation và sự kiện gắn với transaction nào?

Khi một use case gọi nhiều method có `@Transactional`, event sẽ gắn với **transaction có synchronization đang hoạt động lúc publish**, không đơn giản là với tên method hay module.

| Propagation | Ảnh hưởng đến event completion |
| --- | --- |
| `REQUIRED` | Tham gia transaction hiện có; listener chờ transaction đó hoàn tất |
| `REQUIRES_NEW` | Mở transaction riêng; event publish ở đây gắn với completion của transaction mới |
| `NESTED` | Có thể dùng savepoint theo transaction manager; không tự tạo một callback completion độc lập cho từng savepoint |
| `NOT_SUPPORTED` | Không chạy trong transaction hiện có; transactional listener mặc định có thể không được gọi |

Ví dụ:

~~~text
T1 (Orders workflow) bắt đầu
    T2 (REQUIRES_NEW) ghi audit + publish AuditRecorded
        T2 COMMIT
        AFTER_COMPLETION của T2 chạy
    T1 tiếp tục
    T1 ROLLBACK
~~~

Callback gắn với T2 có thể đã chạy dù T1 sau đó rollback. **Outcome của T2 không phải outcome của T1**.

Nếu cần quan sát kết quả của transaction ngoài cùng, phải đăng ký synchronization hoặc publish event trong transaction ngoài phù hợp.

### Savepoint không phải transaction mới

`NESTED` với savepoint không có cùng semantics với `REQUIRES_NEW`. Rollback một savepoint không nhất thiết kích hoạt một `AFTER_COMPLETION` độc lập. Đừng xây nghiệp vụ mong mỗi savepoint rollback đều phát transactional event completion như một transaction vật lý.

## 15. Cân nhắc reactive transaction

Các transaction imperative thường sử dụng transaction context gắn với thread. Trong lập trình reactive, transaction được truyền qua **Reactor context**, không thể áp dụng nguyên giả định thread-local của mọi ví dụ trước.

Từ các phiên bản Spring Framework hỗ trợ transactional events trong reactive transaction, ngữ cảnh transaction phải được truyền theo cơ chế reactive thích hợp; có thể dùng `TransactionalEventPublisher` nếu cần đưa transaction context vào event để listener xử lý.

Nếu dự án dùng WebFlux/R2DBC hoặc reactive transaction manager:

- Không tự gọi `TransactionSynchronizationManager` kiểu imperative rồi mặc định có reactive transaction.
- Kiểm tra API reactive transaction/event được hỗ trợ trong phiên bản Spring.
- Tách các ví dụ `TransactionTemplate` và `PlatformTransactionManager` ở bài này khỏi workflow reactive.
- Viết test theo reactive transaction/context thực tế.

## 16. AFTER_COMPLETION và Event Publication Registry

Spring Modulith có **Event Publication Registry** giúp theo dõi việc giao application events tới các transactional listeners khi cấu hình backend lưu trữ thích hợp, và hỗ trợ phát lại những publication chưa hoàn thành theo khả năng của phiên bản/hạ tầng đang dùng.

Tuy nhiên, `AFTER_COMPLETION` là một lựa chọn phase cần đánh giá kỹ:

- Vì callback chạy cả ở rollback, không nên coi nó là tín hiệu “business event chắc chắn đã commit”.
- Nếu publication record được ghi trong transaction nguồn, bản ghi đó có thể **rollback cùng transaction**. Vì vậy không nên trông chờ registry thông thường tự giữ lịch sử audit cho mọi giao dịch rollback.
- Không giả định mọi listener AFTER_COMPLETION có cùng semantics retry/registry như `@ApplicationModuleListener` sau commit; cần kiểm chứng listener registration và backend.
- Registry theo dõi publication/handling, không biến nó thành nguồn thông tin outcome `COMMITTED` hoặc `ROLLED_BACK` cho mọi transaction.
- Không có bảo đảm exactly-once end-to-end cho một database ngoài, broker hoặc email provider.

### Nếu yêu cầu ghi nhận cả transaction rollback thì sao?

Có thể thiết kế:

1. Bản ghi attempt được tạo trong một transaction bền vững **độc lập** theo yêu cầu nghiệp vụ, nếu cần tracking tồn tại sau rollback.
2. Callback có outcome rõ thông qua `AFTER_COMMIT`/`AFTER_ROLLBACK` hoặc `TransactionSynchronization.afterCompletion(status)`.
3. Cập nhật outcome trong `REQUIRES_NEW` theo business key/idempotency key.
4. Đối soát nếu process crash trước callback hoặc trạng thái outcome là UNKNOWN.

Dùng callback in-memory **không thể cam kết** tất cả lần transaction thất bại đều được audit khi JVM chết đột ngột. Muốn bảo đảm mạnh hơn, cần kiến trúc persistence/recovery cụ thể.

## 17. Retry, idempotency và side effect trong callback

Một cleanup tốt nên idempotent:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void on(OrderConfirmationAttempted event) {
    temporaryCache.removeIfPresent(event.attemptId());
}
~~~

Ngược lại, cộng điểm thưởng:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void on(OrderConfirmationAttempted event) {
    loyalty.creditPoints(event.orderId(), 100);
}
~~~

là không đúng, vì callback chạy sau rollback và việc xử lý trùng có thể cộng điểm hai lần.

Giải pháp phù hợp hơn là phát event nghiệp vụ có nghĩa rõ như `OrderPaid` rồi dùng listener sau commit:

~~~java
@ApplicationModuleListener
public void on(OrderPaid event) {
    loyalty.creditOnce(event.eventId(), event.orderId());
}
~~~

`creditOnce` phải dựa vào database constraint hoặc processed-event record trong transaction consumer, không chỉ một `Set<UUID>` trong singleton listener. Retry do lỗi processing có thể khiến consumer nhận lại cùng event, kể cả khi publisher đã commit từ lâu.

## 18. Một số tình huống cần quyết định phase

| Yêu cầu | Chọn cơ chế | Lý do |
| --- | --- | --- |
| Dừng timer khi transaction kết thúc | `AFTER_COMPLETION` | Chung cho mọi outcome |
| Dọn bộ nhớ tạm gắn với lần thử transaction | `AFTER_COMPLETION` | Không quan tâm commit hay rollback |
| Đếm số transaction commit thành công | `AFTER_COMMIT` | Không lẫn rollback |
| Đếm số transaction rollback | `AFTER_ROLLBACK` | Chỉ rollback |
| Một callback ghi chính xác outcome gồm UNKNOWN | `TransactionSynchronization.afterCompletion(status)` | Có tham số status |
| Tạo email job sau khi đơn được xác nhận | `@ApplicationModuleListener` / `AFTER_COMMIT` + transaction mới | Sự thật đã commit |
| Gửi event sang CRM ngoài JVM | After-commit externalization/outbox thích hợp | Không xuất state bị rollback |
| Ghi audit mọi lần thử ngay cả khi JVM crash | Durable audit/workflow + reconciliation | Callback memory không đủ |
| Giải phóng một lease phải hết hạn ngay cả khi JVM chết | TTL/lease + cleanup | Callback có thể không chạy sau crash |

**Câu hỏi quyết định:** việc này đúng **chỉ khi commit**, **chỉ khi rollback**, hay **với mọi completion**? Chọn phase theo câu trả lời đó, không chỉ vì tên phase trông “muộn nhất”.

## 19. Kiểm thử commit, rollback và không có transaction

Kiểm thử quan trọng nhất là chứng minh `AFTER_COMPLETION` chạy sau **cả hai outcome**.

### 19.1. Test probe đơn giản

~~~java
public record TxProbeEvent(UUID id) {}

@Component
public class TransactionPhaseProbe {

    private final Set<UUID> completed = ConcurrentHashMap.newKeySet();
    private final Set<UUID> committed = ConcurrentHashMap.newKeySet();
    private final Set<UUID> rolledBack = ConcurrentHashMap.newKeySet();

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void completed(TxProbeEvent event) {
        completed.add(event.id());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void committed(TxProbeEvent event) {
        committed.add(event.id());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void rolledBack(TxProbeEvent event) {
        rolledBack.add(event.id());
    }

    public boolean hasCompleted(UUID id) { return completed.contains(id); }
    public boolean hasCommitted(UUID id) { return committed.contains(id); }
    public boolean hasRolledBack(UUID id) { return rolledBack.contains(id); }
}
~~~

Đây là **probe dành cho test**, không phải cơ chế idempotency production. Giả định đã có imports Java `UUID`, `Set`, `ConcurrentHashMap`, annotations transaction và Spring bean; probe được đăng ký trong context test.

### 19.2. Integration test với TransactionTemplate

~~~java
@SpringBootTest
class AfterCompletionIntegrationTest {

    @Autowired PlatformTransactionManager txManager;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired TransactionPhaseProbe probe;

    @Test
    void afterCompletionRunsForCommit() {
        UUID id = UUID.randomUUID();
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status ->
                publisher.publishEvent(new TxProbeEvent(id))
        );

        assertThat(probe.hasCompleted(id)).isTrue();
        assertThat(probe.hasCommitted(id)).isTrue();
        assertThat(probe.hasRolledBack(id)).isFalse();
    }

    @Test
    void afterCompletionRunsForRollback() {
        UUID id = UUID.randomUUID();
        TransactionTemplate tx = new TransactionTemplate(txManager);

        tx.executeWithoutResult(status -> {
            publisher.publishEvent(new TxProbeEvent(id));
            status.setRollbackOnly();
        });

        assertThat(probe.hasCompleted(id)).isTrue();
        assertThat(probe.hasCommitted(id)).isFalse();
        assertThat(probe.hasRolledBack(id)).isTrue();
    }

    @Test
    void listenerDoesNotRunWithoutTransactionByDefault() {
        UUID id = UUID.randomUUID();
        publisher.publishEvent(new TxProbeEvent(id));

        assertThat(probe.hasCompleted(id)).isFalse();
    }
}
~~~

Ví dụ giả định project đã có Spring Boot Test, JUnit, AssertJ, `PlatformTransactionManager` và probe bean; các imports/dependencies cần được bổ sung tương ứng. Test **không được bọc ngoài** bằng `@Transactional` tự rollback, vì sẽ làm thay đổi mốc commit mà `TransactionTemplate` đang được dùng để chứng minh.

Vì probe này không dùng `@Async`, các assertion ngay sau `executeWithoutResult` phù hợp để minh họa việc transaction hoàn tất. Với callback async, phải chờ điều kiện cuối bằng timeout và tránh `Thread.sleep(...)` cố định.

### 19.3. Những test khác nên có

- Với `fallbackExecution = true`, publish ngoài transaction và xác minh callback xử lý theo fallback.
- Với `TransactionSynchronization.afterCompletion(status)`, kiểm tra COMMITTED và ROLLED_BACK.
- Publish trong `REQUIRES_NEW`, rồi rollback transaction ngoài; xác minh sự kiện gắn đúng transaction.
- Cleanup idempotent khi logic được gọi lại.
- Callback ném lỗi nhưng không giả định transaction nguồn có thể rollback sau completion.
- Nếu ghi DB, xác minh transaction `REQUIRES_NEW` thực sự commit, kể cả nhánh transaction nguồn rollback.
- Nếu cần bảo đảm qua restart, kiểm thử crash/recovery bằng hạ tầng phù hợp, không chỉ unit test callback.

## 20. Quan sát trong production

Các tín hiệu cần **phân biệt rõ**:

| Tín hiệu | Nó chứng minh điều gì? |
| --- | --- |
| `AFTER_COMPLETION` callback được gọi | Transaction đã đạt mốc hoàn tất của framework |
| `AFTER_COMMIT` callback được gọi | Transaction đã commit theo transaction manager |
| `AFTER_ROLLBACK` callback được gọi | Transaction rollback |
| `STATUS_UNKNOWN` từ synchronization | Không thể kết luận chắc outcome |
| Publication được registry ghi nhận | Có record theo dõi giao việc, nếu đã cấu hình |
| Listener completed | Listener xử lý xong theo cơ chế completion |
| Email/API bên ngoài thành công | Side effect riêng đã được xác nhận theo nguồn liên quan |

Log mẫu:

~~~text
event=OrderConfirmationAttempted attemptId=A1 listener=Cleanup phase=AFTER_COMPLETION
event=OrderConfirmationAttempted attemptId=A1 outcome=ROLLED_BACK observer=TxSynchronization
event=OrderConfirmed eventId=E1 listener=Notifications phase=AFTER_COMMIT
~~~

Hãy theo dõi lỗi cleanup, số lần commit/rollback, độ trễ callback, tài nguyên tạm tồn đọng, publication pending và side effect chưa hoàn tất. ID riêng của event/attempt nên nằm trong log/tracing, **không làm tag metric có cardinality không giới hạn**.

Không log toàn bộ event có dữ liệu nhạy cảm. `AFTER_COMPLETION` không tự chuyển một transaction event thành integration event; nếu cần phân phối liên tiến trình, dùng cơ chế messaging/externalization thích hợp.

## 21. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi AFTER_COMPLETION là after-commit | Gửi email/cộng điểm khi rollback | Dùng AFTER_COMMIT cho business fact |
| Mong method nhận tham số completion status | Không có outcome trong listener signature | Dùng TransactionSynchronization |
| Đặt boolean “committed” trong event trước commit | Giá trị có thể sai | Dựa vào outcome thực tế |
| Ghi DB sau completion mà không tạo transaction mới | Có thể không lưu bền | REQUIRES_NEW qua bean/proxy |
| Dùng after-completion làm durable queue | Callback có thể mất khi JVM crash | Durable audit/recovery phù hợp |
| Bật fallbackExecution vô điều kiện | Callback chạy cả khi không có transaction | Đánh giá semantics và test |
| Đưa network I/O nặng vào callback đồng bộ | Kéo dài request latency | Async/job và timeout |
| Ghi audit thất bại trong transaction sẽ rollback | Audit biến mất cùng transaction | Lưu outcome ở transaction độc lập |
| Cho rằng callback transaction con là outcome transaction cha | Kết luận sai | Xác định ranh giới transaction thật |
| Tưởng callback có exactly-once | Side effect lặp/mất có thể xảy ra | Idempotency và reconciliation |
| Nhầm @ApplicationModuleListener với AFTER_COMPLETION | Listener nghiệp vụ chạy sai điều kiện | Hiểu shortcut chỉ after-commit |
| Chỉ kiểm thử commit | Không phát hiện sai ở rollback | Test cả commit, rollback, no-tx |

## 22. Bài tập thực hành

### Bài tập 1 — Chọn phase

Chọn phase hoặc synchronization cho các yêu cầu: (1) dừng timer sau transaction, (2) gửi email xác nhận, (3) đếm rollback, (4) ghi outcome COMMITTED/ROLLED_BACK/UNKNOWN, (5) xóa dữ liệu tạm. Giải thích tiêu chí lựa chọn.

### Bài tập 2 — Sửa anti-pattern

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void on(OrderPaid event) {
    loyalty.creditPoints(event.orderId(), 100);
}
~~~

Vì sao code có thể cộng điểm cho transaction rollback? Viết lại theo listener hậu commit và idempotency bền vững.

### Bài tập 3 — Audit khi rollback

Thiết kế audit lưu kết quả cho một lần thử thanh toán, kể cả khi transaction business rollback. Phân biệt: audit callback có chạy trong một JVM đang hoạt động và bảo đảm lưu audit qua sự cố JVM crash. Trình bày cách dùng `REQUIRES_NEW` và reconciliation.

### Bài tập 4 — REQUIRES_NEW trong T1

T1 gọi T2 `REQUIRES_NEW`. T2 publish event rồi commit, nhưng T1 rollback. Listener `AFTER_COMPLETION` của event T2 chạy khi nào? Kết quả đó có cho biết T1 thành công không?

### Bài tập 5 — Test ba pha

Dùng `TransactionTemplate` publish event ở hai nhánh commit/rollback và đối chiếu `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Thêm trường hợp không có transaction với `fallbackExecution` mặc định.

## 23. Checklist code review

- [ ] AFTER_COMPLETION chỉ phục vụ công việc đúng ở **mọi outcome**.
- [ ] Business side effect chỉ hợp lệ sau commit được gắn AFTER_COMMIT.
- [ ] Nếu cần status thật, sử dụng synchronization hoặc các phase tách biệt.
- [ ] Không suy đoán transaction outcome qua entity state hay event timestamp.
- [ ] Callback ghi DB đã có transaction mới khi cần.
- [ ] REQUIRES_NEW được gọi qua Spring proxy.
- [ ] Đã xem xét failure mode khi callback ném exception hoặc JVM crash.
- [ ] Không đưa transaction, JPA entity mutable, HTTP request vào async event.
- [ ] Nếu dùng async, đã cấu hình executor, queue/rejection/shutdown và kiểm thử.
- [ ] Nếu bật fallbackExecution, hiểu rõ behavior khi không có transaction.
- [ ] Không đồng nhất publication completion với commit của publisher.
- [ ] Idempotency và duplicate handling được đảm bảo tại consumer nếu có redelivery.
- [ ] Đã test commit, rollback, rollback-only, no-tx, nested transaction nếu có.
- [ ] Có metrics/log/tracing cho cleanup và outcome mà không lộ thông tin nhạy cảm.

## 24. Tổng kết

**`TransactionPhase.AFTER_COMPLETION` biểu diễn “transaction đã kết thúc”, không biểu diễn “nghiệp vụ đã commit thành công”.** Callback chạy cho cả commit và rollback, thích hợp cho cleanup, kết thúc timer hoặc quan sát không phụ thuộc outcome. Đối với công việc nghiệp vụ chỉ có ý nghĩa khi dữ liệu nguồn đã lưu bền, hãy dùng `AFTER_COMMIT` hoặc `@ApplicationModuleListener` của Spring Modulith.

Nếu cần mã trạng thái completion chính xác, `TransactionSynchronization.afterCompletion(int status)` có thể cung cấp COMMITTED, ROLLED_BACK hoặc UNKNOWN. Nếu cần ghi dữ liệu trong callback, cân nhắc `REQUIRES_NEW` và thiết kế độ bền; bản thân callback không thay thế registry/outbox hay cơ chế recovery khi JVM chết.

Thiết kế transaction phase đúng giúp kiến trúc Spring Modulith duy trì các ranh giới nghiệp vụ rõ ràng, xử lý sau commit chính xác và quan sát/khôi phục sự kiện đáng tin cậy.

### Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — các transaction phase và `fallbackExecution`.
- [Spring Framework — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — callback `afterCompletion(int status)`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — `@ApplicationModuleListener`, registry và giao tiếp giữa module.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) — `REQUIRED`, `REQUIRES_NEW`, `NESTED`.

> Các đoạn mã minh họa đã lược bớt imports/bean nghiệp vụ để tập trung vào transaction semantics; cần điều chỉnh theo phiên bản Spring, transaction manager và hạ tầng của project. Vòng Content QA chuyên sâu thuộc bước sau, không thực hiện trong STEP 4.
