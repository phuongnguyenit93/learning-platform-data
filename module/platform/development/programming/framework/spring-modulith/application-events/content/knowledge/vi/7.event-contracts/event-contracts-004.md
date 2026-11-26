# Schema của event trong Spring Modulith

## 1. Schema của event là hợp đồng giữa các module

Trong module học **SPRING_MODULITH_APPLICATION_EVENTS**, các module Spring Modulith giao tiếp bằng application events để giảm phụ thuộc trực tiếp và giữ ranh giới nghiệp vụ. Khi module `orders` công bố `OrderPlaced`, các module `notifications`, `loyalty`, `reporting` có thể nghe cùng sự kiện. Để các module hiểu thông tin một cách nhất quán, event cần một **schema rõ ràng**.

**Schema của event** là tập quy tắc xác định **một sự kiện có nghĩa gì và dữ liệu hợp lệ trông như thế nào**. Schema không chỉ là danh sách field trong lớp Java; nó còn bao gồm tên sự kiện, ý nghĩa nghiệp vụ, kiểu dữ liệu, tính bắt buộc, đơn vị đo, giá trị hợp lệ, cách nhận dạng sự kiện và quy tắc thay đổi theo phiên bản.

Ví dụ, nếu `OrderPlaced` có field `total`, consumer cần biết:

- `total` là tổng trước thuế hay số tiền khách thực tế phải thanh toán?
- Giá trị `350000` được tính bằng VND, USD hay loại tiền nào khác?
- Có thể là `null` hoặc âm không?
- Giá trị là ảnh chụp lúc đặt hàng hay tổng tiền hiện tại?
- Khi `OrderPlaced` được phát lại, giá trị có giữ nguyên không?

Nếu những câu hỏi này không được giải đáp, hai module có thể **biên dịch và chạy thành công nhưng hiểu sai cùng một event**.

~~~mermaid
flowchart LR
    O["orders<br/>Publisher"] -->|"OrderPlacedV1"| C["Event contract<br/>Schema + semantics"]
    C --> N["notifications<br/>Email"]
    C --> L["loyalty<br/>Điểm thưởng"]
    C --> R["reporting<br/>Báo cáo"]
~~~

Schema làm cho ranh giới giữa module trở nên tường minh: publisher sở hữu sự kiện; consumer dựa vào hợp đồng sự kiện, thay vì đọc trực tiếp entity, repository hoặc service nội bộ của publisher.

### Mục tiêu của bài học

Sau khi học, người đọc có thể thiết kế một schema event bằng Java record, giải thích các quy tắc nullability và invariant, nhận biết thay đổi phá vỡ tương thích, tổ chức API module bằng named interface, kiểm tra schema khi publish/replay và xác định yêu cầu vận hành với Event Publication Registry, retry và idempotency.

## 2. Các thành phần của một schema event

Có thể chia schema thành hai nhóm: **thông tin nhận dạng** và **dữ liệu nghiệp vụ**.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên loại event | `OrderPlacedV1` | Nêu sự thật nghiệp vụ đã xảy ra. |
| Chủ sở hữu | Module `orders` | Xác định nơi phát và quản lý hợp đồng. |
| Định danh sự kiện | `eventId` dạng UUID | Phân biệt các lần xảy ra, hỗ trợ trace/idempotency. |
| Định danh đối tượng | `orderId` dạng UUID | Liên kết đến đơn hàng; một đơn có thể phát nhiều event. |
| Thời điểm xảy ra | `occurredAt` dạng `Instant` | Ghi thời điểm nghiệp vụ, khác lúc listener xử lý. |
| Payload | `payableTotal`, `items` | Các dữ kiện mà consumer cần khi phản ứng. |
| Quy tắc hợp lệ | `payableTotal >= 0`; `items` không rỗng | Ngăn xuất bản dữ liệu tự mâu thuẫn. |
| Quy tắc tương thích | Version/field evolution | Cho phép consumer và publication cũ tiếp tục hoạt động khi nâng cấp. |

`eventId` và `occurredAt` là quy ước thiết kế hữu ích, **không phải field mà Spring bắt buộc mọi event Java phải có**. Event tối giản như `record OrderPlaced(UUID orderId) {}` cũng là một Spring application event hợp lệ.

Cần phân biệt **metadata của ứng dụng** với metadata của transport/broker. Spring `ApplicationEventPublisher` có thể công bố một đối tượng Java thuần túy; Spring không tự bọc mọi object thành envelope JSON gồm `eventId`, `schemaVersion` và `payload`. Nếu hệ thống cần envelope đó, nhóm phát triển phải định nghĩa rõ.

## 3. Chọn tên sự kiện theo sự thật đã xảy ra

Tên event là một phần của schema vì nó quyết định consumer hiểu hành động nào đã hoàn tất.

| Tên | Ý nghĩa | Nhận xét |
| --- | --- | --- |
| `OrderPlaced` | Đơn hàng đã được tạo theo quy tắc của orders. | Phù hợp domain event. |
| `PaymentCaptured` | Tiền thanh toán đã được thu theo nghiệp vụ payments. | Rõ hơn một tên chung `PaymentUpdated`. |
| `ShipmentDispatched` | Kiện hàng đã được bàn giao để vận chuyển. | Nêu sự thật cụ thể. |
| `SendOrderEmail` | Yêu cầu gửi email. | Mang ngữ nghĩa command. |
| `UpdateReport` | Yêu cầu cập nhật báo cáo. | Phụ thuộc vào cách consumer hoạt động. |

Event không nên chứa các cờ điều khiển consumer như `shouldSendEmail` hoặc `shouldAwardPoints`. Module `orders` chỉ cần nói **đơn hàng đã được đặt**, còn mỗi consumer quyết định chính sách phản ứng theo trách nhiệm riêng.

Tương tự, không dùng cùng tên `OrderCompleted` để chỉ lúc khách nhấn đặt hàng trong phiên bản này, rồi đổi thành lúc thanh toán hoàn tất ở phiên bản sau. Đó là thay đổi **ngữ nghĩa nghiệp vụ**, có thể nghiêm trọng hơn việc đổi kiểu dữ liệu.

## 4. Schema minh họa: OrderPlacedV1

Giả sử hệ thống cần gửi email xác nhận chứa các mặt hàng đã mua, đồng thời tạo thống kê giá trị đơn hàng. Schema dùng **ảnh chụp dữ liệu tại thời điểm đặt hàng**.

~~~text
OrderPlacedV1
  eventId          : UUID              (bắt buộc)
  orderId          : UUID              (bắt buộc)
  occurredAt       : Instant           (bắt buộc, UTC instant)
  currencyCode     : String            (bắt buộc, mã tiền tệ 3 chữ)
  payableTotal     : BigDecimal        (bắt buộc, >= 0)
  items            : List<OrderLine>   (bắt buộc, không rỗng)

OrderLine
  sku              : String            (bắt buộc, không trống)
  nameAtPurchase   : String            (bắt buộc, không trống)
  quantity         : int               (bắt buộc, > 0)
  unitPrice        : BigDecimal        (bắt buộc, >= 0)
~~~

**Hợp đồng nghiệp vụ của ví dụ:**

- `payableTotal` là **số tiền khách phải trả đã được chốt** cho đơn hàng, sau các khoản giảm giá, thuế hoặc phí theo quy tắc tính tiền của ứng dụng.
- `unitPrice` là đơn giá đã chốt của mặt hàng tại thời điểm đặt đơn.
- `items` chứa snapshot bất biến, không chứa các entity JPA.
- `occurredAt` là thời điểm nghiệp vụ tạo đơn được ghi nhận, không phải thời điểm email được gửi.
- `eventId` giữ nguyên qua những lần giao lại **cùng một sự kiện**.
- Sự kiện chỉ được công bố khi module orders đã chấp nhận thao tác tạo đơn theo quy tắc nghiệp vụ. Với listener sau commit, tác dụng phụ được kích hoạt sau khi transaction tạo đơn commit.

Không thể kiểm tra một cách máy móc rằng `payableTotal` bằng tổng `quantity * unitPrice` nếu đơn hàng còn có chiết khấu, thuế, phí vận chuyển hoặc các khoản làm tròn. Công thức đầy đủ phải nằm trong mô hình nghiệp vụ và được kiểm thử riêng.

### 4.1. Java record cho phần tử snapshot

File `orders/events/OrderLine.java`:

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(
        String sku,
        String nameAtPurchase,
        int quantity,
        BigDecimal unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(nameAtPurchase, "nameAtPurchase");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || nameAtPurchase.isBlank()) {
            throw new IllegalArgumentException("Blank product field");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be >= 0");
        }
    }
}
~~~

`OrderLine` không phụ thuộc `ProductEntity` hay `OrderItemEntity`. Việc tách record giúp consumer sử dụng thông tin công khai mà không bị ràng buộc bởi cách module orders lưu dữ liệu.

### 4.2. Java record cho event

File `orders/events/OrderPlacedV1.java`:

~~~java
package com.acme.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderPlacedV1(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        String currencyCode,
        BigDecimal payableTotal,
        List<OrderLine> items
) {
    public OrderPlacedV1 {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(currencyCode, "currencyCode");
        Objects.requireNonNull(payableTotal, "payableTotal");
        Objects.requireNonNull(items, "items");

        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code format");
        }
        if (payableTotal.signum() < 0) {
            throw new IllegalArgumentException("payableTotal must be >= 0");
        }
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }
    }
}
~~~

`[A-Z]{3}` chỉ kiểm tra **hình dạng** mã tiền tệ; nếu ứng dụng yêu cầu mã theo ISO 4217 đang được hỗ trợ, cần kiểm tra thêm bằng chính sách hoặc danh mục tiền tệ phù hợp.

`List.copyOf(items)` tạo một danh sách không sửa được bằng accessor và tách khỏi danh sách đầu vào. Vì `OrderLine` là record chứa các kiểu bất biến, consumer không thể sửa phần tử để ảnh hưởng tới listener khác.

**Record chỉ bảo đảm bất biến nông theo cấu trúc của Java.** Nếu một component là `List<MutableObject>`, `List.copyOf` không biến các `MutableObject` thành bất biến. Với nested field là `byte[]`, `Date` hoặc object mutable, phải phòng vệ bằng copy/đóng gói thích hợp hoặc thay đổi thiết kế.

### 4.3. Ví dụ dữ liệu ở dạng JSON để thảo luận schema

~~~json
{
  "eventId": "f3fda048-d795-4ca9-8623-182e5c5c0c65",
  "orderId": "3ae686d3-3f75-4c78-a40b-bb2473c4ee04",
  "occurredAt": "2026-11-25T08:00:00Z",
  "currencyCode": "VND",
  "payableTotal": 550000,
  "items": [
    {
      "sku": "SKU-A",
      "nameAtPurchase": "Bút máy",
      "quantity": 2,
      "unitPrice": 150000
    },
    {
      "sku": "SKU-B",
      "nameAtPurchase": "Sổ tay",
      "quantity": 1,
      "unitPrice": 250000
    }
  ]
}
~~~

Đoạn JSON là **biểu diễn minh họa của dữ liệu**, không phải định dạng mà `ApplicationEventPublisher` bắt buộc tạo ra. Khi có cơ chế lưu publication hoặc gửi ra broker, hình thức lưu/serialize phụ thuộc công nghệ và cấu hình thực tế; cần kiểm tra kiểu số, thời gian, tên field và cách dựng lại Java record.

## 5. Các quy tắc kiểu dữ liệu không nên bỏ qua

### 5.1. Định danh: UUID hay chuỗi?

Dùng `UUID` trong record nếu hệ thống định danh bằng UUID. Nếu ID nghiệp vụ là chuỗi (`ORD-2026-001`), nên dùng `String` với quy tắc định dạng và ý nghĩa rõ ràng, tránh ép giả sang UUID.

`eventId` và `orderId` **khác nhau**: một đơn có thể trải qua nhiều sự kiện; một publication lỗi rồi được giao lại vẫn mang **cùng eventId**. Tạo một `eventId` mới trên mỗi lần retry sẽ phá cơ chế chống trùng dựa trên event identity.

### 5.2. Tiền: giá trị và đơn vị là một cặp

Không dùng `double` để lưu số tiền nghiệp vụ vì sai số nhị phân có thể ảnh hưởng so sánh và tính toán. `BigDecimal` hoặc mô hình Money riêng là lựa chọn dễ kiểm soát hơn.

`payableTotal = 550000` không đủ nếu thiếu `currencyCode = "VND"`. Nếu có nhiều đơn vị tiền tệ, consumer không được cộng các số tiền khác đơn vị rồi xem như một tổng chung.

Không tự giả định số chữ số thập phân hay quy tắc làm tròn từ một tên field; phải mô tả và kiểm thử quy tắc tính tiền của nghiệp vụ.

### 5.3. Thời gian: Instant và ngữ nghĩa

`Instant` biểu diễn một thời điểm tuyệt đối. Nên phân biệt:

- `occurredAt`: khi sự kiện nghiệp vụ xảy ra.
- `publishedAt`: khi ứng dụng công bố event, nếu hệ thống chủ động ghi nhận.
- `processedAt`: khi một listener hoàn tất xử lý.
- `scheduledFor`: thời điểm nghiệp vụ dự kiến trong tương lai, có ngữ nghĩa khác.

Khi consumer cần tính ngày theo múi giờ, phải có quy tắc chọn zone tương ứng; không suy ra ngày kinh doanh từ một `Instant` mà bỏ qua múi giờ.

### 5.4. Null, Optional và collection

Quy ước nên nêu rõ field nào **bắt buộc**, field nào có thể **vắng mặt** và sự vắng mặt có ý nghĩa gì.

Một số quy tắc thực dụng:

- Field cốt lõi như `eventId`, `orderId`, `occurredAt` thường không cho null.
- `items = []` và `items = null` không có cùng ý nghĩa. Với `OrderPlacedV1` ở ví dụ, đơn hàng phải có ít nhất một dòng.
- Không mặc định dùng `Optional<T>` làm field của persisted event; cách serializer xử lý `Optional` phụ thuộc thư viện.
- Nếu một field có thể vắng, cần định nghĩa cách consumer xử lý và kiểm thử trường hợp thiếu đó.

### 5.5. Enum và mã giá trị

Enum Java thuận tiện cho mã trạng thái nội bộ, nhưng thêm/đổi giá trị enum có thể ảnh hưởng payload đã lưu và các consumer. Khi giá trị mở rộng thường xuyên hoặc được trao đổi giữa hệ thống, cân nhắc mã chuỗi với danh sách giá trị hỗ trợ, chính sách unknown và quy ước tương thích.

## 6. Schema phải mô tả trạng thái tại một thời điểm

Giả sử khi khách đặt hàng, sản phẩm có tên “Bút máy” và giá 150.000 VND. Hôm sau catalog đổi tên thành “Bút ký cao cấp” và tăng giá. Listener gửi email bị lỗi, sau đó được replay.

Nếu event chỉ mang `orderId` và listener đọc catalog **hiện tại**, email có thể không thể hiện đúng giao dịch lịch sử. Khi email xác nhận cần dữ liệu đã chốt, schema nên chứa `nameAtPurchase`, `unitPrice` và các số tiền theo hợp đồng đặt hàng.

Tuy nhiên, snapshot không luôn bắt buộc. Nếu listener chỉ cần cập nhật trạng thái giao hàng mới nhất, truy vấn API công khai có thể phù hợp hơn. Cần chọn dựa trên ba câu hỏi:

1. Consumer cần **dữ liệu của thời điểm sự kiện** hay **trạng thái mới nhất**?
2. Có thể truy vấn qua API công khai mà không phá ranh giới module không?
3. Khi consumer chạy trễ hoặc replay sau nhiều giờ, kết quả có vẫn đúng nghiệp vụ không?

Thiết kế “rich event” là một lựa chọn cho schema có snapshot, không phải quy tắc rằng mọi event phải sao chép toàn bộ aggregate.

## 7. Vị trí schema trong kiến trúc Spring Modulith

Một cấu trúc thư mục rõ quyền sở hữu:

~~~text
com/acme/shop/
├── ShopApplication.java
├── orders/
│   ├── events/
│   │   ├── package-info.java
│   │   ├── OrderPlacedV1.java
│   │   └── OrderLine.java
│   └── internal/
│       ├── OrderService.java
│       └── OrderRepository.java
├── notifications/
│   ├── package-info.java
│   └── internal/
│       └── OrderPlacedListener.java
└── reporting/
    ├── package-info.java
    └── internal/
        └── RevenueProjectionListener.java
~~~

Trong cấu hình phát hiện module mặc định, `orders`, `notifications` và `reporting` là các application module. Các lớp bên trong `orders.internal` thuộc implementation của orders và không nên bị consumer import trực tiếp.

Nếu event ở package con `orders.events`, có thể công khai package như named interface:

~~~java
// orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Ở module notifications:

~~~java
// notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.notifications;
~~~

Cách này làm rõ rằng module notifications được tham chiếu **hợp đồng event** do orders công bố. Nó không có lý do để sử dụng `orders.internal.OrderRepository`. Spring Modulith có `ApplicationModules.verify()` để kiểm tra các ranh giới và phụ thuộc đã khai báo.

Nếu hợp đồng event ít và nhỏ, có thể đặt event trực tiếp trong package gốc `orders`, thuộc API mặc định của module; `@NamedInterface` không bắt buộc cho mọi event.

## 8. Publisher phải phát đúng dữ liệu đã được xác nhận

Ví dụ giản lược của module orders:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderLine;
import com.acme.shop.orders.events.OrderPlacedV1;
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

    public OrderService(OrderRepository repository,
                        ApplicationEventPublisher events,
                        Clock clock) {
        this.repository = repository;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = Order.create(command);
        repository.save(order);

        var snapshots = order.lines().stream()
                .map(line -> new OrderLine(
                        line.sku(),
                        line.nameAtPurchase(),
                        line.quantity(),
                        line.unitPrice()
                ))
                .toList();

        var event = new OrderPlacedV1(
                UUID.randomUUID(),
                order.id(),
                clock.instant(),
                order.currencyCode(),
                order.payableTotal(),
                snapshots
        );

        events.publishEvent(event);
        return order.id();
    }
}
~~~

`OrderRepository`, `Order` và `PlaceOrderCommand` là các kiểu nghiệp vụ minh họa, phải được định nghĩa trong ứng dụng thực tế; cần có `Clock` bean và quy tắc cấp ID phù hợp. Mục đích của code là thể hiện **điểm tạo snapshot trong transaction**.

Publisher nên dựng event từ giá trị đã được nghiệp vụ tính và xác nhận. Không nên để listener tự tính lại tổng tiền bằng bảng giá hiện tại nếu tổng tiền đã được chốt ở orders.

**Ranh giới transaction:** `publishEvent` chạy trong `@Transactional` không có nghĩa **mọi** listener đều chờ đến commit. `@EventListener` thông thường có thể chạy đồng bộ ngay trong lệnh publish. Muốn xử lý hậu nghiệp vụ chỉ sau khi commit thành công, cần chọn transactional listener phù hợp.

## 9. Listener tiêu thụ schema công khai

Một consumer của notifications:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlacedV1;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final ConfirmationSender confirmations;

    OrderPlacedListener(ConfirmationSender confirmations) {
        this.confirmations = confirmations;
    }

    @ApplicationModuleListener
    void on(OrderPlacedV1 event) {
        confirmations.sendOrderSummary(
                event.eventId(),
                event.orderId(),
                event.currencyCode(),
                event.payableTotal(),
                event.items()
        );
    }
}
~~~

`ConfirmationSender` là component ví dụ do notifications sở hữu. Listener chỉ cần schema `OrderPlacedV1`; nó không biết cách orders lưu và tính tổng tiền trong entity.

`@ApplicationModuleListener` hỗ trợ xử lý **bất đồng bộ sau commit** với transaction riêng cho listener trong Spring Modulith. Phần gửi email qua hệ thống ngoài cần chính sách idempotency và xử lý lỗi riêng; transaction của listener không tự làm giao dịch gửi email trở nên nguyên tử với database.

Có thể có nhiều listener với cùng loại event; schema phải đủ ổn định để tất cả consumer hiểu đúng, nhưng không vì thế mà chứa dữ liệu của mọi module một cách thiếu kiểm soát.

## 10. Phân biệt schema event, phiên bản schema và serialization

Ba khái niệm liên quan nhưng không đồng nhất:

- **Schema event:** hợp đồng về loại event, field, kiểu dữ liệu và ý nghĩa.
- **Version:** cách nhận diện những thay đổi của hợp đồng qua thời gian.
- **Serialization:** cách chuyển đổi event Java sang dữ liệu lưu trữ hoặc truyền tải rồi đọc trở lại.

Spring application event thuần trong cùng tiến trình có thể được xử lý như một Java object, **không cần JSON**. Khi dùng persistent Event Publication Registry hoặc xuất event ra hạ tầng messaging, cách ghi và phục hồi dữ liệu phụ thuộc persistence integration/serializer được sử dụng.

Ví dụ một hệ thống dùng JSON có thể viết biểu diễn envelope riêng:

~~~json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "eventId": "f3fda048-d795-4ca9-8623-182e5c5c0c65",
  "payload": {
    "orderId": "3ae686d3-3f75-4c78-a40b-bb2473c4ee04",
    "occurredAt": "2026-11-25T08:00:00Z",
    "currencyCode": "VND",
    "payableTotal": 550000,
    "items": [
      {
        "sku": "SKU-A",
        "nameAtPurchase": "Bút máy",
        "quantity": 2,
        "unitPrice": 150000
      },
      {
        "sku": "SKU-B",
        "nameAtPurchase": "Sổ tay",
        "quantity": 1,
        "unitPrice": 250000
      }
    ]
  }
}
~~~

Đây chỉ là **một cấu trúc minh họa khi tự thiết kế envelope**; không phải định dạng mặc định của Spring Modulith. Dữ liệu ví dụ tuân theo invariant của `OrderPlacedV1`. Nếu dữ liệu nhận từ biên tích hợp thiếu field bắt buộc hoặc vi phạm invariant (chẳng hạn `items=[]`), hệ thống phải từ chối hoặc áp dụng chính sách xử lý dữ liệu lỗi rõ ràng.

**Lưu ý:** đặt `V1` trong tên lớp Java và thêm `schemaVersion: 1` vào envelope đều là những lựa chọn versioning; không phải hai thành phần Spring Modulith bắt buộc cung cấp.

### Nên version ở đâu?

Có ba cách thường gặp:

| Cách | Ví dụ | Điểm cần chú ý |
| --- | --- | --- |
| Đổi tên kiểu khi breaking change | `OrderPlacedV1` → `OrderPlacedV2` | Consumer cũ phải còn listener cho V1 trong giai đoạn chuyển tiếp nếu cần. |
| Thêm version vào envelope | `eventType=OrderPlaced`, `schemaVersion=2` | Cần serializer/router xác định được version và mapping. |
| Giữ một kiểu với thay đổi tương thích | Thêm field tùy chọn có default | Phải xác minh compatibility cả ở Java lẫn dữ liệu đã lưu. |

Không có một lựa chọn universal cho mọi dự án. Nếu chỉ có Java modules triển khai cùng một binary, thay đổi source có thể diễn ra đồng bộ; nhưng **publication còn lưu** từ phiên bản trước và các tích hợp ngoài tiến trình vẫn có thể tạo ra yêu cầu tương thích qua các bản triển khai.

## 11. Schema evolution: thay đổi nào an toàn?

Một thay đổi được coi là tương thích khi **consumer và dữ liệu đã lưu liên quan thực sự vẫn được hiểu đúng**. Kết luận phụ thuộc vào API Java, serializer, cấu hình persistence và cách consumer sử dụng event.

| Thay đổi | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Đổi tên `payableTotal` thành `amount` | Consumer source code và dữ liệu đã serialize có thể không còn đọc được. | Xem như breaking change nếu không có mapping chuyển tiếp. |
| Đổi `BigDecimal` thành `String` | Thay kiểu, parser và phép tính của consumer. | Tạo hợp đồng mới hoặc migration rõ ràng. |
| Thêm `couponCode` tùy chọn | Record constructor thay đổi; serializer cũ/mới có thể khác. | Kiểm tra source compatibility, default và deserialization dữ liệu cũ. |
| Bỏ `currencyCode` | Consumer không biết đơn vị của tiền. | Breaking change; tránh bỏ nếu số tiền vẫn tồn tại. |
| Thêm một giá trị enum | Consumer có switch exhaustive hoặc deserializer chưa hỗ trợ. | Quy định xử lý unknown và kiểm thử thực tế. |
| Đổi ý nghĩa `occurredAt` | Lỗi logic dù kiểu `Instant` không đổi. | Không tái sử dụng field cho ngữ nghĩa khác. |
| Thêm field bắt buộc không có default | Publication cũ không có dữ liệu tương ứng. | Cần chuyển đổi schema hoặc phiên bản event mới. |
| Thêm field chỉ dùng nội bộ publisher | Mở rộng API công khai không cần thiết. | Tránh nếu không phục vụ consumer. |

### 11.1. Thay đổi record có thể làm hỏng source compatibility

Ban đầu:

~~~java
public record OrderPlacedV1(UUID eventId, UUID orderId) {}
~~~

Sau đó thay thành:

~~~java
public record OrderPlacedV1(
        UUID eventId,
        UUID orderId,
        String currencyCode
) {}
~~~

Các lệnh `new OrderPlacedV1(eventId, orderId)` cũ không còn biên dịch nếu không cung cấp thêm constructor tương thích. Kể cả khi sửa toàn bộ Java source, publication được serialize trước khi deploy có thể không chứa `currencyCode`. Serializer thực tế phải có cách đọc giá trị vắng, hoặc cần chiến lược migration/version khác.

Thêm field “tùy chọn” **không tự động tương thích** chỉ vì ứng dụng định dùng null. Tính tương thích phải được chứng minh bằng kiểm thử.

### 11.2. Version event khi thay đổi nghiệp vụ

Giả sử `OrderPlacedV1` biểu thị đơn hàng được tạo, còn thiết kế mới đòi hỏi trạng thái “đã thanh toán” mới được xem là đặt hàng thành công. Thay đổi này ảnh hưởng nghiệp vụ và consumer; cân nhắc tạo event mới như `OrderPaymentConfirmed` nếu đó là sự thật khác, thay vì lén thay định nghĩa của `OrderPlacedV1`.

Đổi version không thay thế được việc định nghĩa lại đúng tên và sự thật nghiệp vụ.

## 12. Chiến lược triển khai thay đổi schema

Một quy trình an toàn cho event đang được nhiều module sử dụng:

1. **Thống kê consumer:** liệt kê listener nào nhận `OrderPlacedV1`, field nào đang được sử dụng.
2. **Xác định breaking/non-breaking:** xét cả kiểu Java, ngữ nghĩa, persisted payload và các tích hợp ngoài.
3. **Thiết kế đường chuyển tiếp:** giữ V1 trong thời gian cần thiết, cho phép V2 song hành hoặc chuyển đổi payload khi đọc.
4. **Tạo fixture dữ liệu cũ:** lưu biểu diễn event đã serialize của phiên bản trước và kiểm thử ứng dụng mới có thể đọc.
5. **Kiểm thử publisher và consumer:** kiểm tra dữ liệu đầy đủ, rollback và idempotency với từng version.
6. **Kiểm tra Event Publication Registry:** biết còn publication cũ chưa hoàn tất không trước khi bỏ khả năng xử lý V1.
7. **Triển khai và theo dõi:** quan sát lỗi deserialize, publication tồn đọng và hành vi khác kỳ vọng.
8. **Loại bỏ tương thích cũ khi an toàn:** chỉ khi các consumer và publication liên quan không còn cần V1.

Với thay đổi nhỏ chỉ chạy trong cùng một ứng dụng và không lưu event, quy trình có thể gọn hơn. Tuy nhiên cần kiểm tra **môi trường thực tế** thay vì chỉ nhìn source.

### Không tự suy ra thứ tự từ schema

`eventId` duy nhất giúp nhận dạng, **không bảo đảm thứ tự**. `occurredAt` cũng không đủ để bảo đảm delivery order, nhất là khi đồng hồ khác nhau hoặc listener bất đồng bộ.

Nếu consumer phải áp dụng các sự kiện cập nhật của cùng một aggregate theo thứ tự, có thể cần `aggregateVersion` tăng đơn điệu, cơ chế đồng bộ theo khóa hoặc mô hình xử lý tuần tự. Schema có thể mang version nhưng **cơ chế giao và consumer vẫn phải thực thi quy tắc thứ tự**.

## 13. Event Publication Registry và khả năng đọc lại schema

Spring Modulith có **Event Publication Registry** để theo dõi việc giao event tới các transactional event listener. Khi cấu hình backend lưu trữ phù hợp, hệ thống có thể lưu publication chưa hoàn tất và xử lý khôi phục/phát lại theo cơ chế đã thiết lập.

Lưu publication đồng nghĩa với yêu cầu quan trọng: **consumer ở phiên bản hiện tại phải hiểu được event đã được ghi từ phiên bản trước**, nếu những publication ấy vẫn cần được replay.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant R as Publication Registry
    participant N as notifications
    participant S as Data Store

    O->>R: Ghi nhận publication V1 (khi đã cấu hình)
    O->>S: Commit đơn hàng
    R-->>N: Giao OrderPlacedV1 sau commit
    N->>N: Xử lý lỗi tạm thời
    Note over R,N: Publication vẫn chưa hoàn tất
    Note over O,N: Ứng dụng được triển khai phiên bản mới
    R-->>N: Đọc và giao lại V1 theo recovery
    N-->>R: Đánh dấu hoàn tất sau khi xử lý thành công
~~~

Đây là **sơ đồ logic**. Registry không phải message broker, và cơ chế lưu event, deserialize hoặc tự động replay phụ thuộc Spring Modulith integration và cấu hình thực tế. Không thể suy ra độ bền hay chính sách retry chỉ từ việc gọi `publishEvent`.

Khi thiết kế schema cần dự liệu:

- Có thể deserialize event cũ vào đúng kiểu Java hiện tại không?
- Nếu có nhiều phiên bản event, listener nào xử lý từng phiên bản?
- Khi publication còn tồn, liệu có được xóa lớp V1 hoặc rename package?
- Consumer có xử lý lặp an toàn khi registry phát lại không?
- Có công cụ quan sát publication chưa hoàn tất theo loại event/schema version không?

## 14. Schema phục vụ retry và idempotency như thế nào?

Một kịch bản phổ biến:

1. `OrderPlacedV1` được ghi nhận, orders commit thành công.
2. Listener notifications gửi email xác nhận thành công.
3. Ứng dụng dừng trước khi việc xử lý được đánh dấu hoàn tất.
4. Publication được replay.
5. Listener có nguy cơ gửi email hai lần.

Schema có `eventId` ổn định giúp listener đặt khóa chống trùng, ví dụ `(consumerName, eventId)`. Một bảng minh họa:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer có thể áp dụng unique constraint và ghi kết quả xử lý trong cùng transaction nếu tác dụng phụ là cập nhật dữ liệu **cùng một cơ sở dữ liệu/transaction manager**. Không dùng cách kiểm tra `exists` rồi `insert` tách rời nếu có khả năng xử lý đồng thời, vì hai luồng có thể cùng thấy “chưa tồn tại”.

Với tác dụng phụ bên ngoài như gửi email, không có giao dịch nguyên tử mặc định giữa database và dịch vụ email. Cần sử dụng idempotency key của downstream (nếu hỗ trợ) hoặc thiết kế cơ chế gửi/đối soát riêng. Đánh dấu “đã xử lý” trước khi gửi thật rồi bỏ qua mọi lần retry có thể gây **mất email** nếu gửi thất bại.

**Schema tốt giúp nhận diện giao trùng; nó không tự mang lại exactly-once delivery hay exactly-once side effects.**

## 15. Quyền riêng tư là một ràng buộc của schema

Event có thể được nhiều listener nhận và có thể được lưu lại để recovery. Vì vậy, thêm một field nhạy cảm vào schema không chỉ ảnh hưởng compiler mà còn ảnh hưởng **phạm vi truy cập và thời gian tồn tại của dữ liệu**.

Các field nên cân nhắc cẩn thận:

| Field | Rủi ro | Thiết kế gợi ý |
| --- | --- | --- |
| `customerEmail` | Có thể bị các consumer không cần email nhìn thấy hoặc bị log. | Chỉ đưa vào khi cần snapshot người nhận và được kiểm soát; nếu không dùng API thích hợp. |
| `shippingAddress` | Dữ liệu cá nhân và có thể thay đổi. | Chỉ đưa phần thực sự cần, kiểm soát lưu/truy cập. |
| `paymentCardNumber` | Dữ liệu thanh toán rất nhạy cảm. | Không đưa vào application event dùng chung. |
| `accessToken` | Có thể bị lộ qua log/registry. | Không đưa secret vào event. |
| `items` | Có thể tiết lộ hành vi mua sắm. | Hạn chế log toàn bộ và kiểm soát consumer nhận. |

Cần phân biệt **consumer được phép import event contract** và **consumer có lý do nghiệp vụ để nhận dữ liệu cụ thể**. Một event dùng chung với payload quá giàu có thể mở rộng bề mặt dữ liệu vượt nhu cầu. Khi các consumer cần dữ liệu khác nhau đáng kể, cân nhắc tách các hợp đồng/sự kiện có nghĩa nghiệp vụ rõ ràng hoặc dùng API truy vấn có kiểm soát.

## 16. Kiểm thử schema: nhiều lớp bảo vệ

### 16.1. Test invariant và bất biến của record

~~~java
package com.acme.shop.orders.events;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderPlacedV1ContractTest {

    @Test
    void copiesInputItemsAndRejectsMutation() {
        var input = new ArrayList<OrderLine>();
        input.add(new OrderLine(
                "SKU-A", "But may", 2, new BigDecimal("150000")
        ));

        var event = new OrderPlacedV1(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-11-25T08:00:00Z"),
                "VND",
                new BigDecimal("300000"),
                input
        );

        input.clear();

        assertEquals(1, event.items().size());
        assertThrows(
                UnsupportedOperationException.class,
                () -> event.items().clear()
        );
    }

    @Test
    void rejectsMissingBusinessData() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "SKU-A", "But may", 0, BigDecimal.TEN
                )
        );
    }
}
~~~

Những test này kiểm tra invariant của **hợp đồng**. Chúng chưa chứng minh event đã được publish sau nghiệp vụ hay listener xử lý đúng.

### 16.2. Test publisher và consumer theo module

Spring Modulith có `@ApplicationModuleTest` và `PublishedEvents` để kiểm tra application event được công bố. Với hành vi tạo đơn, cần xác minh `OrderPlacedV1` có đúng `orderId`, `currencyCode`, `payableTotal` và `items` của đơn đã chốt.

Phía consumer cần test các trường hợp:

- Đúng schema cho ra nội dung email hoặc projection đúng.
- Khi transaction tạo đơn rollback, listener **sau commit** không chạy.
- Khi cùng event được xử lý nhiều lần, không tạo tác dụng phụ trùng.
- Listener không cần import repository/entity nội bộ của module orders.

### 16.3. Test serialization và replay

Nếu sử dụng persisted publication, cần dùng **chính serializer và storage integration của hệ thống** để kiểm tra:

1. Serialize rồi deserialize một event có nhiều line item vẫn cho dữ liệu tương đương.
2. Một fixture serialized từ phiên bản trước vẫn đọc được sau nâng cấp, nếu đó là cam kết tương thích.
3. Event có field thiếu, null trái quy tắc hoặc enum lạ được xử lý theo chính sách rõ ràng.
4. Publication tồn đọng có thể được recovery và consumer không gây side effect trùng.

Test chỉ so sánh JSON viết tay **không đủ** nếu registry thực tế sử dụng định dạng hoặc mapping khác.

### 16.4. Test ranh giới module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void respectsApplicationModuleContracts() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện phụ thuộc sai ranh giới, ví dụ `notifications` import `orders.internal.OrderRepository`. Các kiểu trong schema nên được công bố qua API module hoặc named interface thích hợp.

## 17. Quan sát và chẩn đoán lỗi hợp đồng

Khi một publication thất bại hoặc deserialize không được sau deploy, log nên đủ để xác định nguồn gốc mà không ghi lộ toàn bộ payload:

| Trường quan sát | Mục đích |
| --- | --- |
| `eventType`, `schemaVersion` nếu có | Xác định hợp đồng cần đọc. |
| `eventId`, `orderId` | Truy vết sự kiện và đối tượng nghiệp vụ. |
| `publisherModule`, `listenerName` | Tìm nơi phát và consumer gặp lỗi. |
| `occurredAt`, `processedAt` | Tính độ trễ xử lý. |
| `attempt`, `errorCode` | Chẩn đoán retry và lỗi lặp. |
| `publicationStatus` | Xác định publication chưa hoàn tất. |
| `payloadSize` | Cảnh báo schema trở nên quá lớn. |

Ví dụ định dạng log **do ứng dụng tự quy ước**, không phải output mặc định của Spring Modulith:

~~~text
event=OrderPlacedV1 eventId=f3fd... listener=notifications status=FAILED attempt=1 reason=SMTP_TIMEOUT
event=OrderPlacedV1 eventId=f3fd... listener=notifications status=COMPLETED attempt=2
~~~

Không log địa chỉ, token hoặc toàn bộ line item khi không cần. Nên theo dõi tỷ lệ lỗi deserialize, publication tồn đọng, thời gian xử lý và những event không có listener hỗ trợ phiên bản tương ứng.

## 18. Các lỗi thiết kế schema thường gặp

### 18.1. Field mơ hồ

~~~java
public record OrderPlaced(UUID orderId, double amount) {}
~~~

`amount` không có loại tiền, không nói có gồm thuế hay chưa và `double` không phù hợp cho tiền nghiệp vụ. Nên dùng tên chính xác, `BigDecimal`, currency và tài liệu ngữ nghĩa.

### 18.2. Truyền entity thay vì hợp đồng dữ liệu

~~~java
public record OrderPlaced(OrderEntity order) {}
~~~

Schema kéo theo persistence implementation, mutable state và lazy loading. Consumer có thể lỗi sau commit hoặc phụ thuộc vào nội bộ của orders. Thay bằng record snapshot bất biến, tối thiểu và công khai.

### 18.3. Tự ý đổi ý nghĩa field cũ

Tên `occurredAt` giữ nguyên nhưng chuyển từ thời điểm tạo đơn sang thời điểm xử lý xong email. Consumer báo cáo theo ngày sẽ âm thầm sai. Cần field/loại sự kiện đúng nghĩa hoặc schema version có lộ trình.

### 18.4. Dùng một event cho mọi sự thật

`OrderChanged` với hàng chục field optional có thể khiến consumer khó biết thay đổi nào đã xảy ra. Khi nghiệp vụ có các sự thật rõ ràng, cân nhắc các event `OrderPlaced`, `OrderCancelled`, `OrderShipped` có schema riêng.

### 18.5. Giả định thêm field là không phá vỡ tương thích

Java record đổi canonical constructor, payload cũ thiếu field và serializer có thể không dùng default như mong đợi. Phải kiểm thử cả source và persisted dữ liệu liên quan.

### 18.6. Dùng `orderId` làm khóa chống trùng cho mọi event

Một đơn có thể có nhiều event. Consumer cần định danh đúng **lần xảy ra sự kiện** hoặc khóa nghiệp vụ tương ứng, không mặc định mọi `orderId` chỉ được xử lý đúng một lần.

### 18.7. Coi schema hoàn chỉnh là giao sự kiện đáng tin cậy

Schema tốt không ngăn tiến trình dừng giữa lúc consumer đã gửi email và lúc registry đánh dấu hoàn tất. Cần chiến lược transaction, publication registry/recovery, idempotency, kiểm thử và observability.

## 19. Checklist khi công bố một event mới

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Sự kiện mô tả sự thật nào? | Tên rõ nghĩa và điều kiện phát nhất quán. |
| Module nào sở hữu? | Contract được export bởi publisher module. |
| Ai là consumer? | Các module nhận biết field cần thiết, không truy cập implementation. |
| Có ID riêng cho event? | Dùng ID ổn định cho trace/replay khi nghiệp vụ cần. |
| Field bắt buộc hay tùy chọn? | Nullability, rỗng, định dạng và invariant rõ ràng. |
| Có đơn vị và ngữ nghĩa thời gian? | Currency, amount semantics, timezone/Instant thống nhất. |
| Payload có bất biến? | Copy collection, không truyền entity mutable. |
| Có dữ liệu nhạy cảm hoặc quá lớn? | Chỉ chứa dữ liệu có mục đích; giới hạn và chính sách lưu. |
| Có thể đọc lại sau nâng cấp? | Fixture schema cũ, serializer, listener tương thích. |
| Khi event được giao trùng? | Consumer có idempotency đúng tác dụng phụ. |
| Khi transaction rollback? | Listener dùng phase phù hợp với nghiệp vụ. |
| Khi listener thất bại? | Cấu hình registry/retry/recovery và giám sát khi cần. |
| Có kiểm thử module? | Publisher, consumer, ranh giới, schema, rollback, replay. |

## 20. Bài tập thực hành: tiến hóa schema theo ba phiên bản

Hãy bắt đầu với `OrderPlacedV1` có `eventId`, `orderId`, `occurredAt`, `currencyCode`, `payableTotal` và `items`.

**Phần A — Xây dựng hợp đồng**

1. Viết record và invariant như ví dụ; kiểm tra `items` không rỗng, `quantity > 0` và `payableTotal >= 0`.
2. Tạo một đơn gồm 2 mặt hàng, tổng tiền chốt là 550.000 VND, và publish event từ module orders.
3. Viết listener notifications dùng snapshot để tạo nội dung xác nhận mà không truy cập `OrderRepository`.
4. Kiểm thử event không thay đổi khi danh sách item đầu vào bị sửa sau khi tạo record.

**Phần B — Thay đổi schema**

Nhóm sản phẩm yêu cầu bổ sung mã giảm giá, có thể vắng mặt. Hãy phân tích việc thêm `couponCode` vào record: consumer nào dùng, giá trị vắng mặt biểu diễn ra sao, constructor cũ có còn biên dịch không, và publication cũ có đọc lại được không? Chọn giữ V1 với chiến lược tương thích được kiểm chứng hoặc tạo V2 với kế hoạch chuyển tiếp, rồi giải thích quyết định.

**Phần C — Kiểm tra độ tin cậy**

1. Cố tình cho listener notifications lỗi ở lần đầu.
2. Sử dụng cơ chế recovery của Event Publication Registry đã được cấu hình để phát lại publication.
3. Xác minh `eventId` không đổi qua replay và consumer không gửi hai email nếu lần xử lý trước đã thành công.
4. Giả lập payload phiên bản cũ và kiểm tra serializer của hệ thống có thể đọc dưới ứng dụng mới.
5. Ghi log có `eventType`, `eventId`, `listener`, trạng thái và lỗi mà không lộ dữ liệu nhạy cảm.

**Câu hỏi tự kiểm tra:** Vì sao một event có đủ field Java vẫn có thể là hợp đồng tồi? Khi nào thêm field optional trở thành breaking change? Sự khác nhau giữa `eventId` và `orderId` khi retry là gì? Tại sao schema version và publication registry cần được thiết kế cùng nhau?

**Ghi nhớ:** Schema của event là **hợp đồng nghiệp vụ công khai và có vòng đời dài hơn một lời gọi phương thức**. Trong Spring Modulith, schema rõ ràng giúp publisher và listener giao tiếp qua ranh giới module, còn tính bất biến, ngữ nghĩa field, versioning, serializer compatibility, retry và idempotency quyết định hợp đồng có thể vận hành đáng tin cậy khi xử lý sau commit và phát lại hay không.

