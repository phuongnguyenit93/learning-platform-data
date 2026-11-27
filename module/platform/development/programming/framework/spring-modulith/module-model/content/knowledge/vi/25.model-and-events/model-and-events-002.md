# Module phát event và module khác lắng nghe

Application event cho phép một module công bố sự kiện nghiệp vụ để module khác phản ứng mà module phát không cần biết listener cụ thể nào đang tồn tại. Trong Spring Modulith, event còn là một hợp đồng giữa các application module: module nhận cần truy cập kiểu event được module phát công khai, còn module phát chỉ cần công bố sự kiện sau khi nghiệp vụ của nó đạt trạng thái tương ứng.

Ví dụ, module `orders` phát `OrderPlaced` sau khi ghi nhận đơn hàng. Module `inventory` lắng nghe sự kiện để giữ hàng. Quan hệ phụ thuộc tĩnh được tạo bởi module `inventory` tham chiếu kiểu event của `orders`, trong khi luồng sự kiện runtime đi từ `orders` đến listener của `inventory`. Phân biệt hai hướng này là điều quan trọng khi đọc dependency graph.

## 1. Vai trò của publisher và listener

Một luồng event giữa hai module có ba thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Event contract | Kiểu dữ liệu công khai mô tả sự kiện nghiệp vụ đã xảy ra |
| Publisher module | Phát event sau khi thực hiện thay đổi nghiệp vụ của mình |
| Listener module | Đăng ký xử lý event và thực hiện phần nghiệp vụ thuộc trách nhiệm của nó |

Publisher không gọi trực tiếp service của listener. Nó phát event qua `ApplicationEventPublisher`, một abstraction của Spring. Spring tìm listener phù hợp và chuyển event tới các phương thức đã đăng ký.

```text
Mô hình phụ thuộc tĩnh:
inventory ───── phụ thuộc kiểu OrderPlaced ─────> orders

Luồng event runtime:
orders ───── publish OrderPlaced ─────> inventory listener
```

Mũi tên thứ nhất mô tả module nào cần biết hợp đồng của module nào. Mũi tên thứ hai mô tả nơi phát và nơi nhận event khi ứng dụng chạy. Module `orders` không cần import `InventoryOnOrderPlaced` hay biết module `inventory` đang lắng nghe.

## 2. Đặt event contract ở API công khai của module phát

Event được module khác sử dụng phải nằm trong phần API được công khai của module phát. Có thể đặt event trong package gốc của module hoặc tạo named interface riêng cho event.

Với ứng dụng bán hàng, cấu trúc package có thể là:

```text
com.acme.shop
├── orders
│   ├── package-info.java
│   ├── OrderManagement.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal
│       └── OrderRepository.java
└── inventory
    ├── package-info.java
    └── InventoryOnOrderPlaced.java
```

Đánh dấu package event là named interface của module `orders`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
```

Sau đó định nghĩa event contract dưới dạng kiểu bất biến:

```java
// OrderPlaced.java
package com.acme.shop.orders.events;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        Instant occurredAt,
        List<PlacedOrderLine> lines) {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
```

```java
// PlacedOrderLine.java
package com.acme.shop.orders.events;

import java.util.UUID;

public record PlacedOrderLine(
        UUID productId,
        int quantity) {
}
```

`OrderPlaced` là một sự kiện nghiệp vụ ở thì quá khứ: đơn hàng đã được ghi nhận. Payload chỉ mang thông tin mà listener cần để thực hiện trách nhiệm của nó. `PlacedOrderLine` cũng là một phần của hợp đồng event, vì vậy nó được đặt trong cùng package API.

Không nên truyền trực tiếp JPA entity hoặc object nội bộ của module phát. Event contract cần ổn định, bất biến và đủ rõ để listener không phải truy cập repository hay trạng thái nội bộ của publisher. Nếu payload có collection, dùng collection bất biến hoặc sao chép dữ liệu đầu vào khi tạo event để tránh thay đổi sau khi phát.

## 3. Giới hạn module listener vào named interface

Module `inventory` cần sử dụng event contract của `orders`. Có thể khai báo allowlist trên package gốc của `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
```

`orders::events` cho phép module `inventory` phụ thuộc named interface `events` của module `orders`. Module listener không cần quyền truy cập `orders.internal` hoặc các implementation khác.

Nếu không dùng `allowedDependencies`, Spring Modulith vẫn phát hiện quan hệ phụ thuộc qua kiểu event được tham chiếu. Khi muốn giới hạn rõ hợp đồng mà module tiêu thụ được phép sử dụng, khai báo named interface và allowlist giúp ý định kiến trúc dễ đọc, dễ kiểm chứng hơn.

## 4. Publisher phát event bằng ApplicationEventPublisher

Publisher thực hiện nghiệp vụ của mình rồi phát event. Ví dụ sau tạo đơn hàng trong một transaction và công bố `OrderPlaced` sau khi đã lưu dữ liệu:

```java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.acme.shop.orders.events.OrderPlaced;
import com.acme.shop.orders.events.PlacedOrderLine;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderManagement(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    UUID place(PlaceOrderCommand command) {
        Order order = Order.create(command);
        orders.save(order);

        List<PlacedOrderLine> lines = order.getLines().stream()
                .map(line -> new PlacedOrderLine(
                        line.getProductId(), line.getQuantity()))
                .toList();

        events.publishEvent(new OrderPlaced(
                order.getId(), Instant.now(), lines));

        return order.getId();
    }
}
```

`ApplicationEventPublisher.publishEvent(...)` gửi event vào Spring application event infrastructure. Publisher chỉ biết kiểu event và abstraction phát event; nó không tham chiếu listener hoặc service của `inventory`.

Trong ví dụ, `@Transactional` đặt transaction bao quanh thao tác lưu đơn hàng và phát event. Điều này quan trọng khi listener sử dụng cơ chế transactional event listener: listener chỉ được kích hoạt sau khi transaction publisher commit thành công. Nếu transaction rollback, listener mặc định không xử lý event đó.

## 5. Listener xử lý event bằng @ApplicationModuleListener

Trong module `inventory`, tạo một component lắng nghe event:

```java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderPlaced {

    private final InventoryManagement inventory;

    InventoryOnOrderPlaced(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        event.lines().forEach(line ->
                inventory.reserve(
                        line.productId(),
                        line.quantity(),
                        event.orderId()));
    }
}
```

`@ApplicationModuleListener` là annotation tiện ích của Spring Modulith dành cho listener giữa các module. Annotation này kết hợp xử lý bất đồng bộ với transactional event listener và transaction riêng cho phần xử lý listener. Về bản chất, nó kết hợp các hành vi tương ứng với `@Async`, `@Transactional(propagation = REQUIRES_NEW)` và `@TransactionalEventListener`.

Với cấu hình mặc định:

- Listener được gọi sau khi transaction của publisher commit.
- Việc xử lý listener được thực hiện bất đồng bộ thông qua cơ chế task executor của Spring.
- Listener chạy trong transaction riêng với propagation `REQUIRES_NEW`.
- Nếu transaction publisher rollback, transactional listener không được gọi.

Điều này giúp publisher hoàn tất transaction nghiệp vụ của mình mà không phải chờ toàn bộ công việc của listener hoàn tất. Đổi lại, lỗi xảy ra trong listener không thể làm rollback transaction đã commit của publisher.

## 6. Phân biệt @EventListener và @ApplicationModuleListener

Spring cung cấp `@EventListener` và `@TransactionalEventListener`; Spring Modulith bổ sung `@ApplicationModuleListener` để thể hiện rõ ý định tích hợp giữa application module.

| Annotation | Đặc điểm chính | Khi phù hợp |
|---|---|---|
| `@EventListener` | Xử lý event theo cơ chế listener thông thường; mặc định gọi đồng bộ khi event được phát | Phản ứng nội bộ đơn giản, không cần ràng buộc theo transaction commit |
| `@TransactionalEventListener` | Gắn thời điểm xử lý với transaction phase, mặc định là `AFTER_COMMIT` | Cần kiểm soát rõ listener chạy trước hay sau commit |
| `@ApplicationModuleListener` | Listener bất đồng bộ, transactional, dùng transaction riêng và phù hợp cho tích hợp module | Module nhận xử lý event được công bố bởi module khác |

Không nên chọn annotation chỉ vì tên ngắn hơn. Hãy xác định listener cần chạy đồng bộ hay bất đồng bộ, có cần transaction hay không, và có cần bảo đảm chỉ xử lý sau khi publisher commit hay không.

## 7. Event Publication Registry theo dõi việc xử lý

Khi dùng transactional event listener, Spring Modulith có thể theo dõi publication thông qua Event Publication Registry. Registry ghi nhận event publication cần được giao tới từng listener transactional, sau đó cập nhật trạng thái khi listener xử lý thành công.

Vòng đời khái quát:

```text
Publisher transaction bắt đầu
        │
        ▼
Ghi dữ liệu nghiệp vụ + publish event
        │
        ▼
Ghi nhận event publication cho listener
        │
        ▼
Publisher transaction commit
        │
        ▼
Listener được kích hoạt
        │
        ├── Xử lý thành công ──> Publication được đánh dấu hoàn tất
        │
        └── Xử lý thất bại ───> Publication còn chưa hoàn tất
```

Publication registry giúp nhận biết listener nào đã xử lý và listener nào còn publication chưa hoàn tất. Khi cấu hình một implementation lưu trữ bền vững phù hợp (chẳng hạn JDBC, JPA hoặc MongoDB), thông tin publication có thể tồn tại qua lần khởi động lại ứng dụng. Điều này tạo nền tảng để quan sát và resubmit các publication còn dang dở theo cơ chế Spring Modulith cung cấp.

Registry không biến listener thành exactly-once processing. Một listener có thể được thực thi lại trong quá trình phục hồi hoặc khi publication được resubmit. Vì vậy, handler nên được thiết kế idempotent: xử lý lặp lại cùng một `orderId` không tạo ra kết quả sai hoặc giữ hàng hai lần.

## 8. Xử lý lỗi và thiết kế listener idempotent

Giả sử listener giữ hàng cho một đơn. Nếu xử lý thành công nhưng ứng dụng dừng trước khi publication được đánh dấu hoàn tất, publication có thể được xem là chưa hoàn tất và được xử lý lại. Hoặc một lần resubmit có thể gọi handler lần nữa sau khi lỗi hạ tầng được khắc phục.

Một cách thiết kế là dùng `orderId` làm khóa nghiệp vụ để tránh giữ hàng lặp:

```java
@Service
class InventoryManagement {

    private final ReservationRepository reservations;

    @Transactional
    void reserve(UUID productId, int quantity, UUID orderId) {
        if (reservations.existsByOrderIdAndProductId(orderId, productId)) {
            return;
        }

        reservations.save(Reservation.create(orderId, productId, quantity));
        // Cập nhật lượng tồn kho trong cùng transaction.
    }
}
```

Ví dụ này minh họa ý tưởng; repository và cơ chế chống trùng cần được triển khai phù hợp với database thực tế. Nếu có nhiều worker xử lý đồng thời, nên dùng unique constraint hoặc thao tác ghi có tính nguyên tử thay vì chỉ dựa vào bước kiểm tra trước khi insert.

Khi listener thất bại, cần quan sát exception và publication chưa hoàn tất. Tùy persistence implementation và cách vận hành, nhóm có thể dùng API hoặc Actuator support của Spring Modulith để xem và resubmit các publication chưa hoàn tất. Không nên tự xóa publication lỗi trước khi hiểu nguyên nhân và xác định chính sách phục hồi.

## 9. Chọn dữ liệu event và ranh giới hợp đồng

Event là hợp đồng công khai nên cần được thiết kế cẩn thận:

- **Dùng tên thể hiện sự kiện đã xảy ra:** `OrderPlaced`, `PaymentCaptured`, `CustomerRegistered`.
- **Chỉ đưa dữ liệu cần thiết:** listener nhận đủ thông tin để thực hiện trách nhiệm của mình mà không cần truy cập package nội bộ của publisher.
- **Ưu tiên type bất biến:** Java record phù hợp với payload dạng dữ liệu.
- **Tránh truyền entity hoặc repository:** listener không nên nắm vòng đời persistence nội bộ của module phát.
- **Ổn định hóa hợp đồng:** thay đổi tên field, kiểu dữ liệu hoặc ngữ nghĩa event có thể ảnh hưởng tất cả listener.
- **Không giả định thứ tự giữa nhiều listener bất đồng bộ:** nếu nghiệp vụ phụ thuộc thứ tự, cần mô hình hóa quan hệ đó rõ ràng hoặc thiết kế một quy trình điều phối.
- **Thiết kế cho xử lý lặp:** listener nên chịu được việc nhận lại event khi có phục hồi hoặc retry.

Nếu event cần được gửi ra message broker hoặc hệ thống bên ngoài, đó là bước externalization riêng. Application event nội bộ không tự động trở thành message Kafka, RabbitMQ hay sự kiện tích hợp qua mạng. Hãy phân biệt event giữa các module trong cùng ứng dụng với integration event được công bố ra ngoài.

## 10. Kiểm chứng dependency và event flow

Có thể dùng `ApplicationModules` để kiểm tra ranh giới module:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleEventContract() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu module `inventory` tham chiếu `OrderPlaced` từ named interface `orders::events`, dependency đó được kiểm tra theo quy tắc API và `allowedDependencies`. Module listener không cần truy cập implementation nội bộ của `orders`.

Ngoài kiểm tra kiến trúc, cần có integration test xác nhận event thực sự được phát và listener xử lý đúng. Có thể sử dụng `@ApplicationModuleTest` để khởi động phạm vi module cần thiết, rồi phát event hoặc gọi use case tạo event. Với listener bất đồng bộ và transactional, test phải chờ điều kiện kết quả hoàn tất hoặc dùng cơ chế kiểm tra phù hợp; assert ngay sau khi gọi publisher có thể chạy trước khi listener hoàn thành.

Ví dụ một bài kiểm thử nghiệp vụ có thể xác nhận sau khi đặt đơn, reservation tương ứng xuất hiện. Khi viết test, cần kiểm soát transaction test: nếu test bao toàn bộ phương thức trong một transaction chưa commit, listener `AFTER_COMMIT` có thể chưa được gọi cho tới khi transaction đó kết thúc.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Publisher phải gọi service của listener | Publisher phát event qua abstraction; listener tự đăng ký nhận |
| Mũi tên dependency phải cùng chiều event | Listener module phụ thuộc event contract của publisher; runtime event đi từ publisher đến listener |
| Event class có thể nằm trong package internal | Event được module khác tham chiếu phải thuộc API được công khai |
| `@ApplicationModuleListener` chạy ngay trong transaction publisher | Listener mặc định chạy sau commit và trong transaction riêng |
| Publisher rollback nhưng listener vẫn xử lý event | Transactional listener mặc định không chạy khi transaction publisher rollback |
| Listener lỗi làm rollback publisher | Publisher đã commit trước khi listener được kích hoạt; lỗi listener thuộc transaction riêng |
| Event Publication Registry bảo đảm exactly-once | Registry theo dõi publication và trạng thái hoàn tất; handler vẫn cần idempotent |
| `publishEvent()` tự gửi message ra broker | Đây là Spring application event nội bộ; externalization cần cấu hình riêng |
| Test gọi publisher xong có thể assert listener ngay | Listener bất đồng bộ và sau commit; test cần chờ kết quả và quản lý transaction đúng cách |

## 12. Checklist triển khai module event

- [ ] Event contract mô tả một sự kiện nghiệp vụ đã xảy ra.
- [ ] Event type và các payload type liên quan nằm trong API được công khai của module phát.
- [ ] Module nhận chỉ được phép phụ thuộc named interface cần thiết.
- [ ] Publisher phát event qua `ApplicationEventPublisher` sau khi hoàn tất thay đổi nghiệp vụ phù hợp.
- [ ] Publisher transaction được cấu hình đúng khi listener cần xử lý sau commit.
- [ ] Listener dùng `@ApplicationModuleListener` khi cần xử lý bất đồng bộ, transactional và độc lập với publisher.
- [ ] Handler có chiến lược idempotency để chịu được việc xử lý lặp.
- [ ] Event Publication Registry có persistence phù hợp nếu cần theo dõi publication qua restart.
- [ ] Có cách quan sát và phục hồi publication chưa hoàn tất.
- [ ] Architecture test xác minh module dependency và integration test xác nhận event flow thực tế.
- [ ] Không giả định thứ tự xử lý giữa các listener bất đồng bộ nếu chưa thiết kế điều phối.

Spring Modulith giúp event trở thành một hợp đồng module có thể kiểm chứng. Publisher công bố sự kiện nghiệp vụ qua API ổn định, listener phụ thuộc vào hợp đồng đó và xử lý phần việc thuộc module của mình. Khi kết hợp transactional listener, Event Publication Registry và handler idempotent, modular monolith có thể tách trách nhiệm giữa các module mà vẫn kiểm soát được vòng đời event.

## Tài liệu tham khảo

- [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)
- [EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith – Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
