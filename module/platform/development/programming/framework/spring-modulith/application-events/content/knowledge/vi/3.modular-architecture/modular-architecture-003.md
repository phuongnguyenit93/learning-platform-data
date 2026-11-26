# API công khai của module trong Spring Modulith

Trong kiến trúc **modular monolith**, các module cùng chạy trong một ứng dụng Spring Boot nhưng vẫn cần ranh giới rõ ràng. Mỗi module sở hữu nghiệp vụ, dữ liệu và cách triển khai riêng; phần còn lại của hệ thống chỉ nên tiếp xúc với **API công khai** mà module chủ động cung cấp. Đây là một nguyên tắc cốt lõi khi tổ chức giao tiếp bằng **application events** trong Spring Modulith: module đặt hàng có thể thông báo “đơn hàng đã được tạo” mà không cần cho module thông báo truy cập service, repository hoặc entity nội bộ.

Trong chương **Kiến trúc theo module** của `SPRING_MODULITH_APPLICATION_EVENTS`, bài học này tập trung vào cách xác định, công bố và bảo vệ API module. Các ví dụ dùng publisher, listener, xử lý sau commit và kiểm tra ranh giới để làm nền cho việc bổ sung event publication registry, retry và quan sát quá trình giao sự kiện đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **public trong Java** với **API công khai theo ranh giới Spring Modulith**.
- Giải thích quy ước module root package, package con nội bộ và named interface.
- Thiết kế API theo mục đích: service/facade cho lời gọi trực tiếp, event contract cho giao tiếp bằng sự kiện.
- Dùng `@NamedInterface` để công bố một phần API từ package con và `@ApplicationModule(allowedDependencies = ...)` để giới hạn phụ thuộc.
- Thiết kế publisher và listener chỉ dựa trên hợp đồng được công bố, tránh lộ implementation.
- Kiểm tra ranh giới module bằng `ApplicationModules.verify()` và nhận biết giới hạn của kiểm tra kiến trúc tĩnh.

## 2. API công khai của module là gì?

**API công khai của module** là tập hợp các kiểu và hành vi mà module **cho phép module khác sử dụng như một hợp đồng ổn định**. API có thể bao gồm Java interface, facade, record/DTO, kiểu giá trị (value object), event hoặc một điểm mở rộng có chủ đích.

Ví dụ, hệ thống thương mại điện tử có ba module:

| Module | Sở hữu | Hợp đồng cần công bố |
| --- | --- | --- |
| `ordering` | Đặt hàng, trạng thái đơn, lưu dữ liệu đơn hàng | `OrderFacade` để đặt hàng; `OrderPlaced` để thông báo đơn hàng đã tạo |
| `notification` | Nội dung và phương thức gửi thông báo | Listener nhận `OrderPlaced`; không cần gọi repository đặt hàng |
| `analytics` | Thống kê và báo cáo | Listener nhận `OrderPlaced`; không cần biết logic lưu đơn |

Sự khác biệt quan trọng:

- **Public ở cấp ngôn ngữ Java** (`public class`, `public record`, `public method`) xác định mã nguồn khác có thể truy cập về mặt cú pháp và classpath/module path.
- **Public API ở cấp application module** xác định **kiến trúc cho phép** module khác phụ thuộc vào kiểu nào. Một class `public` nằm trong package nội bộ vẫn có thể bị coi là **implementation detail**.
- **API công khai không nhất thiết là HTTP API**. Một Java interface hoặc event contract được các module trong cùng JVM sử dụng cũng là API của module.

Spring Modulith giúp mô hình hóa và kiểm tra quy ước này. Với quy tắc module mặc định, **package gốc của application module** chính là bề mặt API công khai; các **subpackage** được xem là nội bộ, trừ khi được công bố rõ ràng qua **named interface**. Khi kiểm tra kiến trúc, Spring Modulith có thể phát hiện các module phụ thuộc vào kiểu nội bộ dù Java compiler cho phép import.

## 3. Phân chia package và ranh giới trách nhiệm

Giả sử class khởi động `ShopApplication` nằm trong package `com.example.shop` và các module được phát hiện theo cách bố trí mặc định từ các package con trực tiếp.

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/                      # Application module: ordering
│   ├── OrderFacade.java           # API công khai ở root package
│   ├── PlaceOrderRequest.java     # DTO công khai
│   ├── events/
│   │   ├── package-info.java      # @NamedInterface("events")
│   │   └── OrderPlaced.java       # Event contract được công bố
│   └── internal/
│       ├── OrderingService.java   # Chi tiết triển khai
│       ├── OrderRepository.java   # Chi tiết persistence
│       └── OrderEntity.java       # Entity nội bộ
├── notification/                  # Application module: notification
│   ├── package-info.java          # Ràng buộc allowedDependencies
│   └── internal/
│       ├── OrderNotificationListener.java
│       └── EmailSender.java
└── analytics/                     # Application module: analytics
    └── internal/
        └── OrderAnalyticsListener.java
~~~

Với cấu trúc này:

1. `ordering` công bố `OrderFacade` và `PlaceOrderRequest` ở root package.
2. `ordering.events` là subpackage nhưng có thể được công bố thêm như một **named interface**.
3. `ordering.internal` chứa implementation và dữ liệu mà consumer không nên truy cập.
4. `notification` chỉ cần sự kiện `OrderPlaced`. Nếu module này không có nhu cầu gọi đặt hàng đồng bộ, có thể giới hạn nó chỉ được phụ thuộc vào interface `ordering::events`.

Tên `internal` giúp người phát triển nhận biết ý đồ, nhưng **quy tắc không dựa riêng vào chuỗi tên này**: trong mô hình Spring Modulith mặc định, các subpackage khác của module cũng được coi là nội bộ nếu không khai báo thành named interface. Ngoài ra, khả năng phát hiện module có thể được tùy biến; các ví dụ trong bài dựa trên cách sắp xếp module mặc định.

### Sơ đồ phụ thuộc mong muốn

~~~mermaid
flowchart LR
    subgraph O["ordering"]
      API["API / facade"]
      EVENT["Named interface: events<br/>OrderPlaced"]
      IMPL["internal<br/>service, repository, entity"]
      IMPL --> API
      IMPL --> EVENT
    end
    N["notification<br/>OrderNotificationListener"] --> EVENT
    A["analytics<br/>OrderAnalyticsListener"] --> EVENT
~~~

Các mũi tên từ `notification` và `analytics` thể hiện **phụ thuộc mã nguồn vào hợp đồng sự kiện**. Ở chiều runtime, module `ordering` phát sự kiện và Spring chuyển cho các listener. `ordering` không import các listener, nên không có phụ thuộc mã nguồn ngược trở lại.

## 4. Root package: API mặc định của application module

Một facade giúp bên gọi yêu cầu hành động và nhận kết quả rõ ràng mà không biết chi tiết xử lý:

~~~java
// file: com/example/shop/ordering/OrderFacade.java
package com.example.shop.ordering;

import java.util.UUID;

public interface OrderFacade {
    UUID placeOrder(PlaceOrderRequest request);
}
~~~

~~~java
// file: com/example/shop/ordering/PlaceOrderRequest.java
package com.example.shop.ordering;

import java.util.List;
import java.util.UUID;

public record PlaceOrderRequest(
        UUID customerId,
        List<UUID> productIds
) {
    public PlaceOrderRequest {
        productIds = List.copyOf(productIds);
    }
}
~~~

`OrderFacade` và `PlaceOrderRequest` nằm trực tiếp dưới `ordering` nên thuộc bề mặt API mặc định. `List.copyOf(...)` ngăn caller thay đổi danh sách sản phẩm thông qua tham chiếu truyền vào record, giúp hợp đồng dữ liệu dễ kiểm soát hơn.

Implementation có thể nằm trong `ordering.internal`:

~~~java
// file: com/example/shop/ordering/internal/OrderingService.java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.OrderFacade;
import com.example.shop.ordering.PlaceOrderRequest;
import org.springframework.stereotype.Service;
import java.util.UUID;

@Service
class OrderingService implements OrderFacade {

    private final OrderRepository orders;

    OrderingService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public UUID placeOrder(PlaceOrderRequest request) {
        // Repository giả định của riêng module ordering.
        return orders.createOrder(request);
    }
}
~~~

`OrderingService` có phạm vi truy cập package-private và nằm trong subpackage nội bộ. Module khác chỉ nên phụ thuộc vào `OrderFacade`; việc Spring inject bean theo interface không yêu cầu class implementation phải trở thành API của module.

**Khi nào dùng facade?** Khi caller cần hành động ngay, phải biết kết quả trước khi tiếp tục hoặc cần một truy vấn đồng bộ. Ví dụ thao tác đặt hàng cần trả về ID mới tạo. Trong những trường hợp có thể phát đi một sự thật rồi để các module khác tự quyết định phản ứng, **event contract** thường phù hợp hơn.

## 5. Named interface: công bố có chọn lọc một subpackage

Không phải hợp đồng công khai nào cũng cần nằm trong root package. Khi module có nhiều nhóm hợp đồng, gom chúng vào subpackage giúp code rõ mục đích hơn. Spring Modulith cho phép công bố một package con như một **named interface**.

Ví dụ, đặt event contract ở `ordering.events`:

~~~java
// file: com/example/shop/ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

~~~java
// file: com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Annotation `@NamedInterface("events")` khai báo package `ordering.events` là một nhóm hợp đồng được phép cho module khác tham chiếu. Vì vậy:

- `ordering.events.OrderPlaced` được công bố qua interface có tên `events`.
- `ordering.internal.OrderEntity` vẫn là kiểu nội bộ, dù có thể được khai báo `public` trong mã Java.
- Consumer có thể được cấu hình phụ thuộc **chỉ** vào interface `events`, không cần truy cập mọi API của `ordering`.

Giả sử `notification` không cần đặt hàng trực tiếp, mà chỉ phản ứng với event. Khai báo trên root package của module `notification`:

~~~java
// file: com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

Ý nghĩa cú pháp `ordering::events`:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ordering` | Tên application module mà `notification` được phép tham chiếu |
| `::` | Dấu phân tách module và named interface |
| `events` | Tên interface được định nghĩa bởi `@NamedInterface("events")` |

Theo đó, code ở `notification` được phép phụ thuộc vào `OrderPlaced` đã công bố nhưng không được tự ý tham chiếu facade hoặc implementation khác của `ordering` nếu ràng buộc dependency không cho phép. **Giới hạn này được kiểm tra bởi công cụ kiến trúc của Spring Modulith**, chứ không phải Java compiler tự thực thi quy tắc `allowedDependencies`.

Nếu muốn một consumer được phép dùng cả API root và nhóm events, cần mô tả đúng nhu cầu phụ thuộc trong thiết kế module và cấu hình các named interface tương ứng. Không nên mở toàn bộ module chỉ vì một listener cần một event.

### Public trong Java nhưng chưa công khai về kiến trúc

Đoạn code dưới đây biểu diễn một phụ thuộc sai:

~~~java
package com.example.shop.notification.internal;

// Sai ranh giới module: import implementation của ordering.
import com.example.shop.ordering.internal.OrderEntity;

class OrderNotificationHelper {
    void prepare(OrderEntity order) {
        // Phụ thuộc chặt vào entity và cấu trúc dữ liệu của ordering.
    }
}
~~~

Nếu `OrderEntity` được khai báo `public`, đoạn code này **có thể biên dịch Java thành công**. Tuy nhiên, việc tham chiếu vào subpackage nội bộ vi phạm ranh giới Spring Modulith mặc định và có thể bị `ApplicationModules.verify()` phát hiện. Nếu entity package-private, Java compiler đã chặn truy cập từ package khác trước đó.

Sửa theo hướng dùng API hợp lệ:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;

class OrderNotificationHelper {
    void prepare(OrderPlaced event) {
        // Chỉ phụ thuộc vào dữ liệu hợp đồng sự kiện.
    }
}
~~~

Đừng lạm dụng named interface để đưa toàn bộ entity, repository hoặc service nội bộ ra ngoài. Việc mở API rộng khiến module khác ngày càng khó thay đổi độc lập.

## 6. API sự kiện: công bố sự thật, không công bố cách xử lý

Trong `SPRING_MODULITH_APPLICATION_EVENTS`, kiểu API đặc biệt quan trọng là **event contract**. Module phát công bố một sự kiện có ý nghĩa nghiệp vụ; các module quan tâm lắng nghe và thực hiện tác vụ trong phạm vi sở hữu của chúng.

Giả sử phiên bản đầy đủ của `OrderingService` có lưu dữ liệu và publish event:

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.OrderFacade;
import com.example.shop.ordering.PlaceOrderRequest;
import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService implements OrderFacade {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderingService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Override
    @Transactional
    public UUID placeOrder(PlaceOrderRequest request) {
        UUID orderId = orders.createOrder(request);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                Instant.now(clock)
        ));

        return orderId;
    }
}
~~~

Đây là đoạn code minh họa: `OrderRepository` là thành phần persistence riêng của module, và `Clock` được cấu hình như bean để kiểm soát thời gian trong kiểm thử. Ví dụ này thay thế implementation giản lược ở phần trước, không phải tạo hai bean `OrderingService` cùng tồn tại.

Lưu ý các hướng phụ thuộc:

- `OrderingService` biết `ApplicationEventPublisher` và `OrderPlaced`.
- `OrderingService` **không import** `OrderNotificationListener` hay `OrderAnalyticsListener`.
- Bên nhận chỉ cần import `OrderPlaced` từ named interface `ordering::events`.
- Event chứa ID và thời gian; không mang `OrderEntity`, persistence context hoặc đối tượng phụ thuộc lazy-loading sang module khác.

### Listener trong module tiêu thụ

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final EmailSender emailSender;

    OrderNotificationListener(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        emailSender.sendOrderConfirmation(event.orderId());
    }
}
~~~

`EmailSender` là implementation do `notification` sở hữu. `@ApplicationModuleListener` của Spring Modulith hỗ trợ mô hình listener giao dịch xử lý **sau khi transaction nguồn commit**, thường theo cơ chế bất đồng bộ với transaction riêng khi hạ tầng async được bật và cấu hình phù hợp.

Tại sao điều này liên quan đến **API công khai**? Vì sự thay đổi ở bên phát chỉ làm thay đổi **sự thật được công bố**; bên phát không biết người nhận và không quyết định người nhận phải thực hiện những thao tác nào. Module `notification` có thể thay email bằng push notification mà không sửa `OrderingService`, miễn hợp đồng `OrderPlaced` vẫn phù hợp.

### Phụ thuộc mã nguồn và luồng runtime không trùng nhau

~~~mermaid
flowchart TD
    O["ordering.internal<br/>OrderingService"] -->|publish| E["OrderPlaced<br/>ordering::events"]
    E -->|listener| N["notification.internal<br/>OrderNotificationListener"]
    E -->|listener| A["analytics.internal<br/>OrderAnalyticsListener"]
~~~

Sơ đồ trên trình bày **luồng giao sự kiện trong runtime**. Ở lớp phụ thuộc Java, `notification` và `analytics` import kiểu `OrderPlaced` từ `ordering`. Spring Modulith không yêu cầu `ordering` import người nhận để biết sự kiện đã được xử lý.

## 7. Phân biệt các cách giao tiếp tại ranh giới API

Một module có thể công bố nhiều kiểu hợp đồng, vì nhu cầu nghiệp vụ không giống nhau.

| Cách giao tiếp | Hợp đồng công khai | Khi nên dùng | Điều cần chú ý |
| --- | --- | --- | --- |
| **Synchronous facade** | `OrderFacade.placeOrder(request)` | Cần kết quả hoặc lỗi ngay | Caller biết bên phục vụ và có phụ thuộc trực tiếp |
| **Domain/application event** | `OrderPlaced` | Thông báo sự thật cho nhiều bên tự phản ứng | Listener có thể chạy sau commit, bất đồng bộ; không bảo đảm hoàn tất tức thì |
| **Command gửi cho một bên** | `ReserveInventory` hoặc facade tương ứng | Yêu cầu thực hiện một hành động cụ thể | Cần xác định bên chịu trách nhiệm, trạng thái kết quả và retry |
| **Integration message** | Message chứa `OrderPlaced` đã được ánh xạ | Thông báo ra tiến trình/hệ thống ngoài | Cần serialization, versioning, transport và chính sách delivery |

**Event không đồng nghĩa với message.** `OrderPlaced` là một sự thật nghiệp vụ được mô tả trong code. Một message trên Kafka/RabbitMQ có thể mang payload tương ứng cùng metadata; gọi `ApplicationEventPublisher.publishEvent(...)` trong Spring Boot không tự động gửi message qua broker.

Trong nội bộ Spring Modulith, application event có thể đi hoàn toàn qua Spring event infrastructure trong cùng JVM. Khi cần externalization, hệ thống phải chọn và cấu hình adapter tương ứng. Vì vậy API module có thể ổn định trước, trong khi cách vận chuyển sự kiện được bổ sung sau.

## 8. Giao dịch và hợp đồng sự kiện

Định nghĩa API công khai không chỉ là **tên kiểu và trường dữ liệu**. Với event, consumer còn phải hiểu sự kiện có ý nghĩa khi nào:

1. `ordering` mở transaction và lưu đơn hàng.
2. `ordering` gọi `publishEvent(new OrderPlaced(...))`.
3. Transaction có thể **commit** hoặc **rollback** sau lệnh publish.
4. Bên nhận cần quyết định phản ứng ngay lúc publish hay chỉ sau khi dữ liệu đã commit.

Ví dụ với listener Spring thông thường:

~~~java
@EventListener
void on(OrderPlaced event) {
    // Theo cấu hình mặc định, có thể chạy đồng bộ ngay khi publish.
}
~~~

Với listener giao dịch sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    // Chạy sau khi transaction đã commit thành công.
}
~~~

`@TransactionalEventListener` mặc định dùng phase `AFTER_COMMIT`; đoạn code ghi rõ phase để dễ đọc. Khi publish không có transaction đang hoạt động, listener giao dịch sẽ không chạy theo mặc định, trừ khi cấu hình fallback phù hợp. Nếu callback sau commit cần ghi dữ liệu vào database, phải thiết kế transaction mới thích hợp, chẳng hạn `REQUIRES_NEW` hoặc cơ chế tích hợp của `@ApplicationModuleListener`.

Vì thế, hợp đồng event nên mô tả rõ:

- **Ý nghĩa thời điểm**: “đã được xử lý trong bộ nhớ”, “đã ghi nhận vào transaction” hay “đã được commit”?
- **Khả năng quan sát dữ liệu**: consumer có được giả định order ID đã tra cứu được từ dữ liệu commit không?
- **Chính sách lỗi**: lỗi consumer có ảnh hưởng transaction của publisher không?
- **Khả năng xử lý lại**: consumer có thể nhận cùng một event nhiều lần không?

Trong mô hình dùng `@ApplicationModuleListener` sau commit, lỗi email không mặc nhiên làm rollback đơn hàng đã commit. Nhưng điều đó **không tự động bảo đảm** sự kiện không mất hoặc listener chắc chắn được retry.

## 9. API của event cần hỗ trợ độ tin cậy

Một hợp đồng event đơn giản:

~~~java
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Ba trường có vai trò khác nhau:

- `eventId`: định danh **lần xảy ra sự kiện**, có thể dùng để ghi nhận đã xử lý và khử trùng lặp.
- `orderId`: định danh **đơn hàng**, cho phép liên hệ tới aggregate nghiệp vụ.
- `occurredAt`: thời điểm nghiệp vụ ghi nhận sự kiện; không nhất thiết là thời điểm consumer nhận hoặc xử lý xong.

Nếu cùng một event được gửi lại do retry, hãy **giữ nguyên `eventId`**. Không tạo event ID mới cho bản phát lại, nếu không consumer khó nhận biết việc xử lý trùng.

Spring Modulith có **Event Publication Registry** để ghi nhận publication dành cho các listener được hỗ trợ, theo dõi việc hoàn tất và hỗ trợ tìm publication chưa hoàn tất khi đã cấu hình cơ chế lưu trữ tương ứng. Đây là phần hạ tầng phục vụ giao sự kiện đáng tin cậy; **API công khai vẫn cần hợp đồng dữ liệu phù hợp** để thực hiện idempotency và truy vết.

Ví dụ khi listener ghi trạng thái đã gửi email, chiến lược có thể là:

~~~text
OrderPlaced(eventId=E1, orderId=O1)
                |
                v
      Đã xử lý E1 thành công?
          /           \
        Có            Chưa
        |              |
   Bỏ qua an toàn   Thử gửi email
                       |
                 Lưu kết quả / lỗi
~~~

Đây là sơ đồ nguyên tắc. Để ngăn xử lý trùng trong môi trường có concurrency, cần áp dụng ràng buộc dữ liệu, transaction và/hoặc khóa idempotency phù hợp. Với việc gửi ra hệ thống bên ngoài, khả năng chống gửi trùng còn phụ thuộc API đích có hỗ trợ idempotency key hay không.

Không nên đưa retry policy, trạng thái persistence nội bộ, class của registry hoặc DTO của broker vào contract nghiệp vụ nếu consumer không cần chúng. Bên nhận phải hiểu **điều gì đã xảy ra** và **cách nhận diện sự kiện**, trong khi cơ chế giao nhận có thể tiến hóa độc lập.

## 10. Giữ API nhỏ, ổn định và đúng trách nhiệm

### 10.1. API dựa trên nhu cầu của consumer

Đừng công bố cả repository chỉ vì `notification` cần tên khách hàng. Tùy nghiệp vụ, có thể:

- Đưa một snapshot dữ liệu tối thiểu, hợp pháp vào event (ví dụ loại thông báo và locale).
- Công bố một query API có chủ đích để consumer lấy dữ liệu.
- Giao việc chuẩn bị nội dung cho module sở hữu dữ liệu hoặc tích hợp qua một hợp đồng rõ ràng.

Lựa chọn phụ thuộc vào tính nhất quán, dữ liệu nhạy cảm, độ trễ và khả năng thay đổi. **Truy vấn ngược sau khi nhận event** có thể tạo phụ thuộc runtime và gặp trạng thái dữ liệu đã thay đổi; **snapshot trong event** giữ được ngữ cảnh tại lúc xảy ra sự kiện nhưng làm hợp đồng có nhiều dữ liệu hơn.

### 10.2. Hạn chế rò rỉ persistence model

Ví dụ nên tránh:

~~~java
public record OrderPlaced(OrderEntity entity) {}
~~~

Kiểu này khiến consumer hiểu chi tiết JPA, relation, lazy loading và phiên bản entity. Thay vào đó:

~~~java
public record OrderPlaced(UUID eventId, UUID orderId, Instant occurredAt) {}
~~~

Event không bắt buộc chỉ chứa ID, nhưng các trường phải là **dữ liệu hợp đồng có ý nghĩa**, không phải cách triển khai persistence được vô tình tiết lộ.

### 10.3. Quản lý phiên bản hợp đồng

Với event được nhiều module sử dụng:

1. Thêm trường khi có nhu cầu thực và xác định xử lý giá trị mặc định cho consumer cũ.
2. Tránh thay đổi ý nghĩa trường cũ khi không có kế hoạch chuyển đổi.
3. Phân biệt phiên bản Java contract trong cùng ứng dụng với phiên bản schema của integration message qua broker.
4. Khi có nhiều nhóm consumer, dùng named interface để xác định tập hợp hợp đồng họ thật sự cần.

Với message liên tiến trình, rolling deployment và việc consumer dùng phiên bản khác producer có thể yêu cầu schema evolution chặt chẽ hơn so với bản build modular monolith chung.

### 10.4. Không tạo phụ thuộc vòng

Nếu `ordering` gọi service trong `notification` và `notification` lại import repository trong `ordering`, hai module có thể hình thành chu trình phụ thuộc và khó bảo trì.

Application events giúp đổi hướng giao tiếp: `ordering` công bố `OrderPlaced`, còn `notification` chỉ phụ thuộc hợp đồng event. Tuy nhiên event chỉ giảm phụ thuộc khi được thiết kế đúng; một listener gọi ngược vào nhiều implementation nội bộ vẫn tạo ràng buộc phức tạp.

## 11. Kiểm tra ranh giới bằng Spring Modulith

Một trong những lợi ích của Spring Modulith là khả năng **xác minh cấu trúc application modules** dựa trên mô hình package và ràng buộc đã khai báo.

Trong test của ứng dụng, có thể viết:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi được chạy với các dependency Spring Modulith phù hợp, `verify()` có thể phát hiện các lỗi kiến trúc như:

- Một module tham chiếu kiểu từ **subpackage nội bộ** của module khác.
- Phụ thuộc trái với khai báo `allowedDependencies`.
- Các chu trình phụ thuộc giữa application modules mà mô hình phát hiện.

Chẳng hạn `notification` khai báo chỉ phụ thuộc `ordering::events` nhưng vô tình import `ordering.internal.OrderRepository`: test xác minh phải phản ánh vi phạm theo mô hình module được cấu hình.

**Giới hạn cần nhớ:** kiểm tra kiến trúc dựa trên cấu trúc và phụ thuộc mã nguồn không tự chứng minh listener sẽ được gọi, xử lý sau commit chính xác, retry thành công, hay message được giao đúng một lần. Những hành vi đó cần kiểm thử runtime và quan sát phù hợp.

Khi kiểm thử module, `@ApplicationModuleTest` còn giúp bootstrap một module theo ranh giới Spring Modulith để tập trung kiểm tra logic và các tương tác được cho phép. Với application events, các bài test nên kiểm tra thêm:

| Tình huống | Cần chứng minh |
| --- | --- |
| Đặt hàng thành công | `OrderPlaced` được phát với `orderId` và `eventId` hợp lệ |
| Transaction rollback | Listener sau commit không thực hiện side effect |
| Consumer bị lỗi | Transaction đơn hàng đã commit không bị “rollback ngược”; publication chưa hoàn tất được xử lý theo cấu hình |
| Phát lại cùng event | Consumer xử lý an toàn, không nhân đôi tác vụ nghiệp vụ |
| Thêm consumer mới | Publisher vẫn không phụ thuộc code của consumer |

Đây là các **kịch bản kiểm thử cần triển khai ở những bước chuyên sâu**, không phải kết quả đã được xác nhận chỉ nhờ `verify()`.

## 12. Những lỗi thiết kế thường gặp

| Dấu hiệu | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Module khác import `ordering.internal.*` | Phụ thuộc vào implementation | Dùng root API hoặc named interface được công bố |
| Đặt mọi class vào root package | API trở nên quá rộng, khó biết kiểu nào ổn định | Chuyển implementation xuống subpackage, chỉ giữ hợp đồng cần thiết |
| Công bố JPA entity trong event | Lộ persistence model và lazy loading | Dùng record/DTO chứa ID, dữ liệu nghiệp vụ rõ nghĩa |
| `ordering` gọi trực tiếp từng listener | Publisher biết mọi consumer | Publish một event, để từng consumer đăng ký listener |
| Có `@NamedInterface` nhưng không chạy `verify()` | Vi phạm dễ tồn tại mà Java compiler không phát hiện | Bổ sung kiểm tra kiến trúc trong test/CI |
| Xem `@Async` như cơ chế giao sự kiện bền vững | Crash có thể làm mất tác vụ chưa hoàn thành | Thiết kế registry/persistence, retry và idempotency phù hợp |
| Đổi trường event không quản lý tác động | Consumer có thể không còn biên dịch hoặc hiểu sai sự kiện | Quản lý hợp đồng và quy trình nâng phiên bản |
| Dùng event cho yêu cầu bắt buộc có kết quả ngay | Khó thể hiện điều kiện thành công và xử lý lỗi | Cân nhắc facade/command đồng bộ cho thao tác đó |

## 13. Bài thực hành: bảo vệ API giữa ba module

Xây dựng ứng dụng minh họa với `ordering`, `notification` và `analytics`:

1. Trong root `ordering`, công bố `OrderFacade` và `PlaceOrderRequest`. Đặt implementation service, repository, entity trong `ordering.internal`.
2. Tạo `OrderPlaced` trong `ordering.events` gồm `eventId`, `orderId`, `occurredAt`; khai báo `@NamedInterface("events")` ở `package-info.java`.
3. Trong root `notification`, khai báo `@ApplicationModule(allowedDependencies = "ordering::events")`. Tạo listener chỉ import `OrderPlaced` và gọi service gửi thông báo nội bộ.
4. Trong `analytics`, tạo listener thứ hai cập nhật thống kê theo event. Không chỉnh lại `OrderingService` khi thêm consumer mới.
5. Viết test `ApplicationModules.of(ShopApplication.class).verify()` và chạy để kiểm tra phụ thuộc.
6. Cố tình thêm import tới `ordering.internal.OrderEntity` trong `notification`; dự đoán loại vi phạm và kiểm tra kết quả test, sau đó gỡ import.
7. Mô phỏng việc transaction đặt hàng rollback và việc listener thất bại sau commit; giải thích khác biệt giữa ranh giới module và độ tin cậy giao sự kiện.

### Câu hỏi tự đánh giá

**Câu 1.** Một `public class` nằm trong `ordering.internal` có mặc nhiên là API công khai của module không?

*Không.* `public` chỉ là quyền truy cập Java; với ranh giới mặc định của Spring Modulith, subpackage nội bộ không được module khác sử dụng trừ khi có cấu hình công bố hợp lệ.

**Câu 2.** Vì sao cần `@NamedInterface("events")` khi đã có root package API?

*Để công bố có chọn lọc hợp đồng từ một package con*, và cho phép consumer chỉ phụ thuộc vào nhóm hợp đồng sự kiện cụ thể thay vì toàn bộ implementation hoặc API không liên quan.

**Câu 3.** Consumer biết kiểu `OrderPlaced` có phá vỡ mục tiêu giảm phụ thuộc không?

*Không.* Consumer có một phụ thuộc **có chủ đích vào hợp đồng**; thiết kế giảm phụ thuộc vào implementation và giảm việc publisher phải biết từng consumer.

**Câu 4.** `ApplicationModules.verify()` có chứng minh event đã được giao đáng tin cậy không?

*Không.* Nó kiểm tra kiến trúc module; delivery, transaction, retry, idempotency và khả năng khôi phục cần cấu hình, kiểm thử hành vi và quan sát riêng.

## 14. Ghi nhớ để áp dụng

**API công khai của module là lời cam kết về những gì module cho phép bên ngoài phụ thuộc**, không chỉ là các class được gắn từ khóa `public`. Trong Spring Modulith, root package cung cấp API mặc định, named interface công bố có chọn lọc từ package con, còn `allowedDependencies` và `ApplicationModules.verify()` giúp kiểm soát việc sử dụng các hợp đồng đó.

Với bài toán application events, đặt kiểu event ở bề mặt API được công bố, giữ publisher và listener implementation trong module sở hữu, và chỉ trao đổi dữ liệu nghiệp vụ cần thiết. Khi thiết kế thêm xử lý sau commit, event publication registry, retry, kiểm thử và observability, ranh giới API rõ ràng sẽ giúp các module tiến hóa mà không phải phụ thuộc vào chi tiết triển khai của nhau.
