# Cấu trúc package gợi ý cho Spring Modulith Application Events

## 1. Mục tiêu của cách tổ chức package

Trong một ứng dụng Spring Boot sử dụng **Spring Modulith**, các module nghiệp vụ cùng chạy trong một tiến trình nhưng vẫn cần có ranh giới phụ thuộc rõ ràng. Khi các module giao tiếp bằng **application events**, cấu trúc package phải giúp lập trình viên dễ trả lời bốn câu hỏi:

1. Module nào sở hữu một sự kiện nghiệp vụ?
2. Module nào được phép nhìn thấy kiểu sự kiện đó?
3. Publisher và listener được đặt ở đâu để không làm lộ chi tiết nội bộ?
4. Làm thế nào để kiểm tra ranh giới module và vận hành luồng xử lý sau commit?

Một cấu trúc phù hợp cho module học **SPRING_MODULITH_APPLICATION_EVENTS** cần phục vụ cả hai mục tiêu: giảm phụ thuộc giữa các module và giữ chỗ rõ ràng cho publisher, listener, event contract, publication registry, retry, kiểm thử và quan sát.

Nguyên tắc khởi đầu là **package theo năng lực nghiệp vụ** (*package by feature*), không gom toàn bộ source code của ứng dụng theo các lớp kỹ thuật như `controller`, `service`, `repository` hoặc `listener` ở cấp toàn ứng dụng.

## 2. Spring Modulith nhìn nhận package như thế nào?

Với cách phát hiện module mặc định, Spring Modulith xem các **package con trực tiếp** dưới package gốc của ứng dụng là các application module. Ví dụ package gốc là `com.acme.shop`:

~~~text
com.acme.shop
├── ShopApplication
├── orders             <-- module orders
├── notifications      <-- module notifications
├── loyalty            <-- module loyalty
└── payments           <-- module payments
~~~

Mỗi module có thể có các package con khác để chứa implementation, API và event. Theo mô hình module thông thường của Spring Modulith:

- Các kiểu đặt ngay trong **package gốc của module** tạo thành API mặc định của module.
- Các kiểu nằm sâu trong package con, ví dụ `orders.internal`, là chi tiết nội bộ theo ranh giới module; module khác không nên truy cập trực tiếp.
- Một package con có thể được **công khai có chủ đích** bằng `@NamedInterface`, chẳng hạn `orders.events` được công bố dưới tên `events`.
- Có thể dùng `@ApplicationModule(allowedDependencies = ...)` tại `package-info.java` để khai báo cụ thể module được phép phụ thuộc vào module hoặc named interface nào.

Điểm quan trọng: `public class` của Java **không đồng nghĩa** với API được phép sử dụng giữa các module. Một lớp `public` trong `orders.internal` vẫn là thành phần nội bộ theo kiến trúc Spring Modulith. Mục tiêu là tránh việc module tiêu thụ import trực tiếp repository, entity hoặc service nội bộ của module phát hành.

Việc Spring Modulith nhận diện module còn phụ thuộc cấu hình phát hiện và những annotation/module metadata được sử dụng. Bài này sử dụng mô hình **một module cho mỗi package con trực tiếp** để minh họa.

## 3. Cấu trúc package tham khảo cho ứng dụng có nhiều listener

Ví dụ cửa hàng trực tuyến: module **orders** quản lý đơn hàng; **notifications** gửi thông báo; **loyalty** cộng điểm; **payments** quản lý thanh toán.

~~~text
src/
├── main/
│   ├── java/com/acme/shop/
│   │   ├── ShopApplication.java
│   │   │
│   │   ├── orders/
│   │   │   ├── package-info.java
│   │   │   ├── events/
│   │   │   │   ├── package-info.java        # @NamedInterface("events")
│   │   │   │   ├── OrderPlaced.java
│   │   │   │   └── OrderCancelled.java
│   │   │   └── internal/
│   │   │       ├── OrderApplicationService.java
│   │   │       ├── OrderRepository.java
│   │   │       └── OrderEntity.java
│   │   │
│   │   ├── notifications/
│   │   │   ├── package-info.java            # chỉ cho phép orders::events
│   │   │   └── internal/
│   │   │       ├── SendOrderConfirmation.java
│   │   │       └── NotificationGateway.java
│   │   │
│   │   ├── loyalty/
│   │   │   ├── package-info.java            # chỉ cho phép orders::events
│   │   │   └── internal/
│   │   │       ├── AwardPointsOnOrderPlaced.java
│   │   │       └── LoyaltyRepository.java
│   │   │
│   │   └── payments/
│   │       ├── events/
│   │       │   ├── package-info.java        # @NamedInterface("events")
│   │       │   └── PaymentCompleted.java
│   │       └── internal/
│   │           ├── PaymentApplicationService.java
│   │           └── PaymentRepository.java
│   │
│   └── resources/
│       └── application.yml                 # cấu hình Spring và event persistence
│
└── test/
    └── java/com/acme/shop/
        ├── ModularityTests.java
        ├── orders/
        │   └── OrderModuleTests.java
        └── notifications/
            └── NotificationModuleTests.java
~~~

Đây là **cấu trúc gợi ý**, không phải một bộ file bắt buộc phải tạo nguyên xi. Nếu module nhỏ, có thể đặt `OrderPlaced` ngay trong package `orders` và bỏ `orders.events`; phần sau sẽ giải thích hai lựa chọn này.

### Vai trò từng vị trí

| Vị trí | Vai trò | Quy tắc phụ thuộc |
| --- | --- | --- |
| `orders.events` | Các kiểu event công khai do **orders** sở hữu. | Module nghe chỉ phụ thuộc vào hợp đồng event. |
| `orders.internal` | Xử lý đơn hàng, transaction, persistence, publisher. | Không cho module khác sử dụng trực tiếp. |
| `notifications.internal` | Listener và logic gửi thông báo. | Được import event công khai; không import implementation của orders. |
| `loyalty.internal` | Listener và chính sách cộng điểm. | Phụ thuộc vào event, không vào `orders.internal`. |
| `payments.events` | Event do payments phát hành. | Các module khác chỉ sử dụng khi có nhu cầu nghiệp vụ. |
| `src/test/java/.../orders` | Kiểm thử trong bối cảnh module orders. | Xác minh publication và ranh giới nghiệp vụ. |
| `src/test/java/.../notifications` | Kiểm thử hành vi của listener thông báo. | Xác minh phản ứng với event, lỗi và chống xử lý trùng. |

Điểm cốt lõi nằm ở **quyền sở hữu**: `OrderPlaced` thuộc về module **orders**, vì chính module này xác định khi nào một đơn hàng đã được tạo. Module **notifications** không nên định nghĩa `OrderPlaced` thay cho orders, cũng không nên yêu cầu orders import `NotificationService`.

## 4. Đặt event contract ở đâu?

### Lựa chọn A: đặt event ngay trong package gốc module

Đây là lựa chọn đơn giản cho module có ít hợp đồng công khai:

~~~text
com.acme.shop.orders
├── OrderPlaced.java
└── internal/
    ├── OrderApplicationService.java
    └── OrderRepository.java
~~~

`com.acme.shop.orders.OrderPlaced` thuộc API mặc định của module. Các module tiêu thụ chỉ import kiểu đó, không import `orders.internal.*`.

**Ưu điểm:** dễ hiểu, ít annotation, phù hợp bài học ban đầu hoặc module nhỏ.

**Hạn chế:** khi số lượng event, query API và command API tăng, package gốc có thể trở nên đông và khó phân biệt các loại hợp đồng.

### Lựa chọn B: đặt event trong package con có named interface

Khi module có nhiều hợp đồng, có thể tách một package riêng:

~~~text
com.acme.shop.orders
├── events/
│   ├── package-info.java
│   ├── OrderPlaced.java
│   └── OrderCancelled.java
└── internal/
    ├── OrderApplicationService.java
    └── OrderRepository.java
~~~

Nội dung `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Package `orders.events` lúc này được export như named interface `events` của module `orders`. Đối với module tiêu thụ, cú pháp tham chiếu named interface là **`orders::events`**.

Một module có thêm các hợp đồng truy vấn đồng bộ có thể tổ chức package `orders.api` với một named interface khác. Không cần công khai toàn bộ `orders.internal` chỉ vì một consumer cần nghe `OrderPlaced`.

**Ưu điểm:** biểu thị rõ bề mặt API theo nhu cầu, tách event khỏi implementation và thuận tiện đặt giới hạn phụ thuộc cụ thể.

**Hạn chế:** cần quản lý `package-info.java` và cấu hình giới hạn phụ thuộc nhất quán. Nếu đơn giản hóa bằng cách đặt mọi thứ vào `events` chung của toàn ứng dụng, có thể làm mất quyền sở hữu event theo nghiệp vụ.

### Ví dụ event bất biến

File `orders/events/OrderPlaced.java`:

~~~java
package com.acme.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {}
~~~

Thiết kế event nên ưu tiên:

- **Tên ở thì đã xảy ra:** `OrderPlaced`, `PaymentCompleted`; thể hiện sự thật nghiệp vụ, khác với command `SendConfirmationEmail`.
- **Dữ liệu nhỏ, bất biến:** mã định danh, thời điểm, thông tin cần thiết cho hợp đồng; có thể dùng `record` khi phù hợp.
- **Không truyền JPA entity hoặc repository:** tránh lazy loading, trạng thái thay đổi và phụ thuộc vào persistence nội bộ.
- **Không nhồi quyết định của listener vào event:** `OrderPlaced` không cần chứa `shouldSendEmail` hay `shouldAwardPoints`; đây là chính sách của module tiêu thụ.
- **Tính tương thích:** thay đổi field/type của event cần đánh giá tất cả consumer, đặc biệt khi có publication đã lưu để phát lại.

Nếu nhiều consumer cần đọc thêm dữ liệu, cân nhắc bổ sung một trường thật sự thuộc hợp đồng sự kiện hoặc sử dụng một API truy vấn công khai với phụ thuộc được khai báo. Tránh biến event thành bản sao toàn bộ entity chỉ để tiện sử dụng.

## 5. Định nghĩa ranh giới phụ thuộc bằng `package-info.java`

Một listener của `notifications` được phép nhìn thấy `orders::events` mà không cần truy cập implementation của orders.

File `notifications/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.notifications;
~~~

Tương tự, `loyalty/package-info.java` có thể dùng:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.loyalty;
~~~

Theo cấu hình minh họa, cả hai consumer chỉ có nhu cầu phụ thuộc vào named interface events của orders. Nếu `notifications` sau này nghe thêm `payments::events`, cần bổ sung phụ thuộc được phép sau khi xác nhận nhu cầu thực tế:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = { "orders::events", "payments::events" }
)
package com.acme.shop.notifications;
~~~

Có thể hình dung hướng phụ thuộc như sau:

~~~mermaid
flowchart LR
    subgraph ORD["Module orders"]
        P["orders.internal<br/>OrderApplicationService"]
        E["orders.events<br/>OrderPlaced"]
        P -->|"publish"| E
    end

    subgraph NOT["Module notifications"]
        N["notifications.internal<br/>SendOrderConfirmation"]
    end

    subgraph LOY["Module loyalty"]
        L["loyalty.internal<br/>AwardPointsOnOrderPlaced"]
    end

    N -. "tham chiếu orders::events" .-> E
    L -. "tham chiếu orders::events" .-> E
~~~

Các mũi tên nét đứt biểu diễn **phụ thuộc mã nguồn** từ consumer đến event contract. Lúc runtime, orders là bên **phát** sự kiện, còn notifications và loyalty là bên **nhận**. Phân biệt hai chiều này giúp tránh kết luận sai rằng module phát hành phải import listener để gửi thông báo.

Cũng cần phân biệt `allowedDependencies` với danh sách các consumer của event: annotation này kiểm soát **module hiện tại được phép phụ thuộc vào ai**, không chỉ định nơi event phải được giao đến.

## 6. Đặt publisher ở lớp nghiệp vụ sở hữu transaction

Ví dụ phần xử lý tạo đơn đặt trong `orders.internal`:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(OrderRepository orders,
                            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        OrderEntity order = orders.save(OrderEntity.create(command));

        events.publishEvent(new OrderPlaced(
                order.getId(),
                order.getCustomerId(),
                Instant.now()
        ));

        return order.getId();
    }
}
~~~

`OrderRepository`, `PlaceOrderCommand` và `OrderEntity` là các kiểu nội bộ minh họa của orders, không phải API Spring Modulith. Ví dụ giả định `orders.save(...)` trả về một entity có ID đã được gán.

Điều cần rút ra từ cấu trúc này:

1. **Publisher ở module orders**, nơi có thông tin nghiệp vụ để biết lúc nào được phát `OrderPlaced`.
2. **Không có lời gọi trực tiếp** đến `NotificationService` hoặc `LoyaltyService`.
3. **Hợp đồng event được import từ package công khai** `orders.events`.
4. **Transaction tạo đơn do orders quản lý**. Listener sau commit sẽ chờ transaction commit thành công rồi mới phản ứng.

Cần nhớ `ApplicationEventPublisher.publishEvent(...)` là thao tác công bố Spring application event. Bản thân lời gọi này **không bảo đảm mọi listener đã xử lý xong**, không mặc định bất đồng bộ và cũng không tự lưu bền vững event.

## 7. Đặt listener ở module tiêu thụ

File `notifications/internal/SendOrderConfirmation.java`:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SendOrderConfirmation {

    private final NotificationGateway notifications;

    SendOrderConfirmation(NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notifications.sendOrderConfirmation(
                event.orderId(), event.customerId()
        );
    }
}
~~~

File `loyalty/internal/AwardPointsOnOrderPlaced.java`:

~~~java
package com.acme.shop.loyalty.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsOnOrderPlaced {

    private final LoyaltyService loyalty;

    AwardPointsOnOrderPlaced(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        loyalty.awardPointsForOrder(event.orderId());
    }
}
~~~

`NotificationGateway` và `LoyaltyService` là abstraction nội bộ của từng consumer, cần có implementation phù hợp trong dự án thực tế.

`@ApplicationModuleListener` của Spring Modulith kết hợp xử lý event **sau khi transaction phát hành commit**, theo cơ chế **bất đồng bộ** và trong transaction riêng của listener. Đây là lựa chọn thường gặp cho thông báo, audit, đồng bộ chỉ mục hoặc cộng điểm sau khi đơn hàng đã được tạo.

Nếu cần phản ứng **đồng bộ** hoặc **trong cùng transaction**, phải chọn cơ chế listener và ranh giới transaction phù hợp với nghiệp vụ; không nên áp dụng `@ApplicationModuleListener` máy móc cho mọi tác vụ. Ví dụ việc xác thực đủ hàng tồn kho bắt buộc trước khi nhận đơn thường cần một luồng xác nhận hoặc giữ chỗ rõ ràng.

Trong một dự án lớn, nên đặt **mỗi listener theo một trách nhiệm cụ thể** thay vì tạo một `GlobalEventListener` nắm tất cả loại event. Hai listener trên có thể được sửa, kiểm thử, vận hành độc lập với nhau.

## 8. Luồng runtime và lý do cấu trúc package có ích

~~~mermaid
sequenceDiagram
    autonumber
    participant API as API/Khách hàng
    participant O as orders.internal
    participant DB as Order DB
    participant E as Spring event infrastructure
    participant N as notifications.internal
    participant L as loyalty.internal

    API->>O: placeOrder(command)
    O->>DB: Lưu order (transaction)
    O->>E: publishEvent(OrderPlaced)
    O->>DB: Commit
    O-->>API: orderId
    E-->>N: OrderPlaced (sau commit)
    E-->>L: OrderPlaced (sau commit)
    N->>N: Gửi xác nhận
    L->>L: Cộng điểm
~~~

Sơ đồ mô tả **quan hệ logic** và bỏ qua chi tiết lịch thực thi của các listener bất đồng bộ; thứ tự xử lý giữa notifications và loyalty **không được bảo đảm**. Một listener có thể thành công trong khi listener còn lại thất bại.

Thiết kế package hỗ trợ bảo trì trực tiếp:

- Muốn sửa quy tắc tạo đơn: vào `orders.internal`.
- Muốn thêm dữ liệu được công bố: xem `orders.events` cùng các consumer.
- Muốn thay đổi mẫu email: vào `notifications.internal`.
- Muốn điều chỉnh chính sách cộng điểm: vào `loyalty.internal`.
- Muốn tìm bên phát sự kiện: tìm `publishEvent(new OrderPlaced(...))` trong module orders.
- Muốn tìm mọi bên nhận: tìm các listener có tham số `OrderPlaced` trên toàn dự án.

Publisher không phải thay đổi chỉ vì module mới đăng ký xử lý cùng sự kiện. Nhưng event contract vẫn là phụ thuộc chung cần được quản trị khi thay đổi.

## 9. Đặt cấu hình Event Publication Registry và cơ chế retry

Spring Modulith cung cấp **Event Publication Registry** để theo dõi publication đến các transactional event listener. Khi cấu hình một cơ chế lưu trữ phù hợp (ví dụ qua integration persistence được hỗ trợ), publication có thể được ghi nhận và đánh dấu hoàn tất khi consumer xử lý thành công.

Cách chia trách nhiệm hợp lý là:

| Thành phần | Vị trí gợi ý | Trách nhiệm |
| --- | --- | --- |
| Event contract | `orders.events` | Mô tả sự kiện do orders sở hữu. |
| Publisher | `orders.internal` | Công bố sự kiện khi nghiệp vụ tạo đơn diễn ra. |
| Transactional listener | `notifications.internal`, `loyalty.internal` | Xử lý hành vi của consumer sau commit. |
| Persistence/configuration của registry | Cấu hình ứng dụng và module hạ tầng phù hợp | Bật lưu publication, cơ chế khôi phục và cấu hình liên quan. |
| Idempotency | Consumer sở hữu tác dụng phụ | Chống gửi thông báo/cộng điểm hai lần khi xử lý lại. |
| Retry/recovery policy | Phần vận hành sự kiện và consumer liên quan | Xác định khi nào phát lại, số lần thử, xử lý lỗi kéo dài. |
| Monitoring/tracing | Cấu hình observability và các consumer | Theo dõi publication chưa hoàn tất, thời gian xử lý, lỗi. |

Không nên tạo `com.acme.shop.events` chỉ để làm "điểm tập kết" mọi event của orders, payments và loyalty. Điều này làm mờ chủ sở hữu hợp đồng, khuyến khích module đi vòng qua ranh giới nghiệp vụ. Registry cũng **không bắt buộc phải là một module nghiệp vụ riêng**: đây là năng lực hạ tầng của Spring Modulith, được cấu hình phù hợp với hệ thống.

Một chi tiết quan trọng khác: **registry không tự biến mọi lần xử lý thành exactly-once**. Ví dụ listener đã gửi email thành công nhưng ứng dụng dừng trước khi ghi nhận publication đã hoàn tất; lần retry có thể gửi lại email. Vì thế:

~~~text
notifications.internal
├── SendOrderConfirmation.java
├── NotificationGateway.java
└── NotificationDeliveryRepository.java  # theo dõi idempotency nếu cần
~~~

Nếu gửi thông báo có thể lặp, consumer có thể lưu khóa duy nhất kiểu `(eventType, orderId, channel)` hoặc một định danh sự kiện ổn định trong kho dữ liệu của mình. Cách triển khai cụ thể tùy yêu cầu nghiệp vụ và hệ thống gửi thông báo. Với cộng điểm, có thể dùng ràng buộc duy nhất theo `orderId + pointRule` để tránh ghi điểm lặp.

**Giới hạn:** nếu chỉ dùng `ApplicationEventPublisher` trong bộ nhớ mà không cấu hình cơ chế lưu publication và recovery phù hợp, không thể suy ra rằng sự kiện sẽ được phát lại an toàn sau khi ứng dụng gặp sự cố. Thiết kế đáng tin cậy là sự kết hợp của publisher đúng transaction, registry khi cần, listener an toàn khi retry và công cụ quan sát.

## 10. Kiểm tra ranh giới module

Cấu trúc package chỉ mang lại lợi ích khi có kiểm tra tự động. Spring Modulith cung cấp mô hình `ApplicationModules` để phân tích phụ thuộc và phát hiện những quan hệ không hợp lệ.

Ví dụ kiểm tra toàn ứng dụng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Trong cấu trúc đã gợi ý, hai phụ thuộc sau phải được tránh:

~~~java
// SAI: notifications truy cập implementation của orders
import com.acme.shop.orders.internal.OrderRepository;

// SAI: orders gọi trực tiếp implementation của notifications
import com.acme.shop.notifications.internal.NotificationGateway;
~~~

Thay vào đó, consumer chỉ import:

~~~java
// ĐÚNG: phụ thuộc vào hợp đồng sự kiện được export
import com.acme.shop.orders.events.OrderPlaced;
~~~

Với `@NamedInterface("events")` và `allowedDependencies = "orders::events"`, test kiến trúc giúp phát hiện khi một thay đổi vô tình tạo phụ thuộc ngoài ý muốn. Điều kiện chính xác của phép kiểm tra còn phụ thuộc cách mô tả module và các quy tắc verify được cấu hình.

### Kiểm thử event ở đúng module

Có thể tạo các bài kiểm thử riêng:

- **`OrderModuleTests`** trong ngữ cảnh orders dùng `@ApplicationModuleTest`, kiểm tra gọi nghiệp vụ tạo đơn sẽ công bố `OrderPlaced` với dữ liệu mong đợi. Spring Modulith có `PublishedEvents` để hỗ trợ kiểm tra event đã công bố.
- **`NotificationModuleTests`** kiểm tra một `OrderPlaced` hợp lệ khiến module notifications gửi xác nhận đúng đơn hàng. Mô phỏng lỗi dịch vụ gửi và thử lại để đánh giá idempotency.
- **Kiểm thử tích hợp giao dịch** xác nhận listener sau commit không chạy nếu transaction tạo đơn rollback.
- **Kiểm thử recovery** trên cấu hình registry thực tế để kiểm tra publication còn dang dở, khả năng khôi phục và trạng thái hoàn tất.

Với listener bất đồng bộ, kiểm thử cần chờ/đồng bộ kết quả một cách xác định, tránh giả định listener đã chạy xong ngay khi phương thức publisher trả về.

## 11. Các cách tổ chức dễ gây vấn đề

### 11.1. Chia theo tầng kỹ thuật ở cấp toàn ứng dụng

~~~text
com.acme.shop
├── controllers/
├── services/
├── repositories/
├── listeners/
└── events/
~~~

Các package này trộn mã của nhiều nghiệp vụ. Với phát hiện module mặc định, chúng còn có thể được nhận diện thành các module `controllers`, `services`, `repositories` không phản ánh ranh giới nghiệp vụ. Khi thay đổi một tính năng, lập trình viên phải sửa trải rộng nhiều package.

**Điều chỉnh:** tổ chức `orders`, `notifications`, `loyalty` làm package module; bên trong từng module mới chia `internal`, `api`, `events` hoặc các package theo nhu cầu.

### 11.2. Gom mọi event vào một package toàn cục

~~~text
com.acme.shop.events
├── OrderPlaced.java
├── PaymentCompleted.java
└── LoyaltyPointsAwarded.java
~~~

Một package `events` toàn cục che mất việc OrderPlaced do orders sở hữu, còn PaymentCompleted do payments sở hữu. Consumer có thể bắt đầu phụ thuộc vào một "shared event module" chứa mọi thứ.

**Điều chỉnh:** mỗi event contract đặt gần module phát hành, ví dụ `orders.events` và `payments.events`; chỉ có một module giao tiếp/hợp đồng thực sự độc lập khi nghiệp vụ cần thiết.

### 11.3. Đặt listener trong module phát hành chỉ để tiện tìm kiếm

~~~text
orders.internal
├── OrderApplicationService.java
├── SendOrderEmailListener.java
└── AwardLoyaltyPointsListener.java
~~~

Hai listener làm công việc của notifications và loyalty nhưng nằm bên trong orders. Điều này khiến module orders phải biết các phụ thuộc kỹ thuật của module khác.

**Điều chỉnh:** listener đặt tại module **chịu trách nhiệm tác dụng phụ**. Có thể lập một tài liệu liệt kê các consumer của OrderPlaced để tiện truy vết mà không cần gom mọi listener vào một nơi.

### 11.4. Cho phép truy cập trực tiếp implementation

~~~text
notifications.internal.SendOrderConfirmation
    -> orders.internal.OrderRepository
~~~

Ngay cả khi mã Java vẫn biên dịch, phụ thuộc này có thể làm rò rỉ mô hình persistence, phá ranh giới module và khiến thay đổi nội bộ của orders tác động tới notifications.

**Điều chỉnh:** gửi đủ dữ liệu ổn định trong event hoặc tạo một interface truy vấn công khai có mục đích rõ ràng. Không export toàn bộ `internal` để giải quyết một nhu cầu cục bộ.

### 11.5. Dùng event để thay thế mọi lời gọi trực tiếp

Khi module gọi cần kết quả **ngay lập tức** để đưa ra quyết định trong cùng luồng nghiệp vụ, một lời gọi qua API đồng bộ rõ ràng có thể phù hợp hơn. Event sau commit lý tưởng cho việc phản ứng khi một sự thật đã xảy ra, nhưng có thể tạo độ trễ và nhất quán cuối cùng giữa các module.

Ví dụ, xác nhận hạn mức thanh toán trước khi chấp nhận đơn cần được mô hình hóa thành bước nghiệp vụ có kết quả rõ ràng. Gửi email xác nhận sau khi tạo đơn thành công là ứng viên tốt cho event.

## 12. Quy tắc lựa chọn cấu trúc package

| Tình huống | Cách tổ chức gợi ý | Lý do |
| --- | --- | --- |
| Dự án mới, ít event | Đặt `OrderPlaced` ngay trong `orders`. | Hợp đồng được export từ package gốc, đơn giản khi học. |
| Module có nhiều event | `orders.events` + `@NamedInterface("events")`. | Tách hợp đồng sự kiện và đặt giới hạn phụ thuộc rõ. |
| Module có nhiều API khác nhau | Tạo named interface theo mục đích như `api`, `events`. | Consumer chỉ dùng phần thực sự cần. |
| Gửi thông báo sau khi tạo đơn | Listener trong `notifications.internal`. | Notifications sở hữu chính sách gửi thông báo. |
| Cộng điểm sau khi tạo đơn | Listener trong `loyalty.internal`. | Loyalty sở hữu chính sách điểm và chống trùng. |
| Tác vụ sau commit có thể thất bại | Dùng transactional listener, cấu hình registry/recovery theo nhu cầu. | Theo dõi publication chưa hoàn tất và quản lý retry. |
| Cần kiểm soát ranh giới | `package-info.java` + `ApplicationModules.verify()`. | Phát hiện module phụ thuộc vào implementation không hợp lệ. |
| Cần thay đổi event schema | Giữ payload nhỏ, đánh giá consumer và publication còn tồn. | Giảm rủi ro mất tương thích khi phát lại. |

### Danh sách kiểm tra khi tạo một module mới

1. Xác định **năng lực nghiệp vụ** mà module sở hữu và tạo một package con trực tiếp dưới package ứng dụng.
2. Đặt service, repository, entity và chính sách nội bộ trong `<module>.internal` hoặc các package con nội bộ có tên rõ nghĩa.
3. Xác định event nào là **sự thật do module này phát hành**, tạo record bất biến với payload tối thiểu.
4. Export event qua package gốc module hoặc một named interface như `events`.
5. Đặt listener tại module sở hữu **hành vi tiêu thụ**, không dồn về publisher.
6. Nếu cần, khai báo `allowedDependencies` và chạy `ApplicationModules.verify()`.
7. Kiểm thử công bố sự kiện, xử lý sau commit, rollback, lỗi và phát lại.
8. Với tác vụ quan trọng, thiết kế idempotency và theo dõi publication chưa hoàn tất trước khi đưa vào vận hành.

## 13. Bài tập thực hành

Từ cấu trúc trên, hãy bổ sung tính năng gửi cảnh báo nội bộ khi đơn hàng bị hủy:

- Module `orders` công bố `OrderCancelled(orderId, occurredAt)` trong `orders.events`.
- Module mới `audit` nằm trực tiếp dưới `com.acme.shop`.
- `audit.internal` có listener `RecordOrderCancellation` dùng `@ApplicationModuleListener`.
- `audit/package-info.java` giới hạn phụ thuộc vào `orders::events`.
- Không thêm import của `audit.internal` vào `orders.internal`.
- Bổ sung kiểm thử cho event khi hủy đơn, tình huống rollback, và kiểm tra ranh giới module.

Câu hỏi cần giải thích sau khi thực hiện: **Nếu audit ghi dữ liệu thành công nhưng listener chưa được đánh dấu hoàn tất, điều gì xảy ra khi phát lại?** Gợi ý: thiết kế khóa duy nhất dựa trên `orderId` và loại thao tác audit để ghi nhận trùng lặp an toàn.

**Ghi nhớ:** Cấu trúc package hiệu quả cho Spring Modulith Application Events bắt đầu từ **module nghiệp vụ**, sở hữu event tại **module phát hành**, đặt listener tại **module tiêu thụ**, công khai chính xác các hợp đồng cần dùng và che giấu implementation. Cách tổ chức này giúp giảm phụ thuộc, kiểm thử độc lập và quản lý tốt hơn các tác vụ sau commit, registry, retry và observability.

