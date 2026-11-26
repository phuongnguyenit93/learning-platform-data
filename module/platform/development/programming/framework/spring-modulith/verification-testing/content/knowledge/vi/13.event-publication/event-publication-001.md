# ApplicationEvent được phát từ module nào?

## 1. Trả lời trực tiếp

Trong ứng dụng Spring Modulith, **module phát sự kiện là module chứa mã nghiệp vụ thực sự gọi phương thức `ApplicationEventPublisher.publishEvent(...)`**. Để xác định module đó, cần tìm điểm gọi `publishEvent` rồi đối chiếu package của lớp gọi với ranh giới module được Spring Modulith phát hiện.

Điểm dễ nhầm là có **ba vai trò độc lập**:

| Vai trò | Cách xác định | Ví dụ |
| --- | --- | --- |
| **Module phát (publisher)** | Module chứa thành phần gọi `publishEvent(...)` | `order` gọi phát `OrderCompleted` |
| **Module sở hữu kiểu sự kiện** | Module chứa lớp/record định nghĩa payload sự kiện | `order` công bố `order.events.OrderCompleted` |
| **Module nhận (subscriber/listener)** | Module chứa phương thức `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` | `inventory` xử lý `OrderCompleted` |

Ba vai trò có thể nằm ở các module khác nhau. **Tên lớp sự kiện và thuộc tính `ApplicationEvent.getSource()` không phải bằng chứng đáng tin cậy về module đã phát sự kiện**. `getSource()` chỉ phản ánh đối tượng được truyền khi tạo một `ApplicationEvent`; nó không phải metadata do Spring Modulith tự động gắn vào để chỉ ra module nguồn.

Trong phạm vi học phần **SPRING_MODULITH_VERIFICATION_TESTING**, câu hỏi này là bước đầu để kiểm chứng ranh giới kiến trúc, quy tắc phụ thuộc giữa module và luồng sự kiện, sau đó đưa kiểm thử vào quality gate của CI.

### Mục tiêu thực hành

Sau bài này, bạn có thể:

1. Chỉ ra module phát một application event bằng cách đọc code và cấu trúc package.
2. Phân biệt việc **phát sự kiện**, **định nghĩa kiểu sự kiện** và **lắng nghe sự kiện**.
3. Thiết kế event API để các module trao đổi mà không phụ thuộc trực tiếp vào dịch vụ nội bộ của nhau.
4. Dùng `ApplicationModules.verify()` và `@ApplicationModuleTest` để kiểm tra cả ranh giới kiến trúc lẫn hành vi phát sự kiện.
5. Nhận diện điểm cần chú ý khi kiểm thử sự kiện có transaction, database và listener bất đồng bộ.

## 2. Spring ApplicationEventPublisher có thuộc một module không?

`ApplicationEventPublisher` là cơ chế của **Spring Framework**, được Spring cung cấp qua application context. Một service thuộc module bất kỳ có thể inject publisher và gọi `publishEvent(Object)`. Vì thế:

- Không có một “module trung tâm” mặc định sở hữu mọi application event chỉ vì Spring quản lý publisher.
- Đối tượng được phát **không bắt buộc kế thừa `ApplicationEvent`**. Một Java record hay POJO thông thường cũng có thể là event.
- Spring phân phối event tới các listener phù hợp trong application context. Ranh giới module là quy tắc kiến trúc được Spring Modulith mô hình hóa và kiểm chứng; nó không biến mỗi module thành một event bus tách biệt.
- Khi code gọi `publishEvent` qua một abstraction do nhóm dự án tự viết, cần lần theo caller nghiệp vụ. Lớp adapter chung chỉ là nơi chuyển tiếp kỹ thuật, không đủ để kết luận ai khởi phát nghiệp vụ.

Xét ví dụ sau:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderService.java
│   └── events
│       ├── package-info.java
│       └── OrderCompleted.java
└── inventory
    ├── package-info.java
    └── InventoryEventHandler.java
~~~

Giả sử `ShopApplication` là lớp ứng dụng nằm trong `com.example.shop`. Với cách tổ chức module mặc định theo các package con trực tiếp, Spring Modulith nhận diện `order` và `inventory` là hai application module. Trong cấu hình tùy biến, phải kiểm tra lại cách module được khai báo thay vì suy luận chỉ từ tên thư mục.

### 2.1. Module order định nghĩa sự kiện

File `order/events/OrderCompleted.java`:

~~~java
package com.example.shop.order.events;

public record OrderCompleted(String orderId) {}
~~~

`OrderCompleted` là sự kiện mô tả **đơn hàng đã hoàn tất**. Tên sự kiện nên biểu đạt sự thật nghiệp vụ đã xảy ra, không ra lệnh cho module nhận gọi một thao tác cụ thể.

Nếu kiểu sự kiện nằm trong package con `order.events` và module khác cần import nó, hãy công bố package này thành một **named interface**. File `order/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.order.events;
~~~

Động tác trên biến package chứa event thành một phần API được công bố có chủ đích của module `order`. Điều này quan trọng vì Spring Modulith mặc định xem các package con bên trong module là chi tiết triển khai, không tự động công bố toàn bộ chúng.

### 2.2. Module order phát sự kiện

File `order/OrderService.java`:

~~~java
package com.example.shop.order;

import com.example.shop.order.events.OrderCompleted;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void completeOrder(String orderId) {
        // Trong ứng dụng thực: kiểm tra trạng thái và lưu thay đổi đơn hàng.
        events.publishEvent(new OrderCompleted(orderId));
    }
}
~~~

**Đáp án cho ví dụ:** `order` là module phát sự kiện, bởi vì `OrderService` thuộc package `com.example.shop.order` và chính phương thức `completeOrder` gọi `events.publishEvent(...)`. `ApplicationEventPublisher` là hạ tầng chung của Spring; nó không làm thay đổi nguồn phát ở mức nghiệp vụ.

### 2.3. Module inventory lắng nghe sự kiện

File `inventory/InventoryEventHandler.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.order.events.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryEventHandler {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Trong ứng dụng thực: cập nhật dữ liệu tồn kho tương ứng.
        System.out.println("Order completed: " + event.orderId());
    }
}
~~~

`inventory` là **module nhận**. Nó import kiểu sự kiện `OrderCompleted`, nhưng không gọi trực tiếp `OrderService.completeOrder(...)` và không cần truy cập repository nội bộ của module `order`.

Nếu muốn mô tả chặt chẽ phụ thuộc được phép của module nhận, có thể đặt trong `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.example.shop.inventory;
~~~

Ý nghĩa: module `inventory` được phép phụ thuộc vào named interface `events` của `order`. Nếu lập trình viên vô tình import lớp triển khai nội bộ khác của `order`, bước kiểm chứng kiến trúc cần phát hiện vi phạm. Cú pháp này giả định tên module do Spring Modulith nhận diện là `order`; với tên module tùy biến, hãy sử dụng đúng tên đã khai báo.

### 2.4. Luồng chạy

~~~mermaid
sequenceDiagram
    participant Client as API / caller
    participant Order as order.OrderService
    participant Publisher as ApplicationEventPublisher
    participant Inventory as inventory.InventoryEventHandler

    Client->>Order: completeOrder("O-42")
    Order->>Order: Cập nhật trạng thái đơn hàng
    Order->>Publisher: publishEvent(OrderCompleted("O-42"))
    Note over Publisher,Inventory: @ApplicationModuleListener xử lý sau commit của transaction
    Publisher-->>Inventory: OrderCompleted("O-42")
    Inventory->>Inventory: Xử lý dữ liệu tồn kho
~~~

Đọc sơ đồ từ trái sang phải: lời gọi xuất phát từ API, **hành vi phát** ở `order`, việc phân phối do Spring thực hiện, và phần xử lý downstream thuộc `inventory`. Đối với `@ApplicationModuleListener`, việc xử lý có ngữ nghĩa listener theo transaction và bất đồng bộ; sơ đồ diễn tả quan hệ nhân quả chứ không cam kết thời điểm hoàn thành chính xác.

## 3. Quy trình xác định module phát trong dự án thật

Khi nhận câu hỏi “ApplicationEvent này được phát từ module nào?”, nên làm lần lượt:

**Bước 1 — Tìm điểm phát.** Tìm các lời gọi `publishEvent(...)` hoặc phương thức wrapper cuối cùng gọi đến publisher. Nếu cùng một kiểu event được phát ở nhiều điểm, nó có thể có **nhiều module phát**; phải đối chiếu từng call site. Không kết luận chỉ bằng cách tìm nơi khai báo class event.

**Bước 2 — Xác định lớp nghiệp vụ khởi phát.** Lấy package của service, aggregate hoặc thành phần đang thực thi lời gọi. Nếu lời gọi đi qua một event dispatcher dùng chung, xem service nào đã yêu cầu dispatcher phát sự kiện và ghi rõ sự khác biệt giữa nguồn nghiệp vụ với lớp hạ tầng thực hiện lệnh.

**Bước 3 — Đối chiếu ranh giới application module.** Với cách phát hiện module mặc định, package `com.example.shop.order` và các package con thuộc module `order`. Nếu hệ thống dùng named interface, explicit module detection hoặc cấu hình package đặc biệt, hãy dựa vào mô hình `ApplicationModules` của ứng dụng để xác định chính xác.

**Bước 4 — Kiểm tra kiểu sự kiện và các listener.** Xác định module sở hữu event type, nó có được công bố qua API hay không, và những module nào import type để lắng nghe. Bước này làm rõ phụ thuộc giữa module nhưng **không thay thế** bằng chứng ở bước 1 về điểm phát.

**Bước 5 — Kiểm chứng hành vi.** Viết test kích hoạt đúng use case và khẳng định event đã được phát. Test kiến trúc xác nhận phụ thuộc hợp lệ; test hành vi xác nhận code thực sự tạo ra event.

Ví dụ, nếu lớp `com.example.shop.billing.InvoiceService` gọi `publishEvent(new OrderCompleted(...))` thì **module phát tại call site đó là `billing`**, dù `OrderCompleted` được định nghĩa trong `order.events`. Khi một listener ở `inventory` nhận event rồi phát tiếp `StockReserved`, lần phát `StockReserved` có nguồn nghiệp vụ ở `inventory`.

## 4. Kiểm chứng ranh giới bằng ApplicationModules

Spring Modulith cung cấp mô hình `ApplicationModules` để phát hiện module từ ứng dụng và xác minh những quy tắc phụ thuộc kiến trúc. Một bài kiểm tra độc lập có thể là:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Lệnh `verify()` kiểm tra các quy tắc kiến trúc mà Spring Modulith áp dụng, ví dụ phụ thuộc vòng giữa module, truy cập vào kiểu không được công bố và các ràng buộc phụ thuộc đã khai báo. Trong ví dụ, dependency từ `inventory` sang `order.events` hợp lệ khi named interface được công bố và thuộc phạm vi `allowedDependencies`.

**Giới hạn cần hiểu rõ:** `ApplicationModules.verify()` không chứng minh rằng một lệnh `completeOrder` đã chạy hay một event đã được phát ở runtime. Nó cũng không tự gắn module nguồn vào từng `ApplicationEvent`. Vì vậy, kiểm chứng ranh giới và kiểm thử sự kiện cần bổ sung cho nhau.

## 5. Kiểm thử module phát bằng @ApplicationModuleTest

Đặt test dưới package của module `order` để `@ApplicationModuleTest` xác định module đích theo vị trí test:

~~~java
package com.example.shop.order;

import com.example.shop.order.events.OrderCompleted;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderEventTests {

    @Autowired
    OrderService orders;

    @Test
    void emitsOrderCompleted(PublishedEvents events) {
        orders.completeOrder("O-42");

        assertThat(events.ofType(OrderCompleted.class)
                .matching(OrderCompleted::orderId, "O-42"))
                .hasSize(1);
    }
}
~~~

Trong ví dụ này, test kiểm tra hai điều:

1. Khi use case `OrderService.completeOrder("O-42")` chạy, có sự kiện `OrderCompleted` được công bố.
2. Payload sự kiện có `orderId` phù hợp, giúp tránh test chỉ đếm một sự kiện không liên quan.

`PublishedEvents` là tiện ích kiểm thử của Spring Modulith để quan sát event đã phát trong lúc thực thi test. **Test không suy ra module nguồn chỉ từ `PublishedEvents`**: chính việc gọi use case thuộc `order`, cùng bằng chứng call site `publishEvent`, mới cho phép kết luận module nguồn. Trong hệ thống thực, nên chuẩn bị dữ liệu đơn hàng và kiểm tra trạng thái lưu trữ sau khi gọi use case, thay vì để ví dụ giả lập bước ghi database.

Nếu cần kiểm chứng chuỗi xử lý bởi listener bất đồng bộ, hãy dùng API `Scenario` của Spring Modulith hoặc cơ chế chờ theo điều kiện. Tránh `Thread.sleep(...)` với thời lượng cố định vì kết quả phụ thuộc tốc độ máy chạy CI.

### Kiểm thử transaction và dữ liệu

Ví dụ sử dụng `@Transactional` ở `completeOrder`. Cần phân biệt các cách lắng nghe:

| Kiểu listener | Hệ quả đối với test |
| --- | --- |
| `@EventListener` thông thường | Mặc định xử lý đồng bộ trong luồng phát sự kiện; nếu được gọi trong transaction thì thường tham gia ngữ cảnh transaction hiện tại. |
| `@TransactionalEventListener` với pha mặc định `AFTER_COMMIT` | Chạy sau khi transaction commit thành công; nếu không có transaction thì mặc định listener không chạy, trừ khi cấu hình fallback. |
| `@ApplicationModuleListener` | Tiện ích Spring Modulith cho listener theo transaction, xử lý bất đồng bộ; cần kiểm thử cả việc commit và xử lý hoàn tất. |

Vì vậy, một test có `@Transactional` nhưng cuối test rollback có thể **không kích hoạt** listener `AFTER_COMMIT`. Để kiểm tra hiệu ứng downstream, cần bảo đảm transaction thực sự commit, có dữ liệu test phù hợp, và chờ kết quả xử lý bất đồng bộ. Khi kiểm tra dữ liệu của module nhận, dùng integration test phù hợp với database và cấu hình transaction thực tế.

Nếu ứng dụng bật **Event Publication Registry** của Spring Modulith cùng hạ tầng lưu trữ tương ứng, còn có thể kiểm tra việc ghi nhận và hoàn tất các lần phát tới transactional listener. Registry giúp theo dõi quá trình giao sự kiện cho listener, nhưng **không thay thế** phép xác định module đã gọi `publishEvent`; cơ chế lưu trữ, retry và hoàn tất tùy thuộc cấu hình ứng dụng.

## 6. Đưa kiểm chứng vào quality gate CI

Đối với module học chuyên về verification/testing, một quality gate hữu ích cần bao phủ **kiến trúc** và **hành vi**:

| Kiểm tra trong CI | Mục đích | Tín hiệu thất bại |
| --- | --- | --- |
| `ApplicationModules.of(...).verify()` | Ngăn phụ thuộc vòng và truy cập API nội bộ trái quy tắc | `inventory` import trực tiếp một implementation class của `order` |
| `@ApplicationModuleTest` + `PublishedEvents` | Xác minh use case của module nguồn phát đúng event và payload | `completeOrder` bị sửa và quên gọi `publishEvent` |
| Integration test với listener và database | Kiểm tra hiệu ứng sau commit trên dữ liệu thực | Event được phát nhưng transaction rollback hoặc listener không cập nhật dữ liệu |

Cho các test này chạy qua tác vụ test chuẩn của dự án trong CI (chẳng hạn `test` đối với Gradle hoặc Maven). Nếu một test thất bại, pipeline phải báo lỗi; như vậy thay đổi về phụ thuộc module hoặc luồng event sẽ bị phát hiện trước khi tích hợp.

### Những ngộ nhận thường gặp

- **“Event nằm trong package order, chắc chắn order phát.”** Chưa đủ. Một lớp trong module khác vẫn có thể phát cùng một kiểu event; cần kiểm tra call site.
- **“Bean ApplicationEventPublisher do Spring tạo nên sự kiện thuộc Spring hoặc infrastructure.”** Publisher là cơ chế phân phối; ý nghĩa nguồn phát phụ thuộc use case gọi nó.
- **“Subscriber import sự kiện thì đã vi phạm ranh giới module.”** Phụ thuộc vào kiểu event công khai có thể là hợp lệ; cần thiết kế API và kiểm chứng bằng `ApplicationModules`.
- **“Test kiến trúc pass là event đã được phát.”** Sai: `verify()` chỉ kiểm tra mô hình phụ thuộc. Test hành vi mới xác nhận event được xuất bản.
- **“Gọi publishEvent là listener sau commit chắc chắn chạy ngay.”** Không đúng. Thời điểm xử lý phụ thuộc loại listener, transaction, cơ chế async và cấu hình.
- **“ApplicationEvent tự mang tên module phát.”** Không có metadata module nguồn như vậy theo mặc định. Nếu cần audit runtime, ứng dụng phải thiết kế metadata nguồn rõ ràng, nhưng metadata đó vẫn cần được đối chiếu với call site khi kiểm chứng kiến trúc.

## 7. Bài tập tự kiểm tra

Cho ba module `catalog`, `checkout`, `notification`:

~~~java
// com.example.shop.catalog.events.PriceChanged
public record PriceChanged(String sku, long newPrice) {}

// com.example.shop.checkout.CheckoutService
events.publishEvent(new PriceChanged("SKU-1", 120_000L));

// com.example.shop.notification.PriceChangeListener
@EventListener
void on(PriceChanged event) { /* gửi thông báo */ }
~~~

Hãy trả lời: module nào **phát** event ở đoạn code trên; module nào **sở hữu kiểu event**; module nào **nhận** event; và vì sao một test chỉ có `ApplicationModules.verify()` không chứng minh thông báo đã được gửi?

**Đáp án:** `checkout` phát vì `CheckoutService` chứa call site; `catalog` sở hữu `PriceChanged`; `notification` nhận qua `@EventListener`. Test `verify()` chỉ xác nhận quan hệ phụ thuộc hợp lệ, còn việc gửi thông báo là hành vi runtime cần integration test riêng. Ngoài ra, nên kiểm tra xem `PriceChanged` đã nằm trong API được công bố của `catalog` hay chưa, và việc `checkout` tự phát sự kiện mang ý nghĩa thay đổi giá do `catalog` sở hữu có phù hợp nghiệp vụ không.

## 8. Checklist khi điều tra một event

- [ ] Xác định **mọi** nơi gọi `publishEvent` cho kiểu event đang xét.
- [ ] Xác định package/module của service hoặc use case khởi phát từng lời gọi.
- [ ] Phân biệt module nguồn, module sở hữu event type và các module listener.
- [ ] Kiểm tra named interface/API công khai và quy tắc `allowedDependencies`.
- [ ] Có test `ApplicationModules.verify()` để ngăn vi phạm ranh giới.
- [ ] Có test `@ApplicationModuleTest` khẳng định sự kiện được phát với payload đúng.
- [ ] Nếu listener dựa vào transaction/async/database, kiểm chứng sau commit bằng integration test phù hợp.

**Ghi nhớ:** “ApplicationEvent được phát từ module nào?” là câu hỏi về **nơi hành vi phát xảy ra**. Hãy bắt đầu từ call site `publishEvent`, ánh xạ nó vào application module, rồi dùng kiểm thử kiến trúc và kiểm thử sự kiện để chứng minh kết luận.
