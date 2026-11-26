# Tên và ý nghĩa event trong Spring Modulith

## 1. Vì sao đặt tên event là một quyết định kiến trúc?

Trong hệ thống tổ chức theo **Spring Modulith Application Events**, module nghiệp vụ có thể thông báo cho các module khác về một điều vừa xảy ra bằng cách phát hành *application event*. Ví dụ, module quản lý đơn hàng phát `OrderConfirmed`; module thông báo nghe sự kiện đó để lên lịch gửi email, còn module tích điểm nghe cùng sự kiện để ghi nhận điều kiện tính thưởng.

Khi giao tiếp qua event, **tên event là một phần của hợp đồng nghiệp vụ**. Nó cho người phát và người nhận biết chính xác sự thật nào đã xảy ra. Nếu tên mơ hồ, các listener có thể hiểu khác nhau: một bên nghĩ đơn đã thanh toán, bên khác nghĩ đơn chỉ vừa được khách gửi yêu cầu. Hệ quả là các module cùng hoạt động về mặt kỹ thuật nhưng lại ra quyết định sai về nghiệp vụ.

Một tên tốt không chỉ “dễ đọc”; nó phải gắn với **điều kiện phát sinh xác định** và **ý nghĩa không thay đổi tùy consumer**. Người đọc tên `PaymentCaptured` phải hiểu rằng tiền đã được cổng thanh toán xác nhận thu, không phải chỉ mới có yêu cầu thanh toán.

Bài học này thuộc chương **Mô hình sự kiện**, tập trung vào việc đặt tên, định nghĩa ý nghĩa và bảo vệ contract của event trong module. Các ví dụ sử dụng Spring `ApplicationEventPublisher` và `@ApplicationModuleListener` để minh họa cách event trở thành ranh giới giao tiếp thực tế.

### Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

- Phân biệt tên event với tên command, operation, trạng thái và thông báo kỹ thuật.
- Viết tên event mô tả **một sự thật nghiệp vụ đã xảy ra**, xác định đúng thời điểm phát.
- Xây dựng “hợp đồng ngữ nghĩa” cho event: điều kiện trước/sau, dữ liệu tối thiểu, phạm vi và các giả định hợp lệ.
- Tránh các tên có thể gây hiểu sai như `OrderProcessed`, `PaymentSuccess` hoặc `UpdateStatusEvent`.
- Đặt tên sự kiện phù hợp ranh giới module Spring Modulith và kiểm thử rằng implementation thực sự giữ lời hứa từ tên đó.

## 2. Event là sự thật, không phải yêu cầu thực hiện công việc

Trong thiết kế hướng sự kiện, phải phân biệt ba khái niệm dễ bị trộn lẫn:

| Khái niệm | Câu hỏi trả lời | Ví dụ | Có thể thất bại? |
| --- | --- | --- | --- |
| **Command** | “Hãy thực hiện việc gì?” | `ConfirmOrder`, `CapturePayment` | Có; hệ thống có thể từ chối yêu cầu |
| **Event** | “Điều gì đã xảy ra?” | `OrderConfirmed`, `PaymentCaptured` | Bản thân sự thật đã xảy ra không bị “từ chối”; việc xử lý của listener có thể thất bại |
| **State** | “Hiện tại đang như thế nào?” | `Order.status = CONFIRMED` | State thay đổi theo thời gian |

Một command được xử lý thành công thường tạo ra thay đổi state và có thể phát hành event. Tuy nhiên, không phải mọi command đều phải sinh event và không phải mọi thay đổi nhỏ ở database đều cần một event riêng.

Ví dụ:

~~~text
Command: ConfirmOrder(orderId)
     |
     v
Kiểm tra điều kiện nghiệp vụ
     |
     +--> Không hợp lệ: từ chối, không phát OrderConfirmed
     |
     +--> Hợp lệ: Order chuyển sang CONFIRMED
                        |
                        v
                 Event: OrderConfirmed
~~~

`ConfirmOrder` là tên của hành động được yêu cầu; `OrderConfirmed` là kết quả đã thành công. Không nên đặt tên event là `ConfirmOrderEvent` nếu thông điệp chỉ được phát **sau khi** đơn hàng đã xác nhận, vì dạng mệnh lệnh khiến listener tưởng mình phải xác nhận đơn thay publisher.

**Ngoại lệ cần hiểu đúng:** `OrderConfirmationRequested` vẫn có thể là một event hợp lệ nếu yêu cầu xác nhận đơn thực sự đã được ghi nhận như một sự thật nghiệp vụ và các module cần biết về sự thật ấy. Nhưng nó **không** khẳng định đơn đã được xác nhận. Ý nghĩa được quyết định bởi thực tế đã xảy ra, không chỉ bởi hậu tố `Event`.

## 3. Cấu trúc tên event nên dùng

Đối với mã Java, quy ước dễ đọc là:

~~~text
<Thực thể/khái niệm nghiệp vụ><Sự kiện đã hoàn tất>
~~~

Ví dụ:

- `OrderPlaced` — khách hàng đã đặt một đơn hàng theo định nghĩa của hệ thống.
- `OrderConfirmed` — đơn hàng đã vượt qua điều kiện xác nhận và được chấp nhận.
- `PaymentAuthorized` — tổ chức thanh toán đã chấp thuận bước ủy quyền.
- `PaymentCaptured` — nghiệp vụ thu tiền đã được xác nhận hoàn tất.
- `InventoryReserved` — một lượng hàng đã được giữ cho yêu cầu cụ thể.
- `ShipmentDispatched` — lô hàng đã được bàn giao để vận chuyển.
- `InvoiceIssued` — hóa đơn đã được phát hành.
- `SubscriptionCancelled` — đăng ký đã được hủy theo quy tắc nghiệp vụ.

Trong Java, dùng **PascalCase** và tên miền nghiệp vụ; chẳng hạn một `record OrderConfirmed(...)`. Tên type có thể không cần hậu tố `Event` nếu nó đã rõ ràng trong package và API. Hậu tố đó không tự làm ý nghĩa chính xác hơn: `OrderProcessedEvent` vẫn mơ hồ dù có chữ `Event`.

Không cần cố biến mọi tên thành một động từ quá khứ theo cùng một mẫu ngữ pháp tiếng Anh. Điều quan trọng hơn là tên biểu thị sự thật đủ rõ. `OrderReadyForFulfillment` có thể hợp lý nếu “đã sẵn sàng để xử lý” là một mốc nghiệp vụ được xác định chính thức.

### Kiểm tra tên qua một câu định nghĩa

Để đánh giá một tên event, thử viết câu:

> “`OrderConfirmed` được phát **khi và chỉ khi** một đơn hàng được hệ thống xác nhận thành công theo chính sách xác nhận hiện hành.”

Nếu không thể hoàn thành câu với điều kiện kiểm chứng được, tên có thể quá chung hoặc nghiệp vụ chưa được làm rõ.

Tên event tốt phải có câu trả lời thống nhất cho ba câu hỏi:

1. **Ai sở hữu sự thật này?** Ví dụ, Orders sở hữu việc xác nhận đơn.
2. **Điều gì chính xác đã xảy ra?** Đơn được chấp nhận, hay chỉ mới gửi yêu cầu?
3. **Khi nào sự thật có hiệu lực?** Sau kiểm tra hợp lệ và chuyển trạng thái, hay sau callback thanh toán, hay sau commit?

Người nhận không được tự ý diễn giải một mốc sớm thành một mốc muộn hơn chỉ vì muốn bắt đầu công việc của mình.

## 4. Những tên phổ biến nhưng dễ gây hiểu sai

| Tên mơ hồ / dễ sai | Vấn đề | Tên tốt hơn khi biết rõ nghiệp vụ |
| --- | --- | --- |
| `OrderEvent` | Không biết loại sự thật gì xảy ra | `OrderPlaced`, `OrderCancelled` |
| `OrderUpdated` | Không biết điều gì thay đổi và ý nghĩa ra sao | `OrderAddressChanged`, `OrderConfirmed` |
| `ProcessOrder` | Dạng command; mục tiêu “process” không cụ thể | `OrderAcceptedForProcessing` hoặc tên mốc thực tế |
| `SendEmailEvent` | Mô tả công việc của consumer | `OrderConfirmed` để Notifications tự quyết định gửi |
| `PaymentSuccess` | “Success” có thể là authorize, capture hay settle | `PaymentAuthorized` / `PaymentCaptured` theo kết quả thật |
| `PaymentFailed` | Có thể đánh đồng bị từ chối với timeout chưa rõ kết quả | `PaymentDeclined` khi có bằng chứng bị từ chối; dùng tình trạng chưa xác định khi chưa biết kết quả |
| `StockChanged` | Chỉ mô tả dữ liệu, bỏ qua nguyên nhân nghiệp vụ | `InventoryReserved`, `InventoryReleased` nếu đúng phạm vi |
| `UpdateCustomerPoints` | Ra lệnh cho module Loyalty thay vì báo sự thật | `OrderCompleted`, `PaymentCaptured` tùy điều kiện thưởng |
| `EntitySaved` | Phản ánh thao tác persistence, không phải domain event | `InvoiceIssued`, `SubscriptionRenewed` |
| `CompletedEvent` | Thiếu chủ thể và loại hoàn tất | `ShipmentDelivered`, `RefundCompleted` |

Tên tốt phụ thuộc vào **định nghĩa nghiệp vụ thực tế**. Ví dụ, `OrderPlaced` và `OrderCreated` đều có thể hợp lệ nhưng không nhất thiết đồng nghĩa. Một giỏ hàng được tự động khởi tạo trong database có thể là “created”, trong khi “placed” chỉ xảy ra khi khách hàng thật sự bấm đặt hàng.

Tương tự, `PaymentCaptured` không mặc nhiên đồng nghĩa `PaymentSettled`: việc cổng thanh toán xác nhận capture và việc quyết toán/đối soát tiền có thể là hai giai đoạn khác nhau. Hãy dùng đúng thuật ngữ của hệ thống thanh toán được tích hợp.

### Phân biệt tên event với tác vụ mà listener thực hiện

Giả sử có ba module:

~~~mermaid
flowchart LR
    O["Orders\nOrderConfirmed"] --> E(("Event"))
    E --> F["Fulfillment\nPrepare fulfillment"]
    E --> N["Notifications\nSchedule email"]
    E --> L["Loyalty\nCalculate points"]
~~~

Orders chỉ cần nói “đơn hàng đã được xác nhận”. Việc gửi email, mở yêu cầu xử lý hoặc tính điểm là quyết định riêng của từng consumer. Nếu event mang tên `SendOrderConfirmationEmail`, publisher đã ngầm điều khiển một consumer và làm contract khó tái sử dụng cho Fulfillment hoặc Loyalty.

## 5. Tên phải xác định đúng mốc trong vòng đời nghiệp vụ

Các sự kiện liên tiếp thường mô tả **những mốc khác nhau**, không phải nhiều tên cho cùng một việc.

### Vòng đời đơn hàng

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PLACED: OrderPlaced
    PLACED --> CONFIRMED: OrderConfirmed
    PLACED --> REJECTED: OrderRejected
    CONFIRMED --> CANCELLED: OrderCancelled
    CONFIRMED --> COMPLETED: OrderCompleted
~~~

Đây là mô hình minh họa; một ứng dụng có thể định nghĩa các bước, trạng thái hoặc quy tắc chuyển khác. Điều cần giữ là **mỗi event phản ánh một lần chuyển có ý nghĩa**, không tùy tiện tái sử dụng tên cho nhiều loại chuyển trạng thái.

| Event | Ý nghĩa được hứa hẹn | Điều chưa thể kết luận |
| --- | --- | --- |
| `OrderPlaced` | Yêu cầu đặt đơn đã được hệ thống ghi nhận theo quy tắc đặt hàng | Đơn đã được thanh toán hoặc có hàng để giao |
| `OrderConfirmed` | Đơn đã vượt qua điều kiện xác nhận | Kho đã giữ hàng, trừ khi định nghĩa xác nhận bao hàm điều đó |
| `OrderRejected` | Yêu cầu đơn không được chấp nhận với lý do nghiệp vụ | Đã hoàn tiền, nếu có tiền giữ trước |
| `OrderCancelled` | Việc hủy đơn đã được ghi nhận thành công | Mọi side effect downstream đã hoàn tác |
| `OrderCompleted` | Đơn đạt trạng thái hoàn tất theo quy tắc của Orders | Khách đã đọc email hoặc mọi phân hệ đã đồng bộ |

Các cột “điều chưa thể kết luận” rất quan trọng: event truyền **sự thật được định nghĩa**, không truyền mọi hệ quả mong muốn.

### Vòng đời thanh toán

~~~text
PaymentInitiated
       |
       v
PaymentAuthorized
       |
       v
PaymentCaptured
       |
       v
PaymentSettled
~~~

Trong thực tế có nhánh từ chối, hết hạn, hủy ủy quyền, hoàn tiền và kết quả không xác định. Một timeout tới nhà cung cấp thanh toán **không đủ** để phát `PaymentFailed` nếu chưa xác minh rằng giao dịch thật sự thất bại. Nếu sử dụng `PaymentCaptureFailed`, cần nêu rõ tiêu chí nào đủ để kết luận việc capture đã thất bại.

Với nghiệp vụ “đơn đã thanh toán”, hãy định nghĩa chính xác trạng thái thanh toán tương ứng. Có hệ thống coi đơn “paid” sau `PaymentCaptured`; có hệ thống chỉ coi hoàn tất sau mốc khác. Event `OrderPaid` chỉ nên tồn tại khi điều kiện “paid” của Orders được đáp ứng và nhất quán.

## 6. Viết tài liệu ngữ nghĩa như một phần của event contract

Tên sự kiện là nhãn ngắn; **định nghĩa ngữ nghĩa** mới là hợp đồng đầy đủ. Một event dùng qua nhiều module nên có tài liệu thống nhất, chẳng hạn:

| Thuộc tính hợp đồng | Định nghĩa mẫu cho `OrderConfirmed` |
| --- | --- |
| **Publisher / owner** | Module Orders |
| **Sự thật được công bố** | Đơn đã được Orders xác nhận theo bộ quy tắc nghiệp vụ hiện hành |
| **Trigger** | Use case xác nhận đơn chuyển Order từ trạng thái có thể xác nhận sang `CONFIRMED` |
| **Thời điểm tạo** | Sau khi kiểm tra thành công và xác nhận thay đổi state trong transaction của Orders |
| **Tính hiệu lực** | Listener sau commit được xử lý khi transaction xác nhận đã commit thành công |
| **Payload tối thiểu** | `eventId`, `orderId`, `occurredAt` |
| **Dữ liệu không khẳng định** | Đơn đã giao, email đã gửi hoặc điểm thưởng đã cộng |
| **Quy tắc lặp** | Không phát event mới nếu lời gọi lặp không tạo thay đổi nghiệp vụ; consumer vẫn phải chịu được redelivery |
| **Consumer điển hình** | Fulfillment, Notifications, Loyalty |
| **Bảo mật / quyền riêng tư** | Chỉ công bố dữ liệu cần cho contract, không gửi toàn bộ entity hoặc thông tin nhạy cảm |

### Một định nghĩa không đủ chặt

> “`OrderConfirmed`: được phát khi người dùng đặt đơn để các bộ phận khác tiếp tục xử lý.”

Câu này lẫn lộn “đặt đơn” với “xác nhận đơn”. Nếu người dùng đặt đơn nhưng phải chờ kiểm tra tồn kho, listener có thể phản ứng quá sớm.

### Định nghĩa có thể kiểm chứng

> “`OrderConfirmed` được phát cho lần chuyển thành công đầu tiên của Order sang `CONFIRMED` trong một transaction nghiệp vụ. Khi transaction commit, event thông báo rằng Orders đã chấp nhận đơn; nó không xác nhận việc giao hàng hoặc gửi thông báo đã hoàn tất.”

Định nghĩa này giúp reviewer viết test, giúp consumer biết điều được phép giả định và giúp đội phát triển nhận ra khi một thay đổi nghiệp vụ có thể làm vỡ contract.

## 7. Tên event và dữ liệu payload phải nói cùng một câu chuyện

Xét event:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Các trường có nghĩa khác nhau:

- `eventId`: định danh **lần phát sinh sự kiện**; hữu ích cho truy vết và xử lý lặp.
- `orderId`: định danh Order liên quan, có thể có nhiều event trong cả vòng đời.
- `occurredAt`: thời điểm publisher ghi nhận sự kiện đã xảy ra; không tự chứng minh thứ tự xử lý giữa các listener.

Nếu Fulfillment cần giá trị tổng tiền **đã chốt tại thời điểm xác nhận**, event có thể thêm `confirmedTotal`. Tên field nên bộc lộ ý nghĩa thời gian:

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal confirmedTotal
) {}
~~~

`confirmedTotal` là snapshot giá trị tại mốc xác nhận, không phải trường tổng tiền luôn cập nhật theo database. Nếu Order được sửa sau đó, event lịch sử không bị “sai” vì tổng tiền hiện tại thay đổi.

Không chuyển nguyên entity JPA `Order` làm payload. Entity có thể chứa quan hệ lazy, mutable state và các thuộc tính chỉ dành cho nội bộ Orders. Việc phát entity cũng tạo phụ thuộc chặt giữa consumer và persistence model của publisher.

### Phân biệt event type, event instance và aggregate

Giả sử Order A có hai sự kiện:

~~~text
OrderConfirmed(eventId = E1, orderId = A, occurredAt = T1)
OrderCancelled(eventId = E2, orderId = A, occurredAt = T2)
~~~

`OrderConfirmed` và `OrderCancelled` là **hai loại event**; E1 và E2 là **hai lần phát sinh**; A là **một aggregate**. Khi retry để giao lại E1 cho một listener, vẫn phải giữ E1. Nếu một chuyển trạng thái mới của A xảy ra sau đó, cần event ID mới.

`occurredAt` dùng để quan sát thời gian nghiệp vụ, không phải bảo đảm thứ tự tuyệt đối. Nếu consumer cần sắp xếp các event của cùng aggregate, có thể bổ sung `aggregateVersion` với quy tắc tăng nhất quán từ publisher, hoặc dùng cơ chế đồng bộ state phù hợp.

## 8. Tên nằm trong API module và trở thành phụ thuộc lâu dài

Một event được consumer bên ngoài module sử dụng cần nằm trong phần API mà Spring Modulith cho phép phụ thuộc. Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderConfirmed.java         <- public contract
│   └── internal
│       ├── Order.java
│       ├── OrderRepository.java
│       └── OrderConfirmationService.java
└── notifications
    └── internal
        └── OrderConfirmedListener.java
~~~

Với cách phân module mặc định, type trong package gốc `orders` thường thuộc API của module; package con `internal` là phần implementation không nên bị module khác import. Nếu tổ chức hợp đồng trong `orders.events`, có thể công bố package đó qua `@NamedInterface` của Spring Modulith để consumer dùng hợp lệ.

Tại ranh giới module:

- Publisher sở hữu việc **định nghĩa** event và bảo đảm chỉ phát khi sự thật đúng.
- Consumer phụ thuộc vào **tên + ngữ nghĩa + schema** của contract, chứ không nên phụ thuộc entity hoặc repository của module phát.
- Tên của event không gắn với một consumer cụ thể: một `OrderConfirmed` có thể phục vụ Notifications, Loyalty hoặc Reporting mà không cần đổi contract.

Một tên tốt giúp module mở rộng độc lập. Ngược lại, tên mơ hồ khiến mỗi consumer tự định nghĩa nghĩa riêng, biến event công khai thành nguồn phụ thuộc ngầm khó kiểm soát.

## 9. Ví dụ Spring Modulith: phát event đúng khi sự thật xảy ra

Ví dụ dưới đây giả định `Order`, `OrderRepository` và bean `Clock` đã được định nghĩa. Nó minh họa event được tạo khi use case xác nhận đơn thành công:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher eventPublisher;
    private final Clock clock;

    public OrderConfirmationService(
            OrderRepository orders,
            ApplicationEventPublisher eventPublisher,
            Clock clock
    ) {
        this.orders = orders;
        this.eventPublisher = eventPublisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return; // Lần gọi lặp không tạo một lần xác nhận mới.
        }

        order.confirm(); // Domain kiểm tra điều kiện và chuyển state.
        orders.save(order);

        eventPublisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock)
        ));
    }
}
~~~

Ở đây, `order.confirm()` có trách nhiệm từ chối trạng thái không được phép chuyển. Nếu nghiệp vụ chưa thực sự xác nhận thành công, không được phát `OrderConfirmed`.

**Lưu ý transaction:** `publishEvent(...)` được gọi khi transaction còn mở. Với `@EventListener` thông thường, listener có thể chạy ngay trong luồng publisher, trước commit. Với transactional listener chạy ở phase `AFTER_COMMIT`, việc xử lý chỉ bắt đầu sau khi transaction commit thành công. Nếu transaction rollback, listener `AFTER_COMMIT` không nhận lời xác nhận thành công.

Điều này liên quan trực tiếp đến **ngữ nghĩa tên event**: một publisher có thể tạo event sau khi chuyển state trong transaction nhưng consumer xử lý hậu quả nên dựa vào commit đã thành công khi nghiệp vụ yêu cầu sự thật bền vững.

### Consumer sử dụng đúng ý nghĩa

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {

    private final NotificationService notifications;

    OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.scheduleConfirmationIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

`@ApplicationModuleListener` là annotation tiện ích của Spring Modulith cho listener xử lý bất đồng bộ sau commit trong transaction riêng. `NotificationService.scheduleConfirmationIfAbsent(...)` là thao tác minh họa cần triển khai bên trong Notifications.

Listener này không “xác nhận đơn”; nó chỉ phản ứng với **đơn đã xác nhận**. Nếu Notifications lỗi, sự thật “Orders đã xác nhận” vẫn đúng. Module Notifications có thể retry theo cơ chế thích hợp.

Đồng thời, không thể khẳng định `OrderConfirmed` đồng nghĩa “email đã gửi”. Nếu muốn một module khác biết email đã gửi thành công, Notifications có thể phát một sự kiện khác với ý nghĩa rõ, ví dụ `OrderConfirmationEmailSent`, sau khi việc gửi được xác nhận theo chính sách của nó.

## 10. Ý nghĩa của event khi xảy ra lỗi, retry và xử lý muộn

Tên event mô tả **sự thật nghiệp vụ**, trong khi trạng thái “đã gửi tới listener”, “listener hoàn thành” hoặc “đang retry” mô tả **vòng đời truyền/tiêu thụ sự kiện**. Hai lớp này không được nhập làm một.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders
    participant DB as Database
    participant P as Publication registry
    participant N as Notifications
    O->>DB: Order -> CONFIRMED (transaction)
    O->>P: publish OrderConfirmed
    O->>DB: COMMIT
    P-->>N: Deliver OrderConfirmed
    N--xP: Lỗi tạm thời khi xử lý
    Note over P: Publication có thể chưa hoàn thành
    P-->>N: Redeliver event cùng eventId
    N->>N: Xử lý idempotent
    N-->>P: Hoàn thành
~~~

Sơ đồ mô tả một luồng khi đã cấu hình cơ chế lưu trữ publication và khôi phục phù hợp. **Event Publication Registry** của Spring Modulith hỗ trợ theo dõi publication tới transactional listener và khôi phục việc giao chưa hoàn thành. Nó không mặc định biến mọi listener thành exactly-once hay tự tạo lịch retry vô hạn.

Từ góc nhìn hợp đồng tên gọi:

- `OrderConfirmed` **không mất ý nghĩa** khi listener gặp lỗi. Orders đã commit xác nhận, còn việc notification là trách nhiệm khác.
- Khi redelivery, consumer thấy **cùng eventId** và không được nhân đôi side effect.
- Nếu sau đó `OrderCancelled` xảy ra, việc nhận muộn `OrderConfirmed` không cho phép consumer suy ra rằng đơn *hiện vẫn* được xác nhận.
- Event có thể đến không theo thứ tự khi xử lý bất đồng bộ. Nếu thứ tự ảnh hưởng quyết định, consumer cần version, state-machine guard hoặc truy vấn thông tin hiện tại từ API công khai thích hợp.

### Sự thật lịch sử khác trạng thái hiện tại

Giả sử:

~~~text
T1: OrderConfirmed(orderId = A)
T2: OrderCancelled(orderId = A)
T3: Notifications nhận lại OrderConfirmed từ T1
~~~

Tại T3, câu “A từng được xác nhận” vẫn đúng. Nhưng nếu chính sách là không gửi email xác nhận sau khi đơn đã hủy, Notifications phải có thông tin và quy tắc để không gửi một thông báo đã lỗi thời. Chỉ dựa vào tên `OrderConfirmed` mà suy ra trạng thái hiện tại là sai.

## 11. Phân biệt domain event, integration event và technical event

Một ứng dụng có thể ghi nhận nhiều loại sự kiện. Việc phân biệt giúp đặt tên và xác định trách nhiệm:

| Loại sự kiện | Ví dụ | Mục đích | Lưu ý về contract |
| --- | --- | --- | --- |
| **Domain event** | `OrderConfirmed` | Diễn đạt sự thật quan trọng trong miền nghiệp vụ | Gắn với domain model và quy tắc nghiệp vụ |
| **Application event nội bộ** | `OrderConfirmed` được publish trong Spring context | Truyền thông tin giữa phần của ứng dụng/module | Cơ chế truyền thông không quyết định nghĩa nghiệp vụ |
| **Integration event** | `OrderConfirmed` được externalize sang hệ thống khác | Công bố sự thật cho consumer ngoài tiến trình | Cần xem xét versioning, serialization, độ bền và quyền truy cập |
| **Technical/infrastructure event** | `DatabaseConnectionLost` | Theo dõi tình trạng hạ tầng hoặc vận hành | Không nên đánh đồng với sự thật nghiệp vụ |

Một sự kiện có thể vừa là domain event vừa được phân phối qua Spring application events. Nếu đưa ra ngoài ứng dụng, có thể cần hợp đồng integration độc lập với schema version, cơ chế externalization hoặc mapping riêng.

`OrderConfirmed` không nên đổi thành `KafkaOrderConfirmedEvent` chỉ vì thay công nghệ vận chuyển. **Tên miền nghiệp vụ không phụ thuộc vào transport**. Công nghệ như Kafka, RabbitMQ hoặc HTTP webhook là chi tiết của lớp tích hợp; contract có thể có các yêu cầu vận hành khác nhưng vẫn phải giữ nghĩa của sự thật công bố.

Spring Modulith cho phép giao tiếp event nội bộ và hỗ trợ cơ chế theo dõi publication. Việc sử dụng `ApplicationEventPublisher` tự thân không có nghĩa đã gửi một thông điệp ra message broker ngoài tiến trình.

## 12. Đổi tên và tiến hóa event mà không phá vỡ ý nghĩa

Sau khi có consumer, event contract trở thành API. Việc đổi tên hoặc đổi nghĩa có thể tác động tới mã nguồn, dữ liệu publication đang chờ và cả hệ thống tích hợp bên ngoài.

### Khi nào nên giữ tên cũ?

Ví dụ, `OrderConfirmed` ban đầu luôn có `eventId`, `orderId` và `occurredAt`. Thêm một field tùy chọn như `confirmationChannel` có thể là thay đổi schema chấp nhận được **nếu** các consumer và cơ chế serialization đang dùng vẫn tương thích. Cần đánh giá cụ thể, vì thêm một tham số vào Java `record` cũng làm thay đổi constructor và có thể yêu cầu sửa mã sử dụng.

### Khi nào cần tạo event mới?

Nếu trước đây `OrderConfirmed` có nghĩa “khách vừa gửi đơn”, còn sau thay đổi hệ thống nó có nghĩa “đơn đã được xét duyệt”, đó là **thay đổi ý nghĩa**, không đơn thuần thêm field. Không nên giữ nguyên tên trong khi âm thầm thay điều kiện phát.

Lựa chọn phù hợp có thể là:

- Định nghĩa `OrderPlaced` cho mốc khách gửi đơn.
- Chỉ phát `OrderConfirmed` khi bước xét duyệt thực sự thành công.
- Cập nhật consumer, dữ liệu và tài liệu theo kế hoạch tương thích, xử lý các publication cũ còn chờ.

Việc đổi tên type chỉ là một phần của migration; phải tính đến các event đã lưu, listener nhận dữ liệu cũ và quy tắc nghiệp vụ gắn với phiên bản trước đó.

### Không dùng event quá tổng quát để né thay đổi

Một event như:

~~~java
public record OrderStatusChanged(
        UUID orderId,
        String oldStatus,
        String newStatus
) {}
~~~

có thể hữu ích để xây audit/read model tổng quát, nhưng là contract kém diễn đạt nếu consumer cần biết sự thật “đơn đã được chấp nhận” hay “đơn đã hoàn tiền”. Nó yêu cầu consumer phân tích string trạng thái và tự suy luận ý nghĩa. Với những biến cố quan trọng, event cụ thể như `OrderConfirmed` hoặc `OrderRefunded` thường rõ ràng và ổn định hơn.

Không phải **mọi** thay đổi state đều là domain event; việc thay một cột để tối ưu kỹ thuật có thể không đáng công bố ra ranh giới module.

## 13. Kiểm thử để bảo vệ đúng lời hứa của tên event

Kiểm thử không chỉ nên xác nhận “có publish một object kiểu `OrderConfirmed`”, mà phải chứng minh **điều kiện phát đúng với ngữ nghĩa đã công bố**.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Đơn ở trạng thái cho phép xác nhận; quy tắc hợp lệ | Đơn chuyển sang `CONFIRMED` và phát `OrderConfirmed` với dữ liệu đúng |
| Quy tắc nghiệp vụ từ chối xác nhận | Không phát `OrderConfirmed` như một kết quả thành công |
| Gọi xác nhận lặp nhưng không có chuyển trạng thái mới | Không phát thêm một event đại diện cho một lần xác nhận mới |
| Transaction Orders rollback | Không có thay đổi state được commit; listener `AFTER_COMMIT` không xử lý |
| `@ApplicationModuleListener` xử lý lỗi một lần | Đơn vẫn được xác nhận; có thể theo dõi và khôi phục publication theo cấu hình |
| Giao lại cùng `eventId` | Không tạo side effect trùng ở consumer |
| `OrderCancelled` xảy ra sau `OrderConfirmed` | Consumer nhận event cũ không tự ghi đè state bằng dữ liệu lỗi thời |
| Thay đổi event contract | Kiểm tra compatibility của consumer và các payload đang lưu chờ xử lý |

### Kiểm thử ranh giới module

Spring Modulith cung cấp API kiểm tra dependency giữa các module. Một ví dụ:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là kiểm tra kiến trúc để phát hiện những vi phạm ranh giới module được công cụ hỗ trợ. Nó không chứng minh event mang ý nghĩa nghiệp vụ đúng; cần thêm test use case và listener. Có thể sử dụng `@ApplicationModuleTest` và các tiện ích kiểm thử event của Spring Modulith theo phiên bản project đang chạy.

**Lưu ý test sau commit:** nếu test được bọc transaction tự rollback, một listener `AFTER_COMMIT` có thể không bao giờ chạy. Hãy chủ động thiết kế test có commit và chờ kết quả bất đồng bộ bằng điều kiện cùng timeout hữu hạn thay vì `Thread.sleep(...)` cố định.

## 14. Bài tập thực hành đặt tên

### Bài tập 1: Đọc một yêu cầu nghiệp vụ

Hệ thống đặt vé có các bước:

1. Khách bấm “Giữ chỗ”.
2. Hệ thống xác nhận đã giữ ghế thành công.
3. Khách thanh toán qua cổng.
4. Vé điện tử được phát hành.
5. Email vé được gửi thành công.

Hãy đề xuất tên event cho **các sự thật đã xảy ra**, chẳng hạn `SeatReserved`, `PaymentCaptured`, `TicketIssued`, `TicketEmailSent`. Với mỗi tên, hãy viết điều kiện phát hành và chỉ ra các điều **không được suy ra**. Đừng đánh đồng “khách bấm giữ chỗ” với “ghế đã được giữ thành công”.

### Bài tập 2: Phê bình tên cũ

Một codebase có các event:

~~~text
OrderProcessEvent
UpdatePointsEvent
PaymentDoneEvent
CustomerChangedEvent
~~~

Hãy trả lời:

- Event nào đang mang hình thức command?
- Event nào thiếu mốc nghiệp vụ rõ ràng?
- Điều kiện nào cần làm rõ với chủ sở hữu domain trước khi đổi tên?
- Nếu đổi thành các event cụ thể, listener nào có thể không còn dùng chung contract nữa?

### Bài tập 3: Viết contract đầy đủ

Với `RefundCompleted`, hãy định nghĩa publisher, trigger, điều kiện có hiệu lực, `refundId`/`orderId`, giá trị tiền đã hoàn, thời điểm phát sinh và xử lý event lặp. Cân nhắc liệu “refund request được chấp thuận” và “tiền hoàn đã hoàn tất” có phải cùng một mốc hay không.

### Bài tập 4: Xác minh bằng test

Viết hai test nghiệp vụ: một test cho trường hợp xác nhận đơn thành công và một test cho trường hợp xác nhận bị từ chối. Test phải kiểm tra cả state lẫn việc có/không có event tương ứng; sau đó thêm test listener idempotent khi nhận lại cùng event ID.

## 15. Checklist rà soát trước khi công bố event

Trước khi public event contract cho module khác, hãy tự rà soát:

- [ ] Tên mô tả **sự thật đã xảy ra**, không phải mệnh lệnh cho consumer?
- [ ] Chủ thể và mốc nghiệp vụ đã rõ đến mức có thể viết một câu “được phát khi và chỉ khi…”?
- [ ] Thuật ngữ khớp với ubiquitous language, không lẫn “đặt”, “xác nhận”, “thanh toán”, “hoàn thành”?
- [ ] Publisher là module sở hữu sự thật và kiểm soát điều kiện phát?
- [ ] Event không khẳng định nhiều hơn kết quả nghiệp vụ đã được xác nhận?
- [ ] Payload nhỏ, bất biến theo nghĩa contract; định danh/timestamp và dữ liệu snapshot được mô tả chính xác?
- [ ] Consumer không cần import entity hoặc repository nội bộ publisher?
- [ ] Đã nêu trường hợp rollback, duplicate, xử lý muộn và dữ liệu lỗi thời?
- [ ] Thay đổi schema hoặc ý nghĩa được quản lý như thay đổi API?
- [ ] Có test chứng minh publisher chỉ phát event khi điều kiện ngữ nghĩa thỏa mãn?

## 16. Ghi nhớ

**Tên event là lời cam kết về một sự thật nghiệp vụ.** `OrderConfirmed` phải có cùng nghĩa dù người nhận là Fulfillment, Notifications hay Loyalty. Việc event được phát, giao tới listener, retry và xử lý thành công là các giai đoạn kỹ thuật khác nhau, không làm thay đổi nghĩa của sự thật đã được xác nhận.

Trong Spring Modulith, thiết kế tên event rõ ràng cùng contract công khai giúp các module giao tiếp qua application events mà giảm phụ thuộc. Muốn giao sự kiện đáng tin cậy, cần đi cùng transaction sau commit, event publication registry khi phù hợp, retry có kiểm soát, consumer idempotent và kiểm thử điều kiện phát. Những cơ chế này hỗ trợ thực thi đúng ý nghĩa event; chúng không thay thế việc định nghĩa chính xác ý nghĩa đó ngay từ đầu.
