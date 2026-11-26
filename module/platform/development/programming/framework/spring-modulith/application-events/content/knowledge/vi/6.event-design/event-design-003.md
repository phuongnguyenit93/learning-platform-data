# Event giàu dữ liệu trong thiết kế Spring Modulith Application Events

## 1. Event giàu dữ liệu là gì?

Trong kiến trúc module của Spring Modulith, một module có thể thông báo sự kiện nghiệp vụ cho các module khác qua **Spring application events**. Ví dụ, module Đơn hàng công bố `OrderPlaced`, còn module Thông báo, Điểm thưởng và Báo cáo tự quyết định cách phản ứng.

Một **event giàu dữ liệu (rich event)** chứa không chỉ định danh đối tượng nghiệp vụ mà còn mang **một tập dữ liệu có ý nghĩa tại thời điểm sự kiện xảy ra**, đủ để những consumer dự kiến thực hiện phần lớn công việc của mình mà không phải gọi ngược về module phát hành.

Hai dạng event cho cùng một sự thật:

~~~java
// Event mỏng: cho biết đơn hàng nào đã được tạo.
public record OrderPlaced(UUID orderId) {}

// Event giàu dữ liệu: kèm ảnh chụp thông tin cần thiết.
public record OrderPlacedDetails(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        String currency,
        BigDecimal total,
        List<OrderItemSnapshot> items
) {}
~~~

Cả hai đều có thể là **application event** nếu được phát qua `ApplicationEventPublisher`. Điểm khác biệt nằm ở **thiết kế hợp đồng dữ liệu**: event mỏng buộc listener truy vấn thêm khi cần nhiều chi tiết; event giàu dữ liệu đẩy một phần thông tin đã xác định sang consumer ngay trong thông điệp sự kiện.

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, bài này tập trung vào quyết định **nên mang những dữ liệu nào trong event** để bảo vệ ranh giới nghiệp vụ, hạn chế coupling, phục vụ xử lý sau commit và duy trì khả năng retry, kiểm thử, quan sát giao sự kiện.

> “Giàu dữ liệu” không đồng nghĩa với “chứa toàn bộ entity”. Event tốt cung cấp **đủ thông tin cần thiết, có chủ đích và ổn định** cho một sự thật nghiệp vụ.

## 2. Ví dụ: module thông báo cần thông tin gì?

Giả sử khách hàng đặt hàng gồm hai sản phẩm. Sau khi đơn được tạo thành công:

- `notifications` gửi email xác nhận có tên sản phẩm, số lượng và tổng tiền.
- `loyalty` tính điểm dựa trên số tiền đủ điều kiện.
- `reporting` cập nhật thống kê doanh thu theo thời điểm đặt hàng.

Nếu event chỉ có `orderId`, mỗi listener có thể phải gọi API tra cứu đơn hàng của `orders`.

~~~mermaid
flowchart LR
    O["orders<br/>OrderPlaced(orderId)"] --> E(("Event"))
    E --> N["notifications"]
    E --> L["loyalty"]
    E --> R["reporting"]
    N -. "getOrder(orderId)" .-> O
    L -. "getOrder(orderId)" .-> O
    R -. "getOrder(orderId)" .-> O
~~~

Những lời gọi tra cứu này không nhất thiết sai, nhưng tạo ra một số hệ quả: consumer phụ thuộc vào thời gian phản hồi của API tra cứu, phải xử lý tình huống API tạm lỗi và có thể đọc **trạng thái đơn hàng tại thời điểm xử lý**, khác với trạng thái lúc event xảy ra.

Nếu event chứa ảnh chụp các dữ liệu phù hợp, listener có thể hoạt động độc lập hơn:

~~~mermaid
flowchart LR
    O["orders<br/>OrderPlaced với snapshot"] --> E(("Event"))
    E --> N["notifications<br/>Tạo nội dung email"]
    E --> L["loyalty<br/>Tính điểm"]
    E --> R["reporting<br/>Ghi nhận số liệu"]
~~~

Mục tiêu không phải xóa bỏ mọi lời gọi giữa module. Mục tiêu là **truyền đúng dữ kiện của sự kiện để các consumer có thể xử lý nghiệp vụ của họ trong thời điểm phù hợp**.

## 3. Phân biệt event mỏng và event giàu dữ liệu

| Tiêu chí | Event mỏng | Event giàu dữ liệu |
| --- | --- | --- |
| Payload | Thường chỉ chứa `orderId`, `eventId`, thời điểm. | Chứa thêm snapshot của các dữ kiện cần cho consumer. |
| Công việc của listener | Hay phải gọi API truy vấn để lấy thêm chi tiết. | Có thể xử lý từ payload mà không cần truy vấn ngược. |
| Phụ thuộc runtime | Có thể phụ thuộc vào khả năng truy vấn của publisher. | Giảm phụ thuộc truy vấn runtime, tăng phụ thuộc hợp đồng dữ liệu. |
| Tính đúng theo lịch sử | Nếu đọc dữ liệu hiện tại có thể khác thời điểm event. | Có thể giữ chính xác giá trị tại thời điểm sự kiện. |
| Kích thước | Thường nhỏ. | Có thể lớn hơn, cần kiểm soát. |
| Thay đổi hợp đồng | Ít field hơn, thường dễ duy trì. | Nhiều field hơn, cần quản lý tương thích nghiêm túc. |
| Quyền riêng tư | Ít nguy cơ mang dữ liệu không cần thiết. | Phải cân nhắc thông tin cá nhân và dữ liệu nhạy cảm. |
| Lưu publication/replay | Thường nhẹ hơn. | Phải cân nhắc serialisation, dung lượng và khả năng đọc event cũ. |

Một event không tự động tốt hơn chỉ vì nó nhiều field hơn. Cần đánh giá ai tiêu thụ, khi nào tiêu thụ, dữ liệu có biến đổi không, và yêu cầu về giao sự kiện đáng tin cậy đến đâu.

## 4. Hai loại thông tin trong rich event: định danh và ảnh chụp

### 4.1. Định danh để liên kết và chống trùng

Một event thường cần các khóa để liên hệ sự kiện với nghiệp vụ:

- **`eventId`**: định danh ổn định của *lần xảy ra sự kiện*, hỗ trợ log, đối soát, idempotency. Nếu hệ thống phát lại cùng event, phải giữ nguyên `eventId`.
- **`orderId`**: định danh đơn hàng; có thể xuất hiện trong nhiều sự kiện như `OrderPlaced`, `OrderConfirmed`, `OrderCancelled`.
- **`occurredAt`**: thời điểm sự thật nghiệp vụ được ghi nhận, khác với thời điểm consumer nhận hay xử lý event.
- **Version của aggregate** (nếu cần): giúp consumer phân biệt thứ tự các thay đổi trạng thái trên cùng một đối tượng.

Không phải mọi hệ thống đều cần đủ các field này. Ví dụ, với event duy nhất `OrderPlaced` theo mỗi đơn hàng, `orderId` có thể là khóa idempotency nghiệp vụ đủ tốt cho consumer chỉ tạo một bản ghi. Nhưng khi một đơn hàng có nhiều sự kiện hợp lệ cùng loại, khóa `orderId` không đủ để phân biệt các lần xảy ra.

### 4.2. Snapshot cho thông tin đã đúng tại thời điểm phát

Ảnh chụp sự kiện nên phản ánh các **giá trị đã được nghiệp vụ xác nhận** tại thời điểm phát, ví dụ:

- Mã và tên sản phẩm **tại thời điểm đặt hàng**.
- Số lượng và đơn giá đã chốt.
- Loại tiền và tổng tiền đã tính theo quy tắc nghiệp vụ.
- Chính sách giảm giá/thuế đã áp dụng nếu consumer cần tính toán chính xác.
- Thời điểm đặt hàng để ghi nhận báo cáo theo kỳ.

Nếu giá sản phẩm đổi sau đó, email xác nhận hoặc báo cáo lịch sử vẫn phải dùng giá trị đã chốt, không lấy giá niêm yết hiện tại từ catalog.

Ngược lại, thông tin chỉ để hiển thị hồ sơ người dùng hiện tại có thể nên lấy qua API công khai ở thời điểm cần thiết. Tùy mục tiêu, **snapshot và reference có thể cùng tồn tại** trong một event.

## 5. Thiết kế record bất biến trong Java

Ví dụ hợp đồng `OrderPlaced` cung cấp dữ liệu đã chốt của một đơn hàng. Ở đây, `items` là tập các phần tử bất biến, không chứa entity JPA.

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        String currencyCode,
        BigDecimal totalAmount,
        List<OrderItemSnapshot> items
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(currencyCode, "currencyCode");
        Objects.requireNonNull(totalAmount, "totalAmount");
        Objects.requireNonNull(items, "items");

        if (currencyCode.isBlank()) {
            throw new IllegalArgumentException("currencyCode is blank");
        }
        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException("totalAmount is negative");
        }
        items = List.copyOf(items);
    }
}
~~~

Một phần tử snapshot có thể được khai báo độc lập:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.util.Objects;

public record OrderItemSnapshot(
        String sku,
        String productNameAtPurchase,
        int quantity,
        BigDecimal unitPrice
) {
    public OrderItemSnapshot {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(productNameAtPurchase, "productNameAtPurchase");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || productNameAtPurchase.isBlank()) {
            throw new IllegalArgumentException("Missing product identity");
        }
        if (quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid quantity or price");
        }
    }
}
~~~

Các điểm cần chú ý:

1. `record` tự tạo field `final` và accessor, nhưng **không tự sao chép những đối tượng mutable** được truyền vào.
2. `List.copyOf(items)` tạo một danh sách không thể thay đổi cấu trúc qua accessor của event; các phần tử `OrderItemSnapshot` cũng là record chứa các kiểu bất biến.
3. `BigDecimal`, `UUID`, `Instant` và `String` phù hợp cho dữ liệu bất biến trong ví dụ này.
4. Điều kiện `totalAmount >= 0` là chính sách minh họa. Nghiệp vụ hoàn tiền, điều chỉnh giá hoặc các loại event khác cần invariant phù hợp với chính chúng.
5. Việc kiểm tra **tổng tiền khớp các line item** cần xét giảm giá, phí vận chuyển, thuế và quy tắc làm tròn; không nên ngầm áp dụng `sum(quantity * unitPrice) == totalAmount` cho mọi đơn.

### Vì sao không truyền nguyên entity?

Không nên định nghĩa:

~~~java
// Không nên dùng entity sống làm payload chia sẻ giữa module.
public record OrderPlaced(OrderJpaEntity order) {}
~~~

Đối tượng `OrderJpaEntity` có thể chứa lazy collection, quan hệ hai chiều, trạng thái mutable và chi tiết ORM. Khi listener chạy **sau commit** hoặc **bất đồng bộ**, session persistence gốc có thể đã đóng; việc đọc lazy property có nguy cơ lỗi. Đồng thời, consumer trở nên phụ thuộc vào cấu trúc nội bộ của module `orders`.

Event bằng record/snapshot tạo ra một **hợp đồng dữ liệu tường minh**, dễ kiểm thử và dễ cân nhắc khả năng serialize/lưu lại.

## 6. Đặt event contract tại module phát hành

Trong Spring Modulith, mỗi module nên sở hữu những sự kiện diễn tả sự thật nghiệp vụ do mình xác lập:

~~~text
com.example.shop
├── orders/
│   ├── events/
│   │   ├── package-info.java
│   │   ├── OrderPlaced.java
│   │   └── OrderItemSnapshot.java
│   └── internal/
│       ├── OrderService.java
│       ├── OrderRepository.java
│       └── OrderJpaEntity.java
├── notifications/
│   └── internal/
│       └── OrderPlacedListener.java
├── loyalty/
│   └── internal/
│       └── OrderPointsListener.java
└── reporting/
    └── internal/
        └── OrderRevenueListener.java
~~~

Có thể công khai package event bằng named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Và khai báo phụ thuộc consumer được phép:

~~~java
// notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.notifications;
~~~

Khi đó `notifications` phụ thuộc vào `OrderPlaced` và `OrderItemSnapshot`, **không cần import** `orders.internal.OrderRepository`. Đây là lợi ích kiến trúc chính của rich event: giảm nhu cầu tạo các đường truy vấn ngược chỉ để xử lý thông báo hậu nghiệp vụ.

Tuy nhiên, rich event **tăng mức phụ thuộc vào schema công khai**. Nếu thay đổi `OrderItemSnapshot` mà không xét listener, module vẫn bị ảnh hưởng. Chỉ mở rộng hợp đồng khi có yêu cầu tiêu thụ rõ ràng.

## 7. Tạo snapshot tại thời điểm nghiệp vụ hoàn tất

Publisher nên xây dựng event từ **dữ liệu đã được nghiệp vụ xác nhận**, thường bên trong transaction của module phát hành.

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderItemSnapshot;
import com.example.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher,
                        Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = Order.createFrom(command);
        orders.save(order);

        var itemSnapshots = order.lines().stream()
                .map(line -> new OrderItemSnapshot(
                        line.sku(),
                        line.nameAtPurchase(),
                        line.quantity(),
                        line.unitPrice()
                ))
                .toList();

        var event = new OrderPlaced(
                UUID.randomUUID(),
                order.id(),
                clock.instant(),
                order.currencyCode(),
                order.totalAmount(),
                itemSnapshots
        );

        publisher.publishEvent(event);
        return order.id();
    }
}
~~~

`Order`, `OrderRepository` và `PlaceOrderCommand` là các kiểu nghiệp vụ minh họa; trong ứng dụng thật cần định nghĩa chúng, quy tắc cấp ID và `Clock` bean phù hợp. Mẫu thiết kế ở đây là:

- Module `orders` tự quyết định khi nào `OrderPlaced` hợp lệ.
- Publisher chụp `itemSnapshots` **trong lúc có dữ liệu nghiệp vụ cần thiết**.
- Snapshot được tạo trước khi event thoát khỏi transaction và trước khi listener bất đồng bộ chạy.
- Consumer không phải truy cập entity của `orders` để lấy giá và số lượng lúc mua.

### Một điểm quan trọng về thời điểm phát

`publishEvent(event)` gọi bên trong transaction **không đồng nghĩa event chỉ được giao sau commit cho mọi loại listener**. Listener `@EventListener` đồng bộ mặc định có thể nhận ngay trước commit.

Để xử lý hậu nghiệp vụ sau commit, Spring có `@TransactionalEventListener(phase = AFTER_COMMIT)`, còn Spring Modulith cung cấp `@ApplicationModuleListener` để hỗ trợ listener sau commit, bất đồng bộ và transaction riêng.

Nếu transaction đặt hàng rollback, listener sau commit không nên thực hiện tác dụng phụ cho đơn hàng không được tạo thành công. Lựa chọn listener và transaction phải phù hợp với sự thật mà event diễn tả.

## 8. Consumer sử dụng rich event như thế nào?

### 8.1. Tạo email từ snapshot

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {

    private final ConfirmationSender sender;

    OrderConfirmationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendOrderSummary(
                event.eventId(),
                event.orderId(),
                event.currencyCode(),
                event.totalAmount(),
                event.items()
        );
    }
}
~~~

Ví dụ cố ý không đưa email khách hàng vào `OrderPlaced`. Trong ứng dụng thật, cần xác định cách lấy địa chỉ người nhận: dùng snapshot địa chỉ nếu nghiệp vụ cần đảm bảo người nhận đúng ở thời điểm đặt đơn và đáp ứng yêu cầu bảo mật, hoặc dùng một API công khai phù hợp để tra cứu lúc gửi. Đây là quyết định nghiệp vụ riêng với việc cung cấp snapshot giá.

Đặc biệt khi email có thể gửi nhiều lần do retry, `ConfirmationSender` cần có cách ngăn gửi trùng theo `eventId` hoặc khóa nghiệp vụ phù hợp.

### 8.2. Cập nhật số liệu doanh thu

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class RevenueProjectionListener {

    private final RevenueProjection projection;

    RevenueProjectionListener(RevenueProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        projection.recordOrder(
                event.eventId(),
                event.orderId(),
                event.occurredAt(),
                event.currencyCode(),
                event.totalAmount()
        );
    }
}
~~~

Module `reporting` không cần đọc giá sản phẩm hiện tại. Nó có thể ghi số tiền đã chốt trong event, đồng thời phân biệt rõ **thời điểm đặt hàng** với **thời điểm projection được cập nhật**.

Chú ý một báo cáo doanh thu chính thức có thể phải dựa trên sự kiện **thanh toán thành công** chứ không phải **đơn hàng được tạo**. Ví dụ này chỉ phù hợp với chỉ số "giá trị đơn được đặt". Tên event phải phản ánh đúng định nghĩa chỉ số.

## 9. Khi nào nên thêm field vào rich event?

Không nên thêm dữ liệu chỉ vì hệ thống có sẵn trong entity. Mỗi field mới phải trả lời được ít nhất một câu hỏi cụ thể:

1. **Consumer nào sử dụng?** Nếu chưa có consumer hoặc nhu cầu thực tế, giữ payload nhỏ.
2. **Có cần trạng thái tại thời điểm xảy ra không?** Giá bán, thuế đã chốt và tên sản phẩm lúc mua thường là dữ liệu lịch sử.
3. **Consumer có thể lấy dữ liệu qua API công khai không?** Nếu lấy sau vẫn đúng và không tăng phụ thuộc vận hành quá mức, reference có thể đủ.
4. **Dữ liệu thay đổi thường xuyên không?** Giá trị liên tục cập nhật có thể không phù hợp làm snapshot trong event đã xảy ra.
5. **Dữ liệu có nhạy cảm không?** Email, địa chỉ, số điện thoại, thông tin thanh toán hoặc dữ liệu sức khỏe cần có mục đích, phạm vi sử dụng, thời hạn lưu giữ và biện pháp bảo vệ.
6. **Kích thước và khả năng serialize ra sao?** Danh sách hàng nghìn dòng hoặc tệp đính kèm không nên được đưa thẳng vào event chỉ để thuận tiện.
7. **Field có làm lộ nội bộ không?** Không đưa `OrderJpaEntity`, `EntityManager`, trạng thái ORM hoặc DTO chỉ phục vụ một endpoint vào event contract.
8. **Có thể thay đổi hợp đồng an toàn không?** Cần tính tới listener ở phiên bản khác và publication đang chờ replay.

Bảng phân loại ví dụ:

| Field đề xuất | Nên đưa vào? | Lý do |
| --- | --- | --- |
| `eventId` | Thường nên nếu cần theo dõi/chống trùng. | Xác định lần xảy ra sự kiện. |
| `orderId` | Có. | Định danh nghiệp vụ cơ bản. |
| `totalAmount`, `currencyCode` | Có khi consumer cần giá đã chốt. | Chụp đúng giá trị lịch sử. |
| `items` gồm sku, quantity, unitPrice | Có khi email/hóa đơn/projection cần chi tiết. | Giảm truy vấn ngược và giữ snapshot. |
| `JpaOrderEntity` | Không. | Rò rỉ implementation, mutable và có thể phụ thuộc session. |
| `customerPasswordHash` | Không. | Không liên quan sự kiện và đặc biệt nhạy cảm. |
| `shippingAddress` đầy đủ | Chỉ khi thật sự cần, với bảo vệ thích hợp. | Dữ liệu cá nhân có rủi ro khi lưu/phát lại. |
| File PDF hóa đơn dạng byte[] | Thường tránh; dùng storage reference có kiểm soát. | Payload lớn, khó vận hành, lưu trữ tốn kém. |

## 10. Rich event, quyền riêng tư và độ nhạy cảm

Một application event có thể được gửi đến **nhiều listener**. Nếu snapshot chứa thông tin cá nhân không cần thiết, mọi consumer được phép nhận event đều có cơ hội truy cập dữ liệu đó.

Ví dụ event gồm:

~~~text
OrderPlaced(
  orderId,
  customerEmail,
  fullShippingAddress,
  paymentCardNumber,
  orderItems,
  totalAmount
)
~~~

Đây là một hợp đồng nguy hiểm: `loyalty` và `reporting` có thể chỉ cần `orderId`, `totalAmount`, nhưng lại cùng nhìn thấy địa chỉ và dữ liệu thẻ.

Cách xử lý phù hợp là **tối thiểu hóa dữ liệu**:

- Không đưa thông tin thẻ thanh toán đầy đủ hoặc bí mật xác thực vào event.
- Chỉ đưa dữ liệu cá nhân khi có mục đích nghiệp vụ và quyền sử dụng rõ ràng.
- Nếu nhóm consumer có nhu cầu dữ liệu rất khác nhau, cân nhắc các **event có ngữ nghĩa riêng** hoặc hợp đồng/luồng truy cập riêng có kiểm soát.
- Thiết kế retention, logging, truy cập và chính sách dữ liệu trong Event Publication Registry nếu payload được lưu để retry.
- Không log nguyên rich payload chỉ để hỗ trợ debug; ưu tiên `eventId`, `orderId`, loại event và trạng thái xử lý.

Lưu ý việc thêm nhiều event riêng chỉ để phân quyền truy cập cần cân nhắc: các event vẫn phải đại diện sự thật có ý nghĩa hoặc sự kiện tích hợp được thiết kế rõ ràng, tránh tạo nhiều biến thể không nhất quán của cùng một giao dịch.

## 11. Kích thước payload và hiệu năng

Một event nhỏ chứa ID rẻ khi tạo và dễ chuyển qua cơ chế Spring event. Rich event có thể làm tăng:

- Bộ nhớ cần cấp phát để tạo và giữ snapshot.
- Công việc serialize/deserialize khi có cơ chế lưu publication.
- Dung lượng registry khi có nhiều listener hoặc publication tồn đọng.
- Độ phức tạp tương thích khi event được replay từ dữ liệu lưu trước đó.
- Dung lượng log nếu ứng dụng vô tình ghi toàn bộ payload.

**Không có một giới hạn kích thước chung cố định** phù hợp với mọi Spring Modulith application. Quyết định phụ thuộc số lượng event, số consumer, backend lưu trữ, chính sách retention và khả năng phục hồi của hệ thống.

Thực hành gợi ý:

1. Đo kích thước event sau khi serialize với serializer/backend dự kiến sử dụng.
2. Đo số lượng publication phát ra ở tải bình thường và tải cao.
3. Xác định mức tăng dữ liệu khi có backlog do listener lỗi.
4. Không nhét ảnh, PDF, byte array lớn hoặc danh sách dữ liệu không giới hạn vào event; dùng tham chiếu có quyền truy cập và vòng đời rõ ràng.
5. Đặt các giới hạn nghiệp vụ hợp lý cho danh sách trong event và quyết định cách xử lý đơn hàng có kích thước bất thường.
6. Kiểm tra cả performance và tính tương thích khi thay đổi schema.

Nếu sự kiện phải xuất ra message broker bên ngoài, còn cần tuân thủ giới hạn và quy ước của nền tảng nhận. **Rich application event trong Spring không tự biến thành integration event**, và không mặc nhiên có định dạng wire ổn định cho hệ thống khác.

## 12. Event Publication Registry, replay và schema compatibility

Spring Modulith hỗ trợ **Event Publication Registry** để theo dõi việc giao sự kiện đến các transactional event listener. Khi có cơ chế persistence được cấu hình, registry có thể lưu publication còn chờ và ghi nhận khi consumer xử lý thành công.

Một rich event làm tăng giá trị của cơ chế này vì payload có đủ snapshot để consumer có thể xử lý lại khi trạng thái nguồn đã thay đổi. Tuy nhiên nó cũng tăng yêu cầu về khả năng đọc dữ liệu đã lưu.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as orders
    participant R as Publication Registry
    participant N as notifications
    participant DB as Consumer DB

    O->>O: Tạo OrderPlaced với snapshot
    O->>R: Ghi nhận publication khi cấu hình persistence
    O->>O: Commit đơn hàng
    R-->>N: Giao event sau commit
    N->>DB: Ghi nhận xử lý và tạo tác dụng phụ
    alt Consumer thành công
        N-->>R: Publication hoàn tất
    else Consumer lỗi
        Note over R: Publication còn chưa hoàn tất
        R-->>N: Replay theo cơ chế recovery
    end
~~~

Sơ đồ mô tả luồng logic, không mô tả bắt buộc mọi lời gọi nội bộ của từng phiên bản Spring Modulith. Khả năng lưu publication và khôi phục phụ thuộc backend, cấu hình và cách triển khai recovery.

### Vấn đề khi thay đổi schema

Giả sử phiên bản đầu của event là:

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        BigDecimal totalAmount
) {}
~~~

Phiên bản sau thay `totalAmount` thành `paymentSummary` có cấu trúc hoàn toàn khác. Nếu publication của phiên bản cũ vẫn nằm trong registry, ứng dụng mới có thể không đọc lại được payload, tùy cách serializer và persistence hoạt động.

Những hướng xử lý cần cân nhắc:

- Ưu tiên thay đổi có tính tương thích với dữ liệu đã lưu và với listener hiện có.
- Không đổi ngữ nghĩa một field cũ mà vẫn giữ tên giống nhau.
- Dùng phiên bản hợp đồng tường minh khi có thay đổi phá vỡ tương thích, ví dụ tên event mới `OrderPlacedV2` hoặc cơ chế versioning được quản trị.
- Đánh giá publication đang chờ trước khi deploy và chuẩn bị chiến lược migrate/đọc schema cũ khi cần.
- Kiểm thử serialize/deserialize và replay với dữ liệu hợp đồng của phiên bản trước.
- Giữ `eventId` ổn định khi phát lại cùng sự kiện; không tạo ID mới cho mỗi lượt retry.

Việc thêm field optional không luôn tự động an toàn đối với mọi serializer. Cần xác minh bằng cấu hình serializer thực tế của ứng dụng, nhất là với Java record và persisted event publications.

## 13. Idempotency của consumer: trách nhiệm không thể bỏ qua

Rich event giúp consumer ít phải truy vấn ngược nhưng **không ngăn giao sự kiện trùng**. Có thể xảy ra:

1. Listener cộng điểm thành công.
2. Ứng dụng dừng trước khi registry đánh dấu xử lý hoàn tất.
3. Sự kiện được phát lại.
4. Listener cộng điểm thêm lần nữa nếu thiếu idempotency.

Một bảng dữ liệu chống trùng có thể lưu cặp khóa:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Cách dùng an toàn cần đặt thao tác đánh dấu đã xử lý **trong cùng transaction** với cập nhật dữ liệu nghiệp vụ của consumer, khi cả hai nằm trên cùng database/transaction manager. Thao tác chèn khóa duy nhất phải được xử lý **nguyên tử** để hai worker đồng thời không vượt qua kiểm tra kiểu `exists -> insert`.

Với side effect ngoài database như email hoặc webhook, không thể chỉ dựa vào transaction DB để bảo đảm exactly-once. Cần tận dụng idempotency key của dịch vụ ngoài nếu có, hoặc xây quy trình gửi và đối soát phù hợp.

Có thể phác thảo quy tắc:

~~~text
On OrderPlaced(event):
  1. Kiểm tra/ghi nhận duy nhất (consumer, eventId) bằng cơ chế nguyên tử.
  2. Áp dụng thay đổi dữ liệu nghiệp vụ trong transaction phù hợp.
  3. Sau khi thành công, để cơ chế publication đánh dấu listener hoàn tất.
  4. Nếu retry cùng eventId, nhận biết đã xử lý và bỏ qua tác dụng phụ trùng.
~~~

**Lưu ý:** quy trình trên chỉ mô tả một mẫu cho side effect cùng database; việc đánh dấu “đã tiêu thụ” quá sớm rồi thực hiện tác dụng phụ bên ngoài thất bại có thể làm mất khả năng retry đúng. Cần thiết kế trạng thái và thứ tự cập nhật theo tính chất từng hệ thống tích hợp.

## 14. Kiểm thử thiết kế rich event

Các kiểm thử cần đi xa hơn việc khẳng định “`publishEvent` đã được gọi”.

### 14.1. Kiểm thử snapshot có đúng thời điểm không?

Tạo một đơn hàng với giá đã chốt, phát event, rồi thay đổi tên/giá sản phẩm trong catalog. Xác nhận `OrderPlaced` vẫn giữ thông tin **tại thời điểm đặt hàng**.

Ví dụ kiểm thử bất biến của danh sách:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderPlacedContractTest {

    @Test
    void eventKeepsIndependentSnapshotOfItems() {
        var originalItems = new ArrayList<OrderItemSnapshot>();
        originalItems.add(new OrderItemSnapshot(
                "SKU-1", "Áo cotton", 2, new BigDecimal("150000")
        ));

        var event = new OrderPlaced(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-01-01T00:00:00Z"),
                "VND",
                new BigDecimal("300000"),
                originalItems
        );

        originalItems.clear();

        assertEquals(1, event.items().size());
        assertThrows(
                UnsupportedOperationException.class,
                () -> event.items().clear()
        );
    }
}
~~~

Ví dụ giả định test nằm cùng package với các record hợp đồng hoặc đã import `OrderPlaced` và `OrderItemSnapshot`. Trọng tâm là kiểm tra `List.copyOf` giúp tránh thay đổi danh sách thông qua nguồn tham chiếu bên ngoài.

### 14.2. Kiểm thử publisher theo module

Spring Modulith có `@ApplicationModuleTest` và `PublishedEvents` để quan sát các event được công bố. Nên kiểm tra một hành động tạo đơn hợp lệ tạo `OrderPlaced` với **đúng `orderId`, tổng tiền, tiền tệ và line item**; đồng thời xác minh transaction rollback không tạo side effect sau commit.

### 14.3. Kiểm thử consumer không gọi API nội bộ

Mock hoặc test double cho service tiêu thụ để xác nhận listener có thể dựng email hay projection từ event. Kiểm tra kiến trúc với `ApplicationModules.of(ShopApplication.class).verify()` để phát hiện module listener phụ thuộc trực tiếp vào package nội bộ của publisher.

### 14.4. Kiểm thử replay và nâng cấp phiên bản

Giữ fixture của event schema cũ đã serialize, sau đó xác minh phiên bản ứng dụng mới đọc và xử lý theo kế hoạch tương thích. Tạo cùng `eventId` hai lần để xác nhận consumer không gây tác dụng phụ trùng. Nếu dùng registry, kiểm thử đường khôi phục với persistence thực tế thay vì chỉ gọi trực tiếp method listener.

## 15. Theo dõi rich event trong vận hành

Rich event cho nhiều dữ kiện chẩn đoán, nhưng không nên log toàn bộ payload mặc định. Một bộ trường quan sát vừa đủ:

| Trường log/metric | Cách sử dụng |
| --- | --- |
| `eventType`, `eventId` | Truy vết một sự kiện qua publisher và consumer. |
| `aggregateId` / `orderId` | Liên hệ sự kiện với đối tượng nghiệp vụ. |
| `occurredAt`, `processedAt` | Đánh giá độ trễ từ sự kiện đến xử lý. |
| `listener`, `attempt` | Biết consumer nào lỗi và bao nhiêu lượt thử. |
| `publicationStatus` | Theo dõi trạng thái chưa hoàn tất/hoàn tất của publication. |
| `payloadVersion`, `payloadSize` | Phát hiện rủi ro tương thích hoặc tăng dung lượng bất thường. |

Ví dụ log ứng dụng tự thiết kế:

~~~text
event=OrderPlaced eventId=99b... orderId=41c... payloadVersion=1 listener=notifications attempt=1 status=FAILED
event=OrderPlaced eventId=99b... orderId=41c... payloadVersion=1 listener=notifications attempt=2 status=COMPLETED
event=OrderPlaced eventId=99b... orderId=41c... payloadVersion=1 listener=reporting attempt=1 status=COMPLETED
~~~

Dòng log là ví dụ minh họa, không phải định dạng mặc định của Spring Modulith. Cần cấu hình logging, metrics, tracing và giám sát registry tương ứng. Không log địa chỉ, thông tin thanh toán hoặc toàn bộ danh sách item nếu không có nhu cầu vận hành được kiểm soát.

## 16. Các lỗi thiết kế thường gặp

### 16.1. Rich event thành bản sao toàn bộ aggregate

~~~java
public record OrderPlaced(Order order) {}
~~~

**Vấn đề:** rò rỉ mô hình nội bộ, kéo theo thay đổi entity, ảnh hưởng đến serialize và vận hành listener bất đồng bộ.

**Cách cải thiện:** dùng snapshot DTO bất biến, chỉ chọn các field đủ cho hợp đồng.

### 16.2. Snapshot quá ít nên vẫn phải truy vấn ngược để giữ dữ liệu lịch sử

`OrderPlaced(orderId)` khiến email phải truy vấn giá hiện tại, dẫn tới email có tổng tiền sai sau khi điều chỉnh bảng giá.

**Cách cải thiện:** đưa tổng tiền và thông tin dòng hàng **đã được chốt** vào event nếu consumer cần dữ liệu lịch sử này.

### 16.3. Snapshot quá nhiều nên tăng rủi ro dữ liệu

Đưa toàn bộ địa chỉ, hồ sơ khách, token thanh toán và các thuộc tính nội bộ vào một event chung cho nhiều consumer.

**Cách cải thiện:** phân tích yêu cầu từng consumer và chỉ đưa dữ liệu thực sự cần; áp dụng bảo vệ, quyền truy cập, retention khi có dữ liệu cá nhân.

### 16.4. Biến event thành command mang chỉ dẫn cho consumer

~~~java
public record OrderPlaced(
        UUID orderId,
        boolean sendEmail,
        boolean awardPoints,
        boolean updateReport
) {}
~~~

**Vấn đề:** publisher đang quyết định công việc nội bộ của các module khác, làm mất ranh giới trách nhiệm.

**Cách cải thiện:** giữ event mô tả sự thật nghiệp vụ; notifications, loyalty và reporting tự xác định chính sách phản ứng.

### 16.5. Bỏ qua thay đổi schema của persisted publication

Đổi kiểu payload khiến publication cũ đang chờ xử lý không deserialize được khi replay.

**Cách cải thiện:** kiểm thử tương thích theo serializer thực tế và chuẩn bị kế hoạch version/migration trước rollout.

### 16.6. Cho rằng có snapshot là bảo đảm xử lý đúng một lần

Snapshot làm giảm phụ thuộc vào dữ liệu nguồn, nhưng event vẫn có thể được giao trùng hoặc listener lỗi sau khi đã tạo side effect.

**Cách cải thiện:** kết hợp registry/recovery phù hợp, transaction của consumer, idempotency và khả năng quan sát.

## 17. Quy trình quyết định event mỏng hay giàu dữ liệu

~~~mermaid
flowchart TD
    A["Bắt đầu từ một sự kiện nghiệp vụ"] --> B{"Consumer có cần dữ kiện tại đúng thời điểm xảy ra?"}
    B -->|"Có"| C["Chọn snapshot bất biến cho các dữ kiện lịch sử"]
    B -->|"Không"| D{"Có API công khai để truy vấn an toàn khi xử lý?"}
    D -->|"Có"| E["Có thể dùng ID/reference"]
    D -->|"Không hoặc phụ thuộc vận hành quá lớn"| F["Cân nhắc thêm field có mục đích vào event"]
    C --> G{"Payload có nhạy cảm/quá lớn/khó versioning?"}
    F --> G
    E --> H["Xác nhận consumer và mức nhất quán cần thiết"]
    G -->|"Có"| I["Giảm dữ liệu, tách hợp đồng hoặc dùng reference có kiểm soát"]
    G -->|"Không"| H
    I --> H
    H --> J["Kiểm thử publish, consume, retry, replay và quan sát"]
~~~

Một cách triển khai thực tế là bắt đầu bằng **payload tối thiểu đáp ứng use case**, sau đó bổ sung field dựa trên yêu cầu rõ ràng và đánh giá chi phí tương thích. Đừng chọn event mỏng hay giàu dữ liệu theo trào lưu; hãy chọn theo **ngữ nghĩa nghiệp vụ, thời điểm cần dữ liệu và mức độc lập mong muốn của consumer**.

## 18. Bài tập thực hành: email xác nhận và báo cáo doanh thu

Hãy thiết kế luồng xử lý cho đơn hàng có hai sản phẩm:

- `SKU-A`: 2 chiếc, đơn giá `150000 VND`.
- `SKU-B`: 1 chiếc, đơn giá `250000 VND`.
- Tổng tiền đã chốt (chưa xét giảm giá/thuế/phí trong bài tập): `550000 VND`.

Yêu cầu:

1. Thiết kế `OrderPlaced` có `eventId`, `orderId`, `occurredAt`, `currencyCode`, `totalAmount` và hai `OrderItemSnapshot`.
2. Publisher ở `orders.internal` tạo snapshot từ giá trị đã chốt và phát trong transaction tạo đơn.
3. Listener của `notifications` tạo nội dung xác nhận từ snapshot mà không import `OrderRepository`.
4. Listener của `reporting` ghi doanh thu theo `occurredAt`, có chống trùng khi xử lý cùng `eventId` nhiều lần.
5. Giả lập việc thay đổi giá catalog sau khi đơn được tạo; xác minh email và báo cáo vẫn dùng giá đã chốt.
6. Giả lập lỗi trong listener rồi replay bằng cơ chế recovery được cấu hình; xác minh không nhân đôi dữ liệu đã ghi.
7. Thử thêm field `discountAmount` vào hợp đồng; đánh giá ảnh hưởng tới consumer và khả năng đọc persisted publication cũ.

**Câu hỏi tự kiểm tra:** Nếu email cần địa chỉ nhận nhưng reporting không cần, có nên đưa địa chỉ vào event chung? Khi nào chấp nhận truy vấn qua API riêng, khi nào phải dùng snapshot? Nếu event đã lưu để replay, bạn sẽ kiểm thử việc đổi schema như thế nào?

**Ghi nhớ:** Event giàu dữ liệu giúp consumer Spring Modulith xử lý một sự thật nghiệp vụ từ **snapshot bất biến**, giảm phụ thuộc truy vấn ngược và giữ đúng dữ kiện lịch sử. Đổi lại, hợp đồng lớn hơn cần được quản trị về kích thước, thông tin nhạy cảm, versioning và khả năng replay. Với giao tiếp sau commit, hãy kết hợp `@ApplicationModuleListener`, Event Publication Registry khi cần lưu trạng thái giao, recovery, idempotency, kiểm thử và observability để đạt độ tin cậy phù hợp.

