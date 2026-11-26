# Commit và rollback khi sử dụng application events trong Spring Modulith

## 1. Vì sao commit và rollback quyết định tính đúng của event?

Trong một hệ thống Spring Modulith, application event thường được phát khi module hoàn thành một hành động nghiệp vụ. Ví dụ, module `orders` xác nhận đơn và phát `OrderConfirmed` để `notifications` gửi thông báo, `reporting` cập nhật số liệu và `loyalty` tích điểm.

Vấn đề bắt đầu khi sự kiện được phát **trong một transaction chưa commit**. Nếu transaction sau đó rollback nhưng một listener đã gửi email hoặc gọi dịch vụ ngoài, khách hàng có thể nhận thông báo về một đơn hàng thực ra chưa được xác nhận.

Ngược lại, nếu đợi database commit rồi mới gửi một event bằng thao tác không được lưu bền, tiến trình có thể chết ở khoảng giữa: đơn đã xác nhận nhưng listener không nhận được thông báo.

Đó là lý do bài **Commit và rollback**, thuộc chương **Giao dịch và event** của module `SPRING_MODULITH_APPLICATION_EVENTS`, phải gắn chặt việc phát và nghe event với **transaction boundary**, **phương thức dispatch**, **event publication registry**, **retry**, **kiểm thử** và **quan sát**. Mục tiêu chung là giao tiếp giữa các module qua application events mà không tạo phụ thuộc trực tiếp hoặc làm sai sự thật nghiệp vụ.

### 1.1. Tình huống xuyên suốt

~~~text
Client: POST /orders/{orderId}/confirm
           |
           v
    orders.confirm(orderId)
           |
           +-- BEGIN TRANSACTION
           +-- Kiểm tra điều kiện xác nhận
           +-- Đổi trạng thái Order thành CONFIRMED
           +-- publishEvent(OrderConfirmed)
           +-- COMMIT hoặc ROLLBACK
                       |
              Khi COMMIT thành công
                       v
              notifications listener
              reporting listener
              loyalty listener
~~~

Trong mô hình này cần trả lời:

1. `publishEvent(...)` có làm database commit không?
2. Một listener có thể chạy **trước commit** không?
3. Nếu rollback, listener nào được gọi hoặc không được gọi?
4. Nếu commit thành công nhưng listener lỗi, có thể rollback đơn hàng không?
5. Publication được ghi nhận và phát lại thế nào sau khi ứng dụng dừng?
6. Nếu xử lý lại cùng event, làm sao không gửi email hoặc tích điểm hai lần?

**Tư duy cốt lõi:** việc event đã được *phát* không chứng minh transaction đã *commit*, và transaction đã commit không chứng minh mọi listener đã *hoàn tất*.

## 2. Ba ranh giới cần phân biệt

| Ranh giới | Nội dung | Đơn vị chịu trách nhiệm |
| --- | --- | --- |
| **Transaction nguồn** | Cập nhật nghiệp vụ và ghi dữ liệu nguồn | Module phát event, ví dụ `orders` |
| **Dispatch và publication** | Chọn listener, lên lịch thực thi, ghi tiến độ nếu có registry | Spring event infrastructure và Spring Modulith |
| **Transaction hoặc tác dụng phụ của listener** | Cập nhật dữ liệu module nhận, gửi email hoặc chuyển message sang broker | Module/handler nhận event |

Một transaction database chỉ bảo vệ những tài nguyên tham gia vào **transaction manager tương ứng**. Nó không tự bao trùm:

- Một HTTP request tới hệ thống đối tác.
- Việc email provider đã chấp nhận hoặc gửi email.
- Một transaction ở database của hệ thống ngoài.
- Một thread bất đồng bộ đang chạy sau commit.
- Một Kafka consumer đã xử lý message.

Với cùng một database và transaction manager, những thao tác đồng bộ cùng tham gia transaction nguồn **có thể** commit/rollback cùng nhau; nhưng đó là quyết định về thiết kế giao dịch, không phải tính chất của mọi listener.

### 2.1. Sơ đồ thời gian logic

~~~mermaid
sequenceDiagram
    participant API as HTTP API
    participant Orders as orders service
    participant DB as Business DB
    participant Pub as ApplicationEventPublisher
    participant Listener as AFTER_COMMIT listener

    API->>Orders: confirm(orderId)
    Orders->>DB: BEGIN
    Orders->>DB: UPDATE Order
    Orders->>Pub: publishEvent(OrderConfirmed)
    Note over Pub,Listener: Đăng ký xử lý theo pha transaction
    Orders->>DB: COMMIT
    alt Commit thành công
        DB-->>Orders: committed
        Pub-->>Listener: Chạy listener AFTER_COMMIT
        Listener->>Listener: Tác vụ hậu quả
    else Rollback
        DB-->>Orders: rolled back
        Note over Pub,Listener: Không thực hiện AFTER_COMMIT
    end
    Orders-->>API: Kết quả theo hợp đồng API
~~~

Sơ đồ mô tả luồng transaction event logic, không ấn định thời gian trả response so với một listener bất đồng bộ. Với callback đồng bộ sau commit, request có thể còn đang chờ; với async listener, công việc có thể chạy sau khi response đã được trả.

## 3. @EventListener mặc định: gọi listener không phải chờ commit

Spring Framework cung cấp `ApplicationEventPublisher` và `@EventListener`. Với event multicaster đồng bộ mặc định, một `@EventListener` chạy **ngay khi publisher phát event**, thường trong cùng thread và transaction nguồn.

### 3.1. Event bất biến

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

### 3.2. Publisher trong transaction

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

`OrderRepository`, aggregate `Order` và bean `Clock` là các thành phần giả định. Nếu sử dụng JPA, thay đổi trên entity đang được quản lý sẽ được flush/commit theo persistence context; với cơ chế khác có thể phải gọi repository lưu một cách tường minh.

### 3.3. Listener đồng bộ có thể chạy trước commit

~~~java
package com.example.shop.orders.internal.audit;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    private final OrderAuditRepository audits;

    OrderAuditListener(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @EventListener
    void on(OrderConfirmed event) {
        audits.appendConfirmation(
            event.eventId(), event.orderId()
        );
    }
}
~~~

Nếu listener đồng bộ đang tham gia **cùng transaction database** và dùng transaction manager phù hợp, việc ghi audit có thể rollback cùng đơn hàng. Đây là một lựa chọn có chủ ý khi audit là một phần của giao dịch nguồn.

Nhưng nếu thay `audits.appendConfirmation(...)` bằng lời gọi gửi email, email **không tự được thu hồi khi database rollback**. Đó là một tác dụng phụ ngoài ranh giới transaction.

### 3.4. Exception từ listener đồng bộ ảnh hưởng đến publisher

Khi multicaster thực thi listener đồng bộ, một exception không được xử lý có thể truyền ngược qua `publishEvent(...)`. Nếu exception đó làm phương thức `@Transactional` kết thúc với lỗi thuộc diện rollback, transaction nguồn sẽ rollback theo quy tắc Spring transaction.

~~~java
@EventListener
void on(OrderConfirmed event) {
    if (auditStorageUnavailable()) {
        throw new IllegalStateException("Audit storage unavailable");
    }
}
~~~

Ví dụ `IllegalStateException` là runtime exception, thường khiến transaction sử dụng rollback rule mặc định bị rollback. Tuy nhiên, không được tổng quát hóa rằng **mọi exception** đều khiến rollback:

- Quy tắc mặc định thường rollback với `RuntimeException` và `Error`.
- Checked exception có thể không kích hoạt rollback theo mặc định; có thể cấu hình `rollbackFor` hoặc quy tắc tương đương.
- Nếu exception bị bắt, nuốt và không có tín hiệu đánh dấu rollback, transaction có thể vẫn commit.
- Spring proxy/transaction interceptor phải thực sự được áp dụng.
- Một số lời gọi tới resource khác có semantics lỗi riêng.

Vì vậy, một listener đồng bộ có khả năng tham gia quyết định rollback, nhưng **không nên giấu bất biến nghiệp vụ quan trọng sau một danh sách listener khó kiểm soát**.

## 4. @TransactionalEventListener: gắn listener với kết quả transaction

Khi listener chỉ được phép thực hiện tác vụ nếu transaction nguồn đạt một kết quả nhất định, dùng `@TransactionalEventListener` của Spring Framework.

| Transaction phase | Thời điểm | Khi nào phù hợp? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction nguồn thực hiện commit | Kiểm tra cuối hoặc thao tác có chủ đích cần hoàn thành trước commit |
| `AFTER_COMMIT` | Sau khi transaction nguồn commit thành công | Notification, projection hoặc hậu quả chỉ đúng khi nghiệp vụ đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Cleanup/quan sát hoặc hành động bù phù hợp với một transaction thất bại |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, bất kể commit/rollback | Dọn tài nguyên hoặc đo đạc với semantics riêng |

**`AFTER_COMMIT` là phase mặc định** khi sử dụng `@TransactionalEventListener` mà không khai báo `phase`.

### 4.1. Vì sao AFTER_COMMIT an toàn hơn cho email?

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class ConfirmationNotificationListener {

    private final ConfirmationEmailSender sender;

    ConfirmationNotificationListener(ConfirmationEmailSender sender) {
        this.sender = sender;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        sender.sendConfirmation(event.eventId(), event.orderId());
    }
}
~~~

Với transaction nguồn hợp lệ:

- Nếu commit thành công, callback hậu commit được thực thi.
- Nếu rollback, callback `AFTER_COMMIT` không thực thi.
- Lỗi của callback hậu commit **không thể làm transaction nguồn đã commit quay lại trạng thái rollback**.

Tuy vậy, `@TransactionalEventListener` mặc định **không tự đảm bảo một hàng đợi bền vững**. Nếu ứng dụng chết trước khi callback hoàn tất, công việc có thể bị mất khi không có registry hoặc giải pháp lưu publication phù hợp.

### 4.2. AFTER_COMMIT không tự động bất đồng bộ

Một listener `@TransactionalEventListener(AFTER_COMMIT)` thông thường vẫn có thể chạy trên thread đang hoàn tất transaction, nên tác vụ chậm có thể ảnh hưởng thời gian trả response. **After commit** mô tả *thời điểm*, còn **async** mô tả *nơi/cách thực thi*.

Nếu muốn tách thời gian xử lý, cần phối hợp async executor đúng với version Spring/annotation hoặc sử dụng `@ApplicationModuleListener` của Spring Modulith. Khi đổi sang async, phải quản lý transaction riêng, exception, context propagation và recovery.

### 4.3. Không có transaction thì điều gì xảy ra?

Mặc định, `@TransactionalEventListener` chỉ xử lý khi có transaction tương ứng; nếu publisher phát event **ngoài transaction**, listener thường **không được gọi**, trừ khi cấu hình `fallbackExecution = true`.

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
void on(OrderConfirmed event) {
    // Có thể được gọi dù publishEvent nằm ngoài transaction.
}
~~~

**Cảnh báo:** Khi rơi vào fallback, không hề có commit nguồn để chờ. Chỉ bật fallback nếu hành vi ngoài transaction được định nghĩa rõ và hợp lệ; không dùng nó để che lỗi service đáng ra phải có `@Transactional`.

## 5. BEFORE_COMMIT: không phải cứ sắp commit là chắc chắn thành công

Listener `BEFORE_COMMIT` có thể được dùng khi muốn thực hiện một bước cuối trong transaction trước khi commit. Nhưng sau callback đó, commit vẫn có thể thất bại do ràng buộc database, optimistic lock, constraint hoặc hạ tầng lưu trữ.

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void verifyRequiredAudit(OrderConfirmed event) {
    auditPolicy.check(event.orderId());
}
~~~

**Lưu ý:**

1. Nghiệp vụ không nên suy rằng `BEFORE_COMMIT` đồng nghĩa **đã commit**.
2. Exception từ callback trước commit có thể ngăn commit, tùy đường xử lý transaction.
3. Nếu callback gọi hệ thống ngoài và sau đó database rollback, tác dụng phụ đã gọi không được hoàn tác.
4. Những ràng buộc cốt lõi của aggregate nên được đặt trong aggregate/service để dễ đọc và kiểm thử; không lạm dụng listener như một cơ chế validation ngầm.

### 5.1. Flush khác commit

Trong JPA, `flush()` đẩy những thay đổi trong persistence context xuống database theo transaction hiện hành, nhưng **không biến transaction thành đã commit**. Một event được phát sau `saveAndFlush(...)` vẫn có thể thuộc một transaction bị rollback.

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.saveAndFlush(order);
    publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(), orderId, clock.instant()
    ));
    // Một RuntimeException phía sau vẫn có thể làm rollback.
}
~~~

Đoạn mã minh họa repository kiểu Spring Data JPA, không phải hướng dẫn phải flush trước mọi lần phát event. Khi cần listener phản ứng **chỉ sau khi transaction đã commit**, hãy chọn `AFTER_COMMIT` thay vì dùng `flush()` như dấu thành công.

## 6. AFTER_COMMIT: ghi database mới cần transaction mới

Một bẫy quan trọng của Spring transaction synchronization: tại thời điểm callback `AFTER_COMMIT` chạy, transaction nguồn đã commit, nhưng **một số tài nguyên transaction có thể vẫn gắn với thread**.

Nếu listener lại ghi database bằng repository mà **không mở một transaction mới**, thao tác đó không nhất thiết được commit như tác giả mong đợi. Vì vậy, khi cần thay đổi dữ liệu ở module nhận sau commit, phải xác định rõ **transaction ghi mới**.

### 6.1. Ví dụ cập nhật projection sau commit

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class SalesProjectionListener {

    private final SalesProjectionWriter writer;

    SalesProjectionListener(SalesProjectionWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        writer.updateFor(event);
    }
}
~~~

Tách phần ghi DB sang một Spring bean khác:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
class SalesProjectionWriter {

    private final SalesProjectionRepository projections;

    SalesProjectionWriter(SalesProjectionRepository projections) {
        this.projections = projections;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateFor(OrderConfirmed event) {
        projections.applyIdempotently(
            event.eventId(),
            event.orderId()
        );
    }
}
~~~

`applyIdempotently(...)` là method do dự án tự xây dựng, không phải API tự sinh của Spring Data. Nó phải bảo vệ khỏi xử lý lặp nếu listener có thể retry.

Điểm kỹ thuật: `writer.updateFor(...)` là lời gọi **tới Spring bean khác** để transaction proxy có cơ hội áp dụng `REQUIRES_NEW`. Nếu gọi một method được annotate bằng `@Transactional` thông qua `this.method()` trong cùng bean khi sử dụng proxy thông thường, transaction interceptor có thể không chạy.

### 6.2. Vì sao cần tách transaction nguồn và transaction listener?

~~~mermaid
sequenceDiagram
    participant O as orders
    participant DB as Database
    participant L as reporting listener
    participant W as SalesProjectionWriter

    O->>DB: BEGIN TX1
    O->>DB: Update Order
    O->>O: publish OrderConfirmed
    O->>DB: COMMIT TX1
    DB-->>O: committed
    O-->>L: AFTER_COMMIT callback
    L->>W: updateFor(event)
    W->>DB: BEGIN TX2 (REQUIRES_NEW)
    W->>DB: Update projection
    W->>DB: COMMIT TX2
    W-->>L: success
~~~

**TX1 và TX2 không phải một giao dịch nguyên tử.** Nếu TX1 thành công rồi TX2 lỗi, đơn hàng vẫn được xác nhận; projection cần retry hoặc rebuild theo mức độ tin cậy đã chọn.

### 6.3. REQUIRES_NEW khác với “lấy lại transaction cũ”

`Propagation.REQUIRES_NEW` yêu cầu một transaction độc lập đối với transaction hiện có. Nó không kéo dài transaction nguồn; dữ liệu module nhận commit/rollback **theo transaction mới**. Khi nhiều listener cùng xử lý, mỗi listener có thể có kết quả riêng.

Việc mở transaction mới không tự giải quyết tất cả lỗi: có thể xảy ra “TX2 đã commit nhưng publication chưa ghi hoàn tất”, nên vẫn cần idempotency khi resubmit.

## 7. AFTER_ROLLBACK và AFTER_COMPLETION dùng khi nào?

Không phải mọi phản ứng với event đều chỉ liên quan thành công. Spring cho phép xử lý các nhánh kết thúc transaction khác nhau, nhưng phải phân biệt **quan sát thất bại** với **bù trừ nghiệp vụ đã xảy ra ở hệ thống ngoài**.

### 7.1. AFTER_ROLLBACK để ghi nhận kết quả thất bại

~~~java
package com.example.shop.orders.internal;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderRollbackObserver {

    private final OrderFailureMetrics metrics;

    OrderRollbackObserver(OrderFailureMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    void on(OrderConfirmationAttempted event) {
        metrics.incrementRollback(event.orderId());
    }
}
~~~

`OrderConfirmationAttempted` và `OrderFailureMetrics` là contract/tác vụ do ứng dụng định nghĩa. Nếu dùng `OrderConfirmed` như một sự thật đã thành công, phát nó rồi xử lý ở `AFTER_ROLLBACK` có thể gây hiểu nhầm về ngữ nghĩa. Với quan sát một **lần thử xác nhận**, nên đặt tên event phù hợp với điều thực sự đã xảy ra (ví dụ `OrderConfirmationAttempted`) hoặc dùng cơ chế transaction instrumentation riêng.

Chỉ số trong bộ nhớ hay telemetry có thể không cần ghi transaction mới; nếu callback rollback phải **lưu một bản ghi database bền vững**, cần mở transaction mới phù hợp, vì transaction nguồn đã rollback.

### 7.2. AFTER_COMPLETION không phân biệt tự động thành công/thất bại

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void clearRequestScopedCache(OrderConfirmationAttempted event) {
    cacheCleaner.clearLocalReference(event.orderId());
}
~~~

Đây là lựa chọn cho tác vụ cleanup phù hợp **bất kể outcome**. Không dùng `AFTER_COMPLETION` để gửi thông báo “đơn đã xác nhận” nếu transaction rollback cũng có thể đi vào nhánh này.

### 7.3. Rollback không hoàn tác tác dụng phụ ngoài database

Ví dụ:

~~~text
BEGIN TRANSACTION
  UPDATE orders ...
  CALL paymentProvider.charge(...)
  sau đó constraint DB bị lỗi
ROLLBACK TRANSACTION
~~~

Database của `orders` rollback nhưng payment provider có thể **đã thu tiền**. Nếu thiết kế yêu cầu bù trừ, cần một quy trình xác định kết quả giao dịch ngoài, phát yêu cầu hoàn tiền hoặc đối soát, có trạng thái và retry riêng. Không nên giả định callback `AFTER_ROLLBACK` tự có khả năng “đảo ngược” lời gọi ngoài.

Trong các quy trình phân tán, bù trừ (*compensation*) thường là **một hành động nghiệp vụ mới**, có thể thất bại và cần khôi phục, không phải một phép rollback nguyên tử của database gốc.

## 8. @ApplicationModuleListener: hậu commit, async và transaction riêng

Spring Modulith có `@ApplicationModuleListener` để đơn giản hóa cách viết transactional application event listener cho các module. Annotation này kết hợp ý định **xử lý sau commit**, **bất đồng bộ** và **transaction riêng** cho listener theo hạ tầng Spring Modulith và phiên bản được dùng.

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOrderListener {

    private final LoyaltyPointsService points;

    LoyaltyOrderListener(LoyaltyPointsService points) {
        this.points = points;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        points.awardForConfirmedOrder(
            event.eventId(),
            event.orderId()
        );
    }
}
~~~

`LoyaltyPointsService` là service nội bộ của `loyalty` cần thực hiện logic idempotent. Event `OrderConfirmed` phải là contract được module `orders` công bố (package API hoặc named interface) để module khác được phép tham chiếu.

### 8.1. Sự khác nhau khi một listener xảy ra lỗi

| Listener | Thời điểm chạy | Lỗi có thể tác động như thế nào? |
| --- | --- | --- |
| `@EventListener` đồng bộ | Trong đường publish, thường trước commit | Lỗi có thể truyền tới publisher và dẫn đến rollback nguồn |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit; mặc định không tự async | Không thể rollback transaction nguồn đã commit; có thể ảnh hưởng đường trả lỗi nếu callback đồng bộ ném exception |
| `@ApplicationModuleListener` | Hậu commit, async, transaction xử lý riêng | Nguồn đã commit; lỗi của listener phải được quan sát và khôi phục theo cơ chế phù hợp |

Đặc biệt, **không nên khẳng định mọi exception hậu commit đều hoàn toàn vô hình với HTTP caller**. Nếu callback đang chạy đồng bộ trong quá trình hoàn tất transaction, exception có thể ảnh hưởng việc trả response dù dữ liệu DB đã commit. Điều quan trọng là **transaction đã commit không thể bị rollback lại bằng exception đó**.

### 8.2. Async không tự mang theo transaction nguồn

Thread bất đồng bộ không tự kế thừa transaction imperative của thread phát event. Listener phải tạo transaction của mình khi cần ghi database; các `ThreadLocal` như MDC, security context hay tenant context cũng không nên được mặc định truyền.

Không chuyển entity JPA mutable qua event và mong truy cập lazy fields sau commit. Dùng ID hoặc snapshot bất biến cần thiết, rồi mở transaction truy vấn phù hợp trong module nhận.

### 8.3. Spring Modulith không thay thế thiết kế bất biến

Nếu việc đặt chỗ tồn kho là điều kiện bắt buộc trước khi xác nhận đơn, không nên phát `OrderConfirmed` rồi để listener hậu commit quyết định liệu đơn có đủ hàng hay không. Quy tắc đồng bộ đó phải được quyết định trong luồng nghiệp vụ nguồn, hoặc quy trình cần được chuyển thành state machine rõ ràng, chẳng hạn `PENDING_RESERVATION` trước khi thực sự `CONFIRMED`.

## 9. Spring transaction propagation: tác động tới event

Việc hiểu `@Transactional` ở service phát event giúp tránh những suy luận sai về commit và rollback.

### 9.1. REQUIRED tham gia transaction có sẵn

`Propagation.REQUIRED` thường là mặc định. Khi method được gọi từ một transaction đang tồn tại, nó có thể tham gia **cùng transaction vật lý**.

~~~java
@Transactional
public void checkout(UUID orderId) {
    orders.confirm(orderId); // Tham gia TX hiện có nếu dùng REQUIRED.
    billing.prepareInternalInvoice(orderId);
}
~~~

Nếu `orders.confirm(...)` phát `OrderConfirmed`, listener `AFTER_COMMIT` **không nhất thiết chạy khi method confirm trả về**. Nó chờ transaction đang bao ngoài `checkout(...)` hoàn tất. Nếu `billing.prepareInternalInvoice(...)` thất bại và transaction lớn rollback, callback `AFTER_COMMIT` không được thực thi.

### 9.2. REQUIRES_NEW tạo một mốc commit độc lập

Một method `REQUIRES_NEW` có thể commit riêng trong khi transaction bên ngoài vẫn tiếp tục.

~~~text
TX1 checkout bắt đầu
  |
  +-- TX2 (REQUIRES_NEW) ghi dữ liệu/ phát event
  |       |
  |       +-- TX2 COMMIT -> AFTER_COMMIT thuộc TX2 có thể chạy
  |
  +-- TX1 tiếp tục, rồi ROLLBACK
~~~

Do đó, event từ TX2 có thể được xử lý dù TX1 về sau rollback. Đây **không phải lỗi Spring**, mà là hệ quả của việc chọn transaction độc lập. Nếu cần một sự thật nghiệp vụ chỉ đúng sau khi toàn bộ checkout thành công, không phát event đó ở transaction con đã commit sớm mà không có ranh giới nghiệp vụ tương ứng.

### 9.3. NESTED/savepoint không đồng nghĩa transaction mới độc lập

`Propagation.NESTED`, khi transaction manager hỗ trợ, thường dùng savepoint trong transaction vật lý. Rollback về savepoint và rollback toàn bộ transaction có semantics khác với `REQUIRES_NEW`.

Không nên tự giả định transactional event listener có một “AFTER_COMMIT riêng cho savepoint” như một transaction độc lập. Cần kiểm tra hỗ trợ của Spring version/transaction manager và lựa chọn thiết kế rõ ràng nếu nghiệp vụ đòi các mốc commit riêng.

### 9.4. Đánh dấu rollback-only và UnexpectedRollbackException

Một method tham gia transaction hiện có có thể đánh dấu rollback-only. Dù code phía ngoài bắt exception và tiếp tục, cuối cùng transaction vẫn không thể commit. Khi outer method cố commit, Spring có thể báo `UnexpectedRollbackException` để tránh khiến caller tưởng đã commit thành công.

Event đã phát trong transaction đó **không trở thành sự thật đã commit**. Với listener `AFTER_COMMIT`, callback không được chạy cho kết quả rollback này.

### 9.5. @Transactional thông qua Spring proxy

Nếu service gọi method `@Transactional` của chính nó bằng `this.otherMethod()` khi dùng AOP proxy mặc định, interceptor có thể không được áp dụng. Ví dụ:

~~~java
@Service
class OrderService {

    void confirmFromBatch(UUID id) {
        confirm(id); // Self-invocation, không chắc đi qua proxy.
    }

    @Transactional
    public void confirm(UUID id) {
        // Có thể không có transaction mới nếu gọi như trên.
    }
}
~~~

Nếu event chỉ được xử lý bởi `@TransactionalEventListener` khi có transaction, lỗi self-invocation có thể làm listener **không chạy**. Cần kiểm tra entry point transaction thực tế, tách service bean nếu phù hợp hoặc dùng `TransactionTemplate` cho những trường hợp cần điều khiển tường minh.

## 10. Event publication registry nối transaction nguồn với listener

Vấn đề khó không chỉ là chọn `AFTER_COMMIT` mà còn là **điều gì xảy ra khi ứng dụng chết ngay sau commit**.

Spring Modulith có **event publication registry** để ghi nhận publication dành cho transactional listeners và theo dõi việc hoàn tất. Khi cấu hình backend lưu bền phù hợp với transaction nguồn, registry cho phép xác định những publication còn chưa hoàn tất để thực hiện recovery/resubmission theo chính sách.

### 10.1. Một event, nhiều publication

~~~text
OrderConfirmed E-123
   |
   +-- publication P1 -> notifications listener
   |
   +-- publication P2 -> reporting listener
   |
   +-- publication P3 -> loyalty listener
~~~

Nếu `notifications` hoàn tất nhưng `reporting` lỗi, publication P1 có thể được ghi completed trong khi P2 vẫn chờ xử lý. Registry theo dõi **trách nhiệm của từng listener**, không đơn thuần có một trạng thái chung “event xong”.

### 10.2. Commit và rollback với registry lưu bền

~~~mermaid
flowchart TD
    A[BEGIN transaction orders] --> B[Đổi trạng thái Order]
    B --> C[Phát OrderConfirmed]
    C --> D[Registry ghi publication được quản lý]
    D --> E{TX nguồn có commit?}
    E -->|Không| F[ROLLBACK dữ liệu và publication cùng transaction]
    E -->|Có| G[COMMIT dữ liệu và publication]
    G --> H[Listener xử lý hậu commit]
    H --> I{Thành công?}
    I -->|Có| J[Đánh dấu publication hoàn tất]
    I -->|Không| K[Publication cần kiểm tra / resubmit]
    K --> H
~~~

Sơ đồ mô tả nguyên tắc khi **registry backend thực sự tham gia transaction nguồn phù hợp**. Không được mặc định mọi backend/storage và mọi cấu hình đều có một transaction nguyên tử như vậy.

### 10.3. Registry không tự làm mọi listener bền vững

Cơ chế này gắn với những transactional event listeners được Spring Modulith quản lý theo phiên bản/cấu hình. Một `@EventListener` đồng bộ thuần Spring không tự biến thành message queue bền vững chỉ vì thêm dependency registry.

Để triển khai đáng tin cậy, cần xác định:

- Dự án đang dùng phiên bản Spring Modulith nào?
- Backend publication registry được cấu hình là JDBC, JPA, MongoDB hay giải pháp hỗ trợ khác?
- Transaction manager có quản lý **cùng nơi ghi nghiệp vụ và publication** không?
- Serializer có thể đọc event đã lưu qua các lần deploy mới không?
- Listener nào được registry theo dõi?
- Chính sách restart, retry và resubmit được kích hoạt/điều hành thế nào?

### 10.4. Khi nào publication được coi đã hoàn tất?

Khi listener kết thúc thành công theo ngữ nghĩa cơ chế theo dõi, publication tương ứng có thể được đánh dấu completed.

**Không nên nuốt exception của tác vụ bắt buộc:**

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        points.awardForConfirmedOrder(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException ex) {
        log.error("Award points failed", ex);
        // Sai nếu vẫn return bình thường trong khi điểm chưa được ghi.
    }
}
~~~

Nếu lỗi cần retry bị bắt rồi bỏ qua, framework có thể coi listener đã xử lý thành công và đánh dấu completed dù kết quả nghiệp vụ chưa đạt. Cách phù hợp là truyền lỗi ra sau khi log có ngữ cảnh, hoặc chuyển sang quy trình xử lý lỗi có trạng thái minh bạch.

~~~java
@ApplicationModuleListener
void on(OrderConfirmed event) {
    try {
        points.awardForConfirmedOrder(
            event.eventId(), event.orderId()
        );
    } catch (RuntimeException ex) {
        log.error(
            "Could not award points, eventId={}",
            event.eventId(),
            ex
        );
        throw ex;
    }
}
~~~

Không nên gọi API “mark completed” thủ công nếu chưa xác định chính xác publication/target và contract thành công. Với listener được quản lý thông thường, để framework theo dõi kết quả xử lý là cách phù hợp hơn.

## 11. Cửa sổ lỗi giữa commit, side effect và completion

Một hệ thống có thể hỏng ở **bất kỳ** khoảng thời gian nào:

| Điểm xảy ra lỗi | Tình trạng nghiệp vụ | Rủi ro | Cần thiết kế |
| --- | --- | --- | --- |
| Trước transaction nguồn commit | Dữ liệu chưa commit | Listener đồng bộ đã gọi hệ thống ngoài quá sớm | Hậu commit cho side effect hoặc mô hình bù trừ |
| TX nguồn rollback | Đơn không được xác nhận | Event đã được phát trong bộ nhớ | Không coi `publishEvent` là bằng chứng commit |
| Sau commit nhưng trước khi listener được gọi | Đơn đã xác nhận | Mất công việc nếu chỉ có event trong RAM | Registry/outbox bền vững |
| Trong lúc listener ghi DB | Đơn nguồn đã commit | Module nhận có thể rollback độc lập | Transaction listener rõ ràng, retry |
| Side effect đã thành công nhưng chưa ghi completion | Đơn nguồn đã commit, tác vụ có thể đã xảy ra | Retry gây trùng | Idempotency/deduplication |
| Publication completed nhưng consumer broker chưa xử lý | Producer đã giao theo semantics adapter | Downstream còn lag hoặc lỗi | ACK/offset/quan sát ở consumer |
| Event cũ resubmit sau event mới | Trạng thái aggregate có thể đã tiến lên | Áp dụng sai thứ tự | Version/state machine/ordering |

### 11.1. Sơ đồ crash-window khó nhất

~~~mermaid
sequenceDiagram
    participant Reg as Registry
    participant L as Loyalty listener
    participant DB as Loyalty DB

    Reg-->>L: Giao OrderConfirmed E-123
    L->>DB: BEGIN TX2
    L->>DB: Cộng điểm và lưu dấu eventId
    L->>DB: COMMIT TX2
    Note over L,Reg: Process crash trước khi mark completed
    Reg->>Reg: Publication còn chưa hoàn tất
    Reg-->>L: Resubmit E-123
    L->>DB: Kiểm tra eventId đã xử lý
    DB-->>L: Đã có, bỏ qua cộng điểm
    L-->>Reg: Thành công
    Reg->>Reg: Mark completed
~~~

Đây là tình huống cho thấy **độ bền và xử lý đúng một lần không phải cùng một vấn đề**. Registry giúp phát hiện công việc cần khôi phục; listener phải chấp nhận việc có thể nhận lại event.

## 12. Retry và idempotency sau commit

### 12.1. Vì sao retry không thể bị loại bỏ hoàn toàn?

Một listener có thể timeout khi gọi hệ thống ngoài. Timeout không cho biết thao tác đã thất bại hay thực tế đã thành công nhưng response bị mất. Nếu retry, tác vụ có thể bị thực hiện hai lần.

Đừng hứa `exactly-once` end-to-end chỉ vì sử dụng event registry hoặc một broker có cơ chế transaction. Từ transaction nguồn tới listener, database đích và nhà cung cấp ngoài vẫn có những điểm lỗi độc lập.

### 12.2. Dùng eventId để chống xử lý lặp

Ví dụ bảng ghi những event đã áp dụng trong database của `loyalty`:

~~~sql
CREATE TABLE loyalty_processed_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudocode trong transaction của module nhận:

~~~text
on OrderConfirmed(event):
    BEGIN TX loyalty
      INSERT event.eventId vào loyalty_processed_events
      nếu xảy ra unique conflict:
          không cộng điểm lần nữa
      nếu insert mới:
          cộng điểm cho orderId theo chính sách loyalty
    COMMIT TX loyalty
    hoàn tất listener
~~~

**Điểm quan trọng:** việc ghi dấu `eventId` và cập nhật điểm phải được phối hợp trong **cùng transaction local** khi khả thi. Nếu kiểm tra tồn tại rồi cập nhật ngoài transaction, hai worker có thể cùng thấy “chưa xử lý” và cộng điểm hai lần.

Với email hoặc thanh toán qua provider ngoài, local DB transaction không bảo vệ việc gọi API đã xảy ra. Cần idempotency key được provider hỗ trợ, trạng thái gửi có thể đối soát hoặc quy trình bù trừ thích hợp.

### 12.3. Đừng sinh eventId mới khi resubmit

**Resubmit** là thử giao lại publication của **sự kiện cũ**. Nếu tạo một `UUID.randomUUID()` mới cho cùng tác vụ khi retry, consumer có thể coi đó là event hoàn toàn mới và mất khả năng deduplicate.

Một order có thể phát nhiều sự kiện hợp lệ theo thời gian; không nên dùng `orderId` thay thế `eventId` cho mọi tình huống. Chọn khóa idempotency theo ý nghĩa nghiệp vụ: cùng `eventId`, hoặc khóa nghiệp vụ duy nhất như “mỗi đơn chỉ có một lần tặng điểm xác nhận”.

### 12.4. Thông điệp đến trễ và thứ tự

Sau rollback, retry hoặc restart, một publication cũ có thể được xử lý **sau một event mới hơn**. Nếu consumer duy trì trạng thái:

- Dùng `aggregateVersion` hoặc một sequence có ý nghĩa nếu cần phát hiện event cũ.
- Áp dụng optimistic locking/compare-and-set khi cập nhật concurrent.
- Không coi timestamp của event hoặc publication là một total order toàn hệ thống.
- Nếu cần xử lý đủ mọi bước theo thứ tự, thiết kế buffer/state machine hoặc dispatcher theo khóa được kiểm chứng.

Registry theo dõi publication; nó **không mặc nhiên** là một workflow engine hay một FIFO queue toàn cục.

## 13. Dual write và sự khác biệt với transactional outbox

Ngay cả khi producer đợi commit rồi mới gửi message tới broker, vẫn có bài toán **dual write**:

~~~text
BEGIN TX database
  UPDATE orders ...
COMMIT TX database

send Kafka message
~~~

Nếu ứng dụng chết ngay sau `COMMIT` nhưng trước khi gửi Kafka, message có thể không đến broker. Nếu gửi **trước commit**, broker có thể nhận thông điệp cho một transaction sau đó rollback.

### 13.1. Registry giúp xử lý phần nào?

Với externalization phù hợp, Spring Modulith event publication registry có thể lưu **nghĩa vụ gửi** trong transaction nguồn, rồi theo dõi việc adapter xử lý/gửi thành công. Khi gửi thất bại, publication chưa hoàn tất có thể được kiểm tra và resubmit theo cơ chế/chính sách thích hợp.

### 13.2. Một outbox chuyên dụng khác gì?

Một **transactional outbox** lưu message/outbox record trong cùng transaction nguồn, rồi một dispatcher độc lập đọc và chuyển message sang broker với retry, claim, quản lý nhiều instance và các yêu cầu vận hành khác. Mức bảo đảm thực tế phụ thuộc implementation.

| Đặc tính | Event publication registry + transactional listener | Outbox chuyên dụng |
| --- | --- | --- |
| Theo dõi publication liên quan transaction nguồn | Có, khi cấu hình backend đúng | Có, theo thiết kế outbox |
| Ghi dấu xử lý theo listener/target | Trọng tâm của registry | Tùy data model outbox |
| Phục hồi sau lỗi gửi | Có khả năng hỗ trợ resubmit | Thường có dispatcher và retry policy |
| Điều phối nhiều instance, claim, ordering | Phải đánh giá theo backend/phiên bản | Phụ thuộc vào outbox engine |
| Bảo đảm consumer ngoài đã xử lý | Không | Không |

Không nên giả định mọi chế độ externalization của mọi phiên bản Spring Modulith đều hỗ trợ outbox giống nhau. Khi chọn backend hoặc tích hợp outbox chuyên dụng, cần đối chiếu documentation và dependency của phiên bản dự án trước khi triển khai.

### 13.3. Broker accepted không bằng consumer processed

Khi externalizer hoàn tất nhiệm vụ gửi, registry phía producer có thể đánh dấu publication completed theo semantics adapter. Điều đó **không chứng minh** consumer ngoài đã ghi database hoặc hoàn tất nghiệp vụ.

Do đó cần theo dõi riêng:

1. **Business database committed** ở producer.
2. **Publication registered** trong registry/outbox.
3. **Broker accepted** message theo cơ chế xác nhận transport.
4. **Consumer processed** và commit/ACK tiến độ riêng.

Không dùng một trạng thái completed để suy ra mọi hệ thống đã đồng bộ.

## 14. Kiểm thử commit và rollback đúng cách

Kiểm thử application events cần tách:

- Publisher có tạo đúng event khi điều kiện nghiệp vụ hợp lệ?
- Listener được kích hoạt đúng pha commit/rollback?
- Transaction mới ở module nhận có commit?
- Publication trong registry có thể được khôi phục?
- Retry có gây side effect trùng không?

### 14.1. Bẫy của test có @Transactional

Spring Test thường rollback transaction của test `@Transactional` khi kết thúc. Nếu test chỉ gọi publisher và chờ listener `AFTER_COMMIT`, callback có thể **không bao giờ chạy**, dù cấu hình production đúng.

Một ví dụ kiểm soát commit bằng Spring Test:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class AfterCommitFlowTest {

    @Autowired OrderManagement orders;
    @Autowired SalesProjectionRepository projections;

    @Test
    void processesOnlyAfterSourceCommit() {
        UUID orderId = createValidOrderFixture();

        orders.confirm(orderId);

        TestTransaction.flagForCommit();
        TestTransaction.end(); // Commit transaction của test.

        // Nếu listener async, chờ bằng polling có timeout.
        awaitProjection(orderId);
        assertThat(projections.existsFor(orderId)).isTrue();
    }

    private UUID createValidOrderFixture() {
        throw new UnsupportedOperationException("Provide test fixture");
    }

    private void awaitProjection(UUID orderId) {
        throw new UnsupportedOperationException("Wait with timeout");
    }
}
~~~

Đây là **khung integration test**: `OrderManagement`, repository, fixture và helper chờ là thành phần cần triển khai trong dự án. `TestTransaction` chỉ dùng được khi Spring Test đã quản lý transaction của test; `@Transactional` được áp dụng theo cấu hình thích hợp. Không nên coi khung trên là một test tự chạy độc lập.

Nếu listener chạy async, hãy kiểm tra kết quả **cuối cùng bằng điều kiện có timeout** (ví dụ Awaitility), không dùng `Thread.sleep(...)` cố định. Kiểm tra trong transaction độc lập nếu muốn xác thực database thật sự đã commit.

### 14.2. Test rollback

Test cần xác minh:

1. Một transaction nguồn đã phát event nhưng sau đó rollback.
2. Database nguồn không lưu trạng thái thành công.
3. `AFTER_COMMIT` listener **không** tạo hậu quả.
4. `AFTER_ROLLBACK` callback (nếu được khai báo) xử lý đúng một lần theo ngữ nghĩa test.
5. Không còn publication đã commit dành cho kết quả nguồn không tồn tại nếu backend registry tham gia transaction nguồn như thiết kế.

Không nên giả định “test không thấy email” chỉ vì mock chưa được kiểm tra; cần xác nhận listener đăng ký đúng và transaction đã thực sự rollback.

### 14.3. Test listener lỗi sau khi nguồn commit

Kịch bản:

~~~text
TX nguồn commit OrderConfirmed
reporting listener bắt đầu
reporting DB bị lỗi
listener ném RuntimeException
source vẫn ở CONFIRMED
publication của reporting còn cần xử lý (khi registry phù hợp)
khôi phục DB -> resubmit publication
projection được ghi một lần
~~~

Test này chứng minh **transaction independence** và **recovery**. Hãy đọc trạng thái DB nguồn, DB module nhận và registry thay vì chỉ xác minh mock listener được gọi.

### 14.4. Ma trận test

| Trường hợp | Kết quả cần có |
| --- | --- |
| Publish trong transaction và commit | Listener `AFTER_COMMIT` được chạy theo cấu hình |
| Publish rồi rollback | Không có side effect hậu commit |
| Publish ngoài transaction | Listener transactional không chạy, trừ khi có fallback |
| Listener đồng bộ ném runtime exception | Xác minh rollback rule của transaction nguồn |
| Listener AFTER_COMMIT ghi DB | Có transaction mới và commit thật |
| Listener AFTER_COMMIT lỗi | Không rollback được dữ liệu nguồn đã commit |
| Hai listener, một lỗi | Publication/trạng thái xử lý độc lập |
| Process chết sau commit | Publication còn có thể khôi phục nếu registry được cấu hình đúng |
| Xử lý lại cùng eventId | Không nhân đôi tác dụng phụ |
| Event cũ xử lý sau event mới | Consumer không ghi đè trạng thái sai |
| Thay đổi schema khi còn publication cũ | Có thể deserialize hoặc migration rõ ràng |

### 14.5. Kiểm tra module boundary

Spring Modulith có `ApplicationModules` để xác minh phụ thuộc mã nguồn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là kiểm tra cấu trúc giữa các application module; **không thay thế** test commit/rollback, registry persistence, async hoặc idempotency. `@ApplicationModuleTest` và `PublishedEvents` có thể hữu ích để xác minh event đã phát trong phạm vi module, nhưng chúng không tự chứng minh việc listener hậu commit thực hiện thành công.

## 15. Quan sát transaction và event trong môi trường thật

Khi gặp sự cố “đơn đã xác nhận nhưng thông báo không đến”, cần phân tích theo **mốc trạng thái**, không chỉ xem log của method publisher.

### 15.1. Bốn loại câu hỏi vận hành

**Nghiệp vụ nguồn:** Transaction có commit thật không? Order đang ở trạng thái nào? Có rollback do constraint hoặc transaction bị đánh dấu rollback-only không?

**Publication:** Event có được phát trong transaction phù hợp không? Listener có thuộc diện registry theo dõi? Có publication chưa hoàn tất theo event và target không?

**Listener:** Handler đã chạy chưa? Có exception, timeout, duplicate, version/schema không tương thích hoặc thiếu transaction ghi mới không?

**Hệ thống ngoài:** Broker có chấp nhận message không? Consumer có backlog/lag không? Email provider có trả kết quả không? Có tác dụng phụ đã xảy ra nhưng response bị mất không?

### 15.2. Các dấu hiệu nên đo

| Metric / dữ liệu quan sát | Mục đích |
| --- | --- |
| `order_confirmed_committed_total` | Số kết quả nghiệp vụ xác nhận thành công, nếu có instrumentation chính xác |
| `event_publications_incomplete` | Số publication còn cần xử lý |
| `event_publication_oldest_age` | Tuổi của publication chưa hoàn tất lâu nhất |
| `listener_failures_total` | Tần suất lỗi theo listener/event type |
| `listener_processing_duration` | Độ trễ xử lý hậu commit |
| `listener_retries_total` | Tần suất phát lại |
| `event_duplicates_skipped_total` | Số event trùng đã được consumer phát hiện |
| `broker_consumer_lag` | Consumer ngoài có theo kịp producer không |

Đây là **tên metric minh họa**, không khẳng định Spring Modulith tự phát hành các tên này. Cần chọn các nguồn đo lường tương ứng và không đưa thông tin cá nhân vào label có cardinality cao.

### 15.3. Log theo event và publication

~~~json
{
  "eventType": "OrderConfirmed",
  "eventId": "12aa30a5-a78d-43cb-a98d-dc69623e31b7",
  "aggregateId": "16cc7f1b-38f0-4b46-baa9-d963be8a9294",
  "module": "reporting",
  "listener": "SalesProjectionListener",
  "phase": "AFTER_COMMIT",
  "publicationState": "incomplete",
  "attempt": 2,
  "errorCategory": "database_timeout"
}
~~~

Schema log trên do ứng dụng tự thiết kế; trạng thái thật trong publication registry phụ thuộc backend và phiên bản. Hạn chế log toàn bộ payload có thông tin riêng tư. Dùng `eventId`/correlation ID để nối các mốc, nhưng không nhầm `traceId` với bằng chứng commit.

## 16. Những sai lầm thường gặp

### “publishEvent trả về tức là đơn hàng đã commit”

Sai. Event có thể được phát ngay trong method đang chạy transaction. Database có thể rollback ở bước sau hoặc khi commit.

### “saveAndFlush là đã commit”

Sai. Flush không phải commit. Lời gọi ngoài hệ thống vẫn phải đợi commit nếu chỉ hợp lệ sau khi dữ liệu nguồn bền vững.

### “@EventListener đồng bộ luôn chạy sau commit”

Sai. Trong cấu hình mặc định, listener đồng bộ thường chạy ngay lúc publish event, khi transaction nguồn chưa hoàn tất.

### “@TransactionalEventListener(AFTER_COMMIT) tự async”

Sai. Transaction phase và thread/executor là hai khái niệm khác nhau; callback có thể vẫn chạy trên thread đang hoàn tất transaction.

### “Đã AFTER_COMMIT thì ghi repository sẽ tự commit”

Sai. Resource của transaction nguồn có thể vẫn gắn với thread; ghi mới cần transaction rõ ràng, chẳng hạn gọi bean khác có `REQUIRES_NEW`.

### “Exception sau commit sẽ rollback được nghiệp vụ nguồn”

Sai. Transaction đã commit không thể được rollback lại. Lỗi hậu commit cần được theo dõi và xử lý riêng.

### “@Async kế thừa transaction của publisher”

Sai với transaction imperative thông thường. Thread khác cần transaction riêng và không được tin vào request/transaction context của thread nguồn.

### “Đặt @Transactional trên method rồi gọi this.method() là đủ”

Không nhất thiết. Self-invocation khi dùng proxy mặc định có thể bỏ qua transaction interceptor, khiến event phát ra không có transaction như kỳ vọng.

### “Có registry nghĩa là mọi event sẽ tự retry vô hạn”

Sai. Registry ghi nhận publication theo phạm vi hỗ trợ; recovery/resubmit phải theo phiên bản, backend và cấu hình/chính sách. Retry vô hạn còn có thể làm quá tải hệ thống hoặc lặp lỗi dữ liệu.

### “Registry completed nghĩa là hệ thống bên ngoài đã xử lý xong”

Sai. Completion ở producer hoặc listener chỉ nói về nhiệm vụ đã được theo dõi; ACK của broker, consumer transaction và tác dụng phụ phía đối tác có vòng đời khác.

### “Transaction nguồn commit, listener chắc chắn chạy đúng một lần”

Sai. Có thể crash trước khi listener chạy hoặc sau khi side effect thành công nhưng trước khi ghi completion. Cần cơ chế lưu publication, retry và idempotency tương ứng.

## 17. Bài tập thực hành: xác nhận đơn an toàn khi commit và rollback

### 17.1. Bối cảnh

Ứng dụng Spring Modulith có ba application module:

- `orders` sở hữu đơn và trạng thái xác nhận.
- `notifications` gửi email xác nhận.
- `loyalty` tích điểm khi đơn được xác nhận.

Ban đầu service thực thi:

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.confirm();
    publisher.publishEvent(new OrderConfirmed(
        UUID.randomUUID(), orderId, clock.instant()
    ));
}
~~~

Hai listener hiện dùng `@EventListener` và gọi email provider/tăng điểm. Trong thực tế:

1. Một số đơn rollback do constraint nhưng email vẫn đã được gửi.
2. Khi database `loyalty` tạm ngừng, request xác nhận đơn thất bại theo exception của listener.
3. Sau restart, có đơn đã commit nhưng listener chưa hoàn tất.
4. Một số đơn được tích điểm hai lần khi vận hành phát lại event.

### 17.2. Yêu cầu thiết kế lại

1. Giữ điều kiện xác nhận đơn trong transaction `orders`; chỉ phát `OrderConfirmed` sau khi aggregate xác lập trạng thái hợp lệ.
2. Đảm bảo email chỉ được gửi khi transaction nguồn commit thành công.
3. Chuyển tác vụ `loyalty` sang xử lý hậu commit có transaction riêng nếu cho phép eventual consistency.
4. Cấu hình publication registry bền vững và chính sách phục hồi phù hợp với mức độ tin cậy yêu cầu.
5. Thiết kế `eventId` ổn định để listener có thể phát hiện duplicate.
6. Với `loyalty`, lưu dấu event đã xử lý cùng transaction tăng điểm.
7. Với email provider, đánh giá idempotency key hoặc quy trình gửi/đối soát.
8. Tạo test commit, rollback, listener lỗi, resubmit và crash-window.
9. Theo dõi publication chưa hoàn tất và kết quả nghiệp vụ riêng từng module.

### 17.3. Phương án luồng hợp lý

~~~mermaid
flowchart TD
    A[API yêu cầu confirm] --> B[orders: BEGIN TX]
    B --> C[Kiểm tra bất biến + cập nhật Order]
    C --> D[Phát OrderConfirmed]
    D --> E[Registry ghi publication nếu cấu hình]
    E --> F{TX nguồn kết thúc}
    F -->|ROLLBACK| G[Không có thông báo hậu commit]
    F -->|COMMIT| H[notifications: xử lý sau commit]
    F -->|COMMIT| I[loyalty: transaction xử lý riêng]
    H --> J{Email thành công?}
    J -->|Không| K[Retry / đối soát theo chính sách]
    J -->|Có| L[Publication hoàn tất]
    I --> M{Tăng điểm thành công?}
    M -->|Không| N[Publication cần khôi phục]
    M -->|Có| O[Publication hoàn tất]
~~~

### 17.4. Checklist nghiệm thu

- [ ] Transaction nguồn commit/rollback đúng theo quy tắc nghiệp vụ.
- [ ] Không gửi email xác nhận cho transaction rollback.
- [ ] Lỗi listener hậu commit không khiến dữ liệu nguồn đã commit bị mất.
- [ ] Listener ghi DB có transaction riêng với kết quả commit có thể xác minh.
- [ ] Registry ghi publication theo từng listener và có khả năng quan sát.
- [ ] Có cơ chế resubmit đối với publication chưa hoàn tất theo cấu hình.
- [ ] Cùng `eventId` được xử lý lại mà không cộng điểm hai lần.
- [ ] Đã phân biệt hoàn tất của producer với xử lý thành công của email provider.
- [ ] Có test thực sự commit transaction trong môi trường Spring Test.
- [ ] Có kiểm tra trường hợp publisher phát ngoài transaction và self-invocation.
- [ ] Log đủ `eventId`, listener và trạng thái lỗi nhưng không rò rỉ dữ liệu cá nhân.

## 18. Câu hỏi tự kiểm tra

1. `publishEvent(...)` trả về bình thường có chứng minh database đã commit chưa? Vì sao?
2. Vì sao `@EventListener` đồng bộ có thể làm email gửi dù transaction nguồn rollback?
3. Khi nào `@TransactionalEventListener(AFTER_COMMIT)` chạy và khi nào nó bị bỏ qua?
4. Sự khác nhau giữa `AFTER_COMMIT` và `@Async` là gì?
5. Vì sao việc ghi database trong callback sau commit cần cân nhắc `REQUIRES_NEW`?
6. Khi service `confirm()` tham gia transaction `checkout()` lớn hơn, listener hậu commit chờ mốc nào?
7. `REQUIRES_NEW` có thể tạo ra tình huống event được xử lý dù outer transaction rollback thế nào?
8. `@TransactionalEventListener(AFTER_ROLLBACK)` có tự rollback tác vụ gửi email bên ngoài không?
9. Registry giúp gì khi ứng dụng dừng sau commit nhưng trước khi listener xử lý?
10. Tại sao registry không tự bảo đảm consumer chỉ thực thi đúng một lần?
11. Khi listener ghi điểm thành công nhưng chưa mark completed, resubmit cần hành xử thế nào?
12. Vì sao `saveAndFlush(...)` không thể thay cho việc chờ commit?
13. Làm thế nào kiểm thử listener sau commit khi test `@Transactional` thường tự rollback?
14. Vì sao không thể dùng một metric “publication pending = 0” để suy ra toàn bộ quy trình ngoài hệ thống đã hoàn tất?

## 19. Tài liệu đối chiếu và nguyên tắc kết luận

Để triển khai với API và dependency đúng phiên bản, tham khảo các tài liệu chính thức:

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): transaction phase, fallback và reactive transaction context.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED` và các hệ quả transaction.
- [Spring Framework — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): ý nghĩa của callback sau commit và tài nguyên transaction.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, event publication registry và các cơ chế tích hợp liên quan.

**Ghi nhớ:** Commit và rollback xác định **sự thật nghiệp vụ nào thực sự tồn tại**. Application event chỉ nên được sử dụng theo transaction phase phù hợp với ý nghĩa đó. Với Spring Modulith, event publication registry giúp nối kết transaction nguồn với trách nhiệm xử lý của listener, nhưng độ tin cậy thực tế vẫn cần transaction riêng cho hậu quả sau commit, cơ chế khôi phục, idempotency, versioning và kiểm thử các điểm lỗi. Không thay thế thiết kế nghiệp vụ bằng giả định rằng event đã phát, listener đã chạy hoặc publication đã completed đồng nghĩa tất cả hệ thống đã nhất quán.
