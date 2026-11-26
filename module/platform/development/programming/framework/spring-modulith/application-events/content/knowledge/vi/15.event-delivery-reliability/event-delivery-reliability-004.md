# Mất event trong Spring Modulith: nhận diện điểm rơi và thiết kế giao sự kiện đáng tin cậy

## 1. “Mất event” là vấn đề gì?

Trong Spring Modulith, một module có thể công bố **application event** để các module khác phản ứng mà không phải gọi trực tiếp service của nhau. Ví dụ, module `orders` tạo đơn hàng và phát `OrderPlaced`, sau đó `notifications` gửi email xác nhận, `loyalty` cộng điểm và `analytics` cập nhật thống kê.

Câu hỏi quan trọng về độ tin cậy là:

**Nếu đơn hàng đã được commit nhưng một listener không bao giờ nhận hoặc hoàn tất xử lý `OrderPlaced`, hệ thống có biết và có thể khôi phục không?**

Đó là tình huống trọng tâm của bài **Mất event**, thuộc chương **Đảm bảo tin cậy** trong `SPRING_MODULITH_APPLICATION_EVENTS`.

~~~mermaid
flowchart LR
    O["orders<br/>Đơn hàng đã commit"] --> E(("OrderPlaced"))
    E --> N["notifications<br/>Email"]
    E --> L["loyalty<br/>Điểm"]
    E --> A["analytics<br/>Báo cáo"]
    E -. "Nếu tiến trình dừng / cấu hình sai" .-> X["Consumer không hoàn tất"]
~~~

**Mất event** trong thực tiễn có thể mang nhiều nghĩa, cần phân biệt:

- **Không hề tạo hoặc công bố event**: nghiệp vụ đã commit nhưng code không gọi publisher, hoặc đường gọi bị bỏ qua.
- **Event chỉ tồn tại trong bộ nhớ rồi biến mất**: tiến trình dừng trước khi consumer kịp nhận hay xử lý, không có bản ghi bền vững để khôi phục.
- **Event đã được công bố nhưng listener không được kích hoạt**: thiếu bean, sai loại event, sai transaction phase hoặc publisher không có transaction.
- **Listener được kích hoạt nhưng xử lý thất bại**: event không thực sự mất, nhưng tác vụ nghiệp vụ chưa hoàn tất.
- **Tác vụ hoàn tất nhưng dấu vết hoàn tất chưa được ghi**: event có thể được xử lý lại, dẫn đến **trùng side effect**, không phải mất event.
- **Publication tồn tại nhưng không thể phát lại**: schema thay đổi, consumer bị xóa, serializer lỗi hoặc quy trình recovery không được vận hành.

Một hệ thống tốt cần phân biệt những trạng thái này thay vì kết luận “`publishEvent` đã chạy thì mọi thứ đều an toàn”.

### Mục tiêu học tập

Sau bài này, người đọc có thể:

1. Chỉ ra các **failure window** giữa lưu nghiệp vụ, publish, commit, delivery và completion.
2. Phân biệt event trong bộ nhớ với **publication có lưu trữ bền vững**.
3. Hiểu vai trò và giới hạn của `@TransactionalEventListener`, `@ApplicationModuleListener` và **Event Publication Registry**.
4. Thiết kế retry/recovery không gây xử lý trùng.
5. Kiểm thử tình huống rollback, lỗi listener, dừng tiến trình và thay đổi schema.
6. Xây dựng chỉ số và quy trình điều tra event chưa được xử lý.

## 2. Không được đồng nhất các mốc trong chu kỳ giao event

Một chu kỳ điển hình có nhiều mốc độc lập:

~~~mermaid
flowchart TD
    A["Nghiệp vụ tạo đơn"] --> B["Tạo OrderPlaced"]
    B --> C["publishEvent"]
    C --> D{"Transaction của orders"}
    D -->|"Rollback"| R["Không có đơn đã commit"]
    D -->|"Commit"| E["Đơn hàng được xác lập"]
    E --> F["Listener sau commit được kích hoạt"]
    F --> G["Thực hiện tác vụ của consumer"]
    G --> H["Ghi nhận publication đã hoàn tất nếu có registry"]
~~~

Sơ đồ thể hiện **luồng listener sau commit**, không phải hành vi bắt buộc cho tất cả listener của Spring. Một `@EventListener` đồng bộ thông thường có thể chạy ngay trong lệnh `publishEvent`, trước bước commit.

| Mốc | Điều đã xảy ra | Điều chưa thể suy ra |
| --- | --- | --- |
| Tạo `new OrderPlaced(...)` | Đối tượng Java tồn tại. | Event đã được công bố hoặc lưu bền vững. |
| Gọi `publishEvent(event)` | Hạ tầng Spring nhận yêu cầu công bố. | Mọi consumer đã thành công; DB đã commit. |
| Transaction tạo đơn commit | Dữ liệu đơn được xác lập. | Email đã gửi hoặc điểm đã cộng. |
| Listener bắt đầu | Một consumer đã nhận công việc. | Side effect đã hoàn tất. |
| Listener hoàn tất | Phương thức xử lý trả về thành công. | Một hệ thống ngoài chắc chắn có đúng một side effect trong mọi tình huống. |
| Publication được đánh dấu hoàn tất | Registry đã ghi nhận thành công của listener theo cơ chế được cấu hình. | Có distributed transaction giữa DB và email/broker. |

**Cần quan sát riêng tiến độ nghiệp vụ chính và tiến độ của từng consumer**. Khi orders đã commit và notifications còn lỗi, trạng thái đúng là “đơn đã tạo, thông báo chưa hoàn tất”, không phải “toàn bộ giao dịch đơn hàng thất bại”.

## 3. Tại sao application event thuần có thể mất khi ứng dụng dừng?

`ApplicationEventPublisher` của Spring công bố event **trong phạm vi `ApplicationContext` của ứng dụng**. Bản thân một lời gọi publish không đồng nghĩa ghi vào message broker, bảng outbox hoặc file log bền vững.

Ví dụ không có cơ chế lưu publication:

~~~java
@Transactional
public UUID placeOrder(PlaceOrderCommand command) {
    Order order = orders.save(Order.create(command));
    publisher.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            clock.instant()
    ));
    return order.getId();
}
~~~

Giả sử listener được thiết kế bất đồng bộ và chỉ chạy sau commit:

~~~text
T0 — Tạo và lưu order trong transaction.
T1 — publishEvent(OrderPlaced) ở bộ nhớ ứng dụng.
T2 — Transaction orders COMMIT.
T3 — Tiến trình bị dừng đột ngột.
T4 — Listener dự kiến xử lý sau commit chưa kịp hoàn tất.
T5 — Ứng dụng khởi động lại.
~~~

Nếu không có dữ liệu bền vững hoặc cơ chế khôi phục phù hợp, tiến trình mới **không có lý do để tự biết event cũ cần được giao lại**.

Đây là một **khoảng rủi ro mất tác vụ hậu xử lý**. Nó không có nghĩa cứ dùng `@EventListener` hay `@ApplicationModuleListener` là chắc chắn mất event; nó có nghĩa **không được suy ra bảo đảm durability từ annotation hoặc object Java**.

Một event chạy đồng bộ cũng có điểm yếu riêng: listener gửi email hoặc ghi vào hệ thống ngoài **trước commit** có thể tạo side effect ngay cả khi transaction đơn hàng rollback sau đó. Giải pháp phải xét **cả thời điểm commit lẫn độ bền của publication**.

## 4. Bản đồ failure window cần đánh giá

Giả sử nghiệp vụ chính là tạo đơn, consumer là gửi thông báo.

| Thời điểm sự cố | Trạng thái có thể xảy ra | Rủi ro cốt lõi | Biện pháp cần xem xét |
| --- | --- | --- | --- |
| Trước khi lưu đơn | Chưa có đơn, chưa có event. | Nghiệp vụ thất bại bình thường. | Xử lý lỗi command. |
| Đã tạo object event nhưng chưa publish | Event chỉ là dữ liệu trong JVM. | Không có record nào để giao sau restart. | Publish đúng đường nghiệp vụ và transaction. |
| Đã lưu dữ liệu nhưng code không publish | Đơn có thể commit mà không sinh event. | **Mất event do logic**, registry không thể khôi phục event chưa từng phát. | Test publisher và đối soát nghiệp vụ. |
| Publish trước commit, T1 rollback | Một `@EventListener` đồng bộ có thể đã chạy. | Side effect “ma” cho đơn không tồn tại. | Listener sau commit cho tác vụ chỉ hợp lệ sau commit. |
| T1 commit, trước khi async listener hoàn tất | Đơn tồn tại; tác vụ phụ chưa hoàn tất. | Mất tác vụ nếu chỉ có event trong bộ nhớ. | Registry với persistence phù hợp hoặc transactional outbox. |
| Trong khi consumer gọi downstream | Có thể chưa biết gọi thành công hay thất bại. | **Kết quả không chắc chắn**; retry có thể gây trùng. | Timeout, đối soát, idempotency key. |
| Side effect đã thành công nhưng chưa ghi completion | Có thể còn publication chưa hoàn tất. | Replay tạo tác dụng phụ trùng. | Idempotency của consumer. |
| Có publication nhưng không còn listener tương thích | Công việc tồn tại mà không xử lý được. | Backlog lâu dài. | Chính sách schema/listener compatibility và recovery. |
| Dữ liệu registry bị mất hoặc không lưu thành công | Không còn bằng chứng delivery. | Mất khả năng khôi phục. | Thiết kế persistence/transaction/backup phù hợp. |

Không phải mọi lỗi đều có thể xử lý bằng một lựa chọn duy nhất. Đặc biệt, **rủi ro mất event** và **rủi ro xử lý trùng** thường xuất hiện cùng nhau. Để giảm mất event, hệ thống có thể phải cho phép phát lại; vì vậy consumer cần chịu được giao trùng.

## 5. Phân biệt ba nhóm listener và tác động đến mất event

| Cơ chế | Khi nào xử lý? | Đặc điểm độ tin cậy cần chú ý |
| --- | --- | --- |
| `@EventListener` | Thông thường đồng bộ ngay lúc publish với event multicaster mặc định. | Có thể thực thi trước commit; lỗi có thể lan về publisher. Không tự tạo durability. |
| `@TransactionalEventListener` | Theo transaction phase, mặc định `AFTER_COMMIT`. | Tránh xử lý sau-commit khi T1 rollback, nhưng **không tự lưu event bền vững**. |
| `@ApplicationModuleListener` | Spring Modulith hỗ trợ sau commit, bất đồng bộ, transaction riêng. | Phù hợp hậu xử lý giữa module; vẫn cần persistence/recovery và idempotency theo yêu cầu. |

Một ví dụ Spring Framework:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class ConfirmationAfterCommit {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        // Phản ứng sau commit của transaction tạo đơn.
    }
}
~~~

### Bẫy: publish khi không có transaction

Theo mặc định, `@TransactionalEventListener` không được kích hoạt nếu **không có transaction đang hoạt động** tại thời điểm publish. Tùy yêu cầu, Spring có tùy chọn `fallbackExecution = true`, nhưng cần hiểu rằng nó làm thay đổi ngữ nghĩa “chờ commit”.

~~~java
// Nếu publisher thực sự chạy ngoài transaction, listener
// @TransactionalEventListener mặc định sẽ không được gọi.
publisher.publishEvent(new OrderPlaced(
        UUID.randomUUID(), orderId, Instant.now()
));
~~~

Do đó, trước khi kết luận “event bị mất”, hãy kiểm tra **transaction có thật sự mở không**. `@Transactional` trên một method được gọi nội bộ cùng object có thể không đi qua Spring AOP proxy; điều này thường làm hành vi khác với kỳ vọng.

## 6. Thiết kế hợp đồng event để theo dõi và giao lại

Một event cho việc tạo đơn có thể dùng Java record bất biến:

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal payableTotal,
        String currencyCode,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(payableTotal, "payableTotal");
        Objects.requireNonNull(currencyCode, "currencyCode");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (payableTotal.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
~~~

**Ý nghĩa các trường đối với reliability:**

- `eventId` xác định **một lần xảy ra sự kiện**; khi replay **cùng event**, giữ nguyên ID.
- `orderId` xác định đối tượng nghiệp vụ; một đơn có thể tạo nhiều loại event.
- `customerId` giúp liên kết consumer với khách hàng nếu có nhu cầu và được phép truy cập.
- `payableTotal` và `currencyCode` là snapshot số tiền đã chốt phục vụ tính điểm, tránh đọc giá trị lịch sử từ bảng đã bị thay đổi.
- `occurredAt` là thời điểm nghiệp vụ, **không thay bằng thời điểm retry**.

Không có quy định mọi application event Spring phải có các field này. Chúng được chọn để hỗ trợ nghiệp vụ, logging và idempotency.

**Không truyền JPA entity sống hoặc bean Spring** như thành phần event: event có thể được xử lý sau commit, ở luồng khác hoặc được lưu/khôi phục; khi đó object chứa lazy proxy, reference mutable hoặc dữ liệu không serialize được có thể gây lỗi.

### Schema compatibility cũng là yêu cầu chống mất event

Nếu registry lưu một `OrderPlaced` phiên bản cũ, rồi ứng dụng đổi tên package/class hoặc đổi schema không tương thích, publication tồn đọng có thể không đọc lại được. Cần kiểm thử serializer thực tế và có chính sách chuyển tiếp/versioning trước khi triển khai breaking change.

## 7. Publisher phải phát trong đúng ranh giới nghiệp vụ

Một application service của `orders`:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = Order.create(command);
        Order saved = orders.save(order);

        var event = new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                saved.getPayableTotal(),
                saved.getCurrencyCode(),
                clock.instant()
        );

        events.publishEvent(event);
        return saved.getId();
    }
}
~~~

`OrderRepository`, `Order`, `PlaceOrderCommand` là các kiểu nghiệp vụ cần được định nghĩa trong dự án thật. Cần cấu hình `Clock` và bảo đảm `saved.getId()` sẵn có ở thời điểm tạo event.

Các điểm then chốt:

1. **Chỉ phát `OrderPlaced` khi việc tạo đơn đạt quy tắc nghiệp vụ.**
2. Tạo snapshot từ giá trị đã chốt, không lấy entity mutable làm payload.
3. Publish trong transaction T1, trước khi T1 commit, để cơ chế transactional listener và registry có thể liên hệ publication với transaction theo cấu hình.
4. Không để `OrderService` biết `NotificationService` hay `LoyaltyService`.
5. Chọn listener sau commit cho tác vụ chỉ hợp lệ khi đơn đã được commit.

**Ghi chú quan trọng:** publish trong transaction là **điều kiện thiết kế cần thiết**, nhưng **chưa đủ** để bảo đảm độ bền. Cần kiểm tra xem Event Publication Registry/persistence đã được bật và việc ghi publication có chia sẻ transaction tương thích với dữ liệu nghiệp vụ hay không.

## 8. Vì sao “publish sau commit bằng tay” có thể tạo lỗ hổng?

Một cách triển khai dễ nghĩ tới là:

~~~text
Bước A: save order + COMMIT
Bước B: publish OrderPlaced
~~~

Nếu tiến trình dừng **giữa A và B**, order đã được commit nhưng event chưa từng được publish. Listener không thể phục hồi thứ chưa hề được ghi nhận.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as OrderService
    participant DB as Database
    participant E as Event Publisher

    O->>DB: Save order
    O->>DB: COMMIT
    Note over O,E: Crash window
    O-xE: Chưa kịp publish OrderPlaced
~~~

Khi hệ thống cần bảo đảm publication bền vững, một lựa chọn là **ghi nhận thông tin cần giao trong cùng transaction với thay đổi nghiệp vụ**, rồi dispatch sau commit.

Spring Modulith cung cấp **Event Publication Registry** để hỗ trợ theo dõi publication đến transactional event listener khi được cấu hình đúng. Mô hình **transactional outbox** cũng có thể giải quyết bài toán ghi business data và thông điệp dự kiến gửi trong cùng transaction. Chi tiết triển khai khác nhau, nhưng nguyên tắc chung là tránh **dual-write không nguyên tử**: commit nghiệp vụ ở một nơi rồi mới hy vọng một lần ghi/phát thứ hai luôn thành công.

Không nên hiểu ví dụ publisher trong transaction ở mục trước là có thể mất event *chỉ vì* một listener chạy sau commit; quan trọng là **publication có được lưu bền vững cùng ranh giới commit hay không**.

## 9. Event Publication Registry giúp giảm rủi ro mất tác vụ như thế nào?

Spring Modulith có **Event Publication Registry** nhằm theo dõi quá trình giao event đến các **transactional event listener**. Với persistence integration phù hợp, registry có thể ghi nhận publication **chưa hoàn tất**, rồi đánh dấu hoàn tất khi listener thành công.

Ở mức logic, một event được giao tới nhiều listener có các trạng thái riêng:

~~~text
OrderPlaced(E-100), order đã COMMIT
├── publication cho notifications : INCOMPLETE
├── publication cho loyalty       : COMPLETED
└── publication cho analytics     : COMPLETED
~~~

Nếu notifications lỗi hoặc ứng dụng dừng giữa lúc xử lý, trạng thái chưa hoàn tất là cơ sở để ứng dụng **phát hiện và phục hồi công việc** khi có cơ chế recovery/republication tương ứng.

~~~mermaid
flowchart TD
    A["orders tạo OrderPlaced trong T1"] --> B["Ghi publication cho transactional listeners<br/>khi registry/persistence được cấu hình"]
    B --> C{"T1 commit?"}
    C -->|"Không"| R["Rollback nghiệp vụ và các ghi nhận<br/>cùng transaction"]
    C -->|"Có"| D["Listener chạy sau commit"]
    D --> E{"Xử lý thành công?"}
    E -->|"Có"| F["Đánh dấu publication hoàn tất"]
    E -->|"Không"| G["Publication chưa hoàn tất"]
    G --> H["Recovery/republication có kiểm soát"]
    H --> D
~~~

Đây là **sơ đồ khái niệm**, không phải mô tả bắt buộc mọi callback nội bộ của mọi phiên bản Spring Modulith.

### Điều kiện để hình thành bảo đảm thực sự

- Có một **backend persistence** cho publication, không chỉ lưu transient trong bộ nhớ.
- Việc ghi business data và ghi publication cần có **quan hệ transaction đúng** nếu muốn cam kết không có khoảng trống giữa chúng.
- Chỉ các listener thuộc cơ chế mà registry hỗ trợ theo dõi mới được hưởng lợi từ publication tracking tương ứng; không mặc định mọi `@EventListener` đều có record.
- Có cơ chế **recovery/republication** được thiết lập và vận hành.
- Consumer **idempotent** để chịu được việc replay hoặc giao lặp.
- Có **monitoring** để phát hiện publication tồn đọng hoặc lỗi khôi phục.

Khi dùng cùng database và transaction manager phù hợp, việc lưu publication cùng transaction nghiệp vụ có thể tạo ranh giới commit nhất quán hơn. Nếu storage publication và business data ở hai datasource khác nhau, **không tự giả định chúng commit nguyên tử**.

### Registry không làm được những gì?

Registry không tự sửa lỗi publisher **không hề publish** event. Nó không phải message broker, không biến side effect email thành cùng một transaction với database và không bảo đảm exactly-once. Nếu event được tạo với schema không thể deserialize sau khi nâng cấp, dữ liệu registry vẫn có thể tồn tại nhưng cần xử lý tương thích để khôi phục.

## 10. Một listener có thể nhận được event nhưng tác vụ vẫn mất

Ví dụ module notifications:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SendConfirmationOnOrderPlaced {

    private final ConfirmationService confirmations;

    SendConfirmationOnOrderPlaced(ConfirmationService confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        confirmations.sendConfirmation(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`ConfirmationService` và phương thức `sendConfirmation` là API minh họa do ứng dụng phải tự xây dựng.

`@ApplicationModuleListener` trong Spring Modulith thiết kế cho **xử lý sau commit, bất đồng bộ và transaction riêng**. Nó giúp giảm phụ thuộc thời gian và lỗi giữa orders và notifications, nhưng **không tự biến toàn bộ quy trình gửi email thành một giao dịch nguyên tử**.

Nếu `sendConfirmation` ném exception, việc listener được kích hoạt không đồng nghĩa nó đã hoàn tất. Nếu listener nuốt exception rồi trả về thành công, hạ tầng có thể hiểu xử lý đã thành công dù email thực tế chưa được gửi.

~~~java
// Anti-pattern: che giấu lỗi khiến hệ thống khó retry đúng.
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        confirmations.sendConfirmation(
                event.eventId(), event.orderId(), event.customerId()
        );
    } catch (RuntimeException ex) {
        logger.error("Email failed", ex);
        // Phương thức trả về như thể đã xử lý xong.
    }
}
~~~

**Nguyên tắc:** không nuốt lỗi mà vẫn cho publication được đánh dấu hoàn tất nếu tác vụ là bắt buộc. Hãy định nghĩa chính sách: lỗi nào được retry, lỗi nào thuộc diện cần can thiệp, và khi nào chấp nhận bỏ qua theo nghiệp vụ.

### Side effect ngoài database

Nếu email provider nhận request nhưng kết nối timeout trước khi trả response, ứng dụng **không biết chắc** email đã được gửi hay chưa. Retry có thể tạo email thứ hai; không retry có thể mất email thứ nhất. Cần chính sách đối soát hoặc idempotency của downstream nếu có.

## 11. Mất event khác với giao trùng event

Hai nhóm lỗi cần xử lý đồng thời:

| Tình huống | Hệ quả | Thiết kế cần có |
| --- | --- | --- |
| Không lưu publication, ứng dụng dừng trước khi xử lý | Consumer có thể không bao giờ nhận công việc. | Durable publication và recovery. |
| Publication chưa hoàn tất được replay dù side effect đã thực hiện | Consumer có thể thực hiện tác vụ hai lần. | Idempotency và đối soát. |

Với một publication tồn đọng:

~~~text
1. OrderPlaced(eventId=E-100) được ghi nhận.
2. Notifications gửi email thành công.
3. Tiến trình dừng trước khi lưu dấu completion.
4. Ứng dụng phục hồi publication E-100.
5. Notifications nhận lại cùng E-100.
~~~

Nếu `E-100` là cùng sự kiện, **không tạo `eventId` mới** chỉ vì đây là lần giao thứ hai.

**At-least-once** (có thể xử lý hơn một lần) thường là mục tiêu vận hành khả thi của hệ thống có cơ chế lưu và retry phù hợp. Đây là **mục tiêu thiết kế phụ thuộc cấu hình**, không phải lời bảo đảm mặc định cho mọi ứng dụng Spring Modulith. Và at-least-once delivery cũng **không đồng nghĩa exactly-once side effects**.

Một consumer phải được thiết kế sao cho phát lại cùng `eventId` không làm thay đổi kết quả nghiệp vụ quá một lần.

## 12. Idempotency trong database: không cộng điểm hai lần

Giả sử loyalty cộng điểm khi nhận `OrderPlaced`. Có thể dùng ledger với khóa duy nhất:

~~~sql
CREATE TABLE loyalty_awards (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    awarded_points BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Một mô hình xử lý:

~~~java
@Transactional
public void awardOnce(OrderPlaced event) {
    // API giả định insertIfAbsent thực hiện kiểm tra/ghi nguyên tử.
    boolean firstTime = awards.insertIfAbsent(
            event.eventId(),
            event.orderId(),
            event.customerId()
    );

    if (!firstTime) {
        return; // Event này đã được áp dụng trước đó.
    }

    balances.addPointsAtomically(
            event.customerId(),
            calculatePoints(event)
    );
}
~~~

Các API `awards.insertIfAbsent`, `balances.addPointsAtomically` và `calculatePoints` là pseudo-API do dự án cần triển khai. Điều cần giữ:

- Thao tác ghi ledger và cập nhật số dư cần ở **cùng transaction** nếu cùng database/transaction manager.
- Unique constraint/insert-if-absent phải thực hiện **nguyên tử**; không chỉ chạy `exists` rồi `insert` tách rời.
- Nếu database phát exception do duplicate key và transaction bị đánh dấu rollback-only, cần dùng cách xử lý phù hợp thay vì bắt lỗi rồi tiếp tục trong transaction đã không hợp lệ.
- Khóa `event_id` ngăn xử lý lại cùng event; một `orderId` có thể hợp lệ với nhiều loại event khác nhau.

Với nhiều consumer chia sẻ một kho dedup, nên dùng khóa **`(consumerName, eventId)`**, nếu không notifications có thể đánh dấu event đã xử lý làm loyalty bỏ qua nhầm. Một lựa chọn khác là mỗi module sở hữu ledger độc lập.

### Idempotency không tự làm email đúng một lần

Việc cập nhật DB và gửi email qua mạng không được bao trùm bởi một local DB transaction. Nếu đánh dấu “đã gửi” **trước** khi gọi email provider mà lời gọi thất bại, lần retry có thể bị bỏ qua. Nếu đánh dấu **sau** khi gửi thành công, crash ở giữa có thể dẫn đến gửi hai lần.

Các giải pháp tùy hệ thống:

1. Dùng **idempotency key** nếu API downstream hỗ trợ.
2. Tách yêu cầu gửi khỏi quá trình dispatch bằng một **delivery workflow** có trạng thái, khả năng đối soát và retry có kiểm soát.
3. Chấp nhận at-least-once nhưng thiết kế trải nghiệm/đối soát để phát hiện thông báo trùng.
4. Với tác vụ có giá trị tài chính hoặc rủi ro cao, dùng quy trình đối soát chính thức thay vì đoán “timeout nghĩa là chưa thực hiện”.

## 13. Khôi phục publication chưa hoàn tất

Mục đích của **recovery/republication** là xử lý công việc còn tồn tại sau lỗi tiến trình, lỗi downstream hoặc triển khai bản mới.

Một quy trình vận hành nên trả lời:

- **Nguồn dữ liệu:** danh sách publication chưa hoàn tất được lưu ở đâu?
- **Điều kiện tái xử lý:** publication nào thực sự cần retry, publication nào phải chờ sửa dữ liệu?
- **Thời điểm:** thực hiện lúc startup, theo lịch, thủ công hay cơ chế khác?
- **Tần suất:** backoff, jitter, số lần tối đa và giới hạn tải downstream?
- **Quyền sở hữu:** listener nào xử lý publication đó, còn tồn tại và tương thích không?
- **Dừng lặp vô ích:** thế nào là lỗi vĩnh viễn, poison event hoặc payload không hợp lệ?
- **Đối soát:** sau recovery, trạng thái nghiệp vụ consumer đã đúng chưa?

~~~mermaid
flowchart TD
    A["Publication chưa hoàn tất"] --> B{"Consumer và schema còn tương thích?"}
    B -->|"Không"| M["Khoanh vùng; sửa mapping/contract hoặc xử lý thủ công"]
    B -->|"Có"| C{"Lỗi có thể retry?"}
    C -->|"Không"| Q["Quarantine và điều tra nguyên nhân"]
    C -->|"Có"| D["Lên lịch retry có giới hạn"]
    D --> E["Consumer kiểm tra idempotency"]
    E --> F{"Xử lý thành công?"}
    F -->|"Có"| G["Ghi nhận hoàn tất"]
    F -->|"Không"| H{"Còn retry budget?"}
    H -->|"Có"| D
    H -->|"Không"| Q
~~~

Đây là quy trình **đề xuất để xây dựng recovery**, không phải chính sách retry mặc định của mọi bản Spring Modulith.

**Quan trọng:** biết publication tồn tại không có nghĩa framework luôn tự thử lại vào đúng lịch mà ứng dụng mong muốn. Khả năng tự khôi phục lúc startup, API phát lại, scheduler, completion mode hoặc backend hỗ trợ khác nhau theo phiên bản và cấu hình; cần kiểm tra cơ chế thực tế và thử với lỗi giả lập.

### Retry phải có giới hạn

Một listener lỗi do dữ liệu sai không nên được thử vô hạn mỗi vài mili-giây. Retry vô hạn có thể làm nghẽn executor, DB và API downstream. Hãy phân loại lỗi tạm thời (timeout, mất kết nối) và lỗi cần sửa (schema thiếu, identifier không hợp lệ, quy tắc nghiệp vụ mâu thuẫn).

Lập cảnh báo cho publication quá hạn xử lý hoặc vượt giới hạn retry, và thiết kế đường xử lý thủ công được kiểm soát.

## 14. “Mất event” vì listener chưa từng được đăng ký

Một publication không được xử lý không phải lúc nào cũng do crash.

Ví dụ:

~~~java
// Lớp không được Spring quản lý -> annotation không tự đăng ký.
class EmailHandler {
    @TransactionalEventListener
    void on(OrderPlaced event) {
        // ...
    }
}
~~~

Nếu `EmailHandler` không được tạo thành bean và không nằm trong `ApplicationContext`, method listener không tự được đăng ký.

Các lỗi cấu hình khác:

| Dấu hiệu | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Không có listener nào nhận event. | Component scan không quét đúng package, thiếu `@Component`/`@Bean`. | Xác minh Spring context và bean registration. |
| `@EventListener` nhận nhưng transactional listener không nhận. | Publisher phát ngoài transaction. | Kiểm tra transaction manager, AOP proxy và self-invocation. |
| Chỉ một số event không được nhận. | Kiểu tham số hoặc điều kiện `condition` không khớp. | Đối chiếu event class thực tế và handler signature. |
| Đơn đã commit nhưng không có publication. | Publisher không gọi `publishEvent` ở nhánh nghiệp vụ này; registry chưa cấu hình đúng. | Kiểm tra code path, test và cấu hình registry. |
| Sau deploy publication bị kẹt. | Tên/class/schema event hoặc listener identity đã thay đổi. | Kiểm thử deserialization và mapping listener với dữ liệu cũ. |
| Async task bị từ chối hoặc lỗi. | Executor quá tải, ứng dụng đóng, exception không được theo dõi. | Kiểm tra executor, logs, metric và registry. |
| Publication hoàn tất nhưng không thấy email. | Listener nuốt lỗi hoặc side effect bị che giấu. | Kiểm tra quy tắc completion, delivery log và provider. |

Việc một listener được đăng ký hôm nay cũng **không tự có nghĩa nó nhận lại các event đã xảy ra từ hôm qua**. Fan-out application events không phải một durable topic có chức năng replay lịch sử cho subscriber mới theo mặc định.

## 15. Vấn đề thay đổi code: event chưa mất nhưng không đọc lại được

Sự kiện tồn đọng có thể được lưu khi ứng dụng ở phiên bản V1. Sau khi deploy V2, record event đã thay đổi:

~~~java
// Phiên bản đầu:
public record OrderPlaced(UUID eventId, UUID orderId) {}

// Phiên bản mới:
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        String currencyCode,
        BigDecimal payableTotal
) {}
~~~

Java record thay canonical constructor. Persistence/serializer có thể không biết giá trị của field mới nếu publication cũ không chứa nó. Ngay cả việc rename class/package cũng có thể ảnh hưởng định danh loại dữ liệu được lưu.

Để tránh “mất khả năng xử lý event cũ”:

1. Xem publication tồn đọng trước khi deploy breaking change.
2. Tạo fixture của payload được lưu bằng serializer/backend thực tế.
3. Test V2 có đọc/khôi phục được fixture V1 không.
4. Cân nhắc hợp đồng V1/V2 song hành, migration hoặc adapter được quản trị.
5. Không đổi ngữ nghĩa field mà giữ nguyên tên khiến consumer xử lý sai âm thầm.
6. Quản lý thay đổi tên bean/method listener khi có publication chưa hoàn tất.

Thêm field optional cũng **không mặc nhiên tương thích**, đặc biệt với record Java và các serializer khác nhau. Phải chứng minh qua test.

## 16. Event Publication Registry và Transactional Outbox khác gì?

Cả hai đều có thể phục vụ mục tiêu tránh mất công việc khi thay đổi nghiệp vụ đã được commit, nhưng giải quyết các tình huống triển khai khác nhau.

| Tiêu chí | Event Publication Registry (Spring Modulith) | Transactional Outbox |
| --- | --- | --- |
| Mục tiêu chính | Theo dõi publication của application event đến các transactional listener. | Ghi dữ liệu cần truyền ra khỏi transaction nghiệp vụ theo cách bền vững. |
| Đơn vị theo dõi | Publication gắn với listener trong cơ chế của Modulith. | Thông điệp/outbox record do ứng dụng định nghĩa và dispatcher tiêu thụ. |
| Consumer phổ biến | Các module/listener trong ứng dụng. | Dispatcher, broker, dịch vụ khác hoặc các consumer theo thiết kế. |
| Điều kiện tin cậy | Backend persistence và transaction được cấu hình phù hợp. | Business row và outbox row được commit cùng transaction. |
| Khôi phục | Cơ chế recovery/republication của Modulith. | Dispatcher scan/poll/CDC outbox và retry. |
| Rủi ro vẫn tồn tại | Listener side effect lặp; cấu hình, schema, listener identity. | Dispatcher phát trùng; broker/consumer cần idempotency. |

Ví dụ outbox tự thiết kế:

~~~sql
BEGIN;

INSERT INTO orders(order_id, status)
VALUES (:orderId, 'CREATED');

INSERT INTO outbox_events(
    event_id, event_type, payload, created_at
) VALUES (
    :eventId, 'OrderPlaced', :serializedPayload, CURRENT_TIMESTAMP
);

COMMIT;
~~~

Sau commit, một dispatcher riêng đọc outbox và đẩy đi theo hạ tầng đã chọn. Nếu dispatcher dừng sau khi gửi nhưng trước khi đánh dấu record hoàn tất, nó có thể gửi lại cùng event: **outbox cũng cần idempotency ở consumer**.

**Không nên coi đây là hai thứ bắt buộc phải dùng cùng lúc.** Chọn theo ranh giới trong tiến trình hay ngoài tiến trình, dữ liệu cần bảo vệ, backend sẵn có và khả năng vận hành. Nếu sử dụng cả hai, phải mô tả rõ chúng liên quan thế nào để tránh tự gửi sự kiện hai lần.

## 17. Sự cố nhiều database, replica và durability thực tế

Giả sử orders được lưu ở database A nhưng publication được ghi ở database B, không có distributed transaction:

~~~text
Database A: COMMIT orders thành công
Database B: ghi publication thất bại
=> Đơn tồn tại nhưng publication có thể không tồn tại.
~~~

Chỉ đặt `@Transactional` ở application service không tự giải quyết **atomicity giữa hai nguồn dữ liệu**. Nếu yêu cầu độ tin cậy cao, cần xác định transaction manager nào quản lý thao tác ghi nào và dùng mẫu thiết kế phù hợp.

Những điểm vận hành khác:

- **Read replica lag:** listener chạy sau commit nhưng đọc replica chưa kịp sao chép dữ liệu mới. Đây không nhất thiết là mất event; consumer có thể báo “không tìm thấy đơn” do độ trễ.
- **Purge/retention:** xóa publication chưa hoàn tất trước khi xử lý xong sẽ làm mất khả năng recovery.
- **Backup/restore:** restore database về thời điểm cũ có thể ảnh hưởng trạng thái business data và publication theo các mốc khác nhau.
- **Storage outage:** registry backend không sẵn sàng có thể làm publication không lưu được; cần kiểm tra hành vi của transaction và chính sách lỗi.
- **Schema migration:** migration làm mất bảng, cột hoặc dữ liệu publication có thể khiến cơ chế phục hồi không còn đầu vào.
- **Khác nhau giữa môi trường test và production:** test dùng registry in-memory nhưng production cần durable delivery là một khoảng trống kiểm chứng.

Không có một isolation level nào đảm bảo mọi điều trên. Reliability là kết quả của **thiết kế transaction, persistence, giao sự kiện và vận hành**.

## 18. Kiểm thử: phải tạo lỗi ở đúng failure window

Unit test kiểm tra `publisher.publishEvent(event)` được gọi là cần thiết, nhưng không đủ chứng minh rằng application event **không bị mất khi ứng dụng dừng**.

### 18.1. Test publisher thật sự phát event

Spring Modulith có `@ApplicationModuleTest` và `PublishedEvents` để quan sát event được công bố trong module test:

~~~java
package com.acme.shop.orders;

import com.acme.shop.orders.events.OrderPlaced;
import com.acme.shop.orders.internal.OrderService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderEventTest {

    @Autowired
    OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents published) {
        // Fixture do dự án định nghĩa.
        var command = TestOrders.validPlaceOrder();
        UUID orderId = orders.placeOrder(command);

        assertThat(published.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

Đoạn test minh họa yêu cầu fixture `TestOrders` và các dependency Spring Modulith test được cấu hình. Nó chỉ xác minh **event đã publish**, chưa chứng minh consumer hoàn tất hay registry lưu bền vững.

### 18.2. Test rollback

Tạo order trong transaction rồi cố tình ném exception sau publish để rollback. Xác minh:

- Order không được commit.
- Listener `@ApplicationModuleListener` không thực hiện side effect.
- Publication gắn transaction, nếu lưu bền vững trong cùng transaction, không còn dấu vết committed sai.

Chú ý test `@Transactional` có thể tự rollback cuối test; nếu chờ listener after-commit khi transaction chưa commit, test không chứng minh listener lỗi.

### 18.3. Test consumer thất bại

Cho notifications ném exception trước khi hoàn tất. Kiểm tra:

- Đơn đã commit vẫn tồn tại.
- Consumer khác có thể hoàn tất độc lập.
- Registry/backend persistence ghi nhận publication của notifications chưa hoàn tất theo hành vi thực tế.
- Hệ thống có cảnh báo và cơ chế recovery đã chọn.

Không nuốt exception trong test khiến listener “thành công giả”.

### 18.4. Test dừng tiến trình sau commit

Đây là phép thử quan trọng của durability. Quy trình gợi ý:

1. Khởi chạy ứng dụng với backend registry bền vững và database phù hợp.
2. Gây điều kiện cho listener bị chặn trước khi hoàn tất.
3. Tạo order và xác nhận transaction publisher commit.
4. Dừng tiến trình khi publication còn tồn.
5. Khởi động lại ứng dụng với **cùng dữ liệu bền vững**.
6. Kích hoạt recovery theo cơ chế được cấu hình.
7. Xác nhận đúng consumer hoàn tất, không gửi/cộng điểm trùng.

Phép thử phải thực hiện trên môi trường kiểm thử kiểm soát; không dùng cách dừng tiến trình production để “thử”. Dùng điểm đồng bộ/barrier hoặc test hook có chủ đích, không dựa vào khoảng sleep tùy ý.

### 18.5. Test xử lý trùng sau side effect

Cho listener tạo side effect rồi mô phỏng lỗi trước khi completion được ghi nhận. Sau recovery:

- `eventId` vẫn là ID ban đầu.
- Consumer nhận được event lần nữa nếu publication chưa hoàn tất.
- Khóa idempotency ngăn tạo tác dụng phụ trùng.

### 18.6. Test dữ liệu và listener sau nâng cấp

Lưu fixture event phiên bản cũ bằng serializer thật, triển khai logic phiên bản mới, xác minh có thể deserialize và gọi đúng listener. Nếu không, phải có kế hoạch tương thích trước khi deploy.

## 19. Observability: làm sao biết event đã mất hay chỉ đang chậm?

Với listener bất đồng bộ, **không thấy email ngay** chưa đủ để kết luận event bị mất. Cần dữ liệu quan sát theo `eventId` và `listenerName`.

| Tín hiệu | Câu hỏi giúp trả lời |
| --- | --- |
| `eventId`, `orderId`, `eventType` | Đang điều tra event nào của đơn nào? |
| `publisherModule` | Module nào phát? |
| `transactionOutcome` | Nghiệp vụ gốc đã commit hay rollback? |
| `publicationStatus` theo listener | Consumer nào chưa hoàn tất? |
| `publishedAt`, `startedAt`, `completedAt` | Event bị chậm ở giai đoạn nào? |
| `attempt`, `lastError` | Có retry, lỗi tạm thời hay lỗi vĩnh viễn không? |
| `incompletePublicationAge` | Publication lâu nhất chưa hoàn tất bao lâu? |
| `executorQueueDepth`, `rejectedTasks` | Async executor có quá tải không? |
| `downstreamDeliveryId` nếu có | Hệ thống email/webhook đã nhận request hay chưa? |
| `schemaVersion`, lỗi deserialize | Event tồn đọng có còn đọc được không? |

Ví dụ log **do ứng dụng tự thiết kế**:

~~~text
event=OrderPlaced eventId=E-100 orderId=O-100 stage=PUBLISHED
event=OrderPlaced eventId=E-100 listener=notifications attempt=1 status=FAILED reason=MAIL_TIMEOUT
event=OrderPlaced eventId=E-100 listener=loyalty attempt=1 status=COMPLETED
event=OrderPlaced eventId=E-100 listener=notifications attempt=2 status=COMPLETED
~~~

Đây không phải định dạng mặc định được Spring Modulith tự tạo. **Log `PUBLISHED` không chứng minh transaction đã commit hoặc publication có persistence.**

Nên theo dõi tối thiểu:

- Số lượng publication **chưa hoàn tất** theo loại event và listener.
- Tuổi của publication tồn đọng lớn nhất.
- Tỷ lệ hoàn tất trong ngưỡng thời gian nghiệp vụ chấp nhận.
- Tỷ lệ retry/thất bại và các lỗi theo loại.
- Chênh lệch giữa số sự kiện nghiệp vụ đã commit cần xử lý với số tác vụ consumer thực tế đã hoàn tất.

Ví dụ mục tiêu vận hành: “99% xác nhận đơn được hoàn tất trong 5 phút sau khi đơn commit”. Đây là **một SLO minh họa do đội phát triển tự đặt**, không phải bảo đảm hay mặc định của Spring Modulith.

## 20. Quy trình điều tra “đơn đã tạo nhưng không có email”

Khi nhận được sự cố, không nên ngay lập tức gọi lại `publishEvent` với một event mới. Hãy lần theo evidence:

~~~mermaid
flowchart TD
    A["Đơn đã tạo nhưng chưa nhận email"] --> B{"Order đã commit?"}
    B -->|"Không"| C["Điều tra transaction / request thất bại"]
    B -->|"Có"| D{"Có bằng chứng event được publish?"}
    D -->|"Không"| E["Kiểm tra code path publisher và đối soát"]
    D -->|"Có"| F{"Có publication tồn đọng cho notifications?"}
    F -->|"Có"| G["Kiểm tra lỗi listener, schema, executor và retry"]
    F -->|"Không"| H{"Có bằng chứng listener hoàn tất?"}
    H -->|"Có"| I["Đối soát email provider / delivery status"]
    H -->|"Không"| J["Kiểm tra cấu hình bean, transaction, registry, retention"]
    G --> K["Recovery có idempotency và theo dõi"]
    J --> K
~~~

Cách điều tra cụ thể:

1. **Xác thực nghiệp vụ gốc:** tìm order và trạng thái commit; phân biệt order chưa commit với order tồn tại.
2. **Tìm `eventId` của `OrderPlaced`:** dựa vào log/tracing hoặc dữ liệu đã thiết kế để đối soát.
3. **Kiểm tra publisher:** code path có phát event? Event được tạo ở transaction thật không?
4. **Kiểm tra subscriber:** bean `notifications` có được đăng ký? Kiểu event, annotation và transaction phase đúng không?
5. **Kiểm tra registry:** có publication chưa hoàn tất, lỗi gần nhất, hoặc vấn đề deserialize/consumer identity không?
6. **Kiểm tra downstream:** email API trả gì? Timeout có phải kết quả chưa xác định không?
7. **Quyết định replay:** chỉ phát lại khi có khóa idempotency và cách theo dõi tác dụng phụ.
8. **Khắc phục gốc rễ:** nếu lỗi do thiếu publish ở một nhánh code, fix publisher và bổ sung regression test; registry không thể tự phục hồi event chưa hề được công bố.
9. **Đối soát sau khôi phục:** email/điểm/projection ở trạng thái nghiệp vụ mong muốn, publication hoàn tất và không còn backlog bất thường.

## 21. Anti-pattern phổ biến gây mất hoặc làm hỏng event

### 21.1. Chỉ lưu business row rồi publish sau commit mà không có cơ chế bền vững

Một lần crash giữa commit và publish sẽ tạo đơn không có event. Khi cần delivery đáng tin cậy, chọn mô hình publication/outbox được ghi trong transaction phù hợp.

### 21.2. Xem `@Async` là cơ chế lưu hàng đợi

`@Async` chuyển công việc sang executor; **không tự ghi job xuống storage bền vững**. Khi tiến trình dừng, tác vụ đang nằm trong hàng đợi bộ nhớ có thể mất.

### 21.3. Nuốt lỗi listener rồi trả về bình thường

Nếu công việc bắt buộc chưa hoàn tất mà listener vẫn trả success, registry có thể đánh dấu completion sai. Cần báo lỗi và chính sách retry/recovery phù hợp.

### 21.4. Retry bằng event mới với `UUID.randomUUID()`

Nếu chỉ giao lại **cùng một sự kiện**, tạo ID mới khiến consumer không nhận ra bản lặp. Chỉ tạo event mới nếu thực sự có sự thật nghiệp vụ mới.

### 21.5. Không chạy recovery dù đã có publication lưu

Dữ liệu tồn tại không đồng nghĩa task tự chạy lại. Cần biết cơ chế recovery nào đang được bật, thời điểm chạy và người chịu trách nhiệm theo dõi.

### 21.6. Xóa publication “cũ” mà không kiểm tra trạng thái

Purge publication chưa hoàn tất làm mất nguồn dữ liệu phục hồi. Chính sách retention phải phân biệt completed và incomplete, đồng thời xét rủi ro dữ liệu cá nhân trong payload.

### 21.7. Thay đổi schema/listener identity không kiểm tra backlog

Publication phiên bản trước có thể không deserialize được hoặc không gắn được consumer. Phải kiểm thử khả năng đọc dữ liệu cũ và có kế hoạch migration.

### 21.8. Dùng isolation level để thay cho durability

`SERIALIZABLE` bảo vệ cách transaction tương tác trong database, không tự ghi application event vào storage hoặc broker. Isolation, persistence và replay là ba vấn đề khác nhau.

### 21.9. Không có idempotency vì nghĩ retry chỉ chạy khi thất bại

Một consumer có thể đã thực hiện side effect thành công rồi crash trước completion. Retry trong tình huống này là **bản lặp sau thành công**, nên idempotency vẫn cần thiết.

## 22. Checklist độ tin cậy trước khi triển khai

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Event có mô tả sự thật nghiệp vụ đúng thời điểm? | `OrderPlaced` chỉ xuất hiện từ use case tạo đơn hợp lệ. |
| Publisher có thực sự chạy trong transaction? | Kiểm tra Spring proxy và boundary transaction bằng test. |
| Có khoảng trống commit trước publish? | Nếu cần durability, tránh dual-write không nguyên tử. |
| Listener có là Spring bean? | `@Component`/`@Bean` và component scan phù hợp. |
| Listener có chạy đúng phase? | Sau commit với side effect hậu nghiệp vụ. |
| Publication có lưu bền vững? | Backend Event Publication Registry/outbox được cấu hình và thử trên DB thật. |
| Business data và publication có cùng ranh giới commit? | Kiểm tra datasource, transaction manager và integration thực tế. |
| Có cơ chế recovery không? | Biết cách kích hoạt, cấu hình giới hạn và quan sát kết quả. |
| Có thể gặp event trùng? | Consumer có idempotency theo event và tác vụ. |
| Event có được đọc lại sau deploy? | Test schema/serializer tương thích với publication cũ. |
| Lỗi downstream có thể không rõ kết quả? | Có đối soát hoặc idempotency key phù hợp. |
| Có giữ publication đủ lâu? | Không xóa incomplete trước khi recovery. |
| Có theo dõi backlog? | Metric incomplete count/age và cảnh báo vận hành. |
| Có test crash/rollback/restart? | Dùng integration test với persistent storage thực tế. |

## 23. Bài tập thực hành: điều tra và phục hồi OrderPlaced bị thất lạc

### Bối cảnh

Một ứng dụng Spring Modulith có ba module:

- `orders` tạo đơn và phát `OrderPlaced(eventId, orderId, customerId, occurredAt)`.
- `notifications` gửi email xác nhận sau commit.
- `loyalty` cộng 20 điểm khi đơn đạt điều kiện.

Yêu cầu: **Đơn hàng đã commit không được âm thầm mất tác vụ thông báo/cộng điểm**, đồng thời phát lại cùng event không làm cộng điểm hoặc gửi tác dụng phụ trùng mà không kiểm soát.

### Các bước thực hiện

1. Định nghĩa event `OrderPlaced` là record bất biến và có `eventId` ổn định.
2. Trong `OrderService.placeOrder`, lưu order và gọi `ApplicationEventPublisher.publishEvent` trong transaction.
3. Đăng ký hai `@ApplicationModuleListener` tại notifications và loyalty.
4. Cấu hình Event Publication Registry với backend persistence phù hợp; xác minh trên database rằng publication được ghi và liên hệ đúng consumer.
5. Test rollback sau publish: order không commit, listener sau commit không tạo tác dụng phụ.
6. Cho notifications thất bại có chủ đích; loyalty vẫn hoàn tất, trong khi publication notifications còn chưa hoàn tất.
7. Dừng/khởi động lại ứng dụng kiểm thử khi có publication tồn; thực hiện recovery theo cơ chế đã cấu hình.
8. Xác nhận notifications nhận lại **cùng `eventId`**, có idempotency và trạng thái publication chuyển thành hoàn tất khi xử lý thành công.
9. Tạo tình huống loyalty đã ghi điểm nhưng chưa ghi completion; replay và chứng minh số điểm vẫn chỉ cộng một lần.
10. Kiểm tra tác động của việc đổi schema event hoặc tên listener giữa hai lần chạy, dùng fixture dữ liệu publication phiên bản trước.
11. Thêm metrics/log để theo dõi `eventId`, trạng thái từng listener và tuổi publication chưa hoàn tất.
12. Thử đối soát số order đã commit với các tác vụ bắt buộc được tạo/hoàn tất để phát hiện event không từng được publish.

### Câu hỏi tự kiểm tra

- Vì sao `publishEvent` gọi thành công không chứng minh rằng event được lưu bền vững?
- Điểm khác nhau giữa mất event, listener lỗi và replay gây duplicate là gì?
- Nếu tiến trình dừng **giữa business commit và publish**, registry có khôi phục được một event chưa từng được ghi không?
- Nếu email đã gửi nhưng ứng dụng dừng trước completion, cần làm gì trước khi retry?
- Vì sao phải kiểm tra publisher/registry dùng transaction và datasource tương thích?
- Nếu `@TransactionalEventListener` không nhận event, bước kiểm tra transaction có ý nghĩa gì?
- Một publication còn tồn nhưng không deserialize được sau deploy có được coi là “đã xử lý an toàn” không?

**Ghi nhớ:** Chống **mất event** trong Spring Modulith không chỉ là thêm listener sau commit. Cần thiết kế đầy đủ đường đi **nghiệp vụ → publish → commit → lưu publication → xử lý → completion → recovery**, xác định chính xác từng failure window và kiểm tra giới hạn của cấu hình thực tế. Event Publication Registry với persistence phù hợp giúp theo dõi công việc chưa hoàn tất; idempotency giúp phát lại an toàn; kiểm thử crash/restart và observability giúp phát hiện sự cố trước khi chúng trở thành mất mát nghiệp vụ âm thầm.

