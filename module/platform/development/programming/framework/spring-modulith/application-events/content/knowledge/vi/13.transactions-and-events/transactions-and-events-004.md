# Event trước khi commit

## Mục tiêu bài học

Trong Spring Modulith, một module có thể thay đổi trạng thái nghiệp vụ trong transaction và gọi `ApplicationEventPublisher.publishEvent(...)` **trước khi transaction đó commit**. Điều này không sai: event có thể được tạo và công bố như một phần của xử lý nghiệp vụ, còn việc consumer được gọi **ngay lập tức**, **trước khi commit** hay **sau khi commit** lại phụ thuộc vào loại listener.

Điểm dễ nhầm là cụm **“event trước khi commit”** có ít nhất hai cách hiểu:

1. **Publish event khi transaction nguồn chưa commit:** producer gọi `publishEvent` trong một phương thức `@Transactional`; Spring có thể gọi ngay những `@EventListener` đồng bộ.
2. **Nhận event tại pha `BEFORE_COMMIT`:** producer đã publish event trước đó, nhưng `@TransactionalEventListener(phase = BEFORE_COMMIT)` chỉ được kích hoạt khi Spring bước vào pha chuẩn bị commit transaction.

Hai mốc này **không đồng nhất**. Pha `BEFORE_COMMIT` diễn ra muộn hơn việc publish thông thường và vẫn **chưa phải commit thành công**. Nếu một bước kiểm tra, flush hoặc thao tác database cuối cùng thất bại, transaction có thể rollback dù callback `BEFORE_COMMIT` đã chạy.

Bài thuộc chương **Giao dịch và event** của module **SPRING_MODULITH_APPLICATION_EVENTS**. Mục tiêu chung là giao tiếp giữa các module Spring Modulith qua application events nhằm giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ; phần này tập trung vào transaction, listener trước commit, hệ quả của exception, cách chọn listener hậu commit, Event Publication Registry, retry, kiểm thử và khả năng quan sát.

Sau bài này, bạn có thể xác định chính xác từng mốc của một `OrderPaid`, giải thích vì sao một listener chạy **trước commit** có thể làm transaction nguồn rollback, và thiết kế bài test chứng minh được sự khác nhau giữa **immediate listener**, **BEFORE_COMMIT listener** và **AFTER_COMMIT listener**.

## 1. Vì sao cần hiểu thời điểm event chạy?

Giả sử hệ thống bán hàng có bốn module:

| Module | Trách nhiệm | Phản ứng khi nhận `OrderPaid` |
| --- | --- | --- |
| `orders` | Sở hữu đơn hàng và việc xác nhận chuyển sang `PAID` | Producer tạo và publish event |
| `audit` | Lưu dấu chuyển trạng thái để truy vết nội bộ | Có thể cần ghi audit cùng transaction |
| `notifications` | Tạo yêu cầu gửi email cho khách | Chỉ nên gửi sau khi đơn đã commit |
| `loyalty` | Ghi điểm thưởng, quản lý idempotency | Có thể xử lý sau commit bằng transaction riêng |

Nếu một listener gửi email “Đơn hàng đã thanh toán” **trước commit**, nhưng database thất bại ở bước commit, người dùng nhận email cho một đơn chưa thực sự chuyển sang `PAID`. Ngược lại, ghi một audit record **trong cùng transaction** với đơn có thể là mong muốn: cả hai cùng thành công hoặc cùng rollback.

Vì vậy câu hỏi đúng không phải “event sync hay async tốt hơn?”, mà là:

- **Sự thật nghiệp vụ đã được xác lập ở mức logic khi nào?**
- **Dữ liệu tương ứng đã commit thành công chưa?**
- **Tác dụng của listener có rollback được cùng transaction nguồn hay không?**
- **Listener lỗi có được phép làm giao dịch nguồn thất bại không?**
- **Nếu xử lý muộn, cần lưu dấu và khôi phục như thế nào?**

Không thể trả lời những câu hỏi này chỉ bằng tên event hoặc việc code đã gọi `publishEvent()`.

## 2. Dòng thời gian: publish, before commit và commit

Trong mô hình imperative transaction thông thường của Spring, một chuỗi xử lý có thể là:

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders / @Transactional
    participant Spring as Spring application events
    participant Immediate as @EventListener
    participant Before as @TransactionalEventListener BEFORE_COMMIT
    participant DB as Database
    participant After as AFTER_COMMIT listener

    Client->>Orders: recordVerifiedPayment(...)
    Orders->>DB: Thay đổi đơn trong T1
    Orders->>Spring: publishEvent(OrderPaid)
    Spring->>Immediate: Gọi đồng bộ khi publish
    Immediate-->>Spring: Return
    Note over Spring,Before: Đăng ký callback cho phase BEFORE_COMMIT
    Spring-->>Orders: publishEvent trả về
    Orders-->>Orders: Method @Transactional kết thúc
    Orders->>Before: Callback BEFORE_COMMIT
    Before-->>Orders: Return
    Orders->>DB: Flush/commit T1
    DB-->>Orders: Commit thành công
    Orders->>After: Callback AFTER_COMMIT
    After-->>Orders: Return
    Orders-->>Client: Trả kết quả
~~~

Đây là **sơ đồ logic cho một transaction thành công, listener đồng bộ và không có executor tùy biến**. Spring còn có các bước transaction synchronization khác; thứ tự flush cụ thể phụ thuộc transaction manager/JPA provider và có thể có flush trước pha `BEFORE_COMMIT`. Không suy luận từ sơ đồ rằng database luôn flush đúng một lần ở một vị trí cố định.

Các mốc quan trọng:

| Mốc | Có thể xảy ra chuyện gì? | Có khẳng định dữ liệu `PAID` đã commit? |
| --- | --- | --- |
| **T1 đang mở** | Producer đọc/ghi entity, kiểm tra bất biến | Chưa |
| **Publish `OrderPaid`** | Listener `@EventListener` thường chạy ngay | Chưa |
| **`publishEvent` trả về** | Producer tiếp tục code; listener transactional chỉ mới đăng ký theo pha | Chưa |
| **`BEFORE_COMMIT`** | Callback của `@TransactionalEventListener(BEFORE_COMMIT)` chạy | Chưa |
| **Commit vật lý thành công** | Database xác nhận giao dịch | Có, đối với dữ liệu được commit trong T1 |
| **`AFTER_COMMIT`** | Callback hậu commit được kích hoạt | Có, nhưng consumer chưa chắc đã xử lý xong |
| **Consumer riêng hoàn tất** | Ghi điểm/thông báo được commit độc lập nếu thiết kế như vậy | Chỉ khẳng định hiệu ứng tương ứng, không phải mọi consumer |

**Kết luận nền tảng:** `publishEvent`, `BEFORE_COMMIT` và `AFTER_COMMIT` là ba mốc khác nhau. Hãy dùng ngôn ngữ chính xác trong log, tên metric và mô tả thiết kế.

## 3. `@EventListener`: nhận ngay lúc publish, thường trước commit

Với `SimpleApplicationEventMulticaster` mặc định và một listener `@EventListener` thông thường không async, việc phân phối là **đồng bộ**. Khi producer gọi `publishEvent` bên trong transaction, listener được gọi **ngay khi publish**, trước khi mã producer tiếp tục chạy. Transaction nguồn có thể vẫn đang hoạt động.

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class RecordOrderPaidAudit {

    private final AuditEntryRepository audit;

    RecordOrderPaidAudit(AuditEntryRepository audit) {
        this.audit = audit;
    }

    @EventListener
    void on(OrderPaid event) {
        audit.save(AuditEntry.forPayment(
                event.eventId(), event.orderId(), event.occurredAt()
        ));
    }
}
~~~

`AuditEntry` và `AuditEntryRepository` là các thành phần **minh họa do dự án tự triển khai**. Nếu `audit` và `orders` dùng cùng database/transaction manager, repository tham gia T1 và listener không khởi tạo transaction độc lập, bản ghi audit có thể cùng commit hoặc rollback với thay đổi đơn hàng.

Nhưng **đồng bộ không đồng nghĩa chung transaction một cách tự động**. Nếu listener gọi API ngoài, ghi sang một database khác, dùng `REQUIRES_NEW` hoặc side effect không tham gia T1, việc transaction nguồn rollback sẽ không đảo ngược được tác động đó.

### Listener đồng bộ có thể làm producer thất bại

Nếu `RecordOrderPaidAudit.on(...)` ném `RuntimeException`, với multicaster mặc định không cấu hình error handler riêng, exception có thể truyền ngược từ `publishEvent` tới phương thức `@Transactional`. Một runtime exception thoát khỏi phương thức transactional thường khiến Spring rollback theo quy tắc mặc định.

~~~mermaid
flowchart TD
    A["orders mở T1"] --> B["Cập nhật PAID"]
    B --> C["publishEvent(OrderPaid)"]
    C --> D["@EventListener chạy ngay"]
    D --> E{"Listener thành công?"}
    E -->|Có| F["Producer tiếp tục"]
    F --> G{"Commit thành công?"}
    G -->|Có| H["T1 commit"]
    G -->|Không| I["T1 rollback"]
    E -->|"RuntimeException không bị xử lý"| I
~~~

Trong ứng dụng đã thay đổi `rollbackFor/noRollbackFor`, cấu hình multicaster hoặc xử lý exception, kết quả có thể khác. Tuy nhiên, mặc định này đủ để nhắc rằng một listener đồng bộ thuộc module khác vẫn tạo **runtime coupling** với producer dù producer không import service implementation của consumer.

### Vì sao không dùng `@EventListener` để gửi email?

~~~java
@EventListener
void on(OrderPaid event) {
    emailGateway.sendPaymentConfirmation(event.customerId());
}
~~~

Đây là ví dụ **không an toàn khi transaction nguồn còn có thể rollback**: email được gửi rồi không thể được database rollback. Ngoài ra, nếu email provider mất vài giây, lời gọi synchronous giữ producer chờ và có thể kéo dài thời gian transaction mở. Với phản ứng như email, thông thường nên dùng một listener chỉ được gọi **sau commit** và tổ chức gửi lại có kiểm soát.

## 4. `@TransactionalEventListener(BEFORE_COMMIT)` là gì?

`@TransactionalEventListener` gắn lời gọi listener với **một pha của transaction đang hoạt động**. Khi khai báo `phase = TransactionPhase.BEFORE_COMMIT`, Spring không gọi phương thức ngay tại thời điểm publish, mà đăng ký để gọi **khi transaction bước vào pha chuẩn bị commit**.

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AuditBeforeCommitListener {

    private final AuditEntryRepository audit;

    AuditBeforeCommitListener(AuditEntryRepository audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    void on(OrderPaid event) {
        audit.save(AuditEntry.forPayment(
                event.eventId(), event.orderId(), event.occurredAt()
        ));
    }
}
~~~

Ở đây, `OrderPaid` được producer publish **trước đó** trong T1; method `on(...)` chỉ được gọi nếu T1 đi đến pha `BEFORE_COMMIT`. Nếu transaction đã bị đánh dấu rollback và không bước vào pha commit, callback `BEFORE_COMMIT` không được chạy.

Với transaction manager imperative mặc định, callback `BEFORE_COMMIT` được gọi khi transaction vẫn đang hoạt động, nên thao tác ghi database **có thể tham gia cùng T1**. Tuy nhiên nó **không phải “transaction mới”**, và callback chạy xong không bảo đảm commit cuối cùng thành công.

### Vì sao cần pha BEFORE_COMMIT nếu đã có `@EventListener`?

Hai kiểu listener có một khác biệt quan trọng về **thời điểm trong luồng nghiệp vụ**:

~~~text
Trong phương thức @Transactional:
    đổi trạng thái đơn
    publishEvent(OrderPaid)
        -> @EventListener chạy ngay
        -> BEFORE_COMMIT listener được đăng ký
    làm thêm các thao tác nghiệp vụ khác
    return khỏi phương thức
Trong cơ chế transaction:
    -> @TransactionalEventListener(BEFORE_COMMIT) mới chạy
    -> commit nếu không lỗi
~~~

Nếu code sau `publishEvent` còn tiếp tục thay đổi dữ liệu trong cùng transaction, `@EventListener` có thể chạy khi những thay đổi đó **chưa được thực hiện**, còn `BEFORE_COMMIT` thường nhìn thấy trạng thái cuối cùng hơn của T1 trước khi commit.

Tuy vậy, không coi BEFORE_COMMIT là cơ chế “đảm bảo đọc mọi thay đổi cuối cùng” trong mọi trường hợp: thứ tự các transaction synchronization, thay đổi từ callback khác, flush và isolation có thể ảnh hưởng kết quả. Những bất biến cốt lõi vẫn nên được kiểm soát bằng domain model/service và constraint database.

### Những điều `BEFORE_COMMIT` không bảo đảm

- Không bảo đảm transaction nguồn đã commit.
- Không tự tạo một transaction khác.
- Không tự bất đồng bộ, không tự kích hoạt thread khác.
- Không làm side effect ngoài database có thể rollback.
- Không tự lưu publication bền vững để phục hồi sau crash.
- Không bảo đảm callback được gọi nếu event được phát **ngoài transaction**, trừ khi có cấu hình fallback có chủ đích.
- Không thay thế kiểm tra bất biến nghiệp vụ ở producer và database.

## 5. So sánh các pha listener

Spring hỗ trợ nhiều pha của transactional event listener. Chọn pha theo **ý nghĩa công việc**, không chọn theo nhu cầu “thấy listener chạy nhanh” trong test.

| Cơ chế | Khi nào chạy? | Nếu T1 rollback trước commit? | Được ghi dữ liệu trong T1? | Side effect ngoài hệ thống |
| --- | --- | --- | --- | --- |
| `@EventListener` đồng bộ mặc định | Tại `publishEvent` | Có thể **đã chạy** trước rollback | Có thể, nếu cùng resource/transaction | Nguy hiểm nếu không rollback được |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Lúc chuẩn bị commit | Không chạy nếu không đến pha này; đã chạy vẫn có thể rollback sau đó | Có thể tham gia T1 | Vẫn nguy hiểm |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công | Không chạy | T1 đã commit; muốn ghi mới cần transaction riêng phù hợp | Tránh side effect do rollback nguồn, nhưng vẫn có rủi ro thất bại |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Khi transaction rollback | Là pha dành cho nhánh rollback | Không coi là T1 có thể commit lại | Dùng cho quan sát/cleanup theo thiết kế |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi transaction kết thúc | Có thể được gọi cả khi commit hoặc rollback | T1 đã kết thúc | Phải biết kết quả giao dịch trước khi tạo hiệu ứng |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ và transaction mới | Không xử lý nếu T1 rollback | Consumer dùng transaction riêng | Phù hợp phản ứng độc lập, cần idempotency |

**`AFTER_COMMIT` là pha mặc định của `@TransactionalEventListener`** khi không ghi `phase`. Còn `@ApplicationModuleListener` là tiện ích Spring Modulith tổ chức xử lý sau commit, bất đồng bộ và trong transaction mới (`REQUIRES_NEW`).

### BEFORE_COMMIT khác BEFORE_FLUSH

Đừng hiểu tên `BEFORE_COMMIT` thành “chắc chắn chạy trước mọi thao tác flush JPA”. Transaction manager và JPA provider có thể flush dữ liệu ở nhiều mốc khác nhau, ví dụ lúc thực thi truy vấn hoặc trước commit. Một constraint có thể chỉ báo lỗi ở cuối transaction, sau khi BEFORE_COMMIT callback đã thực hiện xong.

Nếu logic yêu cầu database đã xác thực một ràng buộc trước khi xử lý một bước tiếp theo, phải kiểm soát cụ thể thao tác flush/check hoặc thiết kế workflow phù hợp, không chỉ tin vào tên pha.

## 6. Ví dụ đầy đủ: tạo `OrderPaid` trước commit

### Hợp đồng giữa các module

Trong modular monolith, `orders` sở hữu sự thật `OrderPaid`; module `audit` và `loyalty` không nên import entity hay repository nội bộ của `orders`. Một event contract công khai có thể là:

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

Nếu `OrderPaid` nằm ở package con `orders.events`, cần công bố bề mặt module bằng `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Với cách đặt tên module mặc định `orders`, module nhận có thể giới hạn phụ thuộc qua:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.audit;
~~~

Hai annotation này bảo vệ **ranh giới phụ thuộc mã nguồn**; chúng không quyết định transaction phase hay cung cấp retry. `OrderPaid` là sự thật về thanh toán đã được nghiệp vụ chấp nhận, không phải command bảo `audit` hoặc `loyalty` phải thực hiện một method cụ thể.

### Producer phát event trong T1

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

        // Domain method minh họa: chỉ true nếu phát sinh transition mới.
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

`Order`, `OrderRepository`, `markPaidIfNew` là thành phần miền phải tự triển khai; ví dụ giả định `paymentId` đến từ kết quả thanh toán **đã được xác thực**. Để chống callback lặp, producer cần đảm bảo một payment reference không khiến chuyển trạng thái và phát event lần thứ hai, kể cả khi request cạnh tranh đồng thời.

Điểm then chốt: method `recordVerifiedPayment` phát event **khi T1 đang mở**. `@EventListener` có thể chạy ngay; `@TransactionalEventListener(BEFORE_COMMIT)` đăng ký chờ pha commit; `@ApplicationModuleListener` xử lý sau commit. **Producer không phát thêm một event thứ hai chỉ vì đến lúc commit**.

### Vì sao `occurredAt` không phải `committedAt`?

`occurredAt = clock.instant()` là thời điểm producer tạo event cho transition được chấp nhận. Nó có thể sớm hơn commit, và transaction sau đó vẫn có thể rollback. Nếu cần mốc commit thực, phải dùng nguồn thông tin phù hợp cho việc quan sát hoặc lịch sử database; không đoán commit time bằng `Instant.now()` ở giữa phương thức.

Khi event bị giao lại, `occurredAt` phải giữ nguyên; lần retry có `receivedAt` hoặc `attemptedAt` mới, nhưng không tạo ra một sự thật `OrderPaid` mới.

## 7. Dùng BEFORE_COMMIT cho việc gì là hợp lý?

Có những tác vụ **phải nằm trong transaction nguồn**, và về mặt thiết kế được tách thành module khác. BEFORE_COMMIT có thể hữu ích cho các bước chuẩn bị/gắn metadata mang ý nghĩa transaction, khi nhóm dự án đã hiểu rõ hậu quả lỗi.

| Tác vụ | BEFORE_COMMIT có phù hợp? | Lý do |
| --- | --- | --- |
| Ghi một audit record nhỏ cùng T1 | **Có thể** | Audit và thay đổi nguồn cùng commit/rollback khi dùng một resource/transaction |
| Tính một projection DB nội bộ cần cùng T1 | **Có thể** | Cần chứng minh projection thực sự tham gia cùng transaction |
| Kiểm tra một quy tắc nghiệp vụ cốt lõi | **Cân nhắc API/domain validation trực tiếp trước** | Không nên giấu điều kiện thành công trong callback khó lần theo |
| Gửi email xác nhận thanh toán | **Không nên** | Email không thể rollback nếu T1 thất bại |
| Gọi HTTP tới service khác | **Không nên** | Timeout làm T1 chậm; tác động bên ngoài không nằm trong transaction |
| Cộng điểm thưởng cho phép eventual consistency | **Thường không cần** | Nên xử lý sau commit, cách ly lỗi và có retry/idempotency |
| Gửi integration message tới broker | **Không đủ an toàn nếu gửi trực tiếp** | DB rollback nhưng message đã gửi, hoặc DB commit mà gửi thất bại |

Nếu audit phải tuyệt đối ghi thành công trước khi chấp nhận thanh toán, đôi khi **gọi service đồng bộ với contract rõ** phù hợp hơn listener: producer phải biết đây là điều kiện bắt buộc, dễ review và test hơn. Event nên đại diện cho sự thật nghiệp vụ, không được dùng chỉ để giấu một command quan trọng.

### Một listener BEFORE_COMMIT không phải “đã giao event thành công”

Ngay cả khi phương thức `on(OrderPaid)` ghi audit rồi return, transaction vẫn có thể bị rollback do:

- Một transaction synchronization khác ném exception.
- Vi phạm ràng buộc database tại flush/commit.
- Deadlock hoặc lỗi kết nối lúc commit.
- Producer hoặc transaction manager đã quyết định rollback do tình trạng rollback-only.

Vì vậy log `BEFORE_COMMIT listener completed` chỉ chứng minh callback đã chạy xong, **không chứng minh audit/đơn đã được commit**.

## 8. Rollback và exception ở pha BEFORE_COMMIT

Callback `BEFORE_COMMIT` chạy **trước khi transaction hoàn thành**. Một runtime exception không được xử lý trong callback thường khiến quá trình commit thất bại và transaction được rollback bởi transaction manager phù hợp.

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPaid;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class AuditPolicyBeforeCommit {

    private final AuditPolicy policy;

    AuditPolicyBeforeCommit(AuditPolicy policy) {
        this.policy = policy;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    void on(OrderPaid event) {
        // Ví dụ kỹ thuật về propagation, không khuyến nghị
        // giấu invariant thanh toán cốt lõi trong listener.
        policy.assertAllowed(event);
    }
}
~~~

`AuditPolicy` là service minh họa. Nếu `assertAllowed` ném runtime exception và exception không bị nuốt, commit không thành công theo đường đi thông thường.

### Những tình huống cần phân biệt

| Tình huống | `@EventListener` ngay lúc publish | BEFORE_COMMIT | AFTER_COMMIT |
| --- | --- | --- | --- |
| Producer rollback **trước pha commit** | Có thể đã chạy | Không chạy | Không chạy |
| BEFORE_COMMIT ném runtime exception | Đã chạy trước đó | Callback thất bại, T1 thường rollback | Không chạy |
| BEFORE_COMMIT thành công nhưng DB commit lỗi | Có thể đã chạy | Đã chạy | Không chạy |
| T1 commit thành công | Có thể đã chạy | Đã chạy | Được kích hoạt |
| Publish event ngoài transaction | Thông thường vẫn chạy | Mặc định không chạy | Mặc định không chạy |

Lưu ý: việc lỗi `@EventListener` khiến rollback còn phụ thuộc exception có thoát ra khỏi phương thức `@Transactional` không và rollback rules. Bảng thể hiện **trường hợp thường gặp**, không thay thế cấu hình transaction cụ thể.

### Vì sao bắt exception rồi bỏ qua là nguy hiểm?

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void on(OrderPaid event) {
    try {
        audit.save(...);
    } catch (Exception ex) {
        log.warn("Audit failed: {}", event.eventId(), ex);
        // Bỏ qua lỗi dù audit được xem là bắt buộc.
    }
}
~~~

Nếu audit là điều kiện bắt buộc, cách viết này khiến dữ liệu nguồn **có thể** commit mà không có audit. Ngoài ra, nếu một thành phần JPA đã đánh dấu transaction là rollback-only, việc nuốt exception không nhất thiết cứu được commit; có thể vẫn gặp `UnexpectedRollbackException`.

Hãy quyết định rõ **lỗi có được phép làm transaction nguồn rollback không**, ghi trong contract và thể hiện bằng test. Không “chữa lỗi” bằng cách nuốt exception chỉ để API trả thành công.

## 9. Publish ngoài transaction, proxy và cấu hình async

Một listener ở pha `BEFORE_COMMIT` phải gắn với **transaction thực sự đang được Spring quản lý**. Điều này dễ bị bỏ qua trong các tình huống sau.

### Publish event ngoài transaction

~~~java
public void publishOutsideTransaction(OrderPaid event) {
    publisher.publishEvent(event);
}
~~~

Khi không có transaction, `@EventListener` thông thường vẫn có thể được gọi đồng bộ; `@TransactionalEventListener(BEFORE_COMMIT)` mặc định **không thực thi**. Annotation `@TransactionalEventListener` có thuộc tính `fallbackExecution` để cho phép gọi khi không có transaction, nhưng bật nó sẽ khiến nhánh đó **không còn ý nghĩa chuẩn bị commit nguồn**.

### `@Transactional` không được áp dụng vì self-invocation

~~~java
@Service
class PaymentFacade {

    public void handle(UUID orderId) {
        recordWithinTransaction(orderId); // Gọi nội bộ cùng bean.
    }

    @Transactional
    public void recordWithinTransaction(UUID orderId) {
        // Transaction proxy có thể bị bỏ qua nếu tự gọi cùng bean.
    }
}
~~~

Trong cơ chế proxy Spring thông thường, self-invocation không đi qua transaction interceptor. Kết quả có thể không có T1 như bạn tưởng, và listener BEFORE_COMMIT không chạy. Hãy đặt transactional boundary ở phương thức được gọi **qua Spring proxy**, hoặc chọn kiến trúc giao dịch phù hợp, rồi kiểm tra bằng integration test.

### Không dùng BEFORE_COMMIT để lách sang async

Transaction imperative của Spring thường gắn với thread đang thực thi. Nếu chuyển listener sang một executor riêng, luồng async **không tự thừa hưởng transaction của producer**. Vì vậy cố ghép `@Async` với một công việc “phải tham gia T1 trước commit” là thiết kế mâu thuẫn về mục tiêu. Nếu công việc chấp nhận hoàn tất muộn, chuyển nó sang **hậu commit và transaction riêng**, thay vì kỳ vọng async listener ghi dữ liệu nguyên tử với T1.

`@ApplicationModuleListener` của Spring Modulith được thiết kế cho phản ứng hậu commit, bất đồng bộ và transaction mới; không nên coi nó là phiên bản async của `BEFORE_COMMIT`.

## 10. Trước commit có lợi thế và rủi ro nào với ranh giới module?

Spring Modulith khuyến khích các module giao tiếp qua public event contract để giảm phụ thuộc mã nguồn. Tuy nhiên, nếu một listener BEFORE_COMMIT ở `audit` có thể quyết định thành bại của transaction `orders`, hai module vẫn phụ thuộc **lúc chạy** với nhau.

~~~mermaid
flowchart LR
    Orders["orders<br/>T1 đang mở"] --> Event(("OrderPaid"))
    Event --> Audit["audit<br/>BEFORE_COMMIT"]
    Event --> Notify["notifications<br/>AFTER_COMMIT"]
    Audit --> SameTx["Ghi audit cùng T1"]
    SameTx --> Result{"T1 commit?"}
    Result -->|Có| Notify
    Result -->|Không| Stop["Không gửi email"]
~~~

Sơ đồ nhấn mạnh sự khác nhau về trách nhiệm: audit có thể là phần **bắt buộc trong T1**, còn notifications là phản ứng sau commit. Nhưng nếu việc ghi audit là bất biến cốt lõi không thể bỏ qua, hãy review xem một lệnh gọi service rõ ràng hoặc cùng module có phù hợp hơn một event listener hay không.

### Phụ thuộc static khác phụ thuộc runtime

| Loại phụ thuộc | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- |
| **Static/code dependency** | `audit` import `orders.events.OrderPaid` | Công bố named interface; kiểm tra module boundary |
| **Runtime/transaction coupling** | Lỗi audit trước commit khiến T1 thất bại | Quy định trách nhiệm lỗi và transaction |
| **Data coupling** | `audit` import `OrderRepository` nội bộ | Không import internal; chỉ dùng contract |
| **Operational coupling** | Listener trước commit quá chậm kéo dài T1 | Có giới hạn latency, metric, kiểm thử |

Nên đưa vào event **ID, snapshot nhỏ và mốc thời gian cần thiết**, không truyền JPA entity đang managed, `EntityManager`, session hoặc Spring service. Khi consumer dùng contract bất biến, nó có thể phân tích event mà không phụ thuộc vào vòng đời persistence context của `orders`.

## 11. BEFORE_COMMIT khác với độ bền sau commit

Bài học này tập trung vào sự kiện **trước khi commit**, nhưng không nên dùng listener trước commit để giải quyết bài toán **giao sự kiện đáng tin cậy sau commit**. Hai bài toán khác nhau:

- **Đảm bảo nhất quán trong T1:** dùng transaction và tác vụ cùng resource/transaction khi một công việc phải cùng commit/rollback với producer.
- **Đảm bảo phản ứng sau T1 khi consumer có thể lỗi:** dùng transactional listener hậu commit, Event Publication Registry và cơ chế khôi phục khi phù hợp, kết hợp idempotency.
- **Đảm bảo đưa message ra ngoài JVM:** dùng thiết kế integration event, outbox hoặc externalization phù hợp; `publishEvent` không tự gửi qua broker.

### Vì sao Registry không thay thế transaction semantics?

Spring Modulith có **Event Publication Registry** để theo dõi các publication dành cho transactional event listeners được hỗ trợ. Khi cấu hình publication repository bền vững và phát event trong transaction nguồn phù hợp, registry có thể ghi ý định giao cho listener, theo dõi hoàn tất và cho phép tìm publication chưa hoàn tất để resubmit.

Tuy nhiên, không nên suy luận rằng **mọi `@EventListener` chạy trước commit** được registry bảo vệ hoặc tự retry sau restart. Đặc biệt, BEFORE_COMMIT không nên bị đánh đồng với công việc hậu commit có khả năng phục hồi: một callback có thể đã chạy nhưng transaction nguồn **sau đó rollback**. Không thể coi log “callback thành công” là sự thật đã commit.

| Câu hỏi | Cơ chế cần xét |
| --- | --- |
| Một audit record phải rollback cùng đơn? | Cùng T1 và cùng transaction resource |
| Chỉ cộng điểm nếu đơn thật sự commit? | Listener `AFTER_COMMIT`/`@ApplicationModuleListener` |
| JVM dừng sau khi nguồn commit nhưng trước khi loyalty hoàn tất? | Registry bền vững, recovery/resubmit phù hợp |
| Loyalty xử lý lại event có cộng điểm hai lần? | Idempotency, unique constraint, transaction consumer |
| Một message gửi ra broker có đến service khác? | Outbox/externalization, acknowledgement và retry của kênh tích hợp |

**Registry không tự tạo exactly-once side effect.** Consumer có thể commit tác dụng rồi crash trước khi registry đánh dấu hoàn tất, nên lần giao lại phải được xử lý idempotent. Các API/thiết lập registry, repository và resubmit có thể khác theo phiên bản Spring Modulith; cần xác minh dependency thực tế khi triển khai.

### Vì sao gửi message trước commit dễ sai?

~~~java
@Transactional
void confirmPayment(...) {
    orders.save(order);
    brokerClient.send(orderPaidMessage); // Nguy cơ đã gửi nhưng T1 rollback.
}
~~~

Transaction database cục bộ không tự rollback việc gửi qua mạng. Nếu cần thông điệp tích hợp chắc chắn chỉ tương ứng với thay đổi đã commit, thường cần ghi **ý định gửi** cùng T1 rồi phân phối sau commit bằng outbox/externalization có khả năng phục hồi. Khi gửi lại, bên nhận vẫn cần chống trùng.

## 12. Kiểm thử khác biệt giữa immediate và BEFORE_COMMIT

Một test chỉ dùng mock `ApplicationEventPublisher` không thể chứng minh callback BEFORE_COMMIT thực sự chạy đúng pha. Cần một Spring context có transaction manager thực và cho transaction **commit hoặc rollback rõ ràng**.

### Test minh họa bằng `TransactionTemplate`

Đoạn test sau dùng một sự kiện nhỏ `ProbeEvent` để xác nhận thứ tự tương đối: `@EventListener` chạy ngay khi publish, còn `BEFORE_COMMIT` chỉ chạy khi `TransactionTemplate` đi tới commit.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class EventBeforeCommitTests {

    record ProbeEvent() {}

    @Component
    static class PhaseProbe {

        private final List<String> calls = new ArrayList<>();

        @EventListener
        void immediately(ProbeEvent event) {
            calls.add("immediate");
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        void beforeCommit(ProbeEvent event) {
            calls.add("before-commit");
        }

        void clear() {
            calls.clear();
        }

        List<String> calls() {
            return List.copyOf(calls);
        }
    }

    @Autowired ApplicationEventPublisher publisher;
    @Autowired TransactionTemplate transactions;
    @Autowired PhaseProbe probe;

    @BeforeEach
    void reset() {
        probe.clear();
    }

    @Test
    void immediateRunsDuringPublishAndBeforeCommitRunsLater() {
        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent());
            assertThat(probe.calls()).containsExactly("immediate");
        });

        assertThat(probe.calls())
                .containsExactly("immediate", "before-commit");
    }

    @Test
    void beforeCommitDoesNotRunWhenTransactionRollsBack() {
        transactions.executeWithoutResult(status -> {
            publisher.publishEvent(new ProbeEvent());
            status.setRollbackOnly();
        });

        assertThat(probe.calls()).containsExactly("immediate");
    }
}
~~~

**Giả định cho test:** Spring Boot context có `PlatformTransactionManager` và bean `TransactionTemplate` được cấu hình; `PhaseProbe` là Spring bean được quét hoặc đăng ký trong test; không có multicaster/executor async tùy biến; không có transaction test bao ngoài tự rollback. Phần `ProbeEvent` và `PhaseProbe` chỉ phục vụ kiểm tra cơ chế Spring, không phải event nghiệp vụ sản xuất.

Test này chứng minh **thứ tự callback**, không chứng minh ghi database đã rollback đúng vì không có repository thực. Muốn kiểm chứng tác động lên dữ liệu, viết thêm integration test với database dùng trong dự án.

### Ma trận kiểm thử giao dịch đầy đủ

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| **Publish trong T1** | Publish rồi tiếp tục code trong transaction | `@EventListener` đồng bộ chạy ngay; BEFORE_COMMIT chưa chạy tại dòng sau publish |
| **T1 commit** | Để transaction kết thúc bình thường | BEFORE_COMMIT được gọi trước commit |
| **T1 rollback chủ động** | Gọi `setRollbackOnly()` trước pha commit | BEFORE_COMMIT không được kích hoạt; immediate đã có thể chạy |
| **BEFORE_COMMIT ném lỗi** | Handler ném runtime exception | T1 rollback theo quy tắc transaction; không có dữ liệu nguồn đã commit |
| **DB lỗi ở commit** | Tạo constraint/flush lỗi ở cuối T1 | Không coi callback BEFORE_COMMIT thành công là commit thành công |
| **Audit cùng T1** | Immediate/BEFORE_COMMIT listener ghi cùng database | Audit và đơn commit/rollback cùng nhau |
| **Side effect ngoài** | Listener trước commit gọi fake email gateway | Thấy email fake vẫn được gọi dù T1 rollback sau đó |
| **AFTER_COMMIT** | Listener khác dùng phase AFTER_COMMIT | Không gọi khi rollback; gọi khi T1 commit |
| **Publish không có T1** | Phát từ method thường | Listener sync có thể chạy; transactional listener mặc định không chạy |
| **Self-invocation** | Method `@Transactional` bị gọi trực tiếp trong bean | Phát hiện không có transaction như mong đợi |
| **Lỗi sau commit** | Consumer hậu commit ném exception | T1 đã commit, không rollback theo consumer |
| **Retry/recovery** | Dùng registry với repository bền vững | Publication chưa hoàn tất có thể được phát hiện/khôi phục mà không trùng hiệu ứng |

Một test tích hợp sử dụng Spring Modulith có thể bổ sung `ApplicationModules.verify()` để kiểm tra ranh giới module, `@ApplicationModuleTest`, `PublishedEvents` hoặc `Scenario` để kiểm tra tương tác và xử lý hậu commit. Những tiện ích này không thay thế bài test transaction nói trên.

**Bẫy phổ biến:** nếu đánh dấu cả phương thức test bằng `@Transactional` và Spring Test mặc định rollback ở cuối, callback `AFTER_COMMIT` sẽ không chạy; `BEFORE_COMMIT` cũng có thể không được gọi nếu transaction không đi tới pha commit. Sử dụng `TransactionTemplate` hoặc cấu hình test để có **một commit thật** khi muốn quan sát pha commit.

## 13. Quan sát event trước commit trong môi trường chạy thật

Để điều tra “đã có log nhận event nhưng đơn không lưu” cần đủ tín hiệu về **pha và kết quả transaction**, không chỉ log ở listener.

| Tín hiệu | Câu hỏi được trả lời |
| --- | --- |
| `eventId`, `eventType`, `orderId` | Đang theo dõi lần phát sinh nào? |
| `occurredAt` | Producer tạo event khi nào theo contract? |
| `listenerName`, `listenerPhase` | Listener chạy ngay khi publish, BEFORE_COMMIT hay AFTER_COMMIT? |
| `threadName`, `transactionActive` | Listener có thật sự chạy trong transaction imperative trên thread này? |
| `transactionOutcome` | T1 commit hay rollback sau khi listener đã chạy? |
| `handlerDuration` | Listener trước commit có làm T1 lâu bất thường không? |
| `exceptionType`, `rollbackReason` | Có lỗi listener hoặc commit gây rollback không? |
| `publicationPending` | Với registry bền vững, listener hậu commit nào còn dang dở? |
| `retryAttempt`, `duplicateSuppressed` | Lần giao lại nào đã được xử lý an toàn? |

Ví dụ log chẩn đoán tại listener:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

log.info(
        "eventId={}, phase=BEFORE_COMMIT, txActive={}",
        event.eventId(),
        TransactionSynchronizationManager.isActualTransactionActive()
);
~~~

`txActive=true` chỉ có nghĩa transaction đang hoạt động trên thread hiện tại; **không chứng minh đã commit**. Tương tự, log `beforeCommit completed` không nên hiển thị cho nghiệp vụ như “payment completed”.

Đo khoảng thời gian listener bằng monotonic clock hoặc metric timer; tránh để listener sync gọi các API quan sát chậm. Nên thống kê riêng thời gian chờ event consumer trong T1 và thời gian xử lý hậu commit. Hạn chế đưa dữ liệu cá nhân hoặc chi tiết thanh toán vào log; dùng `eventId` và identifier đã kiểm soát quyền truy cập để tìm kiếm.

## 14. Những lỗi hiểu sai thường gặp

**Sai lầm 1 — “Đã publish tức là commit thành công.”** Không. Producer có thể gọi `publishEvent` khi transaction còn mở và commit sau đó thất bại.

**Sai lầm 2 — “`@EventListener` là BEFORE_COMMIT listener.”** Không chính xác. Listener đồng bộ mặc định chạy **ngay lúc publish**; `BEFORE_COMMIT` là phase callback riêng tại thời điểm transaction chuẩn bị commit.

**Sai lầm 3 — “`BEFORE_COMMIT` đã chạy nghĩa là dữ liệu an toàn.”** Không. Một lỗi flush, constraint, deadlock hoặc exception khác vẫn có thể khiến rollback.

**Sai lầm 4 — “Chuyển email sang BEFORE_COMMIT là đủ tránh email sai.”** Không. Email vẫn được gửi trước commit vật lý và không rollback được.

**Sai lầm 5 — “`@TransactionalEventListener` luôn async.”** Không. `@TransactionalEventListener` chỉ chọn phase; muốn async phải chọn cơ chế riêng có ngữ nghĩa transaction phù hợp.

**Sai lầm 6 — “Listener thuộc module khác thì không thể làm rollback module nguồn.”** Sai. Nếu listener đồng bộ hoặc BEFORE_COMMIT thất bại trước khi T1 commit, exception có thể làm transaction nguồn rollback.

**Sai lầm 7 — “Dùng `@Order` để làm workflow liên module là đủ.”** Không. Thứ tự callback không tự bảo đảm side effect ngoài hoặc thứ tự commit của những transaction độc lập.

**Sai lầm 8 — “Event Publication Registry tự retry mọi listener trước commit.”** Không. Độ bền publication phụ thuộc loại listener được hỗ trợ, storage và quy trình recovery; BEFORE_COMMIT không phải cơ chế mặc định bảo đảm phản ứng hậu commit.

**Sai lầm 9 — “Gọi `save()` trong listener là dữ liệu đã nằm bền vững trong DB.”** Không. Trong transaction JPA, `save` có thể chỉ cập nhật persistence context; flush/commit có thể xảy ra sau đó và vẫn thất bại.

**Sai lầm 10 — “Mọi thứ chạy chung transaction vì đều ở cùng Spring Boot app.”** Không. Còn phụ thuộc resource, transaction manager, propagation và thread. Gọi HTTP hoặc ghi DB khác không tự nằm trong cùng T1.

## 15. Bài thực hành: kiểm soát trước commit trong hệ thống đặt vé

### Bối cảnh

Ứng dụng gồm ba module:

- **`reservations`** sở hữu trạng thái đặt vé, xác nhận thanh toán và phát `ReservationPaid`.
- **`audit`** cần một dòng audit đồng nhất với việc đặt vé được xác nhận.
- **`notifications`** tạo yêu cầu gửi email khi thanh toán đã commit.
- Tùy chọn thêm **`loyalty`** để cộng điểm sau commit, retry và chống trùng.

Đề bài yêu cầu chứng minh ba đường đi: **thành công**, **rollback trước BEFORE_COMMIT**, và **lỗi ở BEFORE_COMMIT**.

### Yêu cầu triển khai

1. Định nghĩa `ReservationPaid(eventId, reservationId, paymentId, customerId, occurredAt)` ở public API của `reservations`.
2. Viết producer `@Transactional` chỉ phát event khi một payment reference đã được xác thực tạo transition mới.
3. Viết listener `@EventListener` đồng bộ để **log** thời điểm được gọi ngay khi publish.
4. Viết listener `@TransactionalEventListener(BEFORE_COMMIT)` trong `audit`, lưu audit record nhỏ **cùng database và transaction nguồn**.
5. Tạo một ngoại lệ trong producer **sau publish nhưng trước khi kết thúc phương thức**; xác nhận immediate listener đã chạy, BEFORE_COMMIT không chạy, cả reservation và audit không được commit.
6. Bỏ lỗi producer, cho transaction commit; xác nhận audit và reservation được lưu cùng nhau.
7. Cố ý làm BEFORE_COMMIT listener ném runtime exception; chứng minh T1 rollback theo cấu hình transaction.
8. Thêm listener `@TransactionalEventListener(AFTER_COMMIT)` cho `notifications`. Nếu ghi database mới, gọi một service `REQUIRES_NEW` qua proxy; chứng minh không có email request khi T1 rollback.
9. Bổ sung `@ApplicationModuleListener` cho `loyalty` nếu cần tác vụ bất đồng bộ; mô phỏng lỗi, registry bền vững, resubmit và idempotency.
10. Ghi log theo `eventId`, `phase`, `txActive`, `outcome`; so sánh thời điểm thực sự tạo audit, thời điểm commit và thời điểm nhận thông báo.

### Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| **Đúng contract** | Event biểu diễn thanh toán đã được chấp nhận, không phải yêu cầu thanh toán |
| **Ranh giới module** | Consumer không import repository/entity nội bộ của producer |
| **Immediate listener** | Test ghi nhận chạy trước khi `publishEvent` trả về |
| **BEFORE_COMMIT** | Chạy khi T1 chuẩn bị commit, không chạy nếu T1 rollback trước pha commit |
| **Tính nguyên tử** | Audit cùng T1 commit/rollback với reservation |
| **Exception** | BEFORE_COMMIT ném lỗi dẫn đến kết quả transaction dự kiến |
| **AFTER_COMMIT** | Chỉ tạo yêu cầu gửi sau commit; không có side effect khi rollback nguồn |
| **Độ tin cậy** | Công việc hậu commit có cơ chế theo dõi/khôi phục nếu là yêu cầu nghiệp vụ |
| **Idempotency** | Cùng event được giao lại không tạo thêm điểm hoặc thông báo trùng |
| **Quan sát** | Có thể biết listener đã chạy ở pha nào và transaction cuối cùng ra sao |

### Câu hỏi tự đánh giá

**Câu 1. Event được publish ở dòng giữa phương thức `@Transactional` có nghĩa database đã commit chưa?**

Chưa. `@EventListener` có thể xử lý ngay, nhưng transaction nguồn thường chỉ bước vào commit khi phương thức transactional hoàn tất và transaction interceptor xử lý xong.

**Câu 2. Điều gì khác nhau giữa `@EventListener` và `@TransactionalEventListener(BEFORE_COMMIT)`?**

Listener đồng bộ thông thường chạy tại thời điểm publish. BEFORE_COMMIT listener được đăng ký để chạy tại pha transaction chuẩn bị commit, sau phần code nghiệp vụ thông thường, nếu transaction thực sự đi đến pha này.

**Câu 3. Callback BEFORE_COMMIT đã chạy thành công mà commit lỗi thì có được gửi email không?**

Không nên. Callback thành công không bảo đảm transaction đã commit; email là side effect ngoài database không tự rollback được.

**Câu 4. Một listener BEFORE_COMMIT có thể làm transaction nguồn rollback không?**

Có thể. Runtime exception không bị xử lý trong before-commit callback thường khiến quá trình commit thất bại và transaction rollback theo transaction manager.

**Câu 5. Vì sao chuyển một tác vụ sang `@ApplicationModuleListener` không có nghĩa tác vụ đó vẫn chạy trong T1?**

Vì annotation này dành cho xử lý hậu commit, bất đồng bộ và trong **transaction riêng**. Nó phù hợp cho consumer độc lập nhưng không giữ tính nguyên tử với T1.

**Câu 6. Có nên dùng BEFORE_COMMIT để bảo đảm không mất event khi JVM crash sau commit?**

Không. Đó là bài toán bền vững publication và recovery, thường cần registry/outbox/storage cùng transaction nguồn và phản ứng hậu commit có idempotency, không phải chỉ thay phase của listener.

## 16. Checklist áp dụng

- [ ] Phân biệt **publish trước commit** với **callback ở pha BEFORE_COMMIT**.
- [ ] Định nghĩa sự thật nghiệp vụ rõ ràng trước khi tạo event.
- [ ] Producer chỉ publish khi có transition mới hợp lệ; chống callback thanh toán lặp.
- [ ] Hiểu `@EventListener` đồng bộ thông thường chạy ngay tại publish.
- [ ] Hiểu `@TransactionalEventListener(BEFORE_COMMIT)` chỉ chạy khi transaction chuẩn bị commit.
- [ ] Không suy luận BEFORE_COMMIT thành công đồng nghĩa commit thành công.
- [ ] Chỉ dùng listener trước commit cho thao tác có thể tham gia transaction và rollback đúng.
- [ ] Không gọi email, HTTP hoặc broker ngoài T1 mà giả định có rollback nguyên tử.
- [ ] Xác định rõ exception listener có được phép làm transaction nguồn thất bại không.
- [ ] Không nuốt lỗi bắt buộc hoặc coi log đã nhận event là kết quả đã commit.
- [ ] Kiểm tra transaction thật, proxy `@Transactional` và trường hợp publish ngoài transaction.
- [ ] Phân biệt AFTER_COMMIT với async; ghi dữ liệu hậu commit bằng transaction riêng khi cần.
- [ ] Không giả định registry tự retry mọi `@EventListener` trước commit.
- [ ] Có idempotency cho các consumer có thể nhận event lại sau crash/retry.
- [ ] Kiểm thử commit, rollback, exception ở BEFORE_COMMIT và lỗi commit cuối.
- [ ] Ghi log/metric theo eventId, listener phase, thời gian xử lý và outcome của transaction.
- [ ] Bảo vệ module boundary bằng public event contract và kiểm tra cấu trúc Spring Modulith.

## Ghi nhớ

**Event trước khi commit** là một điểm quan trọng trong vòng đời application events của Spring Modulith. Khi producer gọi `publishEvent` **trong transaction đang mở**, `@EventListener` đồng bộ mặc định có thể chạy ngay trước commit; còn `@TransactionalEventListener(BEFORE_COMMIT)` được gọi tại pha chuẩn bị commit, không phải tại dòng publish. Cả hai đều có thể chạy khi dữ liệu nguồn **chưa được commit bền vững**, và exception hoặc lỗi commit vẫn có thể dẫn đến rollback.

Hãy dùng xử lý trong cùng transaction khi một thao tác thật sự cần cùng commit/rollback với nguồn và có chi phí, lỗi được kiểm soát. Với phản ứng độc lập như gửi thông báo, cộng điểm hoặc đồng bộ báo cáo, nên thiết kế listener **sau commit**, có transaction consumer phù hợp, Event Publication Registry khi cần lưu dấu công việc chưa hoàn tất, retry có kiểm soát, idempotency và khả năng quan sát. Chính sự phân biệt các mốc transaction và quyền sở hữu module giúp giao tiếp qua event giảm phụ thuộc mà vẫn giữ đúng nghiệp vụ.

