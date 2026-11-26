# Định tuyến theo loại event

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application events giúp các module trao đổi thông tin qua những sự kiện mô tả điều đã xảy ra. Khi một ứng dụng có nhiều loại event và nhiều listener, hệ thống cần xác định listener nào nhận loại event nào, đồng thời xác định event nào được gửi ra hệ thống bên ngoài. Định tuyến theo loại event làm rõ trách nhiệm của từng listener và giữ cho luồng nghiệp vụ dễ mở rộng.

Định tuyến có thể diễn ra ở hai ranh giới. Bên trong ứng dụng, Spring phân phối event tới các listener có kiểu tham số phù hợp. Khi externalize, Spring Modulith và integration adapter chuyển event tới target hoặc destination đã cấu hình để broker phân phối cho consumer. Hai lớp này liên quan với nhau nhưng có cấu hình và mục tiêu khác nhau.

## 1. Định tuyến theo loại event là gì?

Định tuyến theo loại event là cách chọn nơi xử lý dựa trên kiểu hoặc ý nghĩa của event. Ví dụ, `OrderConfirmed` có thể được chuyển tới listener cập nhật tồn kho và listener tạo yêu cầu giao hàng; `PaymentCaptured` có thể được chuyển tới listener phát hành biên nhận và listener đối soát.

Trong Spring application events, listener khai báo kiểu event mà nó quan tâm. Spring tìm các listener có thể nhận kiểu đó và gọi chúng khi event được publish. Vì vậy, một event có thể được phân phối tới nhiều listener. Publisher chỉ công bố sự kiện; publisher không cần gọi trực tiếp từng listener.

| Loại event | Listener nội bộ | Ý nghĩa xử lý |
| --- | --- | --- |
| `OrderConfirmed` | Inventory listener | Cập nhật nhu cầu giữ hàng |
| `OrderConfirmed` | Fulfillment listener | Khởi tạo quy trình giao hàng |
| `PaymentCaptured` | Receipt listener | Tạo biên nhận thanh toán |
| `PaymentCaptured` | Accounting listener | Ghi nhận dữ liệu đối soát |

Định tuyến theo loại event không phải là chọn đúng một listener duy nhất. Nếu nhiều listener cùng khai báo nhận một kiểu event, tất cả các listener phù hợp đều có thể được gọi theo cơ chế event multicaster.

## 2. Định tuyến nội bộ bằng kiểu tham số listener

Ví dụ, module Orders publish event sau khi xác nhận đơn hàng:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID orderId,
        Instant occurredAt) {
}
~~~

Publisher công bố event qua `ApplicationEventPublisher`:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final ApplicationEventPublisher events;

    OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        // Thay đổi trạng thái đơn hàng trong transaction.
        events.publishEvent(new OrderConfirmed(orderId, Instant.now()));
    }
}
~~~

Listener nhận đúng loại event mà nó khai báo:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderConfirmed {

    @EventListener
    void reserveStock(OrderConfirmed event) {
        // Tạo hoặc cập nhật yêu cầu giữ hàng cho event.orderId().
    }
}

@Component
class FulfillmentOnOrderConfirmed {

    @EventListener
    void startFulfillment(OrderConfirmed event) {
        // Khởi tạo quy trình giao hàng cho event.orderId().
    }
}
~~~

Cả hai listener đều nhận `OrderConfirmed`, nhưng mỗi listener sở hữu một phản ứng nghiệp vụ riêng. Khi thêm listener mới, publisher không cần biết listener đó tồn tại. Điều này giúp giảm phụ thuộc giữa module phát event và module tiêu thụ event.

Spring cũng có thể phân phối event tới listener nhận một kiểu cha hoặc interface mà event triển khai. Nếu cần định tuyến thật rõ ràng, hãy thiết kế event type có ý nghĩa cụ thể và tránh dùng một listener nhận `Object` hoặc một supertype quá rộng rồi tự viết nhiều nhánh `if/else` cho từng loại event.

## 3. Chọn event type theo ý nghĩa nghiệp vụ

Mỗi event type nên mô tả một sự thật nghiệp vụ đã xảy ra, thường dùng tên ở thì quá khứ như `OrderConfirmed`, `PaymentCaptured` hoặc `ShipmentDispatched`. Tên event cần trả lời được điều gì đã xảy ra mà không gắn chặt vào một hành động kỹ thuật của listener.

Tránh tạo một event tổng quát như `BusinessEvent` với trường `type` chứa nhiều chuỗi khác nhau nếu các biến thể có payload và ý nghĩa khác nhau. Với thiết kế đó, listener thường phải tự kiểm tra discriminator và ép kiểu payload; lỗi sai tên hoặc sai cấu trúc chỉ xuất hiện lúc chạy.

Nếu các event có ý nghĩa và dữ liệu khác nhau, hãy dùng các kiểu riêng:

~~~java
public record OrderConfirmed(UUID orderId) { }

public record PaymentCaptured(UUID paymentId, UUID orderId) { }

public record ShipmentDispatched(UUID shipmentId, UUID orderId) { }
~~~

Nếu các event thật sự chia sẻ một hợp đồng chung, có thể dùng interface hoặc supertype để tạo listener dùng chung. Chỉ nên làm vậy khi listener xử lý cùng một ý nghĩa và không cần phân nhánh theo loại cụ thể.

## 4. Phân biệt định tuyến listener và định tuyến ra broker

Định tuyến nội bộ quyết định listener nào trong ứng dụng nhận application event. Định tuyến externalization quyết định event được gửi ra destination nào và consumer bên ngoài nào đăng ký destination đó.

| Lớp định tuyến | Cơ chế lựa chọn | Ví dụ |
| --- | --- | --- |
| Trong ứng dụng | Kiểu event và kiểu tham số listener | `OrderConfirmed` tới Inventory listener và Fulfillment listener |
| Externalization | Target được khai báo cho event và ánh xạ của integration adapter | Integration event của đơn hàng tới destination `orders` |
| Broker tới consumer | Topic, queue, subscription, routing key hoặc partition key tùy broker | Consumer kho subscribe destination đơn hàng |

Trong Spring Modulith, event cần externalize có thể được đánh dấu bằng `@Externalized`. Target trong annotation biểu thị đích logic của externalization; integration adapter và cấu hình môi trường ánh xạ target đó tới destination thực tế. Tên target không mặc nhiên là tên topic hoặc queue của mọi broker.

Ví dụ khai báo hai integration event có target riêng:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}

@Externalized("payments")
public record PaymentCapturedIntegrationEvent(
        UUID eventId,
        UUID paymentId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

Event `OrderConfirmedIntegrationEvent` được gửi theo target `orders`; event `PaymentCapturedIntegrationEvent` được gửi theo target `payments`. Cấu hình adapter của ứng dụng quyết định hai target này tương ứng với destination cụ thể nào.

Chỉ thêm `@Externalized` chưa đủ để gửi message. Ứng dụng cần có integration tương thích, cấu hình destination, kết nối broker, serialization và quyền publish phù hợp.

## 5. Chuyển application event thành integration event

Application event nội bộ thường phản ánh mô hình và nhu cầu của các module trong cùng ứng dụng. Integration event là hợp đồng công bố cho hệ thống khác, nên cần ổn định và độc lập hơn với implementation nội bộ.

Một cách tổ chức là tạo application event và integration event trong cùng use case nghiệp vụ. Cả hai được publish khi transaction vẫn đang mở; cơ chế externalization xử lý publication theo cấu hình transaction của Spring Modulith:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private final ApplicationEventPublisher events;
    private final OrderRepository orders;

    OrderApplicationService(
            ApplicationEventPublisher events,
            OrderRepository orders) {
        this.events = events;
        this.orders = orders;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.getRequired(orderId);
        order.confirm();
        Instant confirmedAt = Instant.now();

        events.publishEvent(new OrderConfirmed(orderId, confirmedAt));
        events.publishEvent(new OrderConfirmedIntegrationEvent(
                UUID.randomUUID(),
                orderId,
                confirmedAt));
    }
}
~~~

Ví dụ này minh họa ranh giới giữa event nội bộ và hợp đồng bên ngoài. Hai event được publish trong cùng transaction với thay đổi đơn hàng, vì vậy transaction rollback sẽ không để lại một publication thành công cho thay đổi chưa commit khi cơ chế persistence được cấu hình đúng. Trong ứng dụng thực tế, hãy chọn nguồn định danh và thời điểm phát sinh phù hợp với nghiệp vụ; `eventId` được tạo khi xây dựng integration event và phải được giữ nguyên qua các lần retry của chính publication đó.

Event Publication Registry hỗ trợ theo dõi publication tới listener và phục hồi publication chưa hoàn tất khi persistence được cấu hình phù hợp. Cần phân biệt thời điểm listener externalization hoàn tất với thời điểm consumer cuối cùng hoàn thành nghiệp vụ: đó là hai chặng giao nhận riêng biệt.

## 6. Định tuyến theo thuộc tính và routing key

Loại event thường xác định destination logic, còn thuộc tính của event có thể được dùng để chọn partition hoặc routing key. Ví dụ, mọi event liên quan tới cùng một đơn hàng có thể dùng `orderId` làm partition key để broker giữ chúng trong cùng partition. Việc này hỗ trợ thứ tự trong phạm vi key nếu broker và consumer được cấu hình tương ứng.

Không nên tạo destination mới cho từng entity hoặc từng người dùng nếu không có nhu cầu vận hành rõ ràng. Cách làm đó có thể tạo quá nhiều topic hoặc queue, khiến quản lý subscription, retention và quyền truy cập phức tạp.

Phân biệt ba quyết định:

- **Event type:** sự kiện thuộc hợp đồng nào, ví dụ `OrderConfirmed`.
- **Destination:** hệ thống nhận thông điệp từ kênh nào, ví dụ destination dành cho order events.
- **Routing/partition key:** thông điệp được định tuyến hoặc phân vùng theo khóa nào, ví dụ `orderId`.

Khả năng dùng routing key, partition key hay biểu thức target phụ thuộc vào broker và integration adapter. Hãy cấu hình theo cơ chế được adapter hỗ trợ; không giả định mọi integration xử lý target giống nhau.

## 7. Tránh định tuyến mơ hồ và xử lý trùng

Định tuyến rõ ràng cần một số quy ước:

- Một event type đại diện cho một sự thật nghiệp vụ cụ thể.
- Listener chỉ đăng ký kiểu event mà nó thực sự có trách nhiệm xử lý.
- Không để nhiều listener cùng thực hiện một side effect giống nhau nếu chưa có cơ chế phối hợp.
- Tách integration event khỏi object nội bộ khi hợp đồng bên ngoài cần ổn định.
- Đặt tên target và destination theo miền nghiệp vụ, có quy ước nhất quán giữa các module.

Một event có thể được giao nhiều lần do retry hoặc sự cố giữa lúc gửi và lúc ghi nhận hoàn tất. Listener và consumer cần idempotent. Có thể dùng `eventId` để lưu dấu event đã xử lý trong cùng transaction với thay đổi nghiệp vụ; khi nhận lại cùng ID, consumer không áp dụng side effect lần thứ hai.

Nếu thứ tự event quan trọng, hãy dùng khóa phân vùng ổn định và kiểm tra version hoặc sequence của aggregate ở consumer. Định tuyến đúng destination không tự bảo đảm thứ tự xử lý hay giao đúng một lần.

## 8. Kiểm thử định tuyến

Kiểm thử nên chứng minh rằng event tới đúng nhóm listener và không kích hoạt nhầm luồng:

1. Publish `OrderConfirmed` và xác minh các listener có trách nhiệm với đơn hàng được gọi.
2. Publish `PaymentCaptured` và xác minh listener chỉ dành cho thanh toán được gọi.
3. Xác minh một event có nhiều listener được xử lý bởi tất cả listener dự kiến.
4. Xác minh event type không liên quan không làm phát sinh side effect.
5. Kiểm tra application event được ánh xạ sang đúng integration event và target.
6. Kiểm tra retry, event trùng, lỗi broker và khả năng phục hồi publication.

Với externalization, kiểm thử adapter hoặc broker test environment để xác minh target được ánh xạ tới destination đúng, payload được serialize đúng và consumer nhận được hợp đồng mong đợi. Kiểm thử unit của listener không thay thế được kiểm thử cấu hình tích hợp.

## 9. Quan sát định tuyến trong vận hành

Khi một event không tới đúng nơi, cần lần theo được toàn bộ đường đi. Ghi nhận event type, event ID, target, destination, correlation ID và thời điểm publish/gửi/nhận ở những nơi phù hợp. Tránh ghi toàn bộ payload nếu nó chứa dữ liệu nhạy cảm.

Theo dõi số publication đang chờ, tuổi publication lâu nhất, lỗi theo listener hoặc target, số lần retry, độ trễ từ publish tới gửi và số thông điệp bị chuyển sang dead-letter. Nếu một target ngừng nhận message, các chỉ số này giúp xác định sự cố nằm ở publisher, publication tracking, adapter, broker hay consumer.

## Kết luận

Định tuyến theo loại event bắt đầu từ việc thiết kế event type rõ nghĩa và để listener khai báo đúng kiểu mà nó xử lý. Khi đưa event ra ngoài ứng dụng, hãy tách application event khỏi integration event, gán target phù hợp và cấu hình adapter ánh xạ target tới destination. Kết hợp định tuyến rõ ràng với routing key hợp lý, transaction, publication tracking, retry, idempotency và quan sát sẽ giúp giao sự kiện đáng tin cậy khi hệ thống phát triển.
