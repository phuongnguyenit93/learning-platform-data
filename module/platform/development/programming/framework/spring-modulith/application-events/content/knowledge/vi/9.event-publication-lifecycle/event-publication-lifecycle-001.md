# Tạo event trong chu kỳ phát hành Spring Modulith

## 1. Tạo event là bước đầu của chu kỳ phát hành

Trong Spring Modulith, các module nghiệp vụ trao đổi thông tin thông qua **application events** để giảm lời gọi trực tiếp và bảo vệ ranh giới module. Ví dụ, module `orders` xác nhận một đơn hàng đã được đặt, sau đó công bố sự kiện `OrderPlaced`; module `notifications` gửi thông báo, `loyalty` xét cộng điểm và `audit` ghi lại hoạt động.

Chu kỳ xử lý một sự kiện có thể được nhìn ở nhiều bước:

~~~mermaid
flowchart LR
    A["Xử lý nghiệp vụ<br/>và kiểm tra điều kiện"] --> B["Tạo object<br/>OrderPlaced"]
    B --> C["Công bố<br/>publishEvent"]
    C --> D["Commit<br/>giao dịch"]
    D --> E["Listener<br/>sau commit"]
    E --> F["Xử lý / ghi nhận<br/>kết quả"]
~~~

Sơ đồ thể hiện **luồng điển hình khi dùng listener sau commit**, không phải thứ tự bắt buộc với mọi loại listener. `@EventListener` đồng bộ thông thường có thể chạy ngay lúc `publishEvent`, trước khi transaction commit; `@ApplicationModuleListener` xử lý sau commit theo mô hình của Spring Modulith.

**Tạo event** là **xây dựng một đối tượng mô tả sự thật nghiệp vụ**. Đây là bước khác với **công bố event**, tức chuyển đối tượng đó vào `ApplicationEventPublisher`, và cũng khác với **listener xử lý event**, tức thực hiện phản ứng ở module khác.

~~~java
// (1) Tạo object sự kiện trong JVM.
OrderPlaced event = new OrderPlaced(
        eventId, orderId, occurredAt, totalAmount
);

// (2) Công bố object vừa tạo qua hạ tầng Spring.
applicationEventPublisher.publishEvent(event);
~~~

Lời gọi constructor chỉ tạo dữ liệu trong bộ nhớ. Nó **không tự đăng ký listener, không gửi thông điệp ra broker, không lưu bản ghi publication và không bảo đảm bất kỳ side effect nào đã hoàn tất**.

Bài học thuộc chương **Chu kỳ phát hành** của `SPRING_MODULITH_APPLICATION_EVENTS`, tập trung vào cách xác định **khi nào tạo event**, **tạo từ dữ liệu nào**, **giữ tính nhất quán với transaction** và **thiết kế event để giao lại an toàn**.

## 2. Khi nào một sự kiện được phép tồn tại?

Không phải hành động bắt đầu là một sự thật đã xảy ra. Cần phân biệt:

| Trạng thái nghiệp vụ | Có nên tạo `OrderPlaced`? | Vì sao |
| --- | --- | --- |
| Khách gửi yêu cầu tạo đơn | Chưa | Mới là command/yêu cầu. |
| Yêu cầu không hợp lệ, bị từ chối | Không | Đơn hàng chưa được chấp nhận. |
| Đang tính giá và kiểm tra quy tắc | Chưa | Kết quả có thể thất bại. |
| Dữ liệu đơn đã được nghiệp vụ xác nhận để lưu | Có thể tạo object trong transaction | Đây là thời điểm đủ thông tin để mô tả sự thật dự kiến được commit. |
| Transaction lưu đơn rollback | Không có `OrderPlaced` **đã commit** | Event object có thể từng được tạo trong JVM nhưng không đại diện cho một đơn hàng tồn tại bền vững. |
| Transaction commit thành công | Sự thật tạo đơn được xác lập | Listener sau commit có thể phản ứng theo cấu hình. |

Điều kiện tạo sự kiện phải xuất phát từ **module sở hữu nghiệp vụ**, chẳng hạn orders xác nhận đơn được tạo, payments xác nhận đã thu tiền hoặc shipping xác nhận đã bàn giao kiện hàng.

Không nên công bố `OrderPlaced` ngay sau khi API nhận một HTTP request. Tên này nói rằng **đơn hàng đã được đặt thành công**, không phải **người dùng muốn đặt hàng**. Khi cần mô tả một yêu cầu đang xử lý, nên dùng command như `PlaceOrder`.

### Quy tắc nghiệp vụ làm phát sinh event

Ví dụ trình tự tạo đơn:

1. Đọc yêu cầu và kiểm tra dữ liệu.
2. Kiểm tra giới hạn/quy tắc nghiệp vụ cần có trước khi chấp nhận đơn.
3. Tạo aggregate đơn hàng và tính giá cuối cùng.
4. Ghi đơn hàng vào repository trong transaction.
5. Dựng `OrderPlaced` từ các giá trị đã chốt.
6. Gọi `publishEvent` trong transaction để listener sau commit có thể nhận đúng ngữ nghĩa giao dịch.
7. Transaction commit, rồi các listener sau commit bắt đầu xử lý.

Trình tự cụ thể có thể thay đổi theo mô hình aggregate hoặc cách sinh ID. Điều **bất biến về ngữ nghĩa** là publisher không được phát `OrderPlaced` cho trường hợp nghiệp vụ bị từ chối và không được coi một object được tạo trước rollback là một đơn hàng đã commit.

## 3. Phân biệt event, aggregate và publication

Ba đối tượng này thường xuất hiện gần nhau nhưng có vai trò khác nhau:

| Đối tượng | Ví dụ | Vai trò |
| --- | --- | --- |
| **Aggregate/entity nghiệp vụ** | `Order` | Giữ trạng thái và invariant của đơn hàng. |
| **Event object** | `OrderPlaced` | Snapshot bất biến về sự thật đã xảy ra, được truyền giữa các module. |
| **Event publication record** | Bản ghi do Event Publication Registry quản lý khi đã cấu hình | Theo dõi việc giao sự kiện đến từng listener và trạng thái hoàn tất. |

Không nên đồng nhất `Order` với `OrderPlaced`. Entity thường được cập nhật qua nhiều giao dịch; event phải mô tả một thời điểm cụ thể.

Cũng không nên tự tạo một bảng `event_publications` chỉ vì cần gọi `new OrderPlaced(...)`. Spring Modulith có **Event Publication Registry** và các tích hợp lưu trữ của nó cho mục tiêu theo dõi publication. Việc tạo object Java **chưa tự kích hoạt** cơ chế lưu đó.

Một event có thể được phát cho **nhiều listener**, do đó trạng thái xử lý của notifications và loyalty có thể khác nhau. Đơn hàng có thể đã commit, email gửi thất bại, trong khi điểm thưởng đã ghi thành công.

## 4. Xác định event contract trước khi viết constructor

Trước khi tạo event, cần trả lời: listener cần biết những gì để phản ứng mà không phải truy cập implementation của module phát hành?

Ví dụ một hợp đồng nhỏ:

~~~text
OrderPlaced
  eventId         : UUID        - định danh sự kiện
  orderId         : UUID        - định danh đơn hàng
  occurredAt      : Instant     - thời điểm nghiệp vụ
  currencyCode    : String      - mã tiền tệ
  totalAmount     : BigDecimal  - tổng tiền đã chốt
~~~

Các field này có ý nghĩa:

- **`eventId`**: nhận diện *lần xảy ra* sự kiện; cùng event được retry phải giữ nguyên ID. Không phải field Spring bắt buộc.
- **`orderId`**: tham chiếu đơn hàng. Một đơn có thể phát nhiều sự kiện khác nhau.
- **`occurredAt`**: thời điểm xác lập sự kiện theo nghiệp vụ, không nhất thiết bằng thời điểm consumer xử lý.
- **`currencyCode`**: đơn vị của số tiền; giá trị `500000` không có ý nghĩa tài chính nếu thiếu đơn vị.
- **`totalAmount`**: số tiền đã chốt theo quy tắc của orders, không phải giá niêm yết hiện tại.

Một contract tốt cũng xác định field bắt buộc/tùy chọn, bất biến dữ liệu, các giá trị hợp lệ, thông tin nhạy cảm được phép công bố và cách thay đổi schema qua phiên bản.

**Tránh lấy toàn bộ JPA entity làm payload** chỉ vì constructor dễ viết:

~~~java
// Không nên: rò rỉ chi tiết nội bộ, mutable, lazy loading.
public record OrderPlaced(OrderEntity order) {}
~~~

Một listener chạy sau commit hoặc ở luồng khác có thể gặp entity detached/lazy loading hoặc nhìn thấy trạng thái đã thay đổi. Event nên là một object độc lập và mang dữ liệu có ý nghĩa.

## 5. Thiết kế record bất biến bằng Java

Với Java hiện đại, `record` là lựa chọn thuận tiện cho event chứa dữ liệu. Ví dụ:

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        String currencyCode,
        BigDecimal totalAmount
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(currencyCode, "currencyCode");
        Objects.requireNonNull(totalAmount, "totalAmount");

        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
        if (totalAmount.signum() < 0) {
            throw new IllegalArgumentException(
                    "totalAmount must be non-negative"
            );
        }
    }
}
~~~

Các điều kiện trên là invariant minh họa. `[A-Z]{3}` chỉ kiểm tra hình thức mã tiền tệ, chưa xác nhận mã nằm trong danh mục được nghiệp vụ hỗ trợ. `totalAmount >= 0` phù hợp ví dụ tạo đơn thông thường; sự kiện hoàn tiền hoặc điều chỉnh tiền có thể cần quy tắc khác.

Vì `UUID`, `Instant`, `String` và `BigDecimal` là các kiểu bất biến, record này an toàn khi chia sẻ dữ liệu giữa listener ở mức object.

### Record có tự làm mọi thứ bất biến không?

Không. `record` chỉ tạo field `final`; các component chứa object mutable vẫn có thể bị chỉnh sửa.

Nếu event chứa danh sách sản phẩm:

~~~java
package com.acme.shop.orders.events;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderItemsCaptured(
        UUID eventId,
        UUID orderId,
        List<OrderLineSnapshot> items
) {
    public OrderItemsCaptured {
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }
    }
}
~~~

`List.copyOf` tạo bản danh sách không thể thay đổi qua accessor, nhưng **không deep-copy các phần tử**. Trong ví dụ, `OrderLineSnapshot` cũng cần bất biến (chẳng hạn record chỉ chứa `String`, `int`, `BigDecimal`). Với nested mutable object hay `byte[]`, cần áp dụng defensive copy hoặc chọn kiểu dữ liệu khác.

### Không dùng entity hoặc service trong event

Payload không nên chứa `EntityManager`, repository, Spring bean, `HttpServletRequest`, lazy proxy, transaction context hoặc callback. Những thành phần này không mô tả sự thật nghiệp vụ và thường không phù hợp với việc lưu lại/phát lại một event.

## 6. Sở hữu event theo module nghiệp vụ

Một cấu trúc đơn giản:

~~~text
com/acme/shop/
├── ShopApplication.java
├── orders/
│   ├── events/
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── OrderService.java
│       ├── OrderRepository.java
│       └── Order.java
├── notifications/
│   └── internal/
│       └── OrderPlacedListener.java
└── loyalty/
    └── internal/
        └── LoyaltyPointsListener.java
~~~

`orders` sở hữu `OrderPlaced`, vì module này quyết định điều kiện tạo đơn thành công. Các module khác chỉ **sử dụng hợp đồng event được công khai**, không phải service/repository nội bộ của orders.

Với Spring Modulith, có thể công khai package `orders.events` qua named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Consumer có thể hạn chế phụ thuộc:

~~~java
// notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.notifications;
~~~

Nếu hợp đồng ít, event cũng có thể đặt trực tiếp tại package gốc `orders` thuộc API mặc định của module. Việc chọn package là quyết định thiết kế, nhưng **không nên để notifications định nghĩa event mô tả một sự thật do orders sở hữu**.

## 7. Tạo event từ trạng thái nghiệp vụ đã chốt

Giả sử use case tạo đơn đã kiểm tra đầu vào và tính tiền. Một service trong module orders có thể dựng `OrderPlaced` tại thời điểm có dữ liệu cuối cùng.

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

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = Order.createFrom(command);
        Order persisted = repository.save(order);

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                persisted.getId(),
                clock.instant(),
                persisted.getCurrencyCode(),
                persisted.getTotalAmount()
        );

        events.publishEvent(event);
        return persisted.getId();
    }
}
~~~

Các kiểu `Order`, `OrderRepository` và `PlaceOrderCommand` là các kiểu nghiệp vụ minh họa; chúng cần được định nghĩa và cung cấp trong dự án thật. Ví dụ giả định `repository.save` trả về entity có ID đã được gán và tổng tiền đã xác định.

**Lý do dựng event sau khi tạo trạng thái:**

1. Không phát event khi việc kiểm tra yêu cầu thất bại.
2. Dùng `orderId` thực tế của đối tượng được lưu.
3. Chụp tổng tiền/tiền tệ đã tính theo nghiệp vụ, tránh để consumer tính lại theo dữ liệu mới nhất.
4. Gắn việc publish với transaction đang cập nhật đơn, tạo điều kiện cho các listener sau commit chỉ phản ứng khi transaction thành công.

Nếu ID do database sinh ra, bảo đảm nó sẵn có tại thời điểm dựng event theo cơ chế persistence thực tế. Nếu dự án dùng ID được gán từ application, có thể xác định ID ngay khi khởi tạo aggregate.

### Không nhầm tính đúng của object với tính đúng của transaction

Lời gọi `new OrderPlaced(...)` có thể thành công, và `publishEvent(event)` có thể được gọi, nhưng transaction **vẫn có thể rollback**. Tạo object hợp lệ là điều kiện cần; nó không chứng minh bản ghi đơn hàng đã commit.

Với `@ApplicationModuleListener` hoặc `@TransactionalEventListener(AFTER_COMMIT)`, xử lý được gắn với sự kiện transaction commit. Còn listener `@EventListener` đồng bộ thông thường có thể xử lý **trước commit**, cần được cân nhắc khi có tác dụng phụ khó hoàn tác.

## 8. Tạo event và công bố event: hai trách nhiệm khác nhau

Một thiết kế có thể tách việc **sản sinh dữ liệu sự kiện** khỏi **cách phát sự kiện**. Ví dụ:

~~~java
final class OrderEventFactory {

    private final Clock clock;

    OrderEventFactory(Clock clock) {
        this.clock = clock;
    }

    OrderPlaced placed(Order order) {
        return new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                clock.instant(),
                order.getCurrencyCode(),
                order.getTotalAmount()
        );
    }
}
~~~

Factory ở đây minh họa việc tập trung quy tắc dựng event. Nó không bắt buộc: nếu chỉ có một sự kiện đơn giản, tạo record ngay trong application service cũng đủ rõ.

Khi dùng factory cần tránh **tự động phát event trong constructor** hoặc một phương thức getter. Tạo và công bố là hai quyết định có ngữ nghĩa khác nhau:

- Tạo dữ liệu nên dễ kiểm thử như một thao tác thuần từ state và clock/ID generator.
- Công bố cần đúng thời điểm nghiệp vụ và transaction.
- Một object được dựng để kiểm thử, preview hoặc tính toán **không nhất thiết phải được phát**.
- Nếu transaction nghiệp vụ thất bại, không được coi event object chưa công bố là một publication thực sự.

Có dự án chọn aggregate ghi nhận domain events nội bộ, sau đó application service thu thập và phát các event ở ranh giới use case. Mẫu này cũng hợp lệ nếu định nghĩa rõ điểm phát, cách tránh phát trùng và liên hệ với transaction.

## 9. Chọn thời điểm và nguồn dữ liệu cho event

### 9.1. Dữ liệu lịch sử cần snapshot

Nếu email xác nhận phải chứa giá tại thời điểm mua, event nên có snapshot giá/line item khi những dữ liệu đó đã chốt. Listener chạy trễ có thể đọc bảng giá đã thay đổi nếu event chỉ chứa `orderId`.

### 9.2. Dữ liệu hiện tại có thể truy vấn sau

Một consumer chỉ cần trạng thái khách hàng mới nhất có thể tra cứu qua **API công khai** của module sở hữu thông tin đó. Không nên nhét mọi trường của customer vào event rồi vô tình phát tán dữ liệu cá nhân cho nhiều listener.

### 9.3. Phân biệt event mỏng và event giàu dữ liệu

| Cách tạo | Ví dụ payload | Phù hợp khi |
| --- | --- | --- |
| Event mỏng | `orderId`, `eventId`, `occurredAt` | Consumer chỉ cần định danh hoặc có API truy vấn ổn định. |
| Event giàu dữ liệu | ID, thời điểm, giá đã chốt, line item snapshot | Consumer cần dữ kiện lịch sử, muốn giảm truy vấn ngược. |

Hai lựa chọn đều có đánh đổi. Event giàu dữ liệu tăng tính độc lập của listener nhưng làm hợp đồng và persisted publication lớn hơn. Event mỏng nhỏ gọn nhưng có thể tạo phụ thuộc truy vấn runtime. Chọn theo **sự thật cần truyền và nhu cầu dữ liệu của consumer**, không theo số field càng nhiều càng tốt.

## 10. Event identity, timestamp và correlation

Khi tạo event, cần phân biệt ba khái niệm:

**`eventId`** là định danh cho một *lần xảy ra sự kiện*. Nếu cùng event được giao lại cho listener do retry/replay, phải giữ nguyên `eventId` để consumer nhận ra cùng một event.

**`aggregateId`** (ví dụ `orderId`) là ID đối tượng nghiệp vụ. Một đơn có thể có `OrderPlaced`, `OrderPaid`, `OrderCancelled`; không được dùng một quy tắc “mỗi `orderId` chỉ xử lý một lần” cho tất cả các event đó.

**`correlationId`** là định danh liên kết các thao tác trong cùng một yêu cầu hoặc quy trình nhiều bước, nếu ứng dụng lựa chọn mang theo nó. Có thể phân biệt nhiều event cùng phát sinh từ một request bằng các `eventId` riêng, đồng thời dùng một `correlationId` chung để trace.

~~~text
command PlaceOrder (correlationId = C-100)
    ├── OrderPlaced (eventId = E-101, orderId = O-1)
    └── OrderReservationRequested (eventId = E-102, orderId = O-1)

retry delivery của OrderPlaced:
    eventId vẫn là E-101
~~~

`occurredAt` nên phản ánh thời điểm nghiệp vụ được ghi nhận theo quy tắc của hệ thống. Nó khác với **thời điểm listener xử lý**, có thể đến sau hàng giây/phút hoặc sau khi hệ thống recovery. Không nên ghi lại `occurredAt = Instant.now()` mỗi lần replay vì như vậy làm biến đổi lịch sử.

### Tạo ID trước hay sau khi lưu?

Nếu sự kiện liên quan tới entity có ID do database sinh, hãy tạo event sau khi đã nhận được ID ổn định. Nếu hệ thống dùng UUID ứng dụng tạo sẵn, có thể gán `orderId` ngay khi khởi tạo entity. Tránh tạo event với ID tạm rồi sửa object event sau đó: event nên bất biến ngay từ lúc dựng xong.

## 11. Transaction và sự kiện có hiệu lực

Giả sử method `placeOrder()` được gắn `@Transactional`:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant O as OrderService
    participant DB as Orders DB
    participant P as Event Publisher
    participant L as After-commit listener

    C->>O: placeOrder(command)
    O->>DB: Lưu order (trong transaction)
    O->>O: new OrderPlaced(...)
    O->>P: publishEvent(event)
    alt Commit thành công
        O->>DB: COMMIT
        P-->>L: Kích hoạt xử lý sau commit
        O-->>C: orderId
    else Transaction rollback
        O->>DB: ROLLBACK
        Note over P,L: Listener sau commit không xử lý event đó
        O-->>C: Lỗi / kết quả thất bại
    end
~~~

Sơ đồ thể hiện ý nghĩa, **không cam kết thứ tự các callback bất đồng bộ so với việc gửi HTTP response**. Khi transaction hoàn tất, listener sau commit có thể được lên lịch và chạy độc lập; `placeOrder` trả về không có nghĩa mọi listener đã chạy xong.

### Ba loại listener cần phân biệt

| Listener | Quan hệ với transaction phát hành | Hệ quả đối với event vừa tạo |
| --- | --- | --- |
| `@EventListener` | Theo cấu hình mặc định, được gọi đồng bộ khi publish. | Có thể chạy cả khi transaction sau đó rollback. |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT`; hỗ trợ các phase khác. | Chỉ chạy ở phase tương ứng khi có transaction; mặc định không chạy nếu không có transaction. |
| `@ApplicationModuleListener` | Trong Spring Modulith, xử lý bất đồng bộ sau commit và có transaction riêng. | Phù hợp các tác vụ giữa module sau khi nghiệp vụ gốc đã commit. |

`@TransactionalEventListener` có cấu hình `fallbackExecution` khi không có transaction; mặc định là `false`. Không giả định một listener transactional sẽ tự chạy khi publisher nằm ngoài transaction.

Không cố gửi email hoặc gọi hệ thống thanh toán trực tiếp trong quá trình tạo `OrderPlaced` nếu tác dụng phụ đó chỉ hợp lệ sau commit. Nếu transaction rollback sau khi email đã gửi, hệ thống sẽ tạo ra xác nhận sai.

## 12. Listener nhận event đã tạo

Ví dụ module notifications tiêu thụ hợp đồng công khai:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final ConfirmationSender sender;

    OrderPlacedListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendConfirmation(
                event.eventId(),
                event.orderId(),
                event.currencyCode(),
                event.totalAmount()
        );
    }
}
~~~

`ConfirmationSender` là giao diện/dịch vụ nội bộ của module notifications cần được xây dựng trong ứng dụng thực tế.

**Trách nhiệm được tách rõ:**

- `orders`: khi nào đơn đã hợp lệ để phát `OrderPlaced`.
- `orders.events`: cấu trúc và ngữ nghĩa của hợp đồng event.
- `notifications`: điều kiện và cách gửi xác nhận.
- `loyalty`: chính sách tính điểm từ đơn hàng.
- Hạ tầng Spring Modulith: phối hợp giao sự kiện và, khi cấu hình, theo dõi publication.

Publisher không cần biết tên lớp `OrderPlacedListener` hay có bao nhiêu listener nhận sự kiện.

## 13. Tạo event không tự bảo đảm giao sự kiện bền vững

Trong Spring thông thường, `ApplicationEventPublisher` chuyển event qua hạ tầng application event **trong tiến trình ứng dụng**. Nó không phải broker hoặc persistent event log mặc định.

Spring Modulith có **Event Publication Registry** hỗ trợ theo dõi việc giao event đến các transactional event listener. Khi cấu hình persistent store phù hợp, hệ thống có thể ghi nhận publication chưa hoàn tất và đánh dấu hoàn tất sau khi listener xử lý thành công.

Các bước cần phân biệt:

| Thời điểm | Ý nghĩa |
| --- | --- |
| `new OrderPlaced(...)` | Object sự kiện được tạo trong bộ nhớ. |
| `publishEvent(event)` | Hạ tầng Spring được yêu cầu công bố event. |
| Ghi nhận publication (nếu dùng registry/persistence) | Hệ thống có dữ liệu theo dõi giao sự kiện cho listener tương ứng. |
| Transaction tạo đơn commit | Sự thật nghiệp vụ gốc được xác lập. |
| Listener sau commit xử lý | Mỗi consumer thực hiện tác vụ của mình. |
| Registry đánh dấu hoàn tất | Consumer cụ thể đã hoàn tất theo cơ chế của registry. |
| Recovery/republication | Xử lý publication chưa hoàn tất theo công cụ và chính sách đã cấu hình. |

Đăng ký một record event đơn thuần không đồng nghĩa registry đã được cấu hình. Hơn nữa, Event Publication Registry **không tự đảm bảo exactly-once đối với side effect bên ngoài**.

Nếu ứng dụng chỉ công bố sự kiện trong bộ nhớ và dừng trước khi listener nhận/xử lý, không thể suy ra hệ thống sẽ tự khôi phục publication đó. Tính bền vững phụ thuộc cơ chế giao, cấu hình storage, transaction và cách vận hành.

## 14. Retry và idempotency bắt đầu từ cách tạo event

Một sự kiện có thể được giao lại vì listener lỗi hoặc tiến trình dừng trước khi registry ghi nhận hoàn tất:

~~~text
1. orders tạo OrderPlaced(eventId=E-1) và commit.
2. notifications gửi email thành công.
3. Ứng dụng dừng trước khi publication được đánh dấu hoàn tất.
4. Publication được replay theo cơ chế recovery.
5. notifications nhận lại OrderPlaced(eventId=E-1).
~~~

Nếu consumer không chống trùng, khách hàng có thể nhận hai email. Vì thế event nên có **khóa nhận dạng ổn định**. Consumer phải chọn khóa idempotency theo ý nghĩa nghiệp vụ, ví dụ `(consumerName, eventId)` hoặc `(orderId, notificationType)`.

Ví dụ bảng ghi nhận:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Với side effect là ghi dữ liệu vào **cùng một cơ sở dữ liệu**, thao tác đánh dấu và cập nhật nghiệp vụ có thể được đặt trong cùng transaction để chống trùng một cách nguyên tử, kết hợp unique constraint.

Với gửi email hoặc gọi API ngoài, transaction DB không tự tạo atomicity với dịch vụ ngoài. Cần một chiến lược riêng như idempotency key được downstream hỗ trợ, trạng thái gửi/đối soát hoặc cơ chế gửi được thiết kế để chịu được retry. Đánh dấu “đã gửi” trước khi thực sự gửi email có nguy cơ làm mất thông báo khi gửi lỗi.

**Không tạo `eventId` mới khi xử lý lại cùng publication.** ID mới làm cơ chế chống trùng hiểu nhầm đây là sự kiện mới. Chỉ tạo event mới với ID mới nếu đó **thực sự là một lần phát sinh nghiệp vụ mới**.

### Khác biệt giữa retry command và retry delivery

Hai lần HTTP request tạo đơn có thể là hai **command invocation** khác nhau, còn hai lần giao cùng `OrderPlaced` là **delivery attempts** của một sự kiện.

Nếu người dùng gửi `PlaceOrder` hai lần do timeout, chống tạo đơn trùng thường cần một **idempotency key của command** hoặc quy tắc nghiệp vụ cấp đơn. `eventId` chỉ giúp consumer nhận biết giao trùng của **event đã được tạo**; nó không giải quyết tự động việc tạo hai aggregate khác nhau.

## 15. Những lỗi thường gặp tại thời điểm tạo event

### 15.1. Tạo event trước khi xác nhận tính hợp lệ

~~~java
// Sai ngữ nghĩa: event mô tả đơn đã được đặt,
// nhưng nghiệp vụ còn có thể từ chối ngay sau đó.
events.publishEvent(new OrderPlaced(...));
validateAndSaveOrder(command);
~~~

Chỉ tạo và phát `OrderPlaced` khi nghiệp vụ đã xác nhận dữ liệu để giao dịch có thể commit. Tách lỗi validation khỏi sự kiện đã xảy ra.

### 15.2. Dùng `Instant.now()` ở mọi listener

Mỗi listener chạy tại thời điểm khác nhau, gây lệch dữ liệu lịch sử. Nên chụp `occurredAt` **một lần khi tạo event**; consumer lưu thêm `processedAt` riêng nếu cần theo dõi độ trễ.

### 15.3. Gắn snapshot vào entity mutable

~~~java
// Dữ liệu order có thể thay đổi sau publish.
new OrderPlaced(orderEntity);
~~~

Snapshot nên chứa dữ liệu bất biến đã chốt. Không dựa vào vòng đời persistence context của publisher trong một listener bất đồng bộ.

### 15.4. Tạo event mỗi lần đọc dữ liệu

Một getter như `getOrderDetails()` không nên âm thầm tạo `OrderPlaced` và publish. Event phải phát sinh từ **thao tác thay đổi nghiệp vụ có điều kiện rõ ràng**, không từ việc đọc.

### 15.5. Phát nhiều lần vì gọi lặp application service

Nếu application service bị retry nguyên phương thức, một nghiệp vụ có thể bị thực hiện lặp nếu không có idempotency của command. Chỉ có `eventId` trong record không ngăn trùng đơn hàng. Cần bảo vệ riêng cho use case tạo đơn.

### 15.6. Cho rằng mọi listener đều sau commit

`@EventListener` thông thường không có ngữ nghĩa mặc định giống `@ApplicationModuleListener`. Chọn annotation theo yêu cầu transaction, không theo tên sự kiện.

### 15.7. Quá nhiều dữ liệu nhạy cảm trong event

Sự kiện có thể được nhiều module tiêu thụ và được lưu để phát lại. Không đưa token, thông tin thẻ hoặc dữ liệu cá nhân không cần thiết vào một event chung; log cũng không nên ghi toàn bộ payload.

### 15.8. Event name không phản ánh sự thật

`OrderPlaced` và `PaymentCaptured` không phải một. Nếu nghiệp vụ cần chờ thanh toán mới xác nhận đơn, phải phát sự kiện theo đúng thời điểm hoặc định nghĩa các trạng thái/sự kiện khác nhau, không làm mờ ngữ nghĩa `OrderPlaced`.

## 16. Kiểm thử bước tạo event

### 16.1. Test constructor và invariant

~~~java
package com.acme.shop.orders.events;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderPlacedContractTest {

    @Test
    void createsValidEvent() {
        UUID orderId = UUID.randomUUID();
        Instant occurredAt =
                Instant.parse("2026-11-25T08:00:00Z");

        var event = new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                occurredAt,
                "VND",
                new BigDecimal("550000")
        );

        assertEquals(orderId, event.orderId());
        assertEquals(occurredAt, event.occurredAt());
        assertEquals("VND", event.currencyCode());
    }

    @Test
    void rejectsInvalidTotal() {
        assertThrows(IllegalArgumentException.class, () ->
                new OrderPlaced(
                        UUID.randomUUID(),
                        UUID.randomUUID(),
                        Instant.now(),
                        "VND",
                        new BigDecimal("-100")
                )
        );
    }
}
~~~

Test này kiểm tra **hợp đồng dữ liệu**, chưa xác minh thời điểm publish hay transaction commit.

### 16.2. Test publisher có tạo đúng event hay không

Spring Modulith hỗ trợ `@ApplicationModuleTest` và `PublishedEvents` để kiểm tra event do module công bố. Các kiểm tra nên gồm:

- Command hợp lệ tạo ra đúng một `OrderPlaced` với `orderId` và số tiền đã chốt.
- Command bị từ chối **không phát** `OrderPlaced`.
- `occurredAt` dùng clock được kiểm soát để test ổn định.
- Các field snapshot khớp dữ liệu nghiệp vụ tại thời điểm xác nhận.
- Module phát hành không import implementation của notifications/loyalty.

Ví dụ hình thức kiểm tra bằng `PublishedEvents`:

~~~java
@ApplicationModuleTest
class OrderModuleEventsTest {

    @Autowired
    OrderService orders;

    @Test
    void publishesPlacedEvent(PublishedEvents events) {
        // Fixture hợp lệ là thành phần do dự án tự định nghĩa.
        var command = OrderFixtures.validPlaceOrder();
        UUID orderId = orders.placeOrder(command);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

Ví dụ này yêu cầu các import JUnit, AssertJ, Spring injection, Spring Modulith test support và fixture `OrderFixtures` phù hợp trong dự án. `PublishedEvents` kiểm tra **đã publish**, không tự khẳng định listener bất đồng bộ đã hoàn tất.

### 16.3. Test commit và rollback

Với listener sau commit, cần có kiểm thử tích hợp:

1. Lưu đơn và publish event trong transaction hợp lệ.
2. Xác nhận listener sau commit xử lý khi transaction commit.
3. Cho transaction rollback sau publish; xác nhận listener sau commit không tạo side effect.
4. Tạo sự cố ở listener và kiểm tra publication chưa hoàn tất/recovery khi đã có cấu hình registry tương ứng.

Không thể chứng minh đầy đủ ngữ nghĩa transaction và recovery bằng việc chỉ mock `ApplicationEventPublisher` trong unit test.

### 16.4. Test ranh giới Spring Modulith

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Hãy đảm bảo `OrderPlaced` thuộc API công khai hoặc named interface của module orders, và các listener không truy cập trực tiếp repository/entity nội bộ. Tên package Java công khai không có nghĩa ranh giới Spring Modulith tự động cho phép mọi phụ thuộc.

## 17. Quan sát từ lúc tạo đến khi xử lý

Khả năng quan sát cần phân biệt ít nhất ba tín hiệu:

1. **Đã dựng event:** object hợp lệ được tạo trong module orders; có thể mới là dữ liệu trong transaction chưa commit.
2. **Đã công bố event:** phương thức `publishEvent` được gọi; chưa chắc consumer sau commit đã hoàn tất.
3. **Listener đã hoàn tất:** consumer xử lý thành công và trạng thái publication được ghi nhận nếu registry đang được sử dụng.

Ví dụ các dòng log do ứng dụng tự quy ước:

~~~text
event=OrderPlaced eventId=E-1 orderId=O-1 stage=CREATED
event=OrderPlaced eventId=E-1 orderId=O-1 stage=PUBLISHED
event=OrderPlaced eventId=E-1 listener=notifications stage=COMPLETED
event=OrderPlaced eventId=E-1 listener=loyalty stage=FAILED attempt=1
~~~

Đây không phải format log tự có của Spring Modulith. `CREATED` hoặc `PUBLISHED` trong log cũng **không đồng nghĩa transaction đã commit**. Với production, nên ghi nhận rõ `orderId`, `eventId`, loại sự kiện, listener, thời điểm, trạng thái và lỗi theo chính sách không lộ dữ liệu nhạy cảm.

Khi cần độ tin cậy cao, hãy giám sát publication chưa hoàn tất, thời gian xử lý, số lần retry và lỗi deserialize khi khôi phục event cũ. Event Publication Registry giúp theo dõi giao sự kiện nếu persistence và recovery được thiết lập; dashboard/alert vẫn cần cấu hình của ứng dụng.

## 18. Checklist trước khi phát event mới

| Câu hỏi | Câu trả lời kỳ vọng |
| --- | --- |
| Event mô tả điều gì đã xảy ra? | Tên và ngữ nghĩa của sự thật nghiệp vụ rõ ràng. |
| Module nào sở hữu? | Module xác lập sự thật, không phải module xử lý hậu quả. |
| Trường hợp nào không được tạo event? | Validation thất bại, nghiệp vụ bị từ chối hoặc không có trạng thái thay đổi hợp lệ. |
| Dữ liệu đã chốt chưa? | Payload có ID, timestamp, giá trị lịch sử phù hợp. |
| Payload có bất biến? | Không lộ mutable entity, defensive copy khi cần. |
| Transaction chứa thao tác nào? | Lưu dữ liệu và publish theo ranh giới transaction dự kiến. |
| Listener cần sau commit? | Chọn `@ApplicationModuleListener` hoặc transactional listener phù hợp. |
| Có eventId ổn định? | Có khi cần trace/retry/idempotency; replay giữ nguyên ID. |
| Có dữ liệu riêng tư hoặc payload quá lớn? | Tối thiểu hóa và kiểm soát retention/truy cập. |
| Có cần recovery? | Cấu hình publication registry/persistence và cách phát lại. |
| Consumer chịu được giao lại? | Có khóa và logic idempotency phù hợp side effect. |
| Có kiểm thử? | Constructor, publisher, rollback, consumer, replay, module boundaries. |

## 19. Bài tập thực hành: phát OrderPlaced đúng thời điểm

Xây dựng module orders và notifications cho yêu cầu sau:

**Nghiệp vụ:** Khách hàng đặt một đơn hàng tổng `550000 VND`. Module orders chỉ chấp nhận đơn khi các dòng hàng hợp lệ. Notifications phải gửi xác nhận **chỉ sau khi đơn hàng commit**.

Yêu cầu thực hiện:

1. Định nghĩa `OrderPlaced(eventId, orderId, occurredAt, currencyCode, totalAmount)` là record bất biến có invariant rõ ràng.
2. Trong `OrderService.placeOrder` có `@Transactional`, kiểm tra đơn, lưu đơn, tạo `OrderPlaced` từ số tiền đã chốt rồi công bố qua `ApplicationEventPublisher`.
3. Đặt event trong API của orders, ví dụ `orders.events` với `@NamedInterface("events")`.
4. Đặt listener `@ApplicationModuleListener` của notifications trong module notifications; không import `orders.internal`.
5. Dùng `Clock.fixed(...)` trong test để chứng minh `occurredAt` được tạo đúng thời điểm và không thay đổi khi xử lý muộn.
6. Cho tạo đơn lỗi sau publish và transaction rollback; xác minh listener sau commit không thực hiện gửi xác nhận.
7. Mô phỏng listener lỗi sau khi gửi email thành công; thiết kế idempotency cho lần phát lại cùng `eventId`.
8. Nếu hệ thống bật Event Publication Registry, kiểm tra publication chưa hoàn tất và thực hiện recovery theo cơ chế đã cấu hình.

**Các câu hỏi cần trả lời:** Tại sao `new OrderPlaced(...)` không phải `publishEvent(...)`? Khi transaction rollback, object event trong bộ nhớ có thể đã được tạo nhưng sự kiện nghiệp vụ có được coi là hoàn tất không? Vì sao retry delivery phải giữ nguyên `eventId`? Nếu hai HTTP request tạo đơn trùng lặp, `eventId` có đủ để ngăn tạo hai đơn không?

**Điểm ghi nhớ:** Tạo event trong Spring Modulith là bước **chụp lại một sự thật nghiệp vụ bằng dữ liệu bất biến** ở đúng ranh giới module và thời điểm nghiệp vụ. Từ object event tới giao sự kiện đáng tin cậy còn có publish, commit, listener, registry, retry và xử lý lỗi. Thiết kế đúng event ngay từ lúc tạo — về tên, dữ liệu, ID, timestamp, transaction và khả năng chống trùng — giúp module giao tiếp ít phụ thuộc, dễ kiểm thử và có thể quan sát, khôi phục khi vận hành.

