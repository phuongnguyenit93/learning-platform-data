# Event và state trong Spring Modulith

## 1. Mục tiêu bài học

Trong hệ thống chia thành các module nghiệp vụ, một thay đổi trạng thái thường kéo theo công việc ở các module khác: đơn hàng được thanh toán thì module giao hàng bắt đầu xử lý, module hóa đơn ghi nhận chứng từ, module thông báo gửi tin cho khách hàng. **Spring Modulith Application Events** cho phép module phát hành sự kiện về điều đã xảy ra mà không cần gọi trực tiếp từng module nhận.

Sau bài này, bạn có thể:

- Phân biệt **state** (trạng thái hiện tại) với **event** (sự kiện ghi nhận một sự thật đã xảy ra), cũng như với **command** (yêu cầu thực hiện hành động).
- Xác định thời điểm chuyển trạng thái, phát hành sự kiện và commit transaction.
- Hiểu vì sao mỗi module sở hữu trạng thái riêng; event chỉ truyền thông tin để module nhận tự quyết định cập nhật trạng thái của mình.
- Thiết kế sự kiện đủ thông tin, ổn định, có thể xử lý trùng lặp hoặc đến muộn.
- Chọn cơ chế listener và cách kiểm thử phù hợp với tính nhất quán của nghiệp vụ.

> Phạm vi: bài tập trung vào quan hệ giữa event và state trong ứng dụng modular monolith dùng Spring Modulith. Các kỹ thuật như event sourcing, message broker hay distributed saga được nhắc đến để phân biệt, không phải điều kiện bắt buộc để dùng application events.

## 2. Event và state là hai góc nhìn khác nhau

**State** trả lời câu hỏi: *Đối tượng hoặc module đang ở tình trạng nào?* Ví dụ, bản ghi đơn hàng có trường `status = PAID`, tổng tiền và thông tin thanh toán. Trạng thái có thể thay đổi nhiều lần theo vòng đời nghiệp vụ.

**Event** trả lời câu hỏi: *Điều gì đã xảy ra tại một thời điểm?* Ví dụ, `OrderPaid` ghi nhận một lần thanh toán đơn hàng được xác nhận. Một sự kiện đúng về mặt lịch sử vẫn đúng khi trạng thái hiện tại đã thay đổi.

**Command** trả lời câu hỏi: *Hệ thống được yêu cầu làm gì?* Ví dụ, `ConfirmOrderPayment` yêu cầu xác nhận thanh toán; yêu cầu có thể bị từ chối nếu không thỏa điều kiện nghiệp vụ. Chỉ khi thao tác thành công mới có cơ sở phát hành `OrderPaid`.

| Khái niệm | Bản chất | Ví dụ | Cách sử dụng |
| --- | --- | --- | --- |
| Command | Ý định thực hiện hành động; có thể thành công hoặc thất bại | `ConfirmOrderPayment(orderId, paymentRef)` | Đi vào use case hoặc application service |
| State | Dữ liệu mô tả tình trạng hiện tại, thuộc quyền sở hữu của một module | `Order.status = PAID` | Kiểm tra quy tắc, truy vấn và cập nhật trong transaction |
| Domain/application event | Sự thật nghiệp vụ đã xảy ra | `OrderPaid(eventId, orderId, occurredAt)` | Thông báo cho các phần khác tự xử lý hệ quả |
| State của module nhận | Trạng thái riêng được tạo hoặc cập nhật từ sự kiện | `FulfillmentRequest.status = OPEN` | Lưu trữ theo quy tắc của module nhận |

Không nên đặt tên event theo mệnh lệnh như `UpdateOrderStatus` hoặc `SendEmail` khi ý nghĩa thực tế là “đơn hàng đã được thanh toán”. Tên quá thiên về thao tác khiến publisher quyết định luôn cách consumer phải phản ứng và làm tăng sự phụ thuộc giữa module.

### Một lịch sử đơn hàng

Giả sử một đơn hàng được tạo, thanh toán và sau đó hoàn tiền:

| Thời điểm | State của Order sau thao tác | Event được ghi nhận khi thao tác thành công |
| --- | --- | --- |
| T1 | `CREATED` | `OrderCreated` |
| T2 | `PAID` | `OrderPaid` |
| T3 | `REFUNDED` | `OrderRefunded` |

Tại T3, truy vấn trạng thái hiện tại trả về `REFUNDED`. Sự kiện `OrderPaid` ở T2 không trở thành “sai”: nó mô tả một sự thật lịch sử. Vì vậy, listener xử lý muộn `OrderPaid` không được tự suy luận rằng đơn hàng *hiện vẫn* ở trạng thái `PAID`.

Một event có thể chứa dữ liệu tại **thời điểm phát sinh** (ví dụ số tiền đã thanh toán), nhưng dữ liệu đó không phải bản sao luôn đồng bộ của entity. Nếu consumer cần trạng thái hiện tại nhất, hãy truy vấn qua một API phù hợp hoặc dùng cơ chế phiên bản/kiểm tra nghiệp vụ, thay vì coi event cũ là ảnh chụp hiện tại.

## 3. Quyền sở hữu state nằm ở đâu?

Trong Spring Modulith, module nên giữ quyền sở hữu dữ liệu và quy tắc nghiệp vụ của mình.

Ví dụ:

- **Orders** sở hữu `Order` và các phép chuyển trạng thái của đơn hàng.
- **Fulfillment** sở hữu `FulfillmentRequest` và vòng đời xử lý giao hàng.
- **Notifications** sở hữu lịch sử hoặc trạng thái gửi thông báo.

Orders phát hành `OrderPaid` sau khi xác nhận thanh toán. Fulfillment nghe event và mở yêu cầu xử lý. Orders không cần import service nội bộ, repository hoặc entity của Fulfillment. Ngược lại, Fulfillment không nên sửa trực tiếp bảng `orders` để phản hồi một event.

~~~mermaid
flowchart LR
    O["Orders\nOrder: PAID"] -->|"OrderPaid"| E(("Application event"))
    E --> F["Fulfillment\nRequest: OPEN"]
    E --> N["Notifications\nMessage: PENDING"]
~~~

Mỗi mũi tên biểu diễn một thông báo nghiệp vụ, không phải thao tác chia sẻ mutable object giữa các module. Một consumer có thể không quan tâm event; một consumer khác có thể cần nhiều event để tiến hành cả quy trình.

**Quy tắc then chốt:** state thuộc về module sở hữu; event là hợp đồng mô tả điều đã xảy ra. Listener của module nhận phải áp dụng quy tắc của chính module đó trước khi cập nhật state.

## 4. State transition phải hợp lệ trước khi phát sự kiện

Xét một state machine đơn giản cho đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAID: xác nhận thanh toán
    CREATED --> CANCELLED: hủy trước thanh toán
    PAID --> FULFILLING: bắt đầu xử lý
    FULFILLING --> COMPLETED: hoàn tất
    PAID --> REFUNDED: hoàn tiền hợp lệ
~~~

Sơ đồ chỉ minh họa một tập quy tắc. Trong hệ thống thực, điều kiện hoàn tiền hoặc hủy có thể phức tạp hơn và phải được định nghĩa trong domain.

Một thao tác xác nhận thanh toán thường gồm:

1. Nạp aggregate `Order`; xác thực yêu cầu và điều kiện chuyển trạng thái.
2. Chuyển state theo quy tắc nghiệp vụ, ví dụ `CREATED -> PAID`.
3. Lưu thay đổi và phát hành sự kiện mô tả lần chuyển trạng thái thành công, trong cùng transaction nghiệp vụ.
4. Commit transaction; các transactional listener có thể bắt đầu xử lý sau commit.

Nếu đơn hàng bị từ chối thanh toán, không phát hành `OrderPaid`. Nếu một sự kiện được phát ra trước khi biết thao tác thành công, consumer có nguy cơ tin một sự thật chưa được xác nhận.

**Bất biến nghiệp vụ** như “không được xác nhận thanh toán hai lần” cần được bảo vệ tại module Orders, kể cả khi không có listener nào chạy. Event không thay thế domain validation, khóa đồng thời, unique constraint hoặc transaction.

## 5. Ví dụ Java: chuyển state rồi publish event

Giả sử ứng dụng có package module `com.example.shop.orders` và `com.example.shop.fulfillment`. Contract event được đặt trong API mà module nhận được phép phụ thuộc; repository và entity vẫn thuộc nội bộ Orders.

### 5.1. Định nghĩa event bất biến

~~~java
package com.example.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal amount
) {}
~~~

Ở đây:

- `eventId` định danh **một lần phát sinh sự kiện**; khi retry cùng sự kiện phải giữ nguyên ID để hỗ trợ deduplication.
- `orderId` định danh aggregate có thay đổi state.
- `occurredAt` là thời điểm sự kiện xảy ra theo publisher; không đủ để bảo đảm thứ tự xử lý giữa các luồng.
- `amount` là dữ liệu nghiệp vụ tại thời điểm xác nhận thanh toán, cần thiết nếu consumer sử dụng đúng giá trị đã xác nhận.

Java `record` giúp tạo một DTO bất biến ở cấp tham chiếu; hãy ưu tiên các field thuộc kiểu giá trị bất biến. Không gửi entity JPA, lazy proxy hoặc đối tượng chứa state có thể sửa vào event. Event contract nên hạn chế dữ liệu cá nhân, bí mật thanh toán và chi tiết nội bộ không cần thiết.

### 5.2. Application service cập nhật state

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
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
    public void confirmPayment(UUID orderId, String paymentReference) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isPaid()) {
            return; // Ví dụ đơn giản: callback lặp lại không tạo event mới.
        }

        order.markPaid(paymentReference); // Domain kiểm tra chuyển trạng thái.
        orders.save(order);

        events.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock),
                order.getTotal()
        ));
    }
}
~~~

Đoạn code giả định `Order`, `OrderRepository` và bean `Clock` đã được định nghĩa; mục đích là minh họa thứ tự thao tác. `order.markPaid(...)` phải kiểm tra các trạng thái không được phép và từ chối chuyển trạng thái sai. Trong JPA, entity managed có thể được lưu bằng dirty checking khi commit; lệnh `save` ở đây làm rõ ý định lưu.

**Lưu ý về tính đồng thời:** `if (order.isPaid())` không đủ ngăn hai transaction song song cùng xử lý thanh toán. Hệ thống thật cần một cơ chế phù hợp như optimistic locking với `@Version`, khóa bi quan hoặc unique constraint dựa trên mã giao dịch; chỉ phát event khi lần xác nhận đó thực sự được chấp nhận.

### 5.3. Listener cập nhật state thuộc module khác

~~~java
package com.example.shop.fulfillment;

import com.example.shop.orders.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidListener {

    private final FulfillmentService fulfillment;

    public OrderPaidListener(FulfillmentService fulfillment) {
        this.fulfillment = fulfillment;
    }

    @ApplicationModuleListener
    public void on(OrderPaid event) {
        fulfillment.openRequestIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

`FulfillmentService.openRequestIfAbsent(...)` là phương thức nghiệp vụ minh họa: kiểm tra yêu cầu giao hàng đã tồn tại, áp dụng quy tắc và tạo trạng thái riêng nếu cần. Ở cơ sở dữ liệu, nên bổ sung unique constraint theo khóa nghiệp vụ thích hợp, ví dụ mỗi order chỉ có một yêu cầu fulfillment cho quy trình đang xét. Dùng event ID trong bảng xử lý sự kiện giúp nhận biết một event bị giao lại.

Trong Spring Modulith, `@ApplicationModuleListener` là cách thuận tiện để khai báo transactional event listener chạy bất đồng bộ, với transaction xử lý riêng. Listener không điều khiển transaction đã commit của Orders; khi listener thất bại, trạng thái Orders vẫn đã được lưu.

Đặt event vào phần API công khai của module Orders theo cấu trúc module thực tế. Nếu event bị đặt trong package nội bộ không được công bố, module Fulfillment sẽ phụ thuộc sai ranh giới của Spring Modulith.

## 6. Publish trong transaction và consume sau commit

Điểm cần phân biệt là **thời điểm gọi `publishEvent(...)`** với **thời điểm một listener thực hiện công việc**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant O as Orders
    participant D as Orders DB
    participant P as Spring event publisher
    participant F as Fulfillment
    C->>O: confirmPayment(orderId)
    O->>D: Cập nhật Order = PAID (trong TX)
    O->>P: publishEvent(OrderPaid)
    Note over O,P: Lời gọi publish vẫn nằm trong TX của Orders
    O->>D: COMMIT
    P-->>F: Listener AFTER_COMMIT
    F->>F: Mở fulfillment request (TX riêng)
~~~

Trong Spring, các listener có cách xử lý khác nhau:

| Cách nghe event | Thời điểm / đặc điểm | Ý nghĩa đối với state |
| --- | --- | --- |
| `@EventListener` thông thường | Thường gọi đồng bộ ngay khi publish, ngay cả khi transaction publisher chưa commit | Có thể thấy dữ liệu chưa commit; side effect không tự rollback theo transaction publisher |
| `@TransactionalEventListener` mặc định | Phase mặc định là `AFTER_COMMIT`; listener được kích hoạt sau commit khi có transaction | Phù hợp khi consumer chỉ được phản ứng với thay đổi đã commit |
| `@ApplicationModuleListener` | Kết hợp cách nghe sau commit, bất đồng bộ và transaction xử lý riêng | Phù hợp cho giao tiếp giữa module có thể xử lý độc lập |

`@TransactionalEventListener` mặc định không được gọi nếu không có transaction phù hợp tại lúc phát event (trừ khi cấu hình `fallbackExecution`). Annotation này **không tự làm listener bất đồng bộ**; để bất đồng bộ có thể dùng `@Async` hoặc lựa chọn `@ApplicationModuleListener` của Spring Modulith. Với xử lý database sau commit, cần transaction mới phù hợp cho phần ghi của listener.

### Commit và rollback tác động thế nào?

- **Orders rollback trước commit:** state `PAID` không được xác nhận. Listener `AFTER_COMMIT` không xử lý `OrderPaid` như một lần thanh toán thành công.
- **Orders commit, Fulfillment thành công:** state Orders là `PAID`; trạng thái yêu cầu giao hàng được ghi trong transaction của Fulfillment.
- **Orders commit, Fulfillment lỗi:** state Orders vẫn `PAID`, còn Fulfillment có thể chưa mở được yêu cầu. Đây là **nhất quán cuối cùng (eventual consistency)** giữa hai module, đòi hỏi xử lý lỗi và retry có kiểm soát.
- **Listener nhận lặp:** việc cập nhật state phải idempotent; cùng một lần thanh toán không làm phát sinh nhiều yêu cầu giao hàng ngoài ý muốn.

Đừng xem một chuỗi callback listener là một transaction phân tán: việc publish và việc tiêu thụ sau commit có các vòng đời giao dịch khác nhau.

## 7. Event publication registry và độ tin cậy của state dẫn xuất

Một event listener chạy trong bộ nhớ có thể thất bại vì exception, tiến trình bị dừng hoặc ứng dụng restart. Khi đã commit Orders, không thể “rollback lại Order” chỉ vì Fulfillment không xử lý được event.

Spring Modulith có **Event Publication Registry** để theo dõi việc công bố sự kiện tới các transactional listener nếu đã cấu hình cơ chế lưu trữ publication thích hợp. Registry giúp ghi nhận publication chưa hoàn thành, đánh dấu hoàn thành khi listener xử lý thành công và hỗ trợ xử lý lại những publication còn dở theo cơ chế vận hành được cấu hình.

Điều này cải thiện khả năng hội tụ state giữa các module nhưng **không biến consumer thành exactly-once**. Một listener có thể đã commit thay đổi rồi xảy ra lỗi trước khi publication được đánh dấu hoàn thành; hệ thống có thể giao lại event đó. Hệ quả là:

1. Publisher có transaction đúng và cấu hình registry/persistence phù hợp với mục tiêu độ bền.
2. Consumer xử lý **idempotent** dựa trên `eventId` hoặc business key.
3. Hệ thống có cách quan sát publication chưa hoàn thành, lỗi và thời gian chờ, cùng quy trình retry/republication.
4. Các side effect ngoài DB (email, gọi API vận chuyển) có khóa idempotency hoặc cơ chế outbox/queue phù hợp; chỉ kiểm tra trạng thái trong bộ nhớ là chưa đủ.

Registry theo dõi event trong ứng dụng Spring Modulith; nó không mặc nhiên thay thế một message broker khi sự kiện phải vượt ra hệ thống khác. Cơ chế lưu trữ, retry và lịch chạy lại publication cần kiểm tra theo phiên bản Spring Modulith và cấu hình thực tế.

## 8. State của consumer có thể chậm hoặc khác thời điểm

Khi sử dụng listener sau commit, có một khoảng thời gian hợp lệ mà:

~~~text
Orders:      PAID
Fulfillment: chưa có request
Notifications: chưa gửi thông báo
~~~

Đó là đặc trưng của giao tiếp bất đồng bộ, không đồng nghĩa dữ liệu hỏng. Vì thế, API hoặc UI hiển thị tiến độ nên dùng các trạng thái diễn đạt đúng như `PAID`, `PREPARING_FULFILLMENT`, `FULFILLMENT_PENDING` thay vì giả định mọi module đã hoàn thành đồng thời.

Các câu hỏi cần trả lời khi thiết kế:

| Câu hỏi | Cách xử lý |
| --- | --- |
| Có bắt buộc trừ tồn kho trước khi xác nhận Order thành công? | Quy tắc này có thể cần một bước đồng bộ hoặc quy trình giữ chỗ rõ ràng trước commit; không giao hoàn toàn cho event bất đồng bộ nếu đó là invariant bắt buộc ngay lập tức. |
| Fulfillment bị trễ 30 giây có chấp nhận được? | Nếu có, eventual consistency và trạng thái chờ là một lựa chọn phù hợp. |
| Event `OrderPaid` tới sau `OrderRefunded` thì sao? | Module nhận cần quy tắc chuyển trạng thái, phiên bản/thứ tự theo aggregate hoặc kiểm tra trạng thái hiện tại; không đơn giản ghi đè theo lần nhận sau cùng. |
| Hai event giống nhau tới hai lần? | Dùng khóa duy nhất hoặc bản ghi event đã xử lý; đảm bảo cập nhật idempotent trong transaction consumer. |
| Một listener lỗi kéo dài? | Quan sát publication chưa hoàn thành, retry có giới hạn hoặc can thiệp vận hành theo mức độ nghiêm trọng. |

### Thứ tự sự kiện và phiên bản

`occurredAt` giúp truy vết, nhưng đồng hồ giữa các node không phải bảo đảm thứ tự tuyệt đối. Nếu consumer xây dựng read model phụ thuộc thứ tự, có thể thêm `aggregateVersion` do Orders quản lý:

~~~java
public record OrderStateChanged(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        String newState
) {}
~~~

Consumer có thể bỏ qua event có phiên bản cũ hơn phiên bản đã áp dụng, hoặc phát hiện lỗ hổng phiên bản và đồng bộ lại. Đây chỉ là một mẫu thiết kế; không cần dùng event tổng quát kiểu `OrderStateChanged` nếu các sự kiện cụ thể như `OrderPaid`, `OrderRefunded` diễn tả nghiệp vụ rõ hơn. Cơ chế versioning phải thống nhất với cách Orders cập nhật aggregate và bảo đảm tính duy nhất theo order.

Đặc biệt, event là *thông báo có thể xử lý muộn*. Nếu consumer chỉ cần biết “đã từng thanh toán”, event đủ để xử lý; nếu consumer phải quyết định “hiện đang đủ điều kiện giao hàng không”, cần thêm điều kiện nghiệp vụ và/hoặc truy vấn trạng thái phù hợp.

## 9. Thiết kế event contract bền vững

Một event hữu ích thể hiện **một sự thật nghiệp vụ ổn định**. Không biến nó thành một bản sao mọi trường của entity hoặc thành lệnh điều khiển toàn bộ các consumer.

**Nên có khi cần:**

- Tên quá khứ, diễn đạt kết quả thực tế: `OrderPaid`, `InvoiceIssued`, `StockReserved`.
- Định danh event và aggregate; timestamp có ý nghĩa; giá trị nghiệp vụ đã chốt để listener không phải đi đọc dữ liệu mutable.
- Kiểu dữ liệu rõ ràng, không phụ thuộc entity persistence của module phát.
- Quy ước thay đổi schema/version khi event contract được nhiều consumer dùng.
- Định nghĩa trường hợp lặp, lỗi và event đến muộn.

**Tránh:**

- Phát `OrderPaid` chỉ vì *đang bắt đầu* gọi cổng thanh toán; hãy phân biệt `PaymentRequested` với `PaymentConfirmed`/`OrderPaid`.
- Chuyển nguyên `Order` JPA qua event, khiến consumer phụ thuộc cấu trúc bảng, lazy loading và trạng thái đang thay đổi.
- Để consumer chỉnh sửa trực tiếp state của Orders hoặc trả event như kết quả bắt buộc nhằm hoàn thành transaction của Orders.
- Đặt tên theo hoạt động của consumer như `CreateShipmentNow` khi publisher chỉ biết “đơn hàng đã đủ điều kiện xử lý”; module nhận phải quyết định cách thực hiện.
- Cho rằng thứ tự nhận, exactly-once hoặc xử lý tức thời luôn được framework bảo đảm.

Event sourcing là một kiến trúc khác: lịch sử event có thể là nguồn dữ liệu chính để dựng lại state. Trong ứng dụng Spring Modulith thông thường, state vẫn có thể được lưu trong database qua JPA và event chỉ dùng để thông báo các thay đổi nghiệp vụ. **Dùng application events không đồng nghĩa phải dùng event sourcing.**

## 10. Kiểm thử event và state

Một bài kiểm thử tốt xác minh **cả sự thật được phát ra lẫn trạng thái cuối cùng**, kể cả kịch bản thất bại. Có thể dùng `@ApplicationModuleTest` và `Scenario` trong module test của Spring Modulith để kích hoạt một use case, chờ event hoặc điều kiện bất đồng bộ; với phần lưu trữ, cần kiểm tra trạng thái DB thực tế.

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Order ở `CREATED`, xác nhận thanh toán thành công | Orders thành `PAID`; có một `OrderPaid` với `orderId` và amount đúng; Fulfillment cuối cùng có request hợp lệ. |
| Payment bị từ chối / trạng thái chuyển không hợp lệ | Orders giữ state đúng; không có event `OrderPaid` thành công. |
| Transaction Orders rollback | Không commit state `PAID`; listener `AFTER_COMMIT` không thực hiện tác vụ như đã thanh toán. |
| Listener Fulfillment lỗi sau commit | Orders giữ `PAID`; publication thất bại được quan sát/xử lý theo cấu hình độ tin cậy. |
| Cùng `eventId` được xử lý lại | Không sinh thêm fulfillment request hoặc side effect ngoài ý muốn. |
| `OrderPaid` tới muộn sau trạng thái hoàn tiền | Consumer giữ quy tắc chuyển trạng thái; không đưa workflow trở về trạng thái sai. |

Để kiểm thử listener bất đồng bộ, tránh `Thread.sleep(...)` cố định. Chờ điều kiện cuối cùng với timeout hữu hạn và quan sát kết quả đã commit. Khi cần kiểm tra thứ tự transaction, bảo đảm test thực sự commit thao tác publisher: một test bọc toàn bộ logic trong transaction rồi tự rollback có thể khiến listener sau commit không bao giờ chạy.

### Bài thực hành

1. Cài use case `confirmPayment`, sự kiện `OrderPaid` và listener Fulfillment. Viết test xác minh state của Orders sau commit và state của Fulfillment sau khi listener xử lý.
2. Tạo tình huống listener ném exception một lần. Kiểm tra publication chưa hoàn thành bằng cơ chế được cấu hình; xử lý lại và xác nhận chỉ có một yêu cầu fulfillment.
3. Gửi lại cùng `OrderPaid` và kiểm tra idempotency. Sau đó thử event cũ khi Orders đã chuyển sang `REFUNDED` và xác định quy tắc cần thiết cho Fulfillment.
4. Giải thích vì sao một thao tác bắt buộc hoàn tất **trước khi trả kết quả thanh toán thành công** không nên chỉ phụ thuộc vào listener bất đồng bộ.

## 11. Những điểm cần ghi nhớ

- **State** là hiện trạng do module sở hữu; **event** là sự thật về một chuyển biến đã xảy ra; **command** là yêu cầu có thể bị từ chối.
- Chuyển state và phát hành event phải phản ánh cùng một kết quả nghiệp vụ; listener sau commit chỉ làm việc với thay đổi đã được xác nhận.
- Module nhận tự quản lý state và tính idempotent của mình. Sau commit, state giữa các module có thể lệch nhau tạm thời.
- Event có thể đến lặp hoặc đến muộn; registry và retry hỗ trợ độ tin cậy nhưng không loại bỏ nhu cầu kiểm tra state, thứ tự và business invariant.
- Application events giúp giảm phụ thuộc giữa các module Spring Modulith mà vẫn giữ ranh giới sở hữu dữ liệu rõ ràng.
