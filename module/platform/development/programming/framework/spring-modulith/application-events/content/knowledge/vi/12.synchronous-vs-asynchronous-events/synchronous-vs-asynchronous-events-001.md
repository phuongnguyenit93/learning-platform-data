# Xử lý synchronous

## Mục tiêu bài học

Trong Spring Modulith, nhiều module nghiệp vụ cùng tồn tại trong một ứng dụng Spring Boot và có thể cộng tác thông qua **application events**. Cách mặc định của Spring khi phân phối một event cho `@EventListener` thông thường là **synchronous** (đồng bộ): listener được gọi trên luồng thực thi của bên phát event, trong quá trình gọi `ApplicationEventPublisher.publishEvent(...)`.

Cách xử lý này đơn giản, dễ dự đoán và có thể tham gia cùng transaction nguồn. Tuy nhiên, nó cũng khiến **thời gian xử lý, exception và side effect của listener tác động trực tiếp đến producer**. Nếu không phân biệt thời điểm publish với thời điểm commit, ứng dụng có thể gửi email cho đơn hàng vừa rollback hoặc giữ transaction database mở trong lúc gọi một API ngoài rất chậm.

Bài này thuộc chương **Đồng bộ và bất đồng bộ** của mô-đun **SPRING_MODULITH_APPLICATION_EVENTS**: tổ chức giao tiếp giữa các module qua application events để giảm phụ thuộc mã nguồn, bảo vệ ranh giới nghiệp vụ, đồng thời hiểu cách phối hợp publisher, listener, transaction, xử lý sau commit, Event Publication Registry, kiểm thử và quan sát quá trình giao sự kiện đáng tin cậy.

Sau khi học, bạn cần:

1. Giải thích chính xác **listener synchronous chạy lúc nào, trên luồng nào**, và khi nào `publishEvent(...)` trả về.
2. Nhận diện những hệ quả của **exception, rollback, fan-out, thứ tự gọi listener và latency**.
3. Phân biệt `@EventListener` mặc định với `@TransactionalEventListener(AFTER_COMMIT)` **không gắn `@Async`**, cũng như với `@ApplicationModuleListener` bất đồng bộ.
4. Thiết kế ví dụ có một producer, hai consumer và kiểm thử được sự khác nhau giữa thực thi đồng bộ trước commit với xử lý sau commit.
5. Quyết định khi nào nên dùng synchronous event, khi nào nên gọi API đồng bộ trực tiếp, và khi nào chuyển phản ứng sang listener hậu commit có cơ chế phục hồi.

## 1. Synchronous application event là gì?

**Synchronous** nói về **cách một lời gọi listener được thực thi**: producer phát event và lời gọi tới listener thông thường được xử lý ngay trong luồng đó, thay vì được xếp để một thread khác xử lý sau. Với cấu hình mặc định của Spring, việc phát event diễn ra gần giống một lời gọi hàm đồng bộ qua cơ chế phân phối event:

~~~text
orders.recordPayment(...)
    ├── cập nhật dữ liệu nghiệp vụ
    ├── publisher.publishEvent(OrderPaid)
    │     ├── audit.on(OrderPaid)       [chạy đồng bộ]
    │     └── metrics.on(OrderPaid)     [chạy đồng bộ]
    └── tiếp tục code sau publishEvent(...)
~~~

Đối với các listener đồng bộ thông thường:

- `publishEvent(...)` gọi vào hạ tầng phân phối event, nơi chọn listener phù hợp và lần lượt thực thi lời gọi.
- Listener chạy **trước khi** producer tiếp tục qua vị trí gọi `publishEvent(...)`, miễn là mọi lời gọi liên quan hoàn tất bình thường.
- Listener có thể thấy một transaction còn đang mở của producer nếu event được phát trong transaction và listener dùng cùng transaction resource.
- Exception của listener có thể được truyền ngược về producer nếu hạ tầng không cấu hình cách xử lý lỗi khác.
- Việc listener chạy đồng bộ **không đồng nghĩa** event đã được ghi bền vững, mọi transaction đã commit, hay side effect ngoài hệ thống có thể rollback.

Cần hiểu rõ một điểm: `ApplicationEventPublisher` **không cam kết trong API rằng mọi cách phân phối đều đồng bộ**. Hành vi đồng bộ ở đây là hành vi của **`SimpleApplicationEventMulticaster` mặc định khi không cấu hình executor bất đồng bộ**, với những listener thông thường không tự chọn cơ chế async.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / Producer
    participant Events as Spring event multicaster
    participant Audit as audit / @EventListener
    participant Metrics as metrics / @EventListener
    Client->>Orders: recordVerifiedPayment(...)
    Orders->>Orders: Thay đổi trạng thái trong T1
    Orders->>Events: publishEvent(OrderPaid)
    Events->>Audit: on(OrderPaid)
    Audit-->>Events: return
    Events->>Metrics: on(OrderPaid)
    Metrics-->>Events: return
    Events-->>Orders: publishEvent trả về
    Orders->>Orders: Hoàn tất phương thức
    Note over Orders: T1 thường commit khi lời gọi @Transactional kết thúc
    Orders-->>Client: Kết quả
~~~

Sơ đồ cho thấy một **đường thực thi điển hình**, không bảo đảm mọi hệ thống có chính xác thứ tự `audit → metrics`. Thứ tự listener được xem xét ở phần sau và không nên dùng làm quy tắc nghiệp vụ nếu thiếu cơ chế điều phối cụ thể.

## 2. Synchronous là thuộc tính của việc thực thi, không phải tên loại event

`OrderPaid` là một **sự kiện nghiệp vụ**: đơn hàng đã được ghi nhận thanh toán theo điều kiện hợp lệ. Bản thân record `OrderPaid` không mang tính “đồng bộ” hay “bất đồng bộ”. Chính **cách consumer đăng ký và hạ tầng thực thi** quyết định đặc điểm đó.

| Yếu tố | Quyết định điều gì? | Không quyết định điều gì? |
| --- | --- | --- |
| `OrderPaid` record | Ý nghĩa, định danh, payload của sự kiện | Thread, transaction và lịch gọi listener |
| `ApplicationEventPublisher` | Điểm publish event vào cơ chế ứng dụng | Mặc nhiên không chứng minh mọi listener đã commit |
| `@EventListener` | Một method quan tâm event nào | Không buộc chạy sau commit |
| `SimpleApplicationEventMulticaster` | Cách phân phối, gồm khả năng dùng executor | Không biến listener thành message broker |
| `@TransactionalEventListener` | Pha transaction mà listener được kích hoạt | Không tự bật `@Async` hoặc tạo transaction mới |
| `@ApplicationModuleListener` | Tiện ích Modulith cho xử lý sau commit, bất đồng bộ và transaction mới | Không loại bỏ nhu cầu idempotency và cấu hình độ bền |

**Điều quan trọng:** cùng một `OrderPaid` có thể có một listener `@EventListener` chạy đồng bộ ngay lúc publish và một listener `@ApplicationModuleListener` chạy sau commit, bất đồng bộ. Producer không nhất thiết biết hoặc kiểm soát từng cách nhận đó.

## 3. Ví dụ: producer phát event giữa các module

Một ứng dụng bán hàng gồm `orders`, `audit`, `notifications` và `loyalty`.

- **orders** sở hữu trạng thái đơn, xác thực chuyển trạng thái thanh toán và công bố `OrderPaid`.
- **audit** ghi bản ghi kiểm toán nội bộ vào database.
- **notifications** tạo yêu cầu gửi email sau khi giao dịch nguồn được commit.
- **loyalty** cập nhật điểm thưởng với cơ chế chống lặp.

Để tập trung vào synchronous, trước tiên cho `audit` dùng listener đồng bộ. Các phản ứng ngoài hoặc có thể chậm sẽ được so sánh sau.

### Hợp đồng event công khai

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Nếu record nằm trong package con `orders.events`, module `orders` có thể công bố package đó bằng `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Một consumer muốn giới hạn phụ thuộc vào tập event có thể dùng `@ApplicationModule(allowedDependencies = "orders::events")` trong package gốc của chính module đó. Việc Java khai báo `public record` **không tự biến mọi package con thành API module hợp lệ** theo quy tắc kiểm tra cấu trúc của Spring Modulith.

### Producer dùng `ApplicationEventPublisher`

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa, chỉ true khi có transition mới.
        if (!order.markPaidIfNew(paymentId)) {
            return;
        }

        orders.save(order);

        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                paymentId,
                clock.instant()
        ));
    }
}
~~~

Các kiểu `Order`, `OrderRepository` và phương thức `markPaidIfNew` thuộc miền nghiệp vụ **minh họa**, cần được triển khai trong module `orders`. Phương thức trên giả định thông tin thanh toán đã được xác thực ở một bước trước đó, không cho phép tin vào `paymentId` tùy ý từ client.

Trình tự mong muốn là **xác nhận transition nghiệp vụ → lưu trong transaction → publish event trong transaction**. Ở thời điểm `publishEvent` được gọi, transaction của `@Transactional` vẫn có thể đang mở; database chưa nhất thiết commit.

### Consumer đồng bộ trong module khác

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class RecordOrderPaidAudit {

    private final AuditEntryRepository auditEntries;

    RecordOrderPaidAudit(AuditEntryRepository auditEntries) {
        this.auditEntries = auditEntries;
    }

    @EventListener
    void on(OrderPaid event) {
        auditEntries.save(AuditEntry.paymentRecorded(
                event.eventId(), event.orderId(), event.occurredAt()
        ));
    }
}
~~~

`AuditEntry` và `AuditEntryRepository` là các thành phần ví dụ của `audit`. Đoạn code chỉ có ý nghĩa **chung transaction với producer** khi hai module dùng cùng transaction manager/database resource, listener được gọi trên cùng thread và thao tác repository tham gia transaction nguồn. Synchronous **không tự tạo một distributed transaction** nếu mỗi module dùng database hay resource manager khác nhau.

Nếu thao tác audit tham gia **cùng transaction T1**, khi T1 rollback thì bản ghi audit cũng rollback. Nếu việc ghi audit thất bại khiến exception lan ra, T1 cũng có thể rollback theo quy tắc transaction Spring. Đây có thể là hành vi mong muốn cho dữ liệu *phải ghi cùng nhau*, nhưng tạo một mức **runtime coupling** mạnh giữa modules.

## 4. Hành vi cụ thể của `@EventListener` đồng bộ

Giả sử `orders.recordVerifiedPayment(...)` được gọi từ ngoài Spring proxy để `@Transactional` thực sự có hiệu lực. Với multicaster mặc định:

1. Spring mở transaction T1 quanh phương thức nghiệp vụ.
2. Producer kiểm tra chuyển trạng thái `PENDING → PAID`.
3. Producer cập nhật entity và gọi `publishEvent(OrderPaid)`.
4. Hạ tầng xác định những `@EventListener` đồng bộ nhận `OrderPaid`.
5. Những listener này chạy trong quá trình gọi `publishEvent`, thường ở **cùng thread** với producer.
6. Nếu tất cả trở về bình thường, producer tiếp tục chạy mã phía sau `publishEvent`.
7. Transaction T1 commit khi phương thức transactional hoàn tất; commit còn có thể thất bại vì constraint hoặc lỗi database.

Vì vậy, **listener đồng bộ đã chạy không chứng minh transaction cuối cùng đã commit thành công**.

### Cách quan sát cùng thread và transaction

Ví dụ listener dùng logging để xem trạng thái lúc được gọi:

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
class OrderPaidDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(OrderPaidDiagnostics.class);

    @EventListener
    void on(OrderPaid event) {
        log.info(
                "eventId={}, thread={}, txActive={}",
                event.eventId(),
                Thread.currentThread().getName(),
                TransactionSynchronizationManager.isActualTransactionActive()
        );
    }
}
~~~

Khi producer phát trong transaction và listener thực thi đồng bộ bằng multicaster mặc định, log có thể cho thấy **cùng tên thread** và `txActive=true`. Kết quả này là bằng chứng của **cấu hình đang chạy**, không phải khẳng định rằng mọi cấu hình application events trong Spring đều dùng chung thread.

Không dựa riêng vào `txActive=true` để kết luận bản ghi đã commit: transaction **đang hoạt động** nghĩa là chưa kết thúc, không phải đã thành công.

## 5. Exception trong listener có thể khiến producer thất bại

Đây là hệ quả đáng chú ý nhất của synchronous listener. Với multicaster mặc định không gắn error handler đặc biệt, exception từ listener đồng bộ thường truyền ngược qua `publishEvent`.

~~~java
@Component
class RejectOnMissingAuditPolicy {

    @EventListener
    void on(OrderPaid event) {
        if (violatesLocalAuditPolicy(event)) {
            throw new IllegalStateException("Audit policy rejected");
        }
    }

    private boolean violatesLocalAuditPolicy(OrderPaid event) {
        // Ví dụ minh họa, thay bằng quy tắc có căn cứ nghiệp vụ.
        return false;
    }
}
~~~

Nếu runtime exception thoát khỏi listener, đi qua `publishEvent` rồi thoát khỏi phương thức `@Transactional`, Spring mặc định đánh dấu rollback cho các ngoại lệ kiểu `RuntimeException` (và `Error`). Trong trường hợp đó, thao tác ghi đơn cũng bị rollback nếu đang cùng T1.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / @Transactional
    participant Events as Event multicaster
    participant Audit as audit / @EventListener
    participant DB as Database
    Client->>Orders: recordVerifiedPayment(...)
    Orders->>DB: Cập nhật đơn trong T1
    Orders->>Events: publishEvent(OrderPaid)
    Events->>Audit: on(OrderPaid)
    Audit--xEvents: RuntimeException
    Events--xOrders: Exception lan về producer
    Orders->>DB: Rollback T1
    Orders--xClient: Lỗi
~~~

Đây là **kịch bản theo cấu hình mặc định**. Hành vi thực tế có thể khác nếu producer bắt và xử lý exception, đặt rollback rules riêng, cấu hình multicaster với error handler, hoặc listener chạy bất đồng bộ. Không nên mô tả “mọi lỗi từ mọi listener luôn rollback producer”.

### Khi lỗi bị bắt và nuốt

~~~java
@EventListener
void on(OrderPaid event) {
    try {
        auditEntries.save(...);
    } catch (Exception failure) {
        log.warn("Cannot persist audit for {}", event.eventId(), failure);
        // Đã nuốt lỗi. Producer có thể tiếp tục và commit T1.
    }
}
~~~

Đoạn mã là **ví dụ chống chỉ định** cho yêu cầu kiểm toán bắt buộc: transaction có thể hoàn thành trong khi audit chưa được ghi. Nếu repository đã đánh dấu transaction hiện hành là rollback-only, producer cũng có thể gặp `UnexpectedRollbackException` khi commit dù exception được bắt. Vì vậy không được suy luận nuốt exception đồng nghĩa đã phục hồi an toàn.

Nếu audit thật sự là bất biến phải được lưu cùng thanh toán, nên mô hình hóa ràng buộc rõ ràng, kiểm thử rollback và cân nhắc một API đồng bộ trực tiếp thay vì giấu một điều kiện thành công cốt lõi trong listener.

### Một listener lỗi có ảnh hưởng các listener khác?

Với phân phối đồng bộ, nếu listener đầu tiên ném exception và không có cơ chế tiếp tục sau lỗi, việc phân phối có thể dừng trước khi listener tiếp theo được gọi. Do đó **fan-out không phải cam kết rằng mọi listener luôn được gọi** trong trường hợp lỗi.

Nếu ứng dụng đặt `@Order` hoặc cấu hình thứ tự listener, thứ tự này có thể tác động thứ tự thực thi của **các listener đồng bộ**. Nhưng `@Order` không tạo dependency giữa module, không bảo đảm side effect ngoài được rollback và không thay thế quy trình nghiệp vụ có điều phối.

## 6. Synchronous liên quan transaction như thế nào?

Cần phân biệt ba kịch bản thường bị gọi chung là “đồng bộ”:

| Kịch bản | Listener bắt đầu lúc nào? | Chạy trên thread nào? | Tình trạng transaction nguồn |
| --- | --- | --- | --- |
| `@EventListener` với multicaster mặc định | Ngay trong `publishEvent` | Thường cùng thread producer | Có thể **đang mở** |
| `@TransactionalEventListener(AFTER_COMMIT)` không async | Khi transaction producer commit thành công | Thường cùng thread đang thực hiện commit | Đã commit; callback không được mặc định có transaction ghi mới |
| `@ApplicationModuleListener` | Sau commit, được xử lý bất đồng bộ | Thường thread của executor | Transaction nguồn đã commit; consumer mở transaction riêng |

Như vậy **đồng bộ** không nhất thiết là **trước commit**. Có cả cơ chế **callback sau commit được gọi đồng bộ trên thread commit**. Điều này đặc biệt quan trọng khi muốn loại bỏ phản ứng cho transaction rollback, nhưng chưa muốn xử lý bằng async.

### `@TransactionalEventListener`: chọn pha transaction

Spring hỗ trợ `@TransactionalEventListener` với các pha như:

- **`BEFORE_COMMIT`**: listener chạy trước khi commit, vẫn có khả năng rollback sau đó.
- **`AFTER_COMMIT`**: listener chạy sau khi commit thành công (mặc định của annotation này).
- **`AFTER_ROLLBACK`**: listener phản ứng khi transaction rollback.
- **`AFTER_COMPLETION`**: listener phản ứng sau khi transaction hoàn tất, dù thành công hay rollback.

Không có pha nào tự động có nghĩa “chạy trên thread khác”. `@TransactionalEventListener` thuần Spring **không tự gắn `@Async`**. Với listener hậu commit không async, producer có thể **phải đợi listener chạy xong trước khi quá trình trả kết quả kết thúc**, dù dữ liệu nguồn đã commit.

### Ví dụ: callback đồng bộ sau commit

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class WriteAuditAfterCommit {

    private final AuditWriter writer;

    WriteAuditAfterCommit(AuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPaid event) {
        writer.recordCommittedPayment(event);
    }
}
~~~

Nếu callback sau commit cần ghi dữ liệu mới vào database, hãy dùng một transaction riêng thông qua bean Spring được proxy đúng cách:

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {

    private final AuditEntryRepository repository;

    public AuditWriter(AuditEntryRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordCommittedPayment(OrderPaid event) {
        repository.save(AuditEntry.paymentCommitted(
                event.eventId(), event.orderId()
        ));
    }
}
~~~

Các kiểu repository và entity là **minh họa cần hiện thực**. Cách tách `AuditWriter` thành bean riêng giúp lời gọi `recordCommittedPayment` đi qua Spring transaction proxy. Không nên dùng `this.recordCommittedPayment(...)` trong cùng bean rồi cho rằng `@Transactional(REQUIRES_NEW)` chắc chắn được áp dụng.

**Tại sao `REQUIRES_NEW` quan trọng sau commit?** Khi Spring gọi callback hậu commit, một số transaction resource của transaction cũ có thể vẫn còn gắn với thread, nhưng transaction nguồn đã hoàn tất và **sẽ không có một lượt commit mới cho những ghi chép vô tình tham gia resource cũ**. Nếu cần một thao tác ghi mới thực sự, cần bắt đầu transaction mới độc lập.

Nếu listener hậu commit ném exception, exception có thể ảnh hưởng kết quả quan sát được từ lời gọi đang commit, nhưng **không thể rollback transaction nguồn đã commit thành công**. Vì vậy phải tránh báo cho client rằng “thanh toán chưa xảy ra” chỉ vì phản ứng hậu commit thất bại.

### Trường hợp publish ngoài transaction

`@TransactionalEventListener` mặc định **không thực thi** khi event được publish bên ngoài transaction, trừ khi chủ động cấu hình `fallbackExecution = true`. Nếu bật fallback, phải định nghĩa rõ ý nghĩa của việc xử lý khi **không có commit nguồn**.

Một phương thức có annotation `@Transactional` nhưng được gọi thông qua **self-invocation** (gọi nội bộ trong cùng bean, bỏ qua proxy giao dịch) cũng có thể không có transaction như người viết tưởng. Khi chẩn đoán listener hậu commit không chạy, hãy kiểm tra transaction **thật sự đang tồn tại**, không chỉ kiểm tra annotation trên mã nguồn.

## 7. `@EventListener` không bắt buộc luôn synchronous trong mọi cấu hình

Có ba biến thể cần phân biệt:

**Biến thể A — Mặc định đồng bộ.** `SimpleApplicationEventMulticaster` không dùng `TaskExecutor` bất đồng bộ: `@EventListener` thông thường được gọi trên luồng publisher.

**Biến thể B — Listener được đánh dấu `@Async`.** Với hạ tầng async được bật và proxy hoạt động đúng, một phương thức `@EventListener` có thể được thực thi qua executor. Exception và transaction không còn tác động giống bản đồng bộ.

**Biến thể C — Multicaster có executor tùy chỉnh.** Hạ tầng có thể phân phối một số listener bằng executor, tùy khả năng hỗ trợ async của từng listener. Các listener gắn pha transaction có quy tắc riêng và không thể giả định chúng đều được chuyển sang executor chỉ vì multicaster được cấu hình.

Vì vậy câu nói đúng là:

> **Với Spring multicaster mặc định và một `@EventListener` thông thường không async, xử lý là synchronous.**

Không nên kết luận từ riêng annotation `@EventListener` rằng xử lý bắt buộc cùng thread trong mọi ứng dụng Spring Boot.

## 8. Synchronous fan-out, thứ tự và transaction của nhiều module

Một producer có thể có nhiều consumer đồng bộ cùng nhận `OrderPaid`:

~~~text
orders -- OrderPaid --> audit
                    --> metrics
                    --> policy-check
~~~

Mỗi listener phù hợp có thể được gọi khi event được publish. Tuy nhiên:

1. **Không có tính nguyên tử xuyên nhiều resource một cách tự động.** Nếu cả `orders` và `audit` cùng tham gia một transaction database thì thay đổi có thể rollback cùng nhau. Nếu listener gửi HTTP, email hoặc ghi vào một database độc lập, transaction của orders không tự kiểm soát side effect đó.
2. **Thời gian xử lý cộng dồn.** Listener đầu chậm có thể làm những bước còn lại và chính producer phải chờ.
3. **Exception có thể cắt ngắn fan-out.** Listener sau có thể chưa chạy.
4. **Thứ tự không phải workflow.** `@Order` có thể sắp xếp các listener theo thứ tự khi được phân phối đồng bộ, nhưng không bảo đảm một điều kiện nghiệp vụ giữa các module nếu side effect tồn tại ngoài transaction.
5. **Một listener có thể được gọi nhiều lần** nếu publisher phát event nhiều lần cho cùng sự kiện nghiệp vụ; đồng bộ không phải bảo đảm *exactly-once*.

~~~mermaid
flowchart TD
    A["Producer publish OrderPaid trong T1"] --> B["audit listener đồng bộ"]
    B --> C{"Audit thành công?"}
    C -->|Có| D["metrics listener đồng bộ"]
    C -->|Không| E["Exception có thể lan về producer"]
    D --> F["publishEvent trở về producer"]
    F --> G{"Transaction T1 commit?"}
    G -->|Có| H["Trạng thái nguồn được commit"]
    G -->|Không| I["Rollback trạng thái trong T1"]
    E --> I
~~~

Sơ đồ minh họa **đường thực thi mặc định khi exception không được xử lý**; một ứng dụng có error handler hoặc rollback rules khác có thể cho kết quả khác.

### `@Order` có thể dùng để làm gì?

~~~java
@Component
class LocalDiagnostics {

    @Order(10)
    @EventListener
    void inspect(OrderPaid event) {
        // Phản ứng đồng bộ mang tính chẩn đoán.
    }

    @Order(20)
    @EventListener
    void record(OrderPaid event) {
        // Phản ứng khác cùng event.
    }
}
~~~

Các import `@Order`, `@EventListener` và `@Component` được lược bỏ để minh họa ngắn. `@Order` là công cụ sắp xếp lời gọi có phạm vi, **không phải cam kết giao sự kiện bền vững**. Đối với trình tự “phải ghi hóa đơn trước khi gửi hàng”, hãy dùng service/workflow với trạng thái rõ ràng thay vì chỉ dựa vào ưu tiên listener.

## 9. Latency và tài nguyên: synchronous có chi phí thật

Trong đường gọi synchronous, tổng thời gian producer chịu thêm độ trễ của các listener. Nếu các listener được thực thi tuần tự, một mô hình gần đúng là:

\[
T_{request} \approx T_{business} + \sum_{i=1}^{n} T_{listener_i} + T_{commit}
\]

Công thức mang tính **ước lượng kiến trúc** cho đường gọi tuần tự; thời gian thực tế còn có overhead của Spring, database, scheduling, connection pool và các yếu tố khác. Không dùng nó như công thức SLA tuyệt đối.

Ví dụ minh họa:

| Công việc | Độ trễ giả định |
| --- | ---: |
| Xử lý nghiệp vụ đơn hàng | 25 ms |
| Listener audit ghi database | 15 ms |
| Listener gọi dịch vụ email ngoài | 800 ms |
| Commit transaction và overhead | 20 ms |
| **Tổng gần đúng với xử lý tuần tự** | **860 ms** |

Một external API chậm có thể trở thành nguyên nhân lớn nhất làm tăng thời gian response; nếu gọi khi T1 còn mở, transaction giữ connection, lock hoặc resource lâu hơn cần thiết.

### Lựa chọn tác vụ phù hợp

**Phù hợp hơn với synchronous:**

- Kiểm tra/ràng buộc cục bộ cần diễn ra trước khi transaction hoàn tất, nếu team quyết định biểu diễn bằng event và chấp nhận coupling.
- Ghi một thay đổi database nhỏ, có thể tham gia cùng transaction nguồn và phải rollback cùng nhau.
- Phép tính hoặc cập nhật bộ nhớ rẻ, có semantics rõ ràng và không gây side effect bên ngoài.
- Chẩn đoán nhẹ, metric nội bộ được thiết kế không ảnh hưởng chức năng chính.

**Thường không phù hợp với `@EventListener` đồng bộ trong transaction:**

- Gọi email/SMS, cổng thanh toán, dịch vụ vận chuyển hoặc HTTP ngoài có thể timeout.
- Tác vụ CPU nặng, export báo cáo, gửi hàng loạt hoặc batch.
- Những phản ứng có thể hoàn tất sau vài giây và có yêu cầu retry độc lập.
- Side effect không thể rollback khi transaction producer thất bại.

**Synchronous không đồng nghĩa luôn xấu**. Nó là một quyết định tốt khi việc tham gia cùng luồng và transaction thực sự phục vụ bất biến nghiệp vụ, thời gian xử lý có thể dự đoán, và lỗi phải được truyền về producer. Khi các điều kiện này không đúng, hãy cân nhắc listener hậu commit, async hoặc một quy trình nghiệp vụ riêng.

## 10. Synchronous event hay gọi service trực tiếp?

Event giúp giảm phụ thuộc trực tiếp từ producer đến consumer, nhưng **không làm mất coupling ở thời điểm chạy** khi listener đồng bộ nằm trên đường thành công của producer.

| Câu hỏi | Gọi service đồng bộ trực tiếp | Synchronous event |
| --- | --- | --- |
| Producer biết bên nào sẽ xử lý? | Có, gọi API cụ thể | Không phải biết danh sách listener |
| Có cần kết quả trả về để quyết định nghiệp vụ? | Tự nhiên, rõ nghĩa | Không thuận tiện; thường không nên dùng event làm request-response |
| Lỗi consumer có thể ảnh hưởng producer? | Có | Có, với cấu hình sync mặc định |
| Có thêm consumer mà không sửa producer? | Thường cần sửa nơi điều phối | Có thể đăng ký listener mới |
| Có thể ghép vào transaction nguồn? | Có nếu cùng resource/transaction manager | Có với listener sync cùng transaction |
| Có hạ tầng retry bền vững tự động? | Không | Không; `@EventListener` sync thông thường cũng không tự được registry bảo đảm |

Một nguyên tắc thiết kế hữu ích:

- **Bất biến bắt buộc có kết quả ngay:** ưu tiên API/command đồng bộ với contract rõ ràng; có thể sử dụng event sync nếu hiểu và chấp nhận phụ thuộc runtime.
- **Một sự thật đã được commit và có nhiều phản ứng độc lập:** ưu tiên event hậu commit, chọn sync-after-commit hay async theo latency và độ tin cậy.
- **Tác vụ lâu, dễ lỗi, cần khôi phục:** ưu tiên xử lý sau commit với transaction riêng, Event Publication Registry khi phù hợp và idempotency.

Một event không nên chỉ là command ngụy trang. `OrderPaid` nói rằng đơn đã được ghi nhận thanh toán; `SendEmailNow` là chỉ thị một consumer phải hành động. Khi producer cần biết “email đã gửi thành công chưa?”, đồng bộ event thường không phải hợp đồng API rõ ràng nhất.

## 11. Synchronous event và Event Publication Registry

Spring Modulith hỗ trợ **Event Publication Registry** để theo dõi việc phát và hoàn tất các event publication cho những **transactional event listeners được hỗ trợ**. Khi cấu hình repository bền vững (chẳng hạn JDBC hoặc JPA phù hợp phiên bản) và publication được tạo trong transaction nguồn, registry có thể ghi ý định giao cùng transaction với dữ liệu nguồn.

**Điều cần phân biệt:**

- **`@EventListener` đồng bộ thông thường** không vì có Spring Modulith mà tự động được xem như một publication bền vững có cơ chế gửi lại. Nếu listener chạy trước commit, mọi rủi ro side effect vẫn phải được đánh giá như một lời gọi đồng bộ.
- **`@TransactionalEventListener` hậu commit**, kể cả khi callback được gọi đồng bộ, có thể nằm trong mô hình theo dõi publication được hỗ trợ của Spring Modulith khi registry/integration đã cấu hình phù hợp.
- **`@ApplicationModuleListener`** là lựa chọn thuận tiện cho phản ứng hậu commit **bất đồng bộ và transaction riêng**, giúp cách ly lỗi khỏi transaction nguồn, nhưng vẫn cần registry được cấu hình và consumer idempotent.

~~~mermaid
flowchart TD
    P["Producer publish OrderPaid trong T1"] --> S{"Chọn cách đăng ký listener"}
    S --> A["@EventListener sync"]
    S --> B["@TransactionalEventListener AFTER_COMMIT sync"]
    S --> C["@ApplicationModuleListener async"]
    A --> AT["Chạy trong luồng publish, có thể trước commit"]
    B --> BT["Chạy ở pha hậu commit, có thể dùng registry"]
    C --> CT["Chạy sau commit bằng executor và transaction mới"]
    BT --> R["Publication tracking nếu có persistence phù hợp"]
    CT --> R
    R --> F{"Consumer hoàn tất?"}
    F -->|Có| D["Đánh dấu publication hoàn tất"]
    F -->|Không| E["Còn publication chưa hoàn tất, cần recovery"]
~~~

Không được suy ra rằng registry **tự retry vô hạn**, bảo đảm mọi hiệu ứng “chỉ một lần”, hoặc biến event nội bộ thành Kafka/RabbitMQ message. Phải kiểm tra cấu hình storage, trạng thái publication chưa hoàn tất, cách resubmit khi restart và cơ chế xử lý lỗi theo phiên bản được chọn.

### Khác biệt giữa rollback và lỗi sau commit

| Tình huống | `@EventListener` sync trong T1 | Listener AFTER_COMMIT sync |
| --- | --- | --- |
| T1 rollback sau publish | Listener có thể đã chạy; DB cùng T1 rollback, side effect ngoài có thể vẫn xảy ra | Không được gọi cho transaction rollback |
| T1 commit thành công | Listener đã chạy trước commit | Được kích hoạt sau commit |
| Listener ném exception | Có thể khiến T1 rollback | T1 đã commit, không thể rollback theo |
| Listener ghi database mới | Có thể tham gia T1 nếu cùng resource | Cần transaction mới phù hợp để có commit dữ liệu mới |
| Cần recovery sau crash | Không tự có từ annotation `@EventListener` | Cần registry bền vững và resubmit, không chỉ annotation |

## 12. Kiểm thử synchronous event

Một bài kiểm thử tốt không chỉ kiểm tra `publishEvent(...)` được gọi mà cần xác nhận **thứ tự tương đối, transaction, exception và side effect**.

### Ma trận kiểm thử

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Producer phát `OrderPaid` lần đầu | Listener sync phù hợp chạy trước khi producer tiếp tục qua vị trí publish |
| Không có transition mới | Producer không phát event nghiệp vụ trùng |
| Listener đồng bộ ném `RuntimeException` | Exception được truyền về theo cấu hình mặc định; transaction nguồn có thể rollback |
| Producer chủ động rollback sau publish | Những ghi chép của listener trong cùng T1 rollback, side effect bên ngoài không tự rollback |
| Listener không cùng database/resource | Không giả định hai thao tác rollback nguyên tử |
| `@TransactionalEventListener(AFTER_COMMIT)` | Không chạy khi T1 rollback; chạy khi T1 thực sự commit |
| Callback AFTER_COMMIT cần ghi DB | Có transaction độc lập `REQUIRES_NEW`, kiểm tra record được commit |
| Nhiều listener có `@Order` | Thứ tự quan sát khớp cấu hình sync trong bài test |
| Cấu hình async khác mặc định | Không suy luận cùng thread chỉ dựa trên annotation |
| Listener hậu commit lỗi rồi khôi phục | Publication còn chưa hoàn tất nếu registry bền vững đã cấu hình; retry không nhân đôi side effect |

### Test đơn vị với publisher và listener thuần Spring

Để chứng minh hành vi đồng bộ mặc định, có thể dùng một Spring application context thử nghiệm nhỏ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

class SynchronousEventTest {

    record OrderPaid(UUID orderId) {}

    static final class Recorder {
        final List<String> calls = new ArrayList<>();
    }

    @Configuration
    static class TestConfig {

        @Bean
        Recorder recorder() {
            return new Recorder();
        }

        @Bean
        TestListener testListener(Recorder recorder) {
            return new TestListener(recorder);
        }
    }

    static final class TestListener {

        private final Recorder recorder;

        TestListener(Recorder recorder) {
            this.recorder = recorder;
        }

        @EventListener
        public void on(OrderPaid event) {
            recorder.calls.add("listener");
        }
    }

    @Test
    void listenerRunsBeforePublishReturns() {
        try (var context =
                new AnnotationConfigApplicationContext(TestConfig.class)) {

            Recorder recorder = context.getBean(Recorder.class);
            recorder.calls.add("before");

            context.publishEvent(new OrderPaid(UUID.randomUUID()));

            recorder.calls.add("after");

            assertThat(recorder.calls)
                    .containsExactly("before", "listener", "after");
        }
    }
}
~~~

Bài test này cố tình **không dùng transaction, async hoặc Event Publication Registry**, chỉ chứng minh hành vi synchronous cơ bản của application context chuẩn. Nó không chứng minh rollback, khả năng khôi phục sau crash hay rằng mọi bean có `@EventListener` trong mọi ứng dụng luôn đồng bộ.

### Kiểm thử tích hợp có transaction

Trong ứng dụng Spring Boot mẫu, tạo các bài test riêng để quan sát:

1. **Cùng T1:** producer thay đổi đơn và phát event; listener sync ghi audit vào cùng database; transaction nguồn commit → cả hai record tồn tại.
2. **Rollback T1:** producer ném exception sau publish → cả đơn và audit cùng T1 không tồn tại sau rollback.
3. **Listener lỗi:** audit ném runtime exception không bị bắt → producer/transaction phản ứng theo quy tắc rollback dự kiến.
4. **AFTER_COMMIT:** đăng ký một listener `@TransactionalEventListener` không async; producer rollback không tạo phản ứng, commit tạo phản ứng.
5. **`REQUIRES_NEW`:** sau commit, listener gọi một service qua proxy để lưu audit độc lập, xác minh record thực sự được commit.
6. **Publication Registry:** nếu bài thực hành cấu hình registry, tạo lỗi sau commit và kiểm tra publication chưa hoàn tất/recovery, thay vì chỉ mock publisher.

**Bẫy quan trọng:** test được đánh dấu `@Transactional` thường tự rollback ở cuối; listener `AFTER_COMMIT` sẽ **không được kích hoạt** nếu transaction test không commit. Cần tổ chức test sao cho transaction thực sự kết thúc bằng commit khi đang kiểm tra pha đó.

## 13. Quan sát performance và lỗi synchronous listener

Vì listener đồng bộ nằm trong đường gọi producer, **latency và exception của listener cần được giám sát cùng latency nghiệp vụ nguồn**. Nếu request thanh toán chậm bất thường, cần biết thời gian bị tiêu tốn trong database, ở listener nào hay trong resource ngoài.

| Tín hiệu | Mục đích |
| --- | --- |
| `eventType`, `eventId`, `orderId` | Liên hệ một lần phát event với giao dịch nghiệp vụ |
| `listenerName`, `handlerMethod` | Biết phản ứng đồng bộ nào được gọi |
| `threadName`, `txActive` khi chẩn đoán | Xác minh hành vi sync/transaction của cấu hình |
| `handlerDuration`, `publishDuration` | Nhận diện listener làm producer chậm |
| Lỗi và exception type theo listener | Phân biệt lỗi validation, database, external API |
| `transactionOutcome` | Biết nguồn đã commit hay rollback, tránh nhầm với việc listener đã chạy |
| `publicationStatus` với transactional listener | Phát hiện công việc hậu commit còn dang dở nếu đã dùng registry |
| `duplicateSuppressed` trong consumer | Theo dõi lượng event được xử lý lại mà không gây hiệu ứng trùng |

Không log toàn bộ event nếu chứa dữ liệu cá nhân hoặc chi tiết thanh toán nhạy cảm. `eventId` có thể được đưa vào structured log/tracing; **không nên dùng `eventId` làm label metric**, vì tạo số lượng series quá lớn.

Một cách thực hành là đo:

~~~java
long started = System.nanoTime();
try {
    // Thực thi logic listener đồng bộ.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    // Ghi nhận metric duration theo eventType và listener.
}
~~~

`System.nanoTime()` phù hợp để đo **khoảng thời gian tương đối trong một tiến trình**, không phải timestamp tuyệt đối. Nếu cần ngày giờ xảy ra event, dùng `Instant` và định nghĩa rõ mốc nghiệp vụ trong contract.

## 14. Bài tập thực hành: synchronous, rollback và after commit

### Đề bài

Hệ thống đặt vé có các module `reservations`, `audit`, `notifications` và `loyalty`. Khi `reservations` xác nhận thanh toán, nó phát `ReservationPaid`.

- `audit` cần lưu dấu giao dịch trong **cùng database transaction** với reservation.
- `notifications` cần tạo yêu cầu gửi email **chỉ sau khi** reservation commit thành công.
- `loyalty` cộng điểm với cơ chế idempotency và có thể chấp nhận hoàn thành muộn.

### Các bước thực hiện

1. Định nghĩa `ReservationPaid(eventId, reservationId, paymentId, customerId, occurredAt)` ở public API của `reservations`.
2. Viết producer `@Transactional` chỉ phát event nếu một payment reference mới thực sự làm reservation chuyển trạng thái.
3. Viết một `@EventListener` đồng bộ ở `audit`, ghi một audit entry vào cùng database/transaction T1.
4. Thử rollback T1 sau publish; kiểm tra cả reservation và audit entry đều rollback.
5. Thử listener audit ném runtime exception; xác nhận exception ảnh hưởng producer theo cấu hình mặc định và T1 rollback.
6. Viết listener `@TransactionalEventListener(phase = AFTER_COMMIT)` đồng bộ cho `notifications`. Nếu listener ghi DB, gọi service `@Transactional(REQUIRES_NEW)` qua Spring proxy.
7. Thử rollback T1 lần nữa; xác nhận không có yêu cầu email từ listener hậu commit.
8. Đổi `loyalty` sang `@ApplicationModuleListener` để xử lý sau commit, bất đồng bộ và transaction riêng. Cho nó lỗi một lần rồi xử lý lại nếu đã cấu hình registry bền vững.
9. Thiết kế unique constraint theo `eventId` hoặc khóa nghiệp vụ thích hợp, kiểm tra retry không cộng trùng điểm.
10. Đo thời gian request trong trường hợp audit nhanh và audit cố ý chậm, rồi giải thích vì sao listener đồng bộ tăng latency và thời gian giữ transaction.

### Câu hỏi tự đánh giá

**1. `publishEvent(...)` trả về có đồng nghĩa database commit rồi không?** Không. Với producer đang trong transaction, listener đồng bộ có thể chạy xong **trước khi transaction nguồn commit**.

**2. Listener đồng bộ ném lỗi có làm rollback producer không?** Có thể. Với cấu hình đồng bộ mặc định và runtime exception thoát khỏi phương thức `@Transactional`, Spring thường rollback theo quy tắc mặc định. Nhưng bắt lỗi, cấu hình rollback hoặc error handler có thể thay đổi kết quả.

**3. `@TransactionalEventListener(AFTER_COMMIT)` có luôn bất đồng bộ không?** Không. Nếu không gắn cơ chế async riêng, callback có thể chạy đồng bộ trong thread hoàn tất transaction. Nó khác `@EventListener` đồng bộ chạy ngay lúc publish.

**4. `@ApplicationModuleListener` có phải synchronous không?** Không theo cấu hình annotation chuẩn: đây là tiện ích Spring Modulith cho listener hậu commit, bất đồng bộ và transaction mới.

**5. Có nên gọi email provider ngay trong listener đồng bộ của transaction thanh toán không?** Thông thường không. Side effect bên ngoài không tự rollback, có thể timeout và kéo dài transaction. Nên tạo yêu cầu gửi hậu commit hoặc dùng thiết kế outbox/retry thích hợp.

**6. Có Event Publication Registry thì `@EventListener` đồng bộ thường tự được retry sau restart không?** Không. Registry theo dõi các publication của transactional listener được hỗ trợ khi cấu hình phù hợp, không phải đảm bảo chung cho mọi listener synchronous.

## 15. Checklist khi lựa chọn synchronous event

- [ ] Phân biệt sự thật nghiệp vụ của event với cách thực thi listener.
- [ ] Biết `@EventListener` thông thường chạy synchronous **với multicaster mặc định**, không khẳng định cho mọi cấu hình.
- [ ] Xác định listener có chạy trong transaction nguồn hay không.
- [ ] Không nhầm `publishEvent` trả về với commit thành công.
- [ ] Hiểu exception từ listener đồng bộ có thể truyền về producer.
- [ ] Không nuốt lỗi của tác vụ bắt buộc mà không có chính sách nhất quán.
- [ ] Chỉ dùng cùng T1 khi các thao tác thật sự cùng transaction resource.
- [ ] Không làm HTTP/email/SMS chậm hoặc không thể rollback trong T1 nếu nghiệp vụ không yêu cầu.
- [ ] Không dựa vào `@Order` để thay thế một workflow/bất biến nghiệp vụ.
- [ ] Phân biệt `@EventListener` sync với `@TransactionalEventListener(AFTER_COMMIT)` sync.
- [ ] Khi callback hậu commit ghi DB, dùng transaction mới phù hợp thông qua proxy.
- [ ] Biết `@ApplicationModuleListener` chuẩn là hậu commit, bất đồng bộ, transaction riêng.
- [ ] Không cho rằng `@EventListener` sync được registry bảo đảm retry bền vững.
- [ ] Có kiểm thử về thứ tự, rollback, exception và độ trễ.
- [ ] Có log/metric gắn với eventId và listener để chẩn đoán giao tiếp giữa các module.

## Ghi nhớ

**Xử lý synchronous** trong Spring Modulith thường là listener `@EventListener` được gọi ngay trong `publishEvent(...)` nhờ multicaster đồng bộ mặc định. Cách này dễ thực hành, có thể cùng transaction với producer và cho phép exception lan ngược, nhưng làm tăng latency và gắn chặt hơn thành công runtime của producer với consumer.

Đừng nhầm **synchronous** với **“chạy sau commit”**: `@TransactionalEventListener(AFTER_COMMIT)` có thể chạy đồng bộ *sau khi* dữ liệu nguồn đã commit, còn `@ApplicationModuleListener` hỗ trợ hậu commit **bất đồng bộ** và transaction riêng. Lựa chọn đúng phụ thuộc bất biến nghiệp vụ, giới hạn thời gian xử lý, độ tin cậy cần đạt, và cách vận hành retry, idempotency, Event Publication Registry cũng như observability. Hợp đồng event công khai và ranh giới module rõ ràng giúp giảm phụ thuộc mã nguồn; thiết kế transaction đúng giúp giữ được tính nhất quán khi consumer phản ứng.

