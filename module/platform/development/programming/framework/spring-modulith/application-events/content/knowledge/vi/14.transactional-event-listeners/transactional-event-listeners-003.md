# Pha AFTER_COMMIT

## Mục tiêu bài học

Khi module `orders` xác nhận một đơn hàng đã thanh toán, các module `loyalty`, `notifications` và `reporting` có thể cần phản ứng với sự kiện `OrderPaid`. Tuy nhiên, chúng chỉ nên xử lý sự thật **đã được commit**, không phải một trạng thái tạm thời còn có thể rollback trong transaction của `orders`. Trong Spring, `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` là một cơ chế quan trọng để thực hiện điều đó.

Bài thuộc chương **Transactional listener** của mô-đun **SPRING_MODULITH_APPLICATION_EVENTS**: giao tiếp giữa các module Spring Modulith bằng application events, giảm phụ thuộc mã nguồn, bảo vệ ranh giới nghiệp vụ và xây dựng cơ chế xử lý đáng tin cậy thông qua publisher, listener, Event Publication Registry, retry, kiểm thử và quan sát. Trọng tâm ở đây là **pha AFTER_COMMIT**: điều kiện kích hoạt, khác biệt với các pha khác, tác động lên transaction và những giới hạn về độ bền.

Sau bài học, bạn cần giải thích được:

1. Vì sao một event có thể **được publish trước commit** nhưng listener chỉ **nhận sau commit**.
2. Tại sao `AFTER_COMMIT` **không tự đồng nghĩa với bất đồng bộ**, transaction mới hoặc gửi sự kiện bền vững.
3. Cách dùng `@Transactional(propagation = REQUIRES_NEW)` đúng chỗ khi listener hậu commit cần ghi dữ liệu.
4. Vì sao lỗi listener hậu commit **không rollback được transaction nguồn đã thành công**.
5. Cách kết hợp Spring Modulith `@ApplicationModuleListener`, Event Publication Registry, idempotency, retry và kiểm thử để giảm khoảng trống sau commit.

## 1. Tại sao cần AFTER_COMMIT?

Giả sử khách vừa trả tiền cho đơn `O-100`. Module `orders` cập nhật trạng thái `PAID` trong transaction `T1`, sau đó phát `OrderPaid`. Nếu module `notifications` dùng listener chạy ngay tại `publishEvent`, nó có thể gửi email xác nhận trước khi cơ sở dữ liệu hoàn tất transaction. Nếu `T1` rollback, email ấy đã ra ngoài nhưng đơn hàng không thật sự `PAID`.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Orders as orders
    participant DB as Database
    participant Immediate as Listener ngay lúc publish
    participant After as Listener AFTER_COMMIT

    Client->>Orders: Xác nhận thanh toán hợp lệ
    Orders->>DB: Mở T1, lưu trạng thái PAID
    Orders->>Orders: publishEvent(OrderPaid)
    Orders->>Immediate: @EventListener được gọi
    Note over Immediate: Có thể tạo side effect quá sớm
    Orders->>DB: Commit T1
    DB-->>Orders: Commit thành công
    Orders->>After: Kích hoạt AFTER_COMMIT
    Note over After: Chỉ xử lý sau commit nguồn
~~~

Pha `AFTER_COMMIT` giúp mô tả một điều kiện rất cụ thể: **chỉ kích hoạt callback sau khi transaction có liên quan commit thành công**. Khi transaction nguồn rollback, callback này không được gọi. Điều đó phù hợp với những phản ứng như gửi yêu cầu thông báo, lập projection doanh thu, cộng điểm sau thanh toán hoặc bắt đầu một bước hậu xử lý.

Nhưng câu “đã commit nguồn” **không đồng nghĩa** các consumer đã hoàn tất. Một listener hậu commit có thể ném exception, bị chậm hoặc bị mất lời gọi khi tiến trình dừng. AFTER_COMMIT bảo vệ **thời điểm hợp lệ để bắt đầu phản ứng**, không tự bảo đảm **phản ứng chắc chắn thành công**.

### Ba sự thật phải phân biệt

| Sự thật | Khi nào có thể khẳng định? | Không được suy ra |
| --- | --- | --- |
| Event đã được publish | Producer gọi `publishEvent(event)` | Nguồn đã commit |
| Transaction nguồn đã commit | Database/transaction manager hoàn tất commit | Mọi listener đã xử lý |
| Một listener đã hoàn tất | Hiệu ứng nghiệp vụ và trạng thái hoàn tất của listener được kiểm chứng | Tất cả consumer còn lại cũng hoàn tất |

Một `OrderPaid` có thể được nhận bởi ba module. `loyalty` hoàn tất trước, `reporting` còn chờ và `notifications` có lỗi là trạng thái hoàn toàn có thể xảy ra sau commit.

## 2. BEFORE_COMMIT, AFTER_COMMIT và @EventListener khác nhau thế nào?

Spring cung cấp `@EventListener` cho các application event thông thường và `@TransactionalEventListener` để chọn một pha transaction. Với `@TransactionalEventListener`, **`AFTER_COMMIT` là pha mặc định** nếu không chỉ định thuộc tính `phase`.

| Cách đăng ký | Khi nào listener được gọi? | Nếu nguồn rollback? | Có tự bất đồng bộ? |
| --- | --- | --- | --- |
| `@EventListener` với multicaster mặc định | Ngay trong lúc publish, thường đồng bộ | Có thể **đã chạy** | Không |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Khi transaction chuẩn bị commit | Không chạy nếu không đến pha commit; vẫn có thể rollback sau callback | Không |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi commit nguồn thành công | **Không chạy** | Không |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Khi transaction rollback | Chạy cho nhánh rollback | Không |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi transaction kết thúc, dù commit hay rollback | Có thể chạy | Không |
| `@ApplicationModuleListener` | Tiện ích Modulith cho phản ứng sau commit | Không chạy khi nguồn rollback | **Có**, cùng transaction riêng |

Một listener thuần `@TransactionalEventListener` không tự được đưa lên background thread. Nếu không cấu hình `@Async` hoặc cơ chế tương đương, callback AFTER_COMMIT thường được thực thi **đồng bộ trong luồng đang hoàn tất transaction**. Do đó đường gọi API ban đầu vẫn có thể phải đợi callback hậu commit chạy xong mới trả về, mặc dù dữ liệu nguồn đã commit.

Điều này khác `@ApplicationModuleListener`, annotation của Spring Modulith kết hợp ngữ nghĩa xử lý sau commit, thực thi bất đồng bộ và transaction mới. **Đừng nhầm “sau commit” với “ngoài luồng”.**

### Điểm rất quan trọng về tên pha

- **`BEFORE_COMMIT`** là trước khi transaction commit; handler có thể làm commit thất bại.
- **`AFTER_COMMIT`** là sau khi commit thành công; handler không thể đảo ngược commit đó.
- **`AFTER_COMPLETION`** là sau khi transaction hoàn tất, gồm cả commit lẫn rollback. Không dùng nó để gửi thông báo “đã thành công” nếu không phân biệt kết quả.

Thứ tự chính xác giữa các callback và transaction synchronizations khác nhau còn tùy transaction manager; ý nghĩa hợp đồng của AFTER_COMMIT là **commit nguồn đã thành công**, không phải “tất cả resource đã bị đóng hoàn toàn”.

## 3. Mô hình vòng đời event hậu commit

Một đường đi chuẩn cho `OrderPaid` có thể mô tả bằng các mốc:

~~~text
T1 bắt đầu
  1. orders kiểm tra thanh toán đã xác thực
  2. orders chuyển trạng thái PENDING -> PAID
  3. orders tạo OrderPaid(eventId, orderId, ...)
  4. orders gọi ApplicationEventPublisher.publishEvent(event)
  5. Spring đăng ký listener transaction ở pha AFTER_COMMIT
  6. orders kết thúc xử lý trong T1
  7. Transaction manager commit T1 thành công
  8. Spring kích hoạt callback AFTER_COMMIT
  9. Consumer thực hiện phản ứng riêng
 10. Consumer kết thúc; nếu có registry, completion được theo dõi

Nếu T1 rollback ở bước 6 hoặc 7:
  -> không gọi listener AFTER_COMMIT cho T1
~~~

Ở bước 4, event đã được **tạo và publish** nhưng chưa thể coi trạng thái PAID bền vững. Sự kiện được gửi vào cơ chế Spring để các listener được đăng ký và chờ đúng pha. Nếu database báo lỗi constraint tại commit, nhánh AFTER_COMMIT **không chạy**.

Có thể biểu diễn luồng theo hai kết quả:

~~~mermaid
flowchart TD
    A["Producer ở transaction T1"] --> B["Đổi trạng thái nghiệp vụ"]
    B --> C["publishEvent(OrderPaid)"]
    C --> D["Đăng ký listener AFTER_COMMIT"]
    D --> E{"T1 hoàn tất thế nào?"}
    E -->|"Rollback"| F["AFTER_COMMIT không chạy"]
    E -->|"Commit"| G["Kích hoạt listener hậu commit"]
    G --> H{"Consumer thành công?"}
    H -->|"Có"| I["Hiệu ứng consumer được ghi nhận"]
    H -->|"Không"| J["Nguồn đã commit; cần chính sách phục hồi"]
~~~

**Chú ý:** một callback nhận được event không có nghĩa payload sẽ được giữ lại vô thời hạn. Nếu không có hạ tầng publication bền vững phù hợp, sự cố dừng tiến trình có thể làm mất khả năng xử lý lại sau khi nguồn đã commit.

## 4. Thiết kế contract và ranh giới module

Trong Spring Modulith, `orders` là chủ sở hữu sự thật `OrderPaid`. Module khác chỉ phụ thuộc vào **event contract công khai**, không cần truy cập repository hoặc JPA entity nội bộ của `orders`.

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPaid.java
│   └── internal
│       ├── OrderPaymentService.java
│       └── OrderRepository.java
├── loyalty
│   └── internal
│       └── AwardPointsOnOrderPaid.java
└── notifications
    └── internal
        └── NotifyOnOrderPaid.java
~~~

Contract:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

/**
 * Đơn được orders chấp nhận chuyển sang PAID.
 * Hiệu ứng ngoài module nên xử lý sau commit nguồn.
 */
public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Để công bố subpackage `orders.events` làm API module, có thể khai báo trong `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Module `loyalty` có thể hạn chế quyền phụ thuộc trong `loyalty/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.loyalty;
~~~

Ký hiệu `orders::events` giả định module có tên mặc định `orders`. Những annotation về module boundary giúp kiểm tra **phụ thuộc mã nguồn hợp lệ**; chúng **không tự thay đổi phase của listener**, không tạo queue và không làm event bền vững.

### Vì sao nên dùng record bất biến?

Payload chỉ chứa ID, timestamp và snapshot vừa đủ. Một listener hậu commit chạy khi persistence context của producer không còn phù hợp để truy cập lazy entity. Truyền `OrderEntity` đang managed hoặc cả graph object vào event sẽ làm tăng coupling và dẫn đến lỗi lazy loading, dữ liệu bị thay đổi ngoài mong muốn hoặc rò rỉ nội bộ.

`occurredAt` nên có nghĩa rõ: thời điểm module nguồn tạo event cho transition hợp lệ. Nó **có thể sớm hơn commit** và không phải `processedAt` của `loyalty`. Khi nhận lại cùng event, giữ nguyên `eventId` và `occurredAt`; thời điểm retry/received mới thuộc metadata xử lý consumer.

## 5. Producer publish event trong transaction nguồn

Để dùng `AFTER_COMMIT` đúng nghĩa, producer nên publish bên trong transaction đang được Spring quản lý. Ví dụ:

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
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa; false khi thanh toán đã ghi nhận.
        if (!order.markPaidIfNew(paymentId)) {
            return;
        }

        orders.save(order);

        events.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                paymentId,
                clock.instant()
        ));
    }
}
~~~

`Order`, `OrderRepository` và `markPaidIfNew` là các thành phần giả định cần tự triển khai. `paymentId` phải tương ứng một kết quả thanh toán **đã được xác thực** từ nguồn đáng tin, không phải một giá trị do client tự khai là thành công.

Nếu `markPaidIfNew` ngăn transition lặp, cùng callback thanh toán được gửi lại sẽ không phát một `OrderPaid` mới. Với callback cạnh tranh đồng thời, cần thêm transaction isolation, optimistic locking hoặc ràng buộc dữ liệu thích hợp để tránh hai tiến trình cùng tạo event cho một payment.

**Đọc đúng mã:** `events.publishEvent(...)` được gọi **trong T1**, trước khi transaction interceptor commit. `@TransactionalEventListener(AFTER_COMMIT)` chưa chạy ngay tại dòng này. Nếu có listener `@EventListener` đồng bộ khác cùng nhận `OrderPaid`, listener đó có thể chạy ngay tại đây; AFTER_COMMIT là một đăng ký riêng.

### Self-invocation có thể làm mất transaction bạn tưởng đang có

Trong cơ chế Spring proxy thông thường, một phương thức cùng bean tự gọi phương thức `@Transactional` của chính nó có thể **bỏ qua transaction proxy**. Khi đó event có thể được publish **ngoài transaction**, và listener `@TransactionalEventListener` mặc định không chạy.

~~~java
@Service
class PaymentFacade {

    public void handle(UUID orderId, UUID paymentId) {
        // Tự gọi method trong cùng instance: không đi qua proxy transaction.
        record(orderId, paymentId);
    }

    @Transactional
    public void record(UUID orderId, UUID paymentId) {
        // Không chắc có T1 khi gọi từ handle() như trên.
    }
}
~~~

Hãy đặt transaction boundary ở một Spring bean được gọi qua proxy, hoặc chọn cơ chế transaction phù hợp; xác minh bằng integration test thay vì chỉ nhìn annotation.

## 6. Viết listener AFTER_COMMIT đơn giản

Listener có thể dùng trực tiếp `@TransactionalEventListener`, chỉ định phase tường minh để người đọc thấy ý định:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class PaymentNotificationListener {

    private final NotificationRecorder recorder;

    PaymentNotificationListener(NotificationRecorder recorder) {
        this.recorder = recorder;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPaid event) {
        recorder.recordObservedEvent(event);
    }
}
~~~

`NotificationRecorder` là thành phần minh họa. Nếu `recordObservedEvent` chỉ log hoặc ghi metric bằng một cơ chế không cần transaction database, ví dụ là đủ để hiểu mốc gọi. Nếu nó **ghi cơ sở dữ liệu** hoặc tạo một yêu cầu gửi trong database, cần hiểu vấn đề transaction ở phần tiếp theo.

### Có thể bỏ thuộc tính phase không?

Có. Với `@TransactionalEventListener`, `AFTER_COMMIT` là phase mặc định. Hai khai báo này có cùng ý nghĩa chọn pha:

~~~java
@TransactionalEventListener
void on(OrderPaid event) { /* ... */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPaid event) { /* ... */ }
~~~

Ghi `phase = AFTER_COMMIT` thường có lợi khi viết tài liệu giáo dục hoặc khi codebase dùng nhiều pha listener khác nhau. Nó không làm callback bất đồng bộ hơn, nhanh hơn hoặc bền vững hơn.

## 7. Cạm bẫy quan trọng: AFTER_COMMIT nhưng vẫn còn transaction resources

Nhiều người nghĩ: “transaction đã commit, listener ghi database bằng repository như bình thường thì chắc chắn dữ liệu được commit.” Đây là một giả định **nguy hiểm**.

Theo hành vi transaction synchronization của Spring, khi callback hậu commit chạy, một số resource của transaction cũ (chẳng hạn connection hoặc session) **có thể vẫn gắn với thread**. Transaction nguồn đã commit và sẽ **không có thêm một commit mới** cho ghi chép vô tình tham gia resource đó. Vì vậy, Spring khuyến nghị dùng **transaction mới** cho những thao tác dữ liệu cần thực sự được ghi sau commit.

### Thiết kế an toàn: callback mỏng + service REQUIRES_NEW

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class PaymentNotificationListener {

    private final NotificationRequestWriter writer;

    PaymentNotificationListener(NotificationRequestWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPaid event) {
        writer.enqueue(event);
    }
}
~~~

Service ghi trong transaction mới:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NotificationRequestWriter {

    private final NotificationRequestRepository requests;

    public NotificationRequestWriter(NotificationRequestRepository requests) {
        this.requests = requests;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void enqueue(OrderPaid event) {
        requests.insertOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`NotificationRequestRepository.insertOnce` là **API minh họa do ứng dụng tự thiết kế**, phải bảo đảm ghi idempotent, ví dụ bằng unique constraint trên `source_event_id`. Đoạn mã giả định transaction manager hỗ trợ transaction độc lập và được cấu hình đúng với repository.

Vì `PaymentNotificationListener` gọi **một bean Spring khác**, lời gọi đi qua Spring transaction proxy để `REQUIRES_NEW` có hiệu lực. Đừng đặt `@Transactional(REQUIRES_NEW)` lên một method trong cùng bean rồi gọi bằng `this.enqueue(...)` và kỳ vọng Spring tự can thiệp qua self-invocation.

### Không nên làm điều này

~~~java
@Component
class UnsafeNotificationListener {

    private final NotificationRequestRepository requests;

    UnsafeNotificationListener(NotificationRequestRepository requests) {
        this.requests = requests;
    }

    @TransactionalEventListener
    void on(OrderPaid event) {
        // Có nguy cơ dùng resource của transaction vừa commit,
        // không có một lượt commit mới cho thao tác ghi này.
        requests.save(...);
    }
}
~~~

Đây là ví dụ **cảnh báo**, không phải quy tắc rằng mọi `save()` sau commit đều luôn thất bại. Kết quả phụ thuộc transaction manager, propagation, repository và resource. Hãy kiểm thử rằng bản ghi thực sự tồn tại sau khi callback hoàn tất, thay vì chỉ kiểm tra `save` được gọi.

## 8. AFTER_COMMIT có đồng bộ không?

**Mặc định, `@TransactionalEventListener(AFTER_COMMIT)` không tự bất đồng bộ.** Listener có thể được gọi trong thread đang xử lý transaction commit của producer. Điều này có hai hệ quả:

- Callback chạy **sau khi dữ liệu T1 đã commit**, nhưng lời gọi API ban đầu có thể **chưa trả response** vì còn đợi callback xử lý.
- Một công việc hậu commit tốn nhiều thời gian như HTTP/email chậm vẫn có thể làm đường gọi nguồn bị chậm, dù không còn giữ transaction T1 theo cùng cách như lúc trước commit.

~~~mermaid
sequenceDiagram
    participant API as HTTP request thread
    participant DB as Database
    participant L as AFTER_COMMIT listener
    API->>DB: Commit T1
    DB-->>API: Commit OK
    API->>L: Gọi listener sau commit
    L->>L: Xử lý đồng bộ
    L-->>API: Return
    API-->>API: Hoàn tất và trả response
~~~

Sơ đồ mô tả **trường hợp callback đồng bộ điển hình**, không phải cam kết về thứ tự mọi middleware, response wrapper hay executor tùy chỉnh.

Nếu nghiệp vụ có thể chấp nhận eventual consistency và muốn giảm độ trễ request, có thể dùng cơ chế bất đồng bộ phù hợp, nhưng phải hiểu rằng **chạy trên thread khác không tự đồng nghĩa có transaction riêng hoặc có lưu dấu để retry sau crash**.

### So sánh với @ApplicationModuleListener

Trong Spring Modulith, `@ApplicationModuleListener` là annotation thuận tiện cho phản ứng giữa các module: thường kết hợp `@TransactionalEventListener` sau commit, `@Async` và `@Transactional(propagation = REQUIRES_NEW)`.

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsOnOrderPaid {

    private final LoyaltyLedger ledger;

    AwardPointsOnOrderPaid(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        ledger.awardOnce(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`LoyaltyLedger.awardOnce` là phương thức nghiệp vụ minh họa. Cần cài đặt chống cộng điểm trùng trong database. Listener có thể chạy **sau** khi request thanh toán đã trả response; một lần commit của `orders` không có nghĩa ledger của `loyalty` đã được cập nhật ngay.

| Thuộc tính | `@TransactionalEventListener(AFTER_COMMIT)` | `@ApplicationModuleListener` |
| --- | --- | --- |
| Sau commit nguồn | Có | Có |
| Bất đồng bộ mặc định | Không | Có |
| Transaction mới mặc định cho handler | Không | Có theo cấu hình annotation chuẩn |
| Ảnh hưởng latency request | Có thể trực tiếp | Thường cách ly hơn |
| Tự bảo đảm exactly-once | Không | Không |
| Cần registry/storage khi muốn phục hồi sau crash | Có | Có |
| Consumer cần idempotency khi bị giao lại | Có | Có |

Đừng chọn `@ApplicationModuleListener` cho một bất biến đòi hỏi kết quả đồng bộ ngay trước khi trả thành công. Khi đó cần thiết kế workflow hoặc một API service đồng bộ có ngữ nghĩa rõ hơn.

## 9. Khi không có transaction, listener AFTER_COMMIT có nhận event không?

Theo mặc định, **không**. `@TransactionalEventListener` phải liên kết được event với một transaction tương thích. Nếu `publishEvent` được gọi ngoài transaction, không có pha commit nguồn để kích hoạt callback, nên listener bị bỏ qua.

~~~java
@Component
class SomePublisher {

    private final ApplicationEventPublisher publisher;

    SomePublisher(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void publishWithoutTransaction(OrderPaid event) {
        publisher.publishEvent(event);
    }
}
~~~

Một `@EventListener` thông thường vẫn có thể nhận event trên, nhưng `@TransactionalEventListener(AFTER_COMMIT)` mặc định không nhận.

### fallbackExecution

Spring cho phép đặt:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
void on(OrderPaid event) {
    // Có thể được gọi ngay khi không có transaction để chờ commit.
}
~~~

**Cân nhắc kỹ trước khi bật.** Khi không có transaction, nhánh fallback không có commit nguồn làm điều kiện bảo vệ. Nếu logic consumer phụ thuộc chặt vào “đơn hàng đã commit” thì fallback có thể làm suy yếu chính mục tiêu của AFTER_COMMIT. Chỉ bật khi yêu cầu nghiệp vụ xác định rõ xử lý cả hai trường hợp và đã có test.

### Nested transaction và REQUIRES_NEW

Nếu producer publish trong một transaction `REQUIRES_NEW` **bên trong** một workflow bên ngoài đang có transaction khác, callback AFTER_COMMIT gắn với **transaction nơi event được publish**. Nó có thể chạy ngay khi transaction bên trong commit, **dù transaction bên ngoài sau đó rollback**. Đừng suy luận “AFTER_COMMIT nghĩa là toàn bộ request/workflow đã thành công”; nó chỉ nói về **transaction có liên quan**.

Với môi trường dùng reactive transaction, context giao dịch không được truyền giống thread-bound transaction imperative. Các phiên bản Spring hỗ trợ transactional event trong reactive flow cần cơ chế truyền transaction context phù hợp (ví dụ `TransactionalEventPublisher` và thông tin context). Không nên áp dụng nguyên xi giả định thread-local của bài này cho reactive pipeline mà chưa kiểm tra phiên bản và cách publish thực tế.

## 10. Exception sau commit: lỗi consumer không thể rollback lại T1

Một tình huống điển hình:

1. `orders` commit trạng thái `PAID` thành công.
2. Spring kích hoạt callback `AFTER_COMMIT` ở `notifications`.
3. `NotificationRequestWriter.enqueue(...)` gặp lỗi database hoặc gọi external API bị timeout.
4. Consumer không hoàn tất, nhưng **đơn hàng đã ở trạng thái PAID**.

~~~mermaid
flowchart TD
    A["T1 của orders commit thành công"] --> B["AFTER_COMMIT listener nhận OrderPaid"]
    B --> C{"Consumer xử lý thành công?"}
    C -->|"Có"| D["Ghi nhận hiệu ứng consumer"]
    C -->|"Không"| E["Exception / publication chưa hoàn tất"]
    E --> F["T1 không thể rollback ngược"]
    F --> G["Cần retry, khôi phục hoặc xử lý thủ công"]
~~~

Đây là khác biệt về ý nghĩa lỗi so với một `@EventListener` đồng bộ chạy trong T1. Khi lỗi đến trước commit và exception không bị xử lý, T1 thường có thể rollback. Với lỗi **sau commit**, không có cơ chế “trở về trạng thái chưa thanh toán” chỉ vì listener không gửi được email.

**Cẩn trọng với response API:** callback hậu commit đồng bộ có thể làm lỗi được quan sát trên đường hoàn tất transaction tùy hạ tầng và cách xử lý exception. Vì vậy HTTP request có thể gặp exception dù T1 đã commit. Đừng tự động yêu cầu khách “thanh toán lại” khi đường API báo lỗi mà chưa đối chiếu trạng thái database; việc retry request phải idempotent.

### Không nuốt lỗi một cách vô thức

~~~java
@TransactionalEventListener
void on(OrderPaid event) {
    try {
        writer.enqueue(event);
    } catch (RuntimeException failure) {
        log.error("Cannot enqueue notification {}", event.eventId(), failure);
        // Nếu chỉ nuốt lỗi, cơ chế theo dõi có thể coi handler đã thành công.
    }
}
~~~

Nếu hiệu ứng là bắt buộc và hệ thống dùng Event Publication Registry để theo dõi completion, việc bắt rồi bỏ qua exception có thể làm hạ tầng coi listener đã hoàn thành, khiến publication không còn được retry đúng cách. Hãy ghi lỗi và cho exception đi theo đường xử lý thất bại được thiết kế, hoặc chuyển sang một bản ghi công việc bền vững riêng và xác định rõ tiêu chí hoàn tất.

Không phải mọi failure đều nên retry vô hạn. Lỗi tạm thời như database timeout khác lỗi vĩnh viễn do contract sai hoặc dữ liệu không hợp lệ. Cần phân loại, backoff, cảnh báo và đường xử lý thủ công.

## 11. Khoảng trống giữa commit nguồn và hoàn tất consumer

AFTER_COMMIT ngăn consumer phản ứng với **transaction đã rollback**, nhưng không tự đóng khoảng trống:

~~~text
T1 commit thành công
   |
   +-- tiến trình có thể dừng trước khi listener được gọi
   |
   +-- listener có thể thất bại hoặc bị timeout
   |
   +-- consumer có thể commit hiệu ứng nhưng tiến trình
       dừng trước khi ghi nhận listener đã hoàn tất
~~~

Nếu event chỉ nằm trong bộ nhớ, JVM crash có thể khiến công việc hậu commit không còn đường khôi phục. Muốn tăng độ tin cậy, Spring Modulith cung cấp **Event Publication Registry** để theo dõi publication dành cho các transactional event listener được hỗ trợ, khi ứng dụng đã cấu hình storage và cơ chế recovery thích hợp.

### Event Publication Registry giải quyết phần nào?

Trong một cấu hình có publication repository **bền vững**, producer publish trong T1 và registry có thể ghi thông tin publication cho từng listener phù hợp **cùng transaction nguồn**. Khi T1 commit, cả dữ liệu nguồn và publication tồn tại. Listener chạy sau commit; nếu thành công, publication được đánh dấu hoàn tất. Publication còn dang dở có thể được tìm và resubmit theo chính sách vận hành.

~~~mermaid
sequenceDiagram
    participant O as orders / T1
    participant DB as Database
    participant R as Event Publication Registry
    participant L as loyalty / Listener

    O->>DB: Đổi Order thành PAID
    O->>R: publishEvent(OrderPaid)
    R->>DB: Ghi publication cho listener trong T1
    O->>DB: Commit T1
    DB-->>O: T1 thành công
    R-->>L: Kích hoạt listener hậu commit
    L->>DB: Ghi điểm trong transaction mới
    L-->>R: Xử lý thành công
    R->>DB: Ghi publication completion
~~~

Một event có thể có **nhiều publication** tương ứng các listener, ví dụ `loyalty` và `notifications`. Một publication hoàn tất không chứng minh tất cả publication khác đã hoàn tất.

**Các điều kiện phải kiểm tra trong dự án thật:**

- Spring Modulith đã được thêm dependency phù hợp phiên bản, bao gồm tích hợp JDBC/JPA hoặc một implementation lưu publication khác hay chưa?
- Publication repository có **persistence bền vững**, schema/database phù hợp và tham gia cùng transaction nguồn khi phát event hay không?
- Listener đang dùng có nằm trong tập transactional listeners được registry theo dõi theo phiên bản đó không?
- Có cơ chế tìm publication **chưa hoàn tất**, resubmit khi restart hoặc lịch chạy vận hành được cấu hình không?
- Retry có giới hạn, log/metric/cảnh báo và cách xử lý lỗi vĩnh viễn không?
- Consumer có idempotency để phục hồi sau crash giữa business commit và publication completion không?

Không nên viết “có `@TransactionalEventListener` tức là event tự được lưu bền vững và retry mãi mãi”. Bản thân annotation chỉ nói **phase**. Registry/storage và chính sách vận hành là phần khác phải thiết lập.

## 12. At-least-once, idempotency và hai lần hoàn tất khác nhau

Giả sử `loyalty` xử lý `OrderPaid(eventId = E1)`:

| Mốc | Trạng thái |
| --- | --- |
| 10:00:00 | `orders` publish E1 trong T1 |
| 10:00:01 | T1 commit, publication của loyalty tồn tại |
| 10:00:02 | `loyalty` nhận E1 |
| 10:00:03 | `loyalty` ghi điểm và commit T2 |
| 10:00:03 | JVM dừng trước khi registry ghi completion |
| 10:01:00 | Sau restart, E1 được resubmit |
| 10:01:01 | `loyalty` phát hiện E1 đã xử lý, không cộng lại |
| 10:01:01 | Publication được hoàn tất theo cơ chế được cấu hình |

Đây là lý do **không thể đảm bảo đúng một hiệu ứng nghiệp vụ chỉ bằng cách gọi listener một lần**. Khi có khôi phục, một sự kiện có thể được giao nhiều lần; consumer phải xử lý theo mô hình **at-least-once an toàn với idempotency**.

### Ledger chống cộng điểm trùng

~~~sql
CREATE TABLE loyalty_awards (
    id BIGINT PRIMARY KEY,
    source_event_id VARCHAR(36) NOT NULL,
    order_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_loyalty_awards_source_event UNIQUE (source_event_id)
);
~~~

Logic minh họa:

~~~text
on(OrderPaid E1):
    BEGIN transaction mới
    thử ghi loyalty_awards(source_event_id = E1.eventId)
    nếu bản ghi đã tồn tại:
        kết thúc an toàn, không cộng điểm thêm
    nếu ghi mới thành công:
        cập nhật điểm thưởng trong cùng transaction
    COMMIT
    trả kết quả thành công cho listener
~~~

**Ghi dấu idempotency và ghi điểm phải ở cùng transaction** để tránh một phần thành công, một phần thất bại. Cần unique constraint hoặc cơ chế dữ liệu tương đương để chống hai lần xử lý đồng thời; chỉ kiểm tra bằng `SELECT exists` rồi `INSERT` không có unique constraint vẫn có race condition.

Cũng cần chống **trùng nghiệp vụ ở producer**: nếu webhook thanh toán lặp tạo `OrderPaid(E1)` và `OrderPaid(E2)` với hai eventId khác nhau cho cùng `paymentId`, consumer chống trùng theo eventId không đủ. Producer phải tránh phát transition mới cho một payment đã xử lý, có thể kết hợp khóa nghiệp vụ ở consumer nếu cần.

### Email và side effect ngoài database

Nếu listener gọi email provider, bản ghi “đã gửi” trong database không tự biến việc gửi mạng thành transaction nguyên tử. Provider có thể đã nhận email nhưng ứng dụng crash trước khi ghi kết quả. Cần quyết định chiến lược: idempotency key của provider (nếu hỗ trợ), yêu cầu gửi bền vững trong `notifications`, retry với kiểm tra trạng thái và chấp nhận giới hạn duplicate được định nghĩa rõ.

Nếu listener chỉ **ghi một yêu cầu gửi email**, trạng thái “listener đã hoàn tất” chỉ nên có nghĩa yêu cầu đó được lưu bền vững, **không phải** người dùng đã nhận email.

## 13. Kiểm thử AFTER_COMMIT bằng transaction thật

Mock `ApplicationEventPublisher` chỉ chứng minh producer gọi một phương thức. Nó không chứng minh `@TransactionalEventListener` chạy đúng pha, rằng transaction nguồn commit thật hay consumer đã ghi dữ liệu an toàn. Cần test với **Spring application context có transaction manager**.

### Bài test nhỏ bằng TransactionTemplate

Ví dụ sau dùng một event thử nghiệm và một recorder để kiểm chứng **thứ tự tương đối**. Dự án cần có Spring Boot Test, JUnit, AssertJ và **một `PlatformTransactionManager` được cấu hình trong context** (ví dụ nhờ datasource/JPA hoặc cấu hình test).

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@Import(AfterCommitPhaseTests.ProbeConfig.class)
class AfterCommitPhaseTests {

    record ProbeEvent() {}

    static class ProbeRecorder {
        private final List<String> calls = new ArrayList<>();

        void add(String value) {
            calls.add(value);
        }

        void clear() {
            calls.clear();
        }

        List<String> snapshot() {
            return List.copyOf(calls);
        }
    }

    static class ProbeListener {
        private final ProbeRecorder recorder;

        ProbeListener(ProbeRecorder recorder) {
            this.recorder = recorder;
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void on(ProbeEvent event) {
            recorder.add("after-commit");
        }
    }

    @TestConfiguration
    static class ProbeConfig {

        @Bean
        ProbeRecorder recorder() {
            return new ProbeRecorder();
        }

        @Bean
        ProbeListener probeListener(ProbeRecorder recorder) {
            return new ProbeListener(recorder);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager
        ) {
            return new TransactionTemplate(manager);
        }
    }

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    TransactionTemplate transactions;

    @Autowired
    ProbeRecorder recorder;

    @BeforeEach
    void resetRecorder() {
        recorder.clear();
    }

    @Test
    void listenerRunsOnlyAfterCommit() {
        transactions.executeWithoutResult(status -> {
            recorder.add("inside-tx");
            publisher.publishEvent(new ProbeEvent());
            recorder.add("after-publish");
            assertThat(recorder.snapshot())
                    .containsExactly("inside-tx", "after-publish");
        });

        assertThat(recorder.snapshot()).containsExactly(
                "inside-tx",
                "after-publish",
                "after-commit"
        );
    }

    @Test
    void listenerDoesNotRunOnRollback() {
        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent());
            status.setRollbackOnly();
        });

        assertThat(recorder.snapshot()).isEmpty();
    }
}
~~~

Đây là một bài test **imperative transaction**, giả định listener **không async**. Nó kiểm chứng callback được gọi sau commit nhưng **chưa chứng minh** việc ghi database sau commit có transaction mới hay registry bền vững.

Nếu có nhiều `PlatformTransactionManager`, cần chọn đúng manager cho `TransactionTemplate`. Không bọc những test này trong một transaction test bên ngoài đang rollback ở cuối; transaction được lồng sẽ làm thay đổi mốc commit thực sự mà bạn định quan sát.

### Ma trận kiểm thử cần có trong dự án

| Kịch bản | Cách thực hiện | Kỳ vọng |
| --- | --- | --- |
| **Publish trong T1, chưa commit** | Gọi publish rồi kiểm tra ngay trong `TransactionTemplate` | AFTER_COMMIT chưa chạy |
| **T1 commit thành công** | Kết thúc transaction bình thường | AFTER_COMMIT được kích hoạt |
| **T1 rollback** | `status.setRollbackOnly()` hoặc exception | AFTER_COMMIT không chạy |
| **Commit DB thất bại** | Tạo constraint lỗi ở commit | Không tạo hiệu ứng hậu commit |
| **Publish ngoài transaction** | Gọi publisher từ method thường | Transactional listener mặc định không chạy |
| **fallbackExecution** | Bật rồi publish ngoài transaction | Listener chạy theo nhánh fallback; phải giải thích semantics |
| **AFTER_COMMIT ghi DB** | Listener gọi writer `REQUIRES_NEW` qua proxy | Bản ghi consumer commit độc lập và thực sự tồn tại |
| **Self-invocation** | Gọi `@Transactional` từ method cùng bean | Chẩn đoán trường hợp thiếu transaction |
| **Listener hậu commit ném lỗi** | Giả lập database consumer timeout | Dữ liệu nguồn vẫn đã commit |
| **Nhiều consumer** | Một listener thành công, một listener lỗi | Trạng thái hoàn tất độc lập theo publication khi có registry |
| **Restart/recovery** | Commit nguồn rồi gây crash/lỗi consumer | Publication còn tồn tại và có đường resubmit nếu storage đã cấu hình |
| **Retry cùng eventId** | Giao lại E1 | Chỉ một hiệu ứng nghiệp vụ |

Spring Modulith có các công cụ kiểm thử như `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và `ApplicationModules.verify()`. Chọn công cụ phù hợp để kiểm tra **event đã publish**, **tương tác module**, **ranh giới phụ thuộc** và **side effect sau commit**; không coi một bài test verify cấu trúc là bằng chứng listener đã được phục hồi sau crash.

### Bẫy @Transactional trong test

Một bài test được Spring Test bọc `@Transactional` thường tự rollback khi kết thúc. Lúc đó **không có commit nguồn**, nên `AFTER_COMMIT` sẽ không chạy. Nếu test chỉ làm:

~~~java
@Transactional
@Test
void publishesOrderPaid() {
    paymentService.recordVerifiedPayment(...);
    // Không nên chờ AFTER_COMMIT tự chạy ở cuối nếu test rollback.
}
~~~

thì thất bại quan sát listener có thể đến từ **cách tổ chức test**, không phải production code. Hãy dùng transaction manager/template để tạo commit thật hoặc cấu hình test có chủ đích.

### Bẫy async trong test

Với `@ApplicationModuleListener` bất đồng bộ, **không kiểm tra ngay sau phương thức producer** rồi giả định consumer đã xong. Dùng cơ chế đợi một **điều kiện nghiệp vụ quan sát được với timeout** (ví dụ sổ điểm xuất hiện), thay vì `Thread.sleep` cố định.

## 14. Quan sát AFTER_COMMIT trong production

Một hệ thống vận hành tốt phải phân biệt **đã commit nguồn**, **đã kích hoạt listener**, **consumer đã tạo side effect** và **publication đã hoàn tất**. Một dòng log “Event received” chỉ chứng minh listener đã bắt đầu, không chứng minh kết quả cuối cùng.

| Trường/tín hiệu | Ý nghĩa |
| --- | --- |
| `eventId`, `eventType`, `orderId`, `paymentId` | Truy vết lần phát sinh và giao dịch nguồn |
| `occurredAt` | Khi producer tạo event theo contract |
| `sourceCommitOutcome` | Commit nguồn thành công hay rollback |
| `listenerName`, `listenerPhase=AFTER_COMMIT` | Consumer nào đang thực thi ở pha nào |
| `receivedAt`, `processedAt`, `attempt` | Phân biệt thời điểm nhận với hoàn tất và retry |
| `consumerTransactionOutcome` | T2 của consumer có commit hay không |
| `publicationPending`, `publicationAge` | Công việc còn dang dở và mức độ tồn đọng |
| `exceptionCategory`, `retryCount` | Phân loại lỗi tạm thời và lỗi không thể tự khôi phục |
| `duplicateSuppressed` | Số lần consumer bỏ qua event đã xử lý |

Đừng dùng `occurredAt` để khẳng định publication đã hoàn tất. Độ trễ `processedAt - occurredAt` là thước đo hữu ích khi các đồng hồ đủ đồng bộ, nhưng cần ghi nhận sai số do clock skew và khoảng cách giữa tạo event với commit.

### Quy trình xử lý một sự cố

Giả sử khách báo đã thanh toán nhưng chưa được cộng điểm:

1. Tìm `orders` theo `paymentId` và xác nhận nguồn **đã commit** trạng thái `PAID`.
2. Lấy `eventId` đã tạo trong transition và xác định listener thuộc `loyalty`.
3. Kiểm tra publication của listener trong registry **nếu registry đã cấu hình**; biết nó còn chờ hay hoàn tất.
4. Đối chiếu ledger của loyalty, vì consumer có thể đã commit điểm nhưng publication completion chưa được ghi.
5. Phân loại lỗi, khắc phục nguyên nhân rồi resubmit **có kiểm soát**; idempotency phải chặn cộng điểm trùng.
6. Xác minh trạng thái hoàn tất của publication và ledger sau khi phục hồi.

**Không tự sửa trạng thái publication thành “completed” chỉ để xóa cảnh báo** nếu chưa kiểm chứng hiệu ứng nghiệp vụ. Không dùng log có chứa dữ liệu cá nhân hoặc thông tin thanh toán nhạy cảm vượt nhu cầu điều tra; theo dõi bằng các identifier thích hợp và phân quyền.

## 15. Những nhầm lẫn thường gặp

**Nhầm lẫn 1 — `publishEvent` chạy sau commit.** Không. Producer thường publish event **bên trong T1**. Listener AFTER_COMMIT mới đợi commit thành công để bắt đầu xử lý.

**Nhầm lẫn 2 — AFTER_COMMIT đồng nghĩa async.** Không. `@TransactionalEventListener` thuần Spring mặc định **không tự async**. `@ApplicationModuleListener` mới là tiện ích Modulith có async và transaction riêng.

**Nhầm lẫn 3 — AFTER_COMMIT tự mở transaction mới.** Không. Callback có thể còn thấy resource của T1 nhưng T1 đã commit. Muốn ghi dữ liệu mới an toàn, hãy dùng `REQUIRES_NEW` qua proxy Spring đúng cách.

**Nhầm lẫn 4 — AFTER_COMMIT không bao giờ có lỗi.** Sai. Consumer vẫn có thể gặp lỗi database, timeout, lỗi logic hoặc dừng JVM. Lỗi đến sau commit không làm nguồn tự rollback.

**Nhầm lẫn 5 — Đã commit nguồn nghĩa là mọi listener xong.** Sai. Mỗi consumer có transaction và trạng thái hoàn tất riêng.

**Nhầm lẫn 6 — Registry tự động có chỉ vì thêm annotation.** Sai. Cần persistence/integration và cơ chế tìm, xử lý lại publication chưa hoàn tất theo cấu hình.

**Nhầm lẫn 7 — Có registry là exactly-once.** Không. Một event có thể được resubmit sau crash trước completion. Consumer cần idempotency.

**Nhầm lẫn 8 — Publish ngoài transaction thì callback AFTER_COMMIT vẫn chạy sau đó.** Mặc định không. Nếu bật `fallbackExecution`, listener có thể chạy mà **không có commit nguồn**; đó là ý nghĩa khác cần thiết kế rõ.

**Nhầm lẫn 9 — `@Transactional` luôn được áp dụng ở mọi lời gọi.** Không. Self-invocation trong cơ chế proxy thông thường có thể bỏ qua transaction interceptor.

**Nhầm lẫn 10 — Retry HTTP thanh toán là an toàn khi nhận lỗi ở callback hậu commit.** Không tự động. Nguồn có thể đã commit dù đường API trả lỗi; cần đối chiếu trạng thái và chống thanh toán lặp.

**Nhầm lẫn 11 — Event có `occurredAt` nghĩa là thời gian commit chính xác.** Không. Timestamp này là một mốc do producer định nghĩa, có thể trước commit; không thay được commit/processed time.

**Nhầm lẫn 12 — Transaction của mọi module cùng JVM là một transaction toàn cục.** Không. Transaction boundary phụ thuộc manager, resource, thread và propagation. AFTER_COMMIT không tạo transaction phân tán qua email/broker.

## 16. Bài thực hành: đơn hàng commit và cộng điểm hậu commit

### Bối cảnh

Ứng dụng bán vé có ba module:

- `payments`: xác thực thanh toán và phát `PaymentCompleted`.
- `tickets`: phát hành vé khi payment commit.
- `notifications`: tạo yêu cầu gửi email khi payment commit; việc gửi thật được xử lý riêng.

Yêu cầu: nếu transaction nguồn rollback, **không phát vé và không gửi email**; nếu một consumer lỗi sau commit, thanh toán vẫn giữ nguyên; hệ thống có cách phát hiện publication chưa hoàn tất và phục hồi mà không phát vé trùng.

### Các bước triển khai

1. **Định nghĩa contract:** tạo `PaymentCompleted(eventId, paymentId, reservationId, occurredAt)` trong public API của `payments`. Tài liệu hóa rằng event chỉ phát khi một transition thanh toán hợp lệ đã được xác nhận.
2. **Tạo producer:** viết `@Transactional` service, chuyển trạng thái payment và publish event **bên trong T1**. Chống webhook lặp theo `paymentId` hoặc khóa nghiệp vụ.
3. **Tạo listener AFTER_COMMIT thuần Spring:** trong `notifications`, dùng `@TransactionalEventListener(AFTER_COMMIT)` gọi một writer service `REQUIRES_NEW` để lưu yêu cầu gửi.
4. **Tạo listener Spring Modulith:** trong `tickets`, dùng `@ApplicationModuleListener` để phát hành vé bất đồng bộ trong transaction riêng.
5. **Chứng minh rollback:** cố tình ném exception trước commit T1; kiểm tra không có vé/yêu cầu thông báo do listener hậu commit tạo.
6. **Chứng minh commit:** cho T1 commit; kiểm tra request gửi và vé được lưu sau khi consumer hoàn tất. Với listener async, đợi điều kiện nghiệp vụ có timeout.
7. **Cấu hình Event Publication Registry:** dùng repository bền vững phù hợp phiên bản, xác minh publication được commit cùng dữ liệu nguồn và hoàn tất theo listener.
8. **Tạo lỗi consumer:** làm `tickets` ném exception khi ghi vé sau commit, xem publication chưa hoàn tất trong registry.
9. **Khôi phục:** sửa lỗi, resubmit publication với cùng eventId; kiểm tra ràng buộc chống trùng trên `paymentId` hoặc `eventId`.
10. **Thử crash sau business commit:** mô phỏng consumer đã lưu vé nhưng completion chưa được ghi, rồi resubmit và xác minh **không tạo vé thứ hai**.
11. **Đo quan sát:** log `eventId`, `listenerName`, `receivedAt`, `processedAt`, kết quả T1/T2 và tuổi publication chưa hoàn tất.

### Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Event đúng nghiệp vụ | Không phát `PaymentCompleted` từ request chưa xác thực |
| Ranh giới module | Consumer chỉ import event contract công khai |
| Publish trong T1 | Event được tạo trước commit, callback chờ commit |
| Rollback | Không có phản ứng AFTER_COMMIT khi T1 rollback |
| Commit | Listener nhận event chỉ sau khi T1 commit |
| Transaction mới | Ghi từ listener hậu commit thật sự được commit trong T2 |
| Async Modulith | `tickets` có thể hoàn tất muộn hơn response nguồn |
| Registry | Publication còn chờ được ghi nhận và resubmit đúng |
| Idempotency | Cùng event giao lại không phát vé trùng |
| Quan sát | Truy vết được event, listener, lỗi, retry và trạng thái cuối |

### Câu hỏi tự đánh giá

**Câu 1. `@TransactionalEventListener` có cần ghi `phase = AFTER_COMMIT` mới chạy hậu commit không?**

Không. `AFTER_COMMIT` là phase mặc định của annotation. Khai báo tường minh giúp dễ đọc khi có nhiều listener ở các pha khác nhau.

**Câu 2. Tại sao không ghi database ngay trong listener AFTER_COMMIT mà không quan tâm propagation?**

Vì transaction nguồn đã commit nhưng resource có thể còn gắn với thread. Nếu thao tác ghi tham gia resource cũ, không có commit mới cho dữ liệu đó. Dùng transaction mới `REQUIRES_NEW` qua Spring proxy cho công việc cần lưu độc lập.

**Câu 3. Nếu `notifications` ném exception sau commit, đơn thanh toán có bị rollback không?**

Không thể rollback ngược transaction nguồn đã thành công chỉ vì listener hậu commit lỗi. Phải có cơ chế theo dõi và retry hiệu ứng riêng.

**Câu 4. Nếu publisher chạy không có transaction thì AFTER_COMMIT hoạt động ra sao?**

Mặc định listener không được gọi. `fallbackExecution = true` cho phép xử lý nhánh không có transaction, nhưng không còn bảo đảm đã có commit nguồn làm điều kiện.

**Câu 5. Cùng `OrderPaid(E1)` được giao hai lần có vi phạm thiết kế của registry không?**

Không. Publication có thể bị resubmit khi consumer đã làm xong nhưng completion chưa kịp ghi. Idempotency bảo đảm tác động nghiệp vụ không bị nhân đôi.

**Câu 6. Vì sao AFTER_COMMIT không nhất thiết nhanh hơn @EventListener?**

Vì AFTER_COMMIT thuần Spring có thể chạy **đồng bộ trên thread commit**. Phản ứng mất nhiều thời gian vẫn khiến đường API chờ; cần chọn cơ chế async phù hợp nếu muốn cách ly latency.

## 17. Checklist áp dụng trong dự án

- [ ] Event mô tả một sự thật nghiệp vụ đã được producer xác nhận, không phải một yêu cầu còn đang chờ.
- [ ] Producer publish trong transaction Spring **thực sự hoạt động**, không chỉ có annotation trang trí.
- [ ] Hiểu `AFTER_COMMIT` là **listener chạy sau commit nguồn**, không phải event được tạo sau commit.
- [ ] Biết `AFTER_COMMIT` là pha mặc định của `@TransactionalEventListener`.
- [ ] Không nhầm AFTER_COMMIT với async hoặc transaction mới.
- [ ] Với ghi database sau commit, dùng writer `REQUIRES_NEW` qua bean proxy phù hợp.
- [ ] Không tạo side effect cho transaction nguồn rollback.
- [ ] Không retry thanh toán mù quáng khi HTTP lỗi do listener hậu commit.
- [ ] Không bật `fallbackExecution` nếu chưa hiểu đường publish ngoài transaction.
- [ ] Không truyền JPA entity/lazy object của producer vào contract hậu commit.
- [ ] Công bố event contract qua API module, kiểm tra module boundary.
- [ ] Khi cần phục hồi sau crash, cấu hình publication repository bền vững và chính sách resubmit.
- [ ] Consumer có idempotency với unique constraint/transaction.
- [ ] Phân biệt xử lý sau commit trong cùng JVM với integration event qua broker ngoài.
- [ ] Test commit thật, rollback, lỗi listener, self-invocation, retry và case chưa ghi completion.
- [ ] Quan sát từng publication và từng consumer bằng eventId, listener, trạng thái, tuổi và lỗi.
- [ ] Không coi việc biên soạn/đánh dấu bài học là thay thế cho QA chuyên môn và test phiên bản dự án.

## Ghi nhớ

**Pha AFTER_COMMIT** của `@TransactionalEventListener` bảo đảm callback chỉ được kích hoạt sau khi **transaction liên quan đã commit thành công**. Producer vẫn có thể publish event **bên trong transaction nguồn**, và listener có thể chạy đồng bộ trên đường hoàn tất transaction. Khi cần ghi dữ liệu mới, phải có transaction riêng phù hợp; khi cần xử lý bất đồng bộ giữa các module, `@ApplicationModuleListener` là lựa chọn tiện lợi của Spring Modulith.

Tuy nhiên, **AFTER_COMMIT không tự bảo đảm delivery bền vững hay exactly-once side effect**. Nếu consumer lỗi hoặc tiến trình crash, muốn phục hồi cần Event Publication Registry với storage và chính sách retry/resubmit đã cấu hình, cùng idempotency ở consumer. Kết hợp contract công khai, ranh giới module, kiểm thử commit/rollback và quan sát theo từng event/listener sẽ giúp xây dựng giao tiếp ứng dụng đáng tin cậy mà vẫn giữ quyền sở hữu nghiệp vụ rõ ràng.

