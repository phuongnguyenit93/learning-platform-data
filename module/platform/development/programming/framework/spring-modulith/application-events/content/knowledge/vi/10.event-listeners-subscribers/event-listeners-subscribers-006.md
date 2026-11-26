# Một listener nhiều event

Trong Spring Modulith, một module có thể cần phản ứng với **nhiều loại sự kiện nghiệp vụ** do cùng một module khác phát ra. Ví dụ, module `loyalty` cộng điểm khi nhận `OrderPaid`, sau đó điều chỉnh điểm khi nhận `OrderRefunded`. Hai sự kiện đều liên quan đến đơn hàng, nhưng chúng thể hiện **hai sự thật khác nhau** và đòi hỏi hai tác động nghiệp vụ khác nhau.

Bài học thuộc chương **Listener và subscriber** của **SPRING_MODULITH_APPLICATION_EVENTS**. Trọng tâm là cách một listener tham gia xử lý nhiều loại event trong ứng dụng Spring Modulith, từ cấu trúc phương thức, lựa chọn annotation, việc công bố event contract giữa module, đến xử lý sau commit, Event Publication Registry, retry, kiểm thử và quan sát giao sự kiện đáng tin cậy.

Sau bài này, bạn có thể phân biệt ba cách tổ chức thường gặp: **một bean có nhiều phương thức listener**, **một phương thức không tham số đăng ký nhiều event class**, và **một phương thức nhận một kiểu cha chung của nhiều event**. Bạn cũng sẽ biết tại sao “một listener nhận nhiều event” không có nghĩa rằng mọi event sẽ đến đồng thời, theo đúng thứ tự hoặc chỉ được xử lý một lần.

## 1. Hiểu đúng chữ “listener”

Trong Spring, một bean có thể chứa một hoặc nhiều phương thức được đánh dấu `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener`. Về mặt code, ta thường gọi cả bean đó là *listener class*. Nhưng ở mức cơ chế phân phối, **mỗi phương thức được đăng ký có thể là một đích xử lý riêng**.

Ví dụ:

~~~java
@Component
class LoyaltyOrderEventListener {

    @ApplicationModuleListener
    void on(OrderPaid event) {
        // Xử lý thanh toán thành công
    }

    @ApplicationModuleListener
    void on(OrderRefunded event) {
        // Xử lý hoàn tiền
    }
}
~~~

Đây là **một bean**, chứa **hai phương thức listener**. Mỗi lần `OrderPaid` được publish, phương thức nhận `OrderPaid` là ứng viên phù hợp; mỗi lần `OrderRefunded` được publish, phương thức còn lại là ứng viên phù hợp. Spring không tự gọi cả hai phương thức cho mọi event chỉ vì chúng nằm trong cùng một class.

Cũng có thể khai báo **một phương thức** có khả năng nhận nhiều loại event, nhưng phải tuân thủ quy tắc khớp kiểu và chữ ký phương thức. Hai cách này không hoàn toàn tương đương khi cần đọc payload hoặc quản lý lỗi.

| Cách tổ chức | Số bean | Số handler method | Có nhận được payload tương ứng? | Nên dùng khi |
| --- | --- | --- | --- | --- |
| Một bean, nhiều phương thức theo event type | Một | Nhiều | Có, mỗi method có tham số cụ thể | Các event cần hành vi nghiệp vụ khác nhau |
| `@EventListener(classes = {...})` không tham số | Một | Một | Không có tham số event để phân nhánh | Nhiều event cùng kích hoạt một tác vụ không cần payload |
| Một handler nhận kiểu cha/interface chung | Một | Một | Có, dưới kiểu cha hoặc kiểm tra subtype | Các event thật sự có chung hợp đồng và chính sách xử lý |
| Một bean chỉ nhận `ApplicationEvent` quá tổng quát | Một | Một | Phụ thuộc kiểu event/wrapper | Hiếm khi phù hợp cho nghiệp vụ; dễ bắt sự kiện ngoài dự kiến |

**Phân biệt với fan-out:** “Một event → nhiều listener” là nhiều module cùng quan tâm `OrderPaid`; “một listener → nhiều event” là cùng một consumer cần phản ứng với `OrderPaid`, `OrderRefunded` và các sự kiện khác. Trong ứng dụng thực tế, hai mô hình có thể tồn tại đồng thời.

~~~mermaid
flowchart LR
    Paid["orders phát OrderPaid"] --> Listener["LoyaltyOrderEventListener"]
    Refunded["orders phát OrderRefunded"] --> Listener
    Listener --> Credit["on(OrderPaid): cộng điểm"]
    Listener --> Debit["on(OrderRefunded): điều chỉnh điểm"]
~~~

Mũi tên trong sơ đồ thể hiện các đường xử lý theo **loại event**, không có nghĩa một lần publish sẽ chạy cả hai nhánh.

## 2. Ví dụ nghiệp vụ xuyên suốt

Ứng dụng bán hàng gồm các module:

| Module | Quyền sở hữu | Khi nào tham gia? |
| --- | --- | --- |
| `orders` | Trạng thái đơn, thanh toán/hoàn tiền đã được xác nhận và contract event tương ứng | Phát `OrderPaid` hoặc `OrderRefunded` khi có transition hợp lệ |
| `loyalty` | Sổ điểm thưởng và chính sách tích/điều chỉnh điểm | Nhận cả hai event để tạo bút toán điểm |
| `notifications` | Yêu cầu gửi thông báo và trạng thái gửi | Có thể nhận cả hai event để thông báo theo từng nghiệp vụ |
| `reporting` | Projection doanh thu | Có thể xử lý thanh toán và hoàn tiền theo hai hướng đối ứng |

Bài học giả định một đơn có thể nhận thanh toán, sau đó được hoàn lại toàn bộ hoặc một phần. Khi hoàn tiền một phần, phản ứng của `loyalty` **không nhất thiết là trừ toàn bộ điểm**; phải áp dụng chính sách theo số tiền được hoàn và lịch sử điểm đã ghi. Điều này minh họa vì sao hai event nên có phương thức xử lý riêng ngay cả khi cùng thuộc vòng đời một đơn hàng.

### Tên event phải phản ánh một sự thật

- `OrderPaid`: đơn đã được module `orders` xác nhận thanh toán, theo quy tắc của hệ thống.
- `OrderRefunded`: một giao dịch hoàn tiền hợp lệ đã được ghi nhận; nó có thể là hoàn tiền từng phần, nên cần định danh lần hoàn và số tiền.
- `SendPaymentEmail`: là **command**, diễn tả yêu cầu làm một việc, không phải một sự thật đã xảy ra.

Producer không cần biết module `loyalty` sẽ cộng điểm hay trừ điểm ra sao. Producer chỉ phát event có ngữ nghĩa ổn định. Consumer tự sở hữu phản ứng, transaction và dữ liệu của mình.

## 3. Thiết kế hai event contract công khai

Để tránh phụ thuộc vào entity hoặc repository nội bộ, `orders` có thể công bố một package `orders.events` chứa các record bất biến. Chỉ đưa vào payload những thông tin mà consumer thật sự cần.

Cấu trúc ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── events
│   │   ├── package-info.java
│   │   ├── OrderPaid.java
│   │   └── OrderRefunded.java
│   └── internal
│       ├── OrderPaymentService.java
│       └── OrderRepository.java
├── loyalty
│   ├── package-info.java
│   └── internal
│       ├── LoyaltyOrderEventListener.java
│       └── LoyaltyLedger.java
└── notifications
    └── internal
        └── ...
~~~

`orders/events/OrderPaid.java`:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        BigDecimal paidAmount,
        Instant occurredAt
) {}
~~~

`orders/events/OrderRefunded.java`:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderRefunded(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID refundId,
        BigDecimal refundedAmount,
        Instant occurredAt
) {}
~~~

Với hệ thống đa tiền tệ, cần bổ sung loại tiền hoặc một value object tiền tệ đã được thiết kế thành API rõ ràng. Ví dụ dùng `BigDecimal` để tập trung vào quan hệ listener và event; cách làm tròn và quy đổi điểm vẫn do `loyalty` quyết định.

**`eventId` định danh một lần phát sinh event**, khác `orderId` (định danh đơn) và `paymentId`/`refundId` (định danh giao dịch nghiệp vụ). Nếu producer phát lại cùng sự kiện sau lỗi, consumer dựa vào `eventId` để phát hiện nhận trùng. Nếu producer tạo hai `eventId` cho cùng một payment do callback lặp, cần chống trùng ngay tại producer bằng payment reference và ràng buộc trạng thái.

### Công bố named interface cho event

Nếu cấu hình module theo quy ước Spring Modulith, package con `orders.events` không mặc nhiên là API công khai cho module khác. Có thể công bố bằng `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Tại `loyalty/package-info.java`, có thể giới hạn phụ thuộc:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.loyalty;
~~~

Ví dụ giả định định danh module là `orders`. Ký hiệu `orders::events` là tên **bề mặt API** Spring Modulith, không phải tên topic hay hàng đợi. `loyalty` có thể import `OrderPaid` và `OrderRefunded`, nhưng không nên import `orders.internal.OrderRepository`. Kiểm tra cấu trúc module sẽ phát hiện các phụ thuộc không hợp lệ nếu được cấu hình phù hợp.

## 4. Cách 1 — Một bean có nhiều phương thức listener

Đây thường là lựa chọn rõ ràng nhất khi mỗi event cần một quy tắc riêng. Hai phương thức nằm cùng bean, có thể dùng chung dependency và helper, nhưng mỗi phương thức có kiểu tham số và trách nhiệm cụ thể.

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderPaid;
import com.example.shop.orders.events.OrderRefunded;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOrderEventListener {

    private final LoyaltyLedger ledger;

    LoyaltyOrderEventListener(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        ledger.creditForPaymentOnce(
                event.eventId(),
                event.paymentId(),
                event.orderId(),
                event.customerId(),
                event.paidAmount()
        );
    }

    @ApplicationModuleListener
    void on(OrderRefunded event) {
        ledger.adjustForRefundOnce(
                event.eventId(),
                event.refundId(),
                event.orderId(),
                event.customerId(),
                event.refundedAmount()
        );
    }
}
~~~

Hai phương thức `creditForPaymentOnce` và `adjustForRefundOnce` là **API nghiệp vụ minh họa của module loyalty**, không phải API do Spring Modulith cung cấp. Chúng phải được tự triển khai, gồm chính sách tính điểm, trạng thái sổ điểm và cơ chế chống xử lý trùng.

Những điều cần chú ý:

1. Spring phân phối theo loại event nên `on(OrderPaid)` xử lý nhánh thanh toán, `on(OrderRefunded)` xử lý nhánh hoàn tiền.
2. Tên phương thức `on` có thể được overload nhờ tham số khác kiểu; **chữ ký và annotation**, không phải tên `on`, quyết định event tương ứng.
3. Một bean không có nghĩa chỉ có một publication. Mỗi phương thức transactional listener có thể là **một đích publication riêng** được registry theo dõi.
4. Khi thêm `OrderCancelled`, chỉ nên tạo thêm phương thức nếu `loyalty` thực sự có phản ứng với sự kiện đó.
5. Mỗi phương thức nên giữ một trách nhiệm, dễ kiểm thử và có khả năng xử lý trùng độc lập.

`@ApplicationModuleListener` của Spring Modulith hỗ trợ xử lý transactional event **sau commit**, bất đồng bộ và trong transaction riêng. Khi thanh toán đã commit, loyalty có thể ghi điểm; khi hoàn tiền đã commit, loyalty có thể điều chỉnh điểm. Nếu listener thất bại, transaction nguồn đã commit không thể bị rollback theo.

### Tại sao không ghép hai nghiệp vụ vào một phương thức khổng lồ?

Thanh toán và hoàn tiền có thể khác nhau về quy tắc, idempotency key, logic đối soát, mức độ ưu tiên khi retry và cách xử lý event đến muộn. Đặt hai phương thức riêng làm rõ ý nghĩa của từng hợp đồng ngay tại điểm nhận.

Có thể dùng chung một service hoặc helper xử lý kỹ thuật (ghi log, tracing, định danh sự kiện) mà không buộc hai nhánh dùng chung toàn bộ business logic.

## 5. Cách 2 — Một phương thức `@EventListener` đăng ký nhiều class

Spring cho phép khai báo **nhiều lớp sự kiện** qua thuộc tính `classes` (hoặc `value`) của `@EventListener`:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderPaid;
import com.example.shop.orders.events.OrderRefunded;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class SalesDashboardCacheListener {

    private final SalesDashboardCache cache;

    SalesDashboardCacheListener(SalesDashboardCache cache) {
        this.cache = cache;
    }

    @EventListener(classes = {
            OrderPaid.class,
            OrderRefunded.class
    })
    void invalidateSalesSummary() {
        cache.invalidateSummary();
    }
}
~~~

**Quy tắc quan trọng:** khi `@EventListener` liệt kê **nhiều event class**, phương thức được annotation phải **không có tham số**. Vì vậy đây là lựa chọn hợp lý khi *bất kỳ* event nào trong tập đã liệt kê đều làm cùng một việc và **không cần đọc payload**, ví dụ xóa một cache tổng hợp.

Ví dụ sau **không phải chữ ký hợp lệ cho nhiều event class**:

~~~java
// SAI: khai báo nhiều classes nhưng đồng thời yêu cầu tham số.
@EventListener(classes = {OrderPaid.class, OrderRefunded.class})
void on(Object event) {
    // Không dùng dạng này để phân nhánh theo payload.
}
~~~

Nếu cần đọc `orderId`, `paymentId`, `refundedAmount` hoặc biết cụ thể event nào đã xảy ra, hãy dùng **nhiều phương thức có kiểu cụ thể** hoặc thiết kế **kiểu cha chung** như phần tiếp theo.

Cũng cần nhớ `@EventListener` thường thực thi **đồng bộ khi publish** với multicaster mặc định, có thể trước commit của producer. Nếu việc xóa cache phải chắc chắn chỉ xảy ra sau commit, hãy lựa chọn cách xử lý transaction tương ứng thay vì sử dụng ví dụ này nguyên trạng cho production. Phần này minh họa cú pháp đăng ký nhiều event, không phải bảo đảm transaction hay độ bền.

### Khi nào cách không tham số phù hợp?

| Nhu cầu | Phù hợp? | Lý do |
| --- | --- | --- |
| Xóa cache báo cáo khi có thanh toán hoặc hoàn tiền | Có | Cả hai đều kích hoạt cùng thao tác, không cần xem payload |
| Cộng/trừ điểm theo số tiền trong event | Không | Cần biết subtype và trường dữ liệu |
| Gửi email khác nhau cho thanh toán và hoàn tiền | Không | Cần thông tin và quy tắc riêng |
| Tăng một metric chung “có biến động đơn hàng” | Có thể | Phải hiểu mốc metric là lúc publish/receive hay sau commit |
| Bảo đảm xử lý bền vững sau crash | Không đủ | Cần transactional listener, registry/storage và recovery phù hợp |

## 6. Cách 3 — Một phương thức nhận kiểu chung của nhiều event

Khi các event thật sự chia sẻ một hợp đồng chung, có thể tạo interface cha để một phương thức listener nhận tất cả kiểu con. Khác với cách `classes` không tham số, handler **có payload** và có thể dùng thuộc tính chung hoặc phân nhánh theo subtype.

Tạo interface ở package công khai `orders.events`:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public interface OrderLifecycleEvent {
    UUID eventId();
    UUID orderId();
    UUID customerId();
    Instant occurredAt();
}
~~~

Sau đó điều chỉnh hai record công khai để implements interface:

~~~java
public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        BigDecimal paidAmount,
        Instant occurredAt
) implements OrderLifecycleEvent {}

public record OrderRefunded(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID refundId,
        BigDecimal refundedAmount,
        Instant occurredAt
) implements OrderLifecycleEvent {}
~~~

*Đây là phần chữ ký rút gọn để minh họa; mỗi record nằm trong file `public` riêng, có `package` và imports như phần trước.* Để tên accessor triển khai đúng interface, các record phải giữ những component chung như `eventId`, `orderId`, `customerId`, `occurredAt`.

Một listener có thể xử lý chung logging hoặc auditing:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderLifecycleEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventAuditListener {

    private final OrderEventAuditLog auditLog;

    OrderEventAuditListener(OrderEventAuditLog auditLog) {
        this.auditLog = auditLog;
    }

    @EventListener
    void on(OrderLifecycleEvent event) {
        auditLog.record(
                event.eventId(),
                event.orderId(),
                event.occurredAt()
        );
    }
}
~~~

Với các payload event triển khai `OrderLifecycleEvent`, Spring có thể chọn listener theo kiểu tham số chung. Đây là giải pháp khi có **một hành vi chung** có ý nghĩa đối với mọi event trong cùng họ. `OrderEventAuditLog.record` là ví dụ nghiệp vụ tự triển khai.

Nếu cần hành vi riêng trong một handler, có thể phân nhánh:

~~~java
@ApplicationModuleListener
void on(OrderLifecycleEvent event) {
    if (event instanceof OrderPaid paid) {
        ledger.creditForPaymentOnce(
                paid.eventId(), paid.paymentId(),
                paid.orderId(), paid.customerId(), paid.paidAmount()
        );
        return;
    }

    if (event instanceof OrderRefunded refunded) {
        ledger.adjustForRefundOnce(
                refunded.eventId(), refunded.refundId(),
                refunded.orderId(), refunded.customerId(),
                refunded.refundedAmount()
        );
        return;
    }

    throw new IllegalArgumentException(
            "Unsupported order event: " + event.getClass().getName()
    );
}
~~~

Đoạn này minh họa **một phương thức xử lý có điều kiện**; giả định được đặt trong bean Spring và inject `ledger` phù hợp. Đây không phải cách mặc định cần ưu tiên: mỗi subtype mới được thêm vào interface chung có thể khiến handler phải cập nhật. Nếu một handler được đăng ký cho **mọi kiểu triển khai interface**, việc mở rộng họ event cần được review như thay đổi contract.

### Cân nhắc trước khi tạo kiểu cha

- **Có thật sự chung ý nghĩa nghiệp vụ không?** `OrderPaid` và `OrderRefunded` có thể cùng `orderId`, nhưng không phải vì có vài field trùng mà mọi consumer nên xử lý như cùng một nghiệp vụ.
- **Có chung transaction/retry policy không?** Một handler chung thường dùng chung cấu hình annotation; một nhánh nghiệp vụ đặc thù có thể cần chính sách khác.
- **Có cần mở rộng subtype không?** Khi thêm `OrderCancelled`, một generic listener có thể bắt đầu nhận thêm event mà trước đây không nhận.
- **Có tạo phụ thuộc quá rộng không?** Consumer phụ thuộc vào interface chung có thể bị kéo theo thay đổi của nhiều loại event hơn nhu cầu thực tế.
- **Có đụng cả generic và specific listener không?** Nếu đồng thời đăng ký `on(OrderLifecycleEvent)` và `on(OrderPaid)`, một `OrderPaid` có thể khớp **cả hai phương thức**. Phải kiểm soát tác động và idempotency để tránh cùng nghiệp vụ chạy hai lần.

Khi các event cần logic khác nhau, ví dụ ghi bút toán tăng hoặc giảm điểm, **hai phương thức typed trong cùng bean** thường dễ đọc, dễ test và dễ giải thích lỗi hơn một phương thức có nhiều nhánh `instanceof`.

## 7. Một bean nhiều event nhưng mỗi event là một transaction riêng

Đặt hai handler trong cùng một bean **không nối transaction của chúng thành một transaction tổng**. Mỗi event có transaction nguồn riêng và listener được kích hoạt tùy mốc commit của transaction tương ứng.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant DB as Database
    participant Spring as Spring Modulith Events
    participant L as LoyaltyOrderEventListener
    O->>DB: T1: ghi nhận thanh toán
    O->>Spring: publish OrderPaid trong T1
    O->>DB: COMMIT T1
    Spring-->>L: on(OrderPaid), transaction T2
    L->>DB: Ghi điểm và COMMIT T2
    O->>DB: T3: ghi nhận hoàn tiền
    O->>Spring: publish OrderRefunded trong T3
    O->>DB: COMMIT T3
    Spring-->>L: on(OrderRefunded), transaction T4
    L->>DB: Điều chỉnh điểm và COMMIT T4
~~~

Sơ đồ trình bày một kịch bản thành công theo **thứ tự nghiệp vụ mong muốn**. Trong thực tế, listener bất đồng bộ có thể bị trễ hoặc retry, nên `on(OrderRefunded)` có thể xử lý trước khi `on(OrderPaid)` đã hoàn tất. Không được lấy thứ tự xuất hiện trong sơ đồ làm một cam kết về thứ tự thực thi.

### Vai trò của các annotation

| Annotation | Thời điểm thực thi thông thường | Điều cần cẩn trọng |
| --- | --- | --- |
| `@EventListener` | Đồng bộ trong luồng publish với multicaster mặc định | Có thể chạy trước commit và lan truyền exception |
| `@TransactionalEventListener` mặc định | Sau khi transaction publisher commit | Không tự bật async hoặc transaction mới |
| `@TransactionalEventListener(phase = BEFORE_COMMIT)` | Trước khi commit | Không phù hợp với side effect không thể rollback |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ, transaction mới | Phản ứng có thể hoàn tất muộn, thất bại hoặc được giao lại |

`@ApplicationModuleListener` là tiện ích của Spring Modulith kết hợp đặc tính của transactional event listener, async và transaction mới (`REQUIRES_NEW`). Đó là cơ chế phù hợp cho nhiều consumer độc lập trong một modular monolith.

Nếu producer publish ngoài transaction, `@TransactionalEventListener` mặc định **không được kích hoạt**, trừ khi `fallbackExecution` được cấu hình có chủ đích. Nếu phương thức `@Transactional` bị gọi qua self-invocation không đi qua proxy, có thể không tồn tại transaction như người viết code tưởng. Kiểm tra transaction thật là một phần của việc chẩn đoán event “không đến”.

## 8. Producer: phát đúng event cho đúng transition

Để consumer nhận nhiều event một cách đáng tin, producer phải giữ ngữ nghĩa từng event. Không nên phát `OrderPaid` từ mọi lần gọi API thanh toán, cũng không nên phát `OrderRefunded` khi hoàn tiền mới được yêu cầu mà chưa được xác nhận.

Ví dụ producer rút gọn:

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPaid;
import com.example.shop.orders.events.OrderRefunded;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderLifecycleService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderLifecycleService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(
            UUID orderId, VerifiedPayment payment
    ) {
        Order order = orders.findById(orderId).orElseThrow();

        // Chỉ true khi payment mới tạo transition hợp lệ.
        if (!order.markPaidIfNew(payment.id())) {
            return;
        }

        orders.save(order);
        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(), orderId, order.getCustomerId(),
                payment.id(), payment.amount(), clock.instant()
        ));
    }

    @Transactional
    public void recordVerifiedRefund(
            UUID orderId, VerifiedRefund refund
    ) {
        Order order = orders.findById(orderId).orElseThrow();

        // Chỉ true khi lần hoàn tiền mới được ghi nhận.
        if (!order.recordRefundIfNew(refund.id(), refund.amount())) {
            return;
        }

        orders.save(order);
        publisher.publishEvent(new OrderRefunded(
                UUID.randomUUID(), orderId, order.getCustomerId(),
                refund.id(), refund.amount(), clock.instant()
        ));
    }
}
~~~

`Order`, `OrderRepository`, `VerifiedPayment`, `VerifiedRefund`, `markPaidIfNew` và `recordRefundIfNew` là các kiểu/phương thức **minh họa cần được hiện thực bởi dự án**. Code giả định kết quả thanh toán/hoàn tiền đã được xác thực qua nguồn tin cậy, repository lưu trong transaction hiện hành và các trường tiền tệ đã có quy tắc rõ.

**Publish trong transaction nguồn** là một lựa chọn quan trọng khi muốn publication bền vững được gắn với commit của thay đổi nghiệp vụ. `publishEvent` tự nó không đảm bảo commit, sau commit hay độ bền; các đặc tính đó phụ thuộc listener và Event Publication Registry đã cấu hình.

## 9. Event Publication Registry khi một bean có nhiều handler

Giả sử listener `LoyaltyOrderEventListener` có hai phương thức `on(OrderPaid)` và `on(OrderRefunded)`, đều được đánh dấu `@ApplicationModuleListener`. Spring Modulith có khả năng theo dõi event publication cho các transactional listener được hỗ trợ khi **Event Publication Registry** và repository bền vững được cấu hình phù hợp.

Khi `OrderPaid` được publish trong transaction, registry có thể lưu một publication dành cho handler phù hợp với `OrderPaid`; tương tự, `OrderRefunded` có publication dành cho handler tương ứng. **Không phải cứ một class listener là có một publication chung cho mọi loại event.** Đích xử lý, contract và trạng thái hoàn thành của từng lần publication mới là những đối tượng cần theo dõi.

~~~mermaid
flowchart TD
    Paid["Publish OrderPaid"] --> PaidPub["Publication cho handler OrderPaid"]
    Refund["Publish OrderRefunded"] --> RefundPub["Publication cho handler OrderRefunded"]
    PaidPub --> Credit["on(OrderPaid)"]
    RefundPub --> Debit["on(OrderRefunded)"]
    Credit --> CP{"Thành công?"}
    Debit --> RP{"Thành công?"}
    CP -->|Có| DonePaid["Publication paid hoàn tất"]
    CP -->|Không| PendingPaid["Publication paid chưa hoàn tất"]
    RP -->|Có| DoneRefund["Publication refund hoàn tất"]
    RP -->|Không| PendingRefund["Publication refund chưa hoàn tất"]
~~~

Registry giúp xử lý khoảng trống: **transaction nguồn đã commit nhưng consumer chưa hoàn tất**, hoặc JVM dừng trước khi completion được ghi nhận. Khi có storage bền vững phù hợp và cơ chế resubmit, publication chưa hoàn tất có thể được phát hiện để xử lý lại.

| Tình huống | Trạng thái cần xét |
| --- | --- |
| Transaction phát `OrderPaid` rollback | Listener hậu commit không chạy; publication cùng transaction không được commit |
| `OrderPaid` commit, `on(OrderPaid)` thành công | Publication của handler tương ứng được đánh dấu hoàn tất |
| `on(OrderRefunded)` lỗi sau commit | Publication của event hoàn tiền có thể còn chưa hoàn tất |
| Consumer đã ghi ledger nhưng crash trước completion | Publication có thể bị resubmit; consumer phải chống trùng |
| Thêm một handler khác cũng nghe `OrderPaid` | Có thêm một đích xử lý phù hợp, cần quan sát trạng thái độc lập |

Chỉ thêm `@ApplicationModuleListener` **không tự đảm bảo** storage publication bền vững hoặc retry vô hạn. Cần cấu hình integration lưu publication (ví dụ JDBC/JPA phù hợp phiên bản), kiểm tra việc ghi publication cùng transaction nguồn và quy trình resubmit chưa hoàn tất. Không dựa vào tên class để giả định số bản ghi publication; hãy kiểm tra thực tế listener đã đăng ký.

## 10. Idempotency phải tách theo tác động của mỗi event

Một `OrderPaid` có thể bị giao hai lần sau lỗi, và một `OrderRefunded` cũng có thể bị giao lại. Nếu consumer chỉ cộng/trừ điểm ở mỗi lần nhận, khách hàng có thể nhận điểm sai.

Một ledger minh họa trên PostgreSQL có thể lưu khóa chống trùng cho **từng tác động của handler**:

~~~sql
CREATE TABLE loyalty_event_effects (
    event_type    VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    handler_name  VARCHAR(100) NOT NULL,
    order_id      UUID NOT NULL,
    points_delta  INTEGER NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (event_type, event_id, handler_name)
);
~~~

Ví dụ, lần xử lý `OrderPaid(E1)` thành công sẽ tạo một bản ghi `(OrderPaid, E1, credit-points)`. Khi nhận lại `E1`, consumer không được cộng thêm điểm. Với `OrderRefunded(E2)`, bản ghi `(OrderRefunded, E2, refund-adjustment)` độc lập; việc hoàn tiền không được bị bỏ qua chỉ vì đơn `orderId` đã từng có thanh toán.

**Ghi dấu idempotency và thực hiện tác động nghiệp vụ phải là một transaction logic an toàn.** Nếu chỉ ghi “đã xử lý” rồi crash trước khi ghi điểm, lần retry có thể bỏ qua sai. Nếu chỉ ghi điểm rồi crash trước khi ghi dấu, lần retry có thể cộng trùng. Dùng transaction và unique constraint để bảo vệ cả sự cạnh tranh giữa nhiều lần xử lý đồng thời.

### Phân biệt event trùng và nghiệp vụ trùng

| Loại trùng | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| Một event bị giao lại | `OrderPaid` với cùng `eventId = E1` đến lần hai | Consumer dùng khóa event/handler |
| Nhiều event cho một payment | Producer phát `OrderPaid(E1)` và `OrderPaid(E2)` do webhook lặp | Producer kiểm tra paymentId và transition; consumer có thể thêm khóa nghiệp vụ |
| Hoàn tiền nhiều phần | `OrderRefunded(E3)` và `OrderRefunded(E4)` ứng với hai refundId hợp lệ | Không được gộp bừa theo orderId; cần cộng dồn điều chỉnh đúng |
| Cùng event khớp hai handler | Một method generic và một method typed đều nhận `OrderPaid` | Thiết kế registration rõ ràng; chống hai handler cùng ghi một tác động |

Idempotency không đồng nghĩa cứ thấy `orderId` đã xuất hiện thì bỏ qua. Một đơn có thể phát nhiều event hợp lệ trong suốt vòng đời; khóa chống trùng phải phản ánh **một tác động nghiệp vụ duy nhất**.

## 11. Xử lý thứ tự khi listener nhận nhiều loại event

Hai loại event không phải lúc nào cũng được xử lý theo thứ tự phát. Với `@ApplicationModuleListener`, mỗi lời gọi có thể được thực thi bất đồng bộ; việc retry sau lỗi có thể khiến event cũ hoàn thành sau event mới.

Ví dụ `OrderPaid` được publish và đã commit trước `OrderRefunded`, nhưng `on(OrderPaid)` gặp lỗi tạm thời. Handler hoàn tiền có thể đến trước khi ledger thanh toán được ghi.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant L as LoyaltyOrderEventListener
    O-->>L: OrderPaid(E1)
    Note over L: Handler paid lỗi, chờ retry
    O-->>L: OrderRefunded(E2)
    L->>L: Không được giả định bút toán paid đã tồn tại
    O-->>L: Resubmit OrderPaid(E1)
    L->>L: Phục hồi theo quy tắc ledger và trạng thái hiện tại
~~~

Có một số cách giải quyết tùy bất biến nghiệp vụ:

1. **Ledger cộng dồn theo sự kiện**, trong đó mỗi bút toán độc lập và tổng điểm tính từ các bút toán hợp lệ. Cần quy tắc rõ cho refund một phần, hoàn tiền vượt hạn mức, và các bút toán chưa xuất hiện.
2. **Version trên aggregate**, ví dụ một số thứ tự nghiệp vụ tăng trong transaction của `orders`. Consumer chỉ áp dụng transition hợp lệ hoặc lưu event đến sớm để xử lý sau.
3. **Điều phối thứ tự**, khi quy trình không thể chấp nhận out-of-order. Có thể dùng workflow/process manager hoặc cơ chế serialize xử lý theo khóa aggregate.

Không dùng riêng `occurredAt` để bảo đảm thứ tự. Đồng hồ có thể lệch, có thể nhiều event cùng timestamp và transaction bắt đầu trước không có nghĩa commit trước.

Nếu quy tắc là “không trừ điểm khi chưa từng cộng điểm”, listener hoàn tiền cần xử lý **trạng thái đang chờ/đối soát**, chứ không ném lỗi rồi retry vô hạn mà không có cách xác minh tiến độ.

## 12. Kiểm thử ba cách đăng ký listener

Test cần xác nhận từng loại event đi vào đúng nhánh, transaction xảy ra đúng thời điểm, và người học không vô tình đăng ký chồng chéo gây hiệu ứng kép.

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Handler riêng cho thanh toán | Publish `OrderPaid` hợp lệ | Chỉ chạy nhánh cộng điểm; không gọi nhánh hoàn tiền |
| Handler riêng cho hoàn tiền | Publish `OrderRefunded` hợp lệ | Chỉ chạy nhánh điều chỉnh điểm; không cộng điểm mới |
| Một method `classes = {...}` không tham số | Publish mỗi kiểu đã liệt kê | Tác vụ chung được kích hoạt cho mỗi event |
| Method `classes = {...}` có tham số | Viết chữ ký sai | Sửa thiết kế; không coi đây là cách nhận payload đa kiểu |
| Interface chung | Publish một event triển khai interface | Handler chung nhận và xử lý theo contract đã định |
| Đăng ký generic và typed trùng nhau | Có cả hai method phù hợp với `OrderPaid` | Xác định nguy cơ xử lý trùng, loại bỏ chồng chéo hoặc làm idempotent |
| Producer rollback | Publish trong transaction rồi rollback | Không có hiệu ứng hậu commit |
| Hai transaction commit | Phát `OrderPaid` rồi `OrderRefunded` | Consumer xử lý đúng nghiệp vụ dù hoàn thành có thể lệch thứ tự |
| Retry cùng eventId | Giao lại `OrderPaid(E1)` hoặc `OrderRefunded(E2)` | Không ghi thêm bút toán trùng |
| Listener lỗi sau commit | Handler ném exception | Nguồn đã commit không rollback; publication còn dang dở nếu registry được cấu hình |
| Đổi contract event | Thêm/đổi field hay subtype | Build, test và ý nghĩa nghiệp vụ được kiểm tra lại |

Có thể kiểm tra ranh giới Spring Modulith bằng một test kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ShopModuleBoundaryTests {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là lớp ứng dụng minh họa tại package gốc; test giả định đã có phụ thuộc Spring Modulith và JUnit thích hợp.

Spring Modulith cung cấp `@ApplicationModuleTest`, `PublishedEvents` và `Scenario` để hỗ trợ kiểm tra event và tương tác module theo bộ dependency, phiên bản đã chọn. Với async listener, dùng cách chờ theo **điều kiện nghiệp vụ có timeout** thay vì `Thread.sleep` cố định.

### Hai bẫy test dễ bỏ sót

**Bẫy transaction:** test bọc `@Transactional` rồi tự rollback thường không kích hoạt `AFTER_COMMIT`. Muốn chứng minh listener nhận sau commit, phải để transaction nguồn thực sự commit.

**Bẫy kiểu chung:** test chỉ phát `OrderPaid` sẽ không cho thấy handler generic vô tình nhận thêm `OrderCancelled` sau khi một record mới implements interface chung. Hãy liệt kê tập event mà mỗi listener thực sự đăng ký, và có negative test với những kiểu không được phép gây side effect.

## 13. Quan sát: một bean, nhiều loại publication

Để chẩn đoán sự cố, không chỉ log tên class `LoyaltyOrderEventListener`: cùng class này có thể chứa các phương thức với tác động hoàn toàn khác nhau. Log/metric nên phân biệt **event type, eventId, method/handler, lần thử, trạng thái xử lý và độ trễ**.

| Dữ liệu quan sát | Vì sao cần? |
| --- | --- |
| `eventType`, `eventId` | Phân biệt `OrderPaid(E1)` với `OrderRefunded(E2)` |
| `orderId`, `paymentId` hoặc `refundId` | Liên hệ với một giao dịch nghiệp vụ cụ thể |
| `listenerClass`, `handlerMethod` | Biết nhánh nào trong cùng bean đang xử lý |
| `occurredAt`, `receivedAt`, `completedAt` | Phân tích độ trễ từ producer đến consumer |
| `attempt`, `errorCategory` | Theo dõi lỗi, retry và nguyên nhân thất bại |
| Publication chưa hoàn tất theo event/handler | Xác định chính xác việc còn tồn đọng |
| Số bút toán idempotency bị từ chối do trùng | Thấy được lượng event giao lại mà hệ thống đã chặn |
| Độ tuổi publication cũ nhất | Phát hiện handler bị kẹt lâu |

Có thể theo dõi hai nhóm metric riêng `loyalty_paid_processing_duration` và `loyalty_refunded_processing_duration` (tên minh họa), hoặc dùng metric chung với tag `event_type` và `handler`. Cần kiểm soát cardinality của metric: `eventId` thường nên xuất hiện trong log/tracing, **không nên làm label metric có vô số giá trị**.

Khi một consumer lỗi:

1. Tra `eventId`, `eventType` và transaction nguồn để biết sự thật nghiệp vụ đã commit chưa.
2. Xem đúng method handler được đăng ký, không chỉ bean name.
3. Xác nhận ledger/side effect đã xảy ra chưa trước khi resubmit.
4. Kiểm tra publication còn mở, số lần retry và exception gần nhất.
5. Sửa nguyên nhân rồi giao lại có kiểm soát; xác nhận không ghi bút toán trùng.
6. Nếu nghi lệch thứ tự, so sánh version/trạng thái nghiệp vụ, không chỉ timestamp.

Không log toàn bộ payload có dữ liệu nhạy cảm. Nên dùng định danh tương quan đủ để truy vết và áp dụng chính sách quyền truy cập log.

## 14. Bài thực hành: một listener cho ba sự kiện đơn hàng

### Đề bài

Ứng dụng quản lý vé có module `payments`, `tickets`, `loyalty` và `notifications`. Module `payments` phát `PaymentCompleted` và `PaymentRefunded`; module `tickets` phát `TicketCancelled`.

Module `notifications` cần phản ứng với cả ba loại event để tạo thông báo tương ứng. Module `loyalty` chỉ cần nhận thanh toán và hoàn tiền; `notifications` còn có một cache “lịch sử giao dịch gần đây” cần làm mới khi bất kỳ một trong ba event xảy ra.

### Các bước

1. **Công bố contract:** thiết kế record `PaymentCompleted`, `PaymentRefunded`, `TicketCancelled` ở public API đúng module sở hữu sự thật.
2. **Một bean nhiều phương thức:** viết `NotificationEventListener` với ba method typed `@ApplicationModuleListener`, mỗi method chuyển sang nghiệp vụ tạo yêu cầu gửi tương ứng.
3. **Một method chung không tham số:** tạo một `@EventListener(classes = {...})` để invalidate cache khi có các event phù hợp. Giải thích vì sao method không đọc payload.
4. **So sánh kiểu cha:** nếu muốn một `OrderLifecycleEvent` hay `PaymentLifecycleEvent` chung, xác định field nào thực sự chung và tập subtype được phép.
5. **Chống lặp:** dùng khóa duy nhất `(eventType, eventId, handler)` hoặc khóa nghiệp vụ phù hợp để tạo thông báo/điểm thưởng không trùng.
6. **Kiểm thử commit/rollback:** khi transaction thanh toán rollback, các method hậu commit không được tạo yêu cầu gửi.
7. **Kiểm thử lỗi một nhánh:** cho handler hoàn tiền ném exception, còn handler thanh toán chạy thành công; xác nhận publication khác nhau.
8. **Kiểm thử thứ tự:** cho refund được xử lý trước khi paid handler hoàn tất, rồi xác định chính sách xử lý trạng thái chờ.
9. **Bật registry bền vững:** cấu hình storage phù hợp để tra publication chưa hoàn tất; kiểm thử resubmit và idempotency.
10. **Quan sát:** ghi log/metric theo loại event, handler và outcome; xác định được nhánh xử lý bị kẹt.

### Câu hỏi tự đánh giá

**Câu 1. Một class chứa ba method `@ApplicationModuleListener` có phải một lần publish sẽ gọi cả ba method không?**

Không. Spring lựa chọn phương thức theo loại event tương thích và phase. Nếu ba method có kiểu tham số khác nhau, chỉ những method phù hợp với event đang publish mới được xem xét. Một event có thể khớp nhiều method khi có kiểu chung hoặc chồng chéo.

**Câu 2. Vì sao `@EventListener(classes = {A.class, B.class})` không nhận một tham số `Object`?**

Vì hợp đồng annotation dành cho **nhiều event class** yêu cầu method **không có tham số**. Nếu cần biết loại và payload, dùng nhiều method cụ thể hoặc một kiểu cha chung.

**Câu 3. `OrderRefunded` đến trước khi listener `OrderPaid` hoàn tất có nhất thiết là lỗi của producer không?**

Không. Consumer bất đồng bộ hoặc retry có thể hoàn tất khác thứ tự publish. Cần thiết kế bất biến, version/ledger và đường khôi phục phù hợp.

**Câu 4. Có registry rồi thì cùng event có thể được giao hai lần không?**

Có. Consumer có thể commit side effect rồi crash trước khi registry đánh dấu hoàn tất; resubmit sẽ gửi lại event. Idempotency phải nằm ở nơi ghi hiệu ứng nghiệp vụ.

**Câu 5. Nếu phương thức listener không được gọi, cần kiểm tra gì?**

Kiểm tra bean được Spring scan, annotation/chữ ký đúng, loại event tương thích, application context, transaction nguồn và phase của listener. Nếu dùng `@ApplicationModuleListener`, kiểm tra thêm hạ tầng async, publication registry và exception đã ghi nhận.

## 15. Checklist trước khi áp dụng

- [ ] Hiểu rõ “một bean nhiều method” khác “một method nhiều loại event”.
- [ ] Chọn các event có ngữ nghĩa nghiệp vụ rõ ràng, không đặt tên như command trá hình.
- [ ] Công bố contract trong API của module nguồn, tránh import package nội bộ.
- [ ] Dùng nhiều method typed khi các event có quy tắc xử lý khác nhau.
- [ ] Dùng `@EventListener(classes = {...})` **không tham số** khi mọi event kích hoạt cùng một tác vụ không cần payload.
- [ ] Chỉ dùng kiểu cha chung khi các event thật sự có contract và chính sách phù hợp.
- [ ] Không đăng ký chồng chéo generic và specific handler tạo cùng một tác động.
- [ ] Phân biệt xử lý ngay lúc publish với xử lý sau commit.
- [ ] Kiểm chứng transaction nguồn thực sự tồn tại; tránh giả định `@Transactional` luôn được áp dụng.
- [ ] Mỗi event có định danh riêng; producer chống input/transition trùng.
- [ ] Consumer dùng transaction và unique constraint để chống nhận trùng.
- [ ] Có chiến lược out-of-order cho event liên quan cùng aggregate.
- [ ] Registry/storage/recovery được cấu hình khi cần giao sự kiện bền vững.
- [ ] Test cả paid/refund, rollback, lỗi, retry, chồng chéo handler và thứ tự.
- [ ] Log/metric tách theo `eventType`, `handler` và trạng thái hoàn tất.

## Ghi nhớ

**Một listener nhiều event** trong Spring Modulith có thể được tổ chức thành **một bean chứa nhiều phương thức typed** hoặc **một phương thức nhận kiểu chung**. Với `@EventListener(classes = {A.class, B.class})`, phương thức không có tham số nên thích hợp cho một tác vụ chung không cần dữ liệu event. Khi nghiệp vụ của từng event khác nhau, nhiều phương thức `@ApplicationModuleListener` trong cùng bean thường rõ ràng hơn và giúp mỗi phản ứng có ranh giới trách nhiệm riêng.

Điều quan trọng là **một bean không đồng nghĩa một transaction, một publication hay một lần xử lý duy nhất**. Mỗi event có thể được nhận sau commit, chạy bất đồng bộ, thất bại và được giao lại. Hợp đồng sự kiện công khai, Event Publication Registry đã cấu hình, retry có kiểm soát, idempotency, kiểm thử transaction và khả năng quan sát theo từng event/handler là nền tảng để các module giao tiếp đáng tin cậy mà vẫn giữ ranh giới nghiệp vụ.

