# Phụ thuộc một chiều

## 1. Vì sao hướng phụ thuộc quyết định chất lượng ranh giới module?

Trong một ứng dụng **modular monolith**, các module cùng chạy trong một tiến trình nhưng cần có ranh giới nghiệp vụ và mã nguồn rõ ràng. Một ranh giới chỉ thực sự hữu ích nếu mỗi module biết **nó được phép phụ thuộc vào ai** và **module nào được phép sử dụng API của nó**.

Giả sử một ứng dụng bán hàng có bốn module:

- `catalog` quản lý thông tin sản phẩm được phép bán.
- `orders` tạo đơn hàng, kiểm tra điều kiện đặt hàng và công bố các sự kiện của đơn hàng.
- `notifications` gửi xác nhận cho khách khi đơn được tạo.
- `analytics` tổng hợp chỉ số từ các sự kiện đơn hàng.

Khi `orders` cần tra cứu giá, nó gọi **API công khai** của `catalog`. Khi đơn đã được đặt, `orders` phát `OrderPlaced`; `notifications` và `analytics` đăng ký listener để phản ứng. Nếu `orders` không import những lớp thuộc `notifications` hay `analytics`, việc bổ sung loại thông báo hoặc báo cáo mới không buộc sửa phần điều phối trong `orders`.

**Phụ thuộc một chiều** nghĩa là một quan hệ giữa hai module được định nghĩa theo một hướng rõ ràng, chẳng hạn `orders → catalog`. Nếu chiều ngược lại `catalog → orders` cũng xuất hiện, hai module hình thành **vòng phụ thuộc trực tiếp** và không còn phát triển độc lập dễ dàng. Với nhiều module, vòng phụ thuộc còn có thể gián tiếp: `A → B → C → A`.

Mục tiêu của bài này là hiểu được:

1. Hướng phụ thuộc trong **mã nguồn** khác gì hướng giao sự kiện khi ứng dụng chạy.
2. Cách sử dụng API công khai, package nội bộ và application event để giữ đồ thị phụ thuộc **không có chu trình**.
3. Cách Spring Modulith phát hiện vi phạm ranh giới bằng `ApplicationModules.verify()` và giới hạn phụ thuộc bằng `allowedDependencies`.
4. Cách giữ phụ thuộc một chiều khi dùng listener sau commit, Event Publication Registry và retry.

## 2. Phân biệt dependency trong code với luồng giao tiếp khi chạy

Một module **phụ thuộc vào** module khác ở cấp Java khi mã nguồn của nó tham chiếu kiểu hoặc API thuộc module kia. Ví dụ:

~~~java
// Đoạn code thuộc module orders
import com.example.shop.catalog.CatalogQuery;

class OrderApplicationService {
    private final CatalogQuery catalog;

    OrderApplicationService(CatalogQuery catalog) {
        this.catalog = catalog;
    }
}
~~~

Import `CatalogQuery` tạo cạnh phụ thuộc tĩnh **orders → catalog**, vì `orders` cần API của `catalog` để biên dịch. Hướng mũi tên trong đồ thị phụ thuộc nên được định nghĩa nhất quán là **module dùng → module được dùng**.

Với event, một chi tiết dễ gây nhầm là **hướng event chạy có thể ngược với hướng phụ thuộc mã nguồn**:

~~~mermaid
flowchart LR
    subgraph DEP["Đồ thị phụ thuộc mã nguồn — A → B nghĩa là A dùng API của B"]
        N["notifications"] -->|"import OrderPlaced"| O["orders"]
        A["analytics"] -->|"import OrderPlaced"| O
        O -->|"dùng CatalogQuery"| C["catalog"]
    end
~~~

Ở thời điểm chạy, `orders` phát sự kiện, còn `notifications` và `analytics` nhận:

~~~mermaid
flowchart LR
    O["orders"] -->|"publish OrderPlaced"| E(("Application Event"))
    E -->|"dispatch"| N["notifications"]
    E -->|"dispatch"| A["analytics"]
~~~

Hai hình mô tả **hai loại quan hệ khác nhau**. Vì `notifications` cần biết lớp `OrderPlaced`, nó có phụ thuộc Java vào API sự kiện của `orders`. Nhưng `orders` không biết listener hoặc service của `notifications`; do vậy **không tồn tại cạnh phụ thuộc mã nguồn ngược lại**.

Nói "dùng event là không có phụ thuộc" là chưa chính xác. Event vẫn là một **hợp đồng giữa module phát và module nhận**. Ưu điểm nằm ở việc module phát không cần biết tất cả người nhận và không phải gọi các implementation của họ.

## 3. Đồ thị phụ thuộc phải là một DAG

Có thể mô hình hóa kiến trúc thành một **đồ thị có hướng**: mỗi đỉnh là một module, mỗi cạnh là một phụ thuộc mã nguồn đã được phép. Đồ thị lý tưởng cho tính độc lập là một **DAG (directed acyclic graph)**, tức đồ thị có hướng và **không có chu trình**.

Ví dụ một đồ thị hợp lệ:

~~~mermaid
flowchart TB
    N["notifications"] --> O["orders"]
    A["analytics"] --> O
    O --> C["catalog"]
    I["inventory"] --> C
    F["fulfillment"] --> O
    F --> I
~~~

Ở đây, `fulfillment` có thể phụ thuộc cả API `orders` và `inventory`; điều đó không tự tạo vòng lặp. DAG cũng **không bắt buộc** là kiến trúc nhiều tầng cứng nhắc hay mỗi module chỉ được phụ thuộc đúng một module.

Ví dụ không hợp lệ:

~~~mermaid
flowchart LR
    O["orders"] --> P["payments"]
    P --> I["inventory"]
    I --> O
~~~

Nếu `orders` gọi API thanh toán, `payments` truy cập API tồn kho, rồi `inventory` lại import implementation của `orders`, cả ba tạo vòng phụ thuộc. Hậu quả thường thấy:

- Sửa API một module khiến nhiều module khác phải đổi theo.
- Khó kiểm thử một module riêng vì cần khởi tạo các dependency vòng quanh.
- Khó tách cấu trúc package và quy tắc giao dịch trong tương lai.
- Trách nhiệm sở hữu trạng thái bị mờ: module này có thể gọi ngược để sửa dữ liệu của module kia.
- Dễ xuất hiện vòng gọi lồng nhau khi chạy, gây lỗi nghiệp vụ và transaction khó theo dõi.

Spring Modulith có thể kiểm tra các phụ thuộc module được phát hiện trong mã nguồn và phát hiện vòng phụ thuộc. Tuy vậy, một đồ thị Java không có chu trình **chưa bảo đảm** không có vòng tương tác nghiệp vụ gián tiếp qua SQL, event đồng bộ hoặc HTTP; các luồng đó cũng cần được thiết kế và kiểm thử.

## 4. Xây ví dụ module orders chỉ phụ thuộc catalog

Giả sử mỗi package trực tiếp dưới `com.example.shop` là một application module trong cấu hình Spring Modulith theo quy ước:

~~~text
com.example.shop/
├── ShopApplication.java
├── catalog/
│   ├── CatalogQuery.java           # API công khai
│   ├── ProductView.java            # DTO công khai
│   └── internal/
│       ├── ProductEntity.java
│       └── JpaCatalogQuery.java
├── orders/
│   ├── OrderPlaced.java            # Event công khai
│   └── internal/
│       ├── OrderEntity.java
│       ├── OrderRepository.java
│       └── OrderApplicationService.java
├── notifications/
│   └── internal/
│       ├── OrderPlacedNotificationListener.java
│       └── NotificationService.java
└── analytics/
    └── internal/
        └── OrderPlacedProjectionListener.java
~~~

Theo quy ước API của Spring Modulith, các kiểu ở package gốc của module có thể được công bố cho module khác, còn package nội bộ không phải đường truy cập được phép. Khi cần công khai một package con, có thể định nghĩa **named interface** thay vì đưa toàn bộ implementation ra ngoài.

### 4.1. catalog cung cấp API đọc ổn định

~~~java
// CatalogQuery.java
package com.example.shop.catalog;

import java.util.UUID;

public interface CatalogQuery {
    ProductView requireSellable(UUID productId);
}
~~~

~~~java
// ProductView.java
package com.example.shop.catalog;

import java.math.BigDecimal;
import java.util.UUID;

public record ProductView(UUID productId, BigDecimal price) {}
~~~

`ProductView` là một DTO bất biến. `orders` không cần import `ProductEntity`, `JpaCatalogQuery` hay `CatalogRepository`. Module `catalog` có thể thay cách truy vấn database, miễn giữ hợp đồng API đã công bố.

### 4.2. orders xử lý nghiệp vụ và phát event

~~~java
// OrderPlaced.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {}
~~~

~~~java
// OrderApplicationService.java
package com.example.shop.orders.internal;

import com.example.shop.catalog.CatalogQuery;
import com.example.shop.catalog.ProductView;
import com.example.shop.orders.OrderPlaced;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final CatalogQuery catalog;
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderApplicationService(CatalogQuery catalog,
                                   OrderRepository orders,
                                   ApplicationEventPublisher events,
                                   Clock clock) {
        this.catalog = catalog;
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(UUID productId, UUID customerId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        ProductView product = catalog.requireSellable(productId);
        OrderEntity order = orders.save(
                OrderEntity.create(product.productId(), customerId,
                                   quantity, product.price()));

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(), order.getId(),
                customerId, Instant.now(clock)));
        return order.getId();
    }
}
~~~

Đoạn mã minh họa giả định `OrderEntity`, `OrderRepository`, `Clock` và implementation của `CatalogQuery` đã được tạo và cấu hình. Nếu giá sản phẩm có thể thay đổi, quy tắc lưu **giá chốt trên đơn** phải được `orders` xác định rõ; ví dụ trên lưu giá nhận được lúc tạo đơn.

Tại đây, `orders` phụ thuộc `catalog` **qua API đọc**; các bước lưu đơn thuộc `orders.internal`. Sau khi đặt đơn, `orders` phát một sự thật nghiệp vụ: `OrderPlaced`. Nó không import `NotificationService` và không cần biết có bao nhiêu listener.

### 4.3. notifications nhận sự kiện từ orders

~~~java
// OrderPlacedNotificationListener.java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedNotificationListener {
    private final NotificationService notifications;

    OrderPlacedNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notifications.sendOrderConfirmationOnce(
                event.orderId(), event.customerId());
    }
}
~~~

`sendOrderConfirmationOnce(...)` là phương thức minh họa: phần triển khai phải có khóa chống gửi trùng (chẳng hạn `orderId + notificationType`) và lưu trạng thái giao nhận phù hợp. Java annotation không tự bảo đảm chỉ gửi một lần.

Phụ thuộc tĩnh của `notifications` là **notifications → orders**, bởi listener import kiểu event công khai. Chỉ một module nhận thay đổi khi bổ sung cách gửi thông báo; module `orders` vẫn giữ nguyên.

Nếu `analytics` cũng nghe `OrderPlaced`, nó chỉ cần biết event và ghi projection riêng. Không nên để `analytics` đọc trực tiếp `orders.internal.OrderRepository` rồi sửa các bảng thuộc `orders`.

## 5. Bảo vệ hướng phụ thuộc bằng Spring Modulith

Spring Modulith xây dựng mô hình application module dựa trên cấu trúc package và cho phép xác minh những quan hệ module tìm thấy. Hai công cụ quan trọng cho yêu cầu **phụ thuộc một chiều** là API công khai và quy định module được phép phụ thuộc.

### 5.1. Chỉ công khai những kiểu cần dùng

Ví dụ `catalog` công bố `CatalogQuery` và `ProductView` trong package gốc, giữ repository/entity trong `catalog.internal`. Module khác chỉ import kiểu công khai. Nếu `orders` cố import `catalog.internal.ProductEntity`, nó đã đi vào implementation của module khác, làm mất ranh giới đóng gói.

Khi API đặt trong package con, khai báo *named interface* theo quy ước:

~~~java
// com/example/shop/catalog/api/package-info.java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.catalog.api;
~~~

Khi đó các kiểu được đặt trong `catalog.api` tạo thành một mặt giao tiếp được công bố tên là `catalog::api`. Chỉ dùng ví dụ này nếu các interface/DTO thực sự được chuyển sang package đó; ví dụ `CatalogQuery` và `ProductView` ở trên đang nằm tại package gốc `catalog`.

### 5.2. Giới hạn module được phép tham chiếu

Có thể khai báo ràng buộc cho `orders` tại `package-info.java`:

~~~java
// com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog"
)
package com.example.shop.orders;
~~~

Khai báo này nói rằng `orders` được phép phụ thuộc vào module `catalog`, ngoài những thành phần nền tảng không thuộc application module của ứng dụng. Nếu `orders` vô tình import API của `notifications` hoặc một module nghiệp vụ không được cho phép, bước xác minh module có thể phát hiện sự phụ thuộc ngoài phạm vi.

Khi dùng *named interface* `catalog::api`, có thể giới hạn chặt hơn:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog::api"
)
package com.example.shop.orders;
~~~

Các snippet `package-info.java` trên **là hai cách cấu hình thay thế**, không đặt đồng thời vào một package. Danh sách dependency phải đúng với cách tổ chức package/API thực tế; nếu `orders` cần thêm API của module khác theo nghiệp vụ, phải khai báo cụ thể và xem lại đồ thị.

### 5.3. Kiểm tra cấu trúc tự động

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleStructureTest {

    @Test
    void dependenciesFollowModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` là bước kiểm tra ranh giới module phù hợp cho CI: nó có thể phát hiện truy cập vào phần không công khai, các phụ thuộc không được phép và các chu trình giữa application modules. Kết quả kiểm tra phụ thuộc cấu hình module, package và các loại quan hệ mà Spring Modulith phát hiện.

Không nên dựa duy nhất vào việc code **biên dịch thành công**. Java cho phép import một public class ở package khác, nhưng điều đó chưa có nghĩa class đó được phép sử dụng qua ranh giới Spring Modulith.

## 6. Khi xuất hiện phụ thuộc hai chiều, xử lý thế nào?

Giả sử hệ thống ban đầu có quan hệ:

~~~text
orders   -> notifications   // orders gọi gửi email khi tạo đơn
notifications -> orders     // notifications đọc trạng thái đơn
~~~

Có ít nhất ba cách tiếp cận, mỗi cách giải quyết một nguyên nhân khác nhau:

**Cách 1: Phát sự kiện khi bên nhận chỉ cần phản ứng với sự kiện đã xảy ra.**

- `orders` phát `OrderPlaced` sau khi ghi nhận đơn.
- `notifications` import kiểu `OrderPlaced` và tự đăng ký listener.
- Xóa lời gọi trực tiếp từ `orders` sang `notifications` nếu thông báo là tác vụ phụ, không phải điều kiện bắt buộc để đơn được chấp nhận.

Đồ thị tĩnh còn **notifications → orders**. Nếu email lỗi, đơn vẫn có thể tồn tại; phải bổ sung retry và idempotency.

**Cách 2: Dùng API chỉ đọc của module sở hữu khi cần trạng thái hiện tại.**

Nếu `notifications` cần lấy thông tin đơn mới nhất, `orders` cung cấp `OrderLookup` trả DTO. `notifications` vẫn phụ thuộc `orders` theo một chiều, nhưng không import entity hoặc repository nội bộ.

**Cách 3: Đưa điều phối vào module nghiệp vụ thực sự chịu trách nhiệm quy trình.**

Giả sử cả `orders` và `payments` đều phải ra quyết định dựa trên nhau, đồng thời cần kết quả tức thì. Một module `checkout` có thể điều phối qua API công khai:

~~~mermaid
flowchart TB
    X["checkout"] --> O["orders"]
    X --> P["payments"]
~~~

Sơ đồ này phù hợp khi `checkout` thực sự sở hữu quy trình checkout và các bất biến có thể được duy trì qua các API ấy. Không nên thêm module điều phối giả tạo chỉ để đồ thị trông đẹp; nếu hai phần đang cùng sở hữu một bất biến dữ liệu chặt chẽ, cần cân nhắc lại **ranh giới nghiệp vụ và quyền sở hữu dữ liệu**.

Không nên tạo một module `common` để dồn mọi entity, repository và service của các module vào đó. Cách này thường chỉ **chuyển phụ thuộc sang một vị trí chung** mà không làm rõ ai sở hữu hành vi. Shared kernel chỉ nên chứa những khái niệm thực sự dùng chung, ổn định và có phạm vi xác định.

## 7. Một chiều không đồng nghĩa mọi giao tiếp đều bất đồng bộ

Nhu cầu nghiệp vụ quyết định chọn API đồng bộ hay event:

| Tình huống | Quan hệ phụ thuộc thường thấy | Cách giao tiếp phù hợp |
| --- | --- | --- |
| `orders` cần giá hiện tại trước khi đặt hàng | `orders → catalog` | Gọi API `CatalogQuery` đồng bộ |
| `notifications` phản ứng khi đơn tạo thành công | `notifications → orders` | Listener của `OrderPlaced` |
| `analytics` cập nhật dữ liệu báo cáo | `analytics → orders` | Event và projection riêng |
| `checkout` phải biết thanh toán thành công hay thất bại mới trả lời | `checkout → payments` | Gọi API hoặc quy trình giao dịch có trạng thái rõ ràng |
| Module đọc dữ liệu riêng của mình | Không tạo thêm phụ thuộc liên module | Repository/service nội bộ |

Phải phân biệt:

**`@EventListener`:** theo cấu hình Spring thông thường, listener chạy **đồng bộ tại `publishEvent(...)`**. Nếu listener gọi ngược module nguồn, có thể tạo chuỗi gọi phức tạp dù đồ thị Java không có vòng import trực tiếp. Exception của listener đồng bộ cũng có thể ảnh hưởng transaction publisher.

**`@TransactionalEventListener`:** mặc định chỉ kích hoạt sau commit thành công (`AFTER_COMMIT`) khi event được phát trong transaction đang hoạt động. Annotation này không tự bật async và không tự mở transaction mới. Nếu phát event ngoài transaction, listener mặc định không chạy trừ khi được cấu hình `fallbackExecution = true`.

**`@ApplicationModuleListener`:** do Spring Modulith cung cấp, kết hợp xử lý sau commit, async và transaction riêng (`REQUIRES_NEW`). Mẫu này phù hợp với phản ứng phụ thuộc kết quả đã commit, như thông báo hay cập nhật projection. Cần bảo đảm hạ tầng async và executor được cấu hình phù hợp trong ứng dụng.

Với mô hình `orders` phát event rồi `notifications` xử lý sau commit, việc thông báo lỗi **không thể rollback đơn đã commit**. Đây là một lựa chọn về tính nhất quán, không chỉ là chi tiết annotation.

## 8. Giữ ranh giới trong xử lý event đáng tin cậy

Nếu application event chỉ tồn tại trong bộ nhớ, hệ thống có thể mất việc xử lý khi tiến trình dừng giữa lúc module nguồn commit và lúc listener chạy. Spring Modulith cung cấp **Event Publication Registry** để ghi dấu publication cho các transactional listeners được theo dõi, cho phép nhận diện publication chưa hoàn tất và hỗ trợ khôi phục.

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant API as API Client
    participant O as orders
    participant DB as Database
    participant R as Publication Registry
    participant N as notifications
    API->>O: placeOrder(...)
    O->>DB: Lưu đơn (transaction A)
    O->>R: Ghi publication cho listener phù hợp (A)
    O->>DB: COMMIT A
    DB-->>API: Tạo đơn thành công
    R-->>N: Giao event sau commit
    N->>DB: Ghi trạng thái thông báo (transaction B)
    N-->>R: Xử lý hoàn tất
~~~

Sơ đồ lược hóa cách Spring thực thi event và registry; implementation và thời điểm đánh dấu hoàn tất có thể khác nhau theo phiên bản/cấu hình. Để lưu publication bền vững, cần chọn backend registry phù hợp (ví dụ JDBC/JPA), cấu hình database và transaction. Chỉ dùng `@ApplicationModuleListener` không tự biến event thành message bền vững.

Ranh giới một chiều vẫn được duy trì khi:

1. `orders` chỉ phát `OrderPlaced` thuộc API của chính nó.
2. Registry là hạ tầng kỹ thuật giao sự kiện, **không phải API nghiệp vụ của `notifications`** mà `orders` cần gọi.
3. `notifications` tự quyết định retry, trạng thái gửi, giới hạn lần thử và ghi nhận tác động của nó.
4. Listener xử lý idempotent theo khóa nghiệp vụ, chẳng hạn `(order_id, notification_type)`. Việc publication được gửi lại có thể xảy ra sau một lỗi hoặc restart.
5. Quan sát số publication chưa hoàn tất, thời gian trễ, lỗi listener và lượng retry để phát hiện sự cố mà không ghép logic giám sát của module nhận vào module phát.

**Event Publication Registry không cam kết tác động bên ngoài chỉ xảy ra đúng một lần (exactly-once).** Nếu gửi email thành công rồi JVM dừng trước khi ghi nhận xử lý hoàn tất, việc phục hồi có thể dẫn đến gửi lại. Sự an toàn này là trách nhiệm của thiết kế idempotency và trạng thái xử lý ở module nhận.

Không nên biến event nội bộ thành "thủ thuật" để tránh phụ thuộc khi module phát thực tế vẫn cần kết quả từ module nhận mới được commit. Khi đó, hãy dùng API đồng bộ hoặc mô hình quy trình dài hạn có trạng thái rõ ràng.

## 9. Kiểm thử không chỉ kiểm tra mũi tên trên sơ đồ

Một kiến trúc phụ thuộc một chiều cần được xác nhận ở ba mức:

| Mức kiểm tra | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Cấu trúc module | Có chu trình hoặc truy cập API nội bộ sai quy định không? | `ApplicationModules.of(...).verify()` PASS |
| Hợp đồng giao tiếp | Publisher có phát đúng event và consumer có dùng đúng event công khai không? | Test publisher và listener độc lập |
| Giao dịch và độ tin cậy | Rollback, xử lý trùng và retry có làm sai dữ liệu không? | Integration test có commit thật, mô phỏng lỗi và phục hồi |

Một số tình huống nên kiểm thử:

- **Vi phạm API:** cố import `catalog.internal.ProductEntity` vào `orders`. Kiểm tra cấu trúc cần phát hiện nếu dependency đó nằm trong phạm vi module được phân tích.
- **Vòng phụ thuộc:** thêm lời gọi từ `catalog` đến API `orders` trong khi `orders → catalog` đã tồn tại. Kiểm tra cấu trúc cần phát hiện chu trình.
- **Publisher rollback:** tạo đơn rồi gây exception trong transaction. Listener `AFTER_COMMIT` không được xử lý như thể đơn đã hoàn tất.
- **Listener lỗi:** đơn đã commit vẫn tồn tại; failure publication được lưu/theo dõi đúng theo registry đã cấu hình.
- **Listener nhận lặp:** gửi lại cùng `OrderPlaced`, bảo đảm bảng/thao tác thông báo không tạo tác động ngoài ý muốn hai lần.
- **Tách consumer:** bỏ module `analytics` hoặc thêm một listener `reporting` mà không phải sửa mã nghiệp vụ `orders`.

Với `@ApplicationModuleListener` bất đồng bộ, test phải thực sự kích hoạt commit và **chờ kết quả với timeout**; không kiểm tra ngay sau `publishEvent(...)`. Nếu test method đang bị bao bởi một transaction tự rollback, listener `AFTER_COMMIT` có thể không chạy.

`verify()` không phân tích mọi đường phụ thuộc thực tế, chẳng hạn truy cập SQL trực tiếp qua `JdbcTemplate` vào bảng của module khác, reflection hoặc sự phụ thuộc thông qua endpoint bên ngoài. Cần kết hợp code review và quy tắc sở hữu dữ liệu cho các trường hợp đó.

## 10. Cách chuyển một monolith có phụ thuộc hai chiều sang một chiều

Khi cải tổ một hệ thống đã tồn tại, nên ưu tiên các bước có thể kiểm chứng:

1. **Vẽ đồ thị hiện tại.** Liệt kê mỗi module và tất cả import, injection, lời gọi API, quyền đọc/ghi dữ liệu xuyên ranh giới. Đánh dấu các vòng phụ thuộc trực tiếp và gián tiếp.
2. **Xác định nguồn sự thật và owner.** Module nào chịu trách nhiệm cho trạng thái đơn, giao dịch, tồn kho hoặc thông báo? Chỉ owner được quyết định cách ghi dữ liệu đó.
3. **Định nghĩa public API nhỏ.** Tách interface/DTO/value object cần thiết khỏi repository/entity nội bộ. Đừng mặc định mọi lớp `public` phải thuộc hợp đồng giữa module.
4. **Phân loại tương tác.** Yêu cầu cần phản hồi tức thời dùng API; tác vụ phản ứng với kết quả đã commit có thể dùng event.
5. **Thay các chiều phụ thuộc không cần thiết.** Di chuyển trách nhiệm điều phối đến owner phù hợp, hoặc chuyển lời gọi phụ sang listener tiêu thụ event của module nguồn.
6. **Thiết lập kiểm tra cấu trúc.** Thêm `allowedDependencies` và `ApplicationModules.verify()`; bổ sung test cho event, rollback và idempotency.
7. **Quan sát sau thay đổi.** Kiểm tra độ trễ listener, publication pending, kết quả retry và dữ liệu projection khi chuyển từ đồng bộ sang sau commit.

Một thay đổi tưởng đơn giản như thay `notifications.send(...)` bằng `publishEvent(...)` có thể đổi **ngữ nghĩa transaction**. Cần xác định trước hệ thống có chấp nhận đơn thành công dù email gửi thất bại hay không; nếu có, phải thể hiện chính sách khôi phục thông báo.

## 11. Bài thực hành: phát hiện và xóa một vòng phụ thuộc

Cho hệ thống có ba module:

~~~text
orders         -> payments        // Đặt đơn gọi PaymentService
payments       -> notifications   // Thanh toán gọi NotificationService
notifications  -> orders          // Email tra OrderRepository
~~~

Hãy thực hiện:

1. Vẽ đồ thị phụ thuộc tĩnh và chỉ ra chu trình. Xác định những API/repository nào đang vượt ranh giới.
2. Xác định việc gửi email có phải điều kiện bắt buộc để thanh toán thành công không. Nếu không, thay lời gọi từ `payments` đến `notifications` bằng event `PaymentConfirmed` thuộc API `payments`.
3. Để `notifications` chỉ import `PaymentConfirmed` và, nếu cần, gọi API chỉ đọc công khai của `orders`. Tuyệt đối không import `OrderRepository` nội bộ.
4. Kiểm tra lại đồ thị: `orders → payments`, `notifications → payments` và `notifications → orders`. Không còn cạnh `payments → notifications`, nên vòng phụ thuộc trong ví dụ ban đầu được loại bỏ.
5. Đặt `allowedDependencies` phù hợp và chạy `ApplicationModules.of(...).verify()` trong test.
6. Viết test thanh toán thành công, transaction rollback, listener lỗi và cùng event được giao lại; xác định khóa chống gửi email trùng.

**Câu hỏi suy luận:** nếu `notifications` vẫn yêu cầu `payments` phải gọi nó và đợi kết quả, event giúp xóa vòng phụ thuộc mã nguồn đến đâu? Nếu event phát sau commit nhưng registry chưa lưu bền, lỗi JVM có thể gây điều gì? Nếu `notifications` import `orders.OrderPlaced`, hướng phụ thuộc mã nguồn là hướng nào và tại sao?

## 12. Nguyên tắc áp dụng

**Phụ thuộc một chiều** là quy tắc về **API và mã nguồn**: module sử dụng biết hợp đồng công khai của module được sử dụng, nhưng module được sử dụng không cần biết implementation của module gọi. Một hệ thống có nhiều quan hệ phụ thuộc vẫn tốt nếu các quan hệ đó không tạo chu trình và giữ được quyền sở hữu nghiệp vụ.

Với Spring Modulith, hãy công khai interface/DTO/event cần thiết, giấu repository/entity nội bộ, giới hạn `allowedDependencies` khi phù hợp và chạy `ApplicationModules.verify()` trong CI. **Application events** giúp module phát không phụ thuộc trực tiếp vào module tiêu thụ, song module tiêu thụ vẫn phụ thuộc vào hợp đồng event. Khi listener chạy sau commit, cần thêm publication registry, khả năng phục hồi, idempotency và kiểm thử để bảo đảm ranh giới tốt cả khi hệ thống gặp lỗi.

**Tài liệu tham khảo chính thức:**

- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
