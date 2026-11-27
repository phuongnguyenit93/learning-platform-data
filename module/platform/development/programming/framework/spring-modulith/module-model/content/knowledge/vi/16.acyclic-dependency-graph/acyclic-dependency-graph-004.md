# Chu kỳ do event listener tạo ra

Event là cách quan trọng để các application module giao tiếp mà không cần gọi trực tiếp Spring bean của nhau. Tuy nhiên, **event listener vẫn tạo ra một quan hệ phụ thuộc ở cấp module**: module khai báo listener phụ thuộc vào module sở hữu type event. Vì vậy, dùng event không tự động bảo đảm đồ thị module không có chu kỳ.

Một listener theo một chiều thường tạo ra một cạnh phụ thuộc. Chu kỳ xuất hiện khi có thêm một quan hệ ngược chiều, chẳng hạn hai module lắng nghe event của nhau hoặc một module vừa lắng nghe event của module khác vừa gọi trực tiếp component của module đó theo chiều ngược lại.

## 1. Event listener tạo dependency theo hướng nào?

Giả sử module `orders` công bố event `OrderCompleted`, còn module `inventory` lắng nghe event đó để cập nhật tồn kho:

```text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderCompleted.java
│   └── OrderManagement.java
└── inventory
    └── InventoryEventHandler.java
```

Event được sở hữu bởi module phát hành:

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
```

Module `orders` phát hành event bằng `ApplicationEventPublisher`:

```java
package com.example.shop.orders;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderManagement {

    private final ApplicationEventPublisher events;

    public OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void complete(UUID orderId) {
        // Hoàn tất trạng thái đơn hàng trước khi công bố sự kiện.
        events.publishEvent(new OrderCompleted(orderId));
    }
}
```

Module `inventory` lắng nghe event:

```java
package com.example.shop.inventory;

import com.example.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryEventHandler {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho dựa trên đơn hàng đã hoàn tất.
    }
}
```

Trong mô hình Spring Modulith, quan hệ được biểu diễn theo hướng **module lắng nghe → module phát hành event**:

```text
inventory ──[EVENT_LISTENER]──> orders
```

Lý do là `inventory` cần biết type `OrderCompleted` để khai báo listener. Ngược lại, `orders` chỉ gọi `ApplicationEventPublisher` của Spring và không cần biết module nào sẽ nhận event. Publisher không cần inject bean của listener.

Spring Modulith phân loại quan hệ này bằng `DependencyType.EVENT_LISTENER`. Javadoc mô tả đây là dependency do module khai báo listener cho event được module khác công bố; module đích không cần được bootstrap chỉ để chạy module nguồn. Điều đó làm dependency này khác với `USES_COMPONENT`, nhưng nó vẫn là một quan hệ module cần được đưa vào phân tích kiến trúc.

## 2. Một event listener không tự tạo thành chu kỳ

Trong ví dụ trên chỉ có một cạnh `inventory → orders`. Không có cạnh ngược `orders → inventory`, vì `orders` không gọi component của `inventory` và không import type thuộc module đó.

Đây là một đồ thị không chu kỳ:

```text
inventory ──[EVENT_LISTENER]──> orders
```

Nhiều module có thể cùng lắng nghe event của `orders`:

```text
inventory ──[EVENT_LISTENER]──> orders
shipping  ──[EVENT_LISTENER]──> orders
loyalty   ──[EVENT_LISTENER]──> orders
```

Đây vẫn là các cạnh cùng hướng về module công bố event. `orders` không cần biết có bao nhiêu listener và không cần thay đổi khi thêm một module tiêu thụ event mới. Cách tích hợp này giảm sự phụ thuộc trực tiếp từ module phát hành tới các module nhận.

## 3. Chu kỳ xuất hiện khi có quan hệ ngược chiều

Giả sử `orders` vẫn inject `InventoryManagement` để gọi trực tiếp một thao tác, trong khi `inventory` lắng nghe `OrderCompleted`:

```java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

import com.example.shop.orders.Order;

@Service
class OrderManagement {

    private final InventoryManagement inventory;

    OrderManagement(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    void complete(Order order) {
        // Hoàn tất đơn hàng...
        inventory.updateStockFor(order);
    }
}
```

Giả sử `InventoryEventHandler` vẫn lắng nghe event do `orders` công bố. Khi đó, mô hình có hai cạnh:

```text
orders    ──[USES_COMPONENT]──> inventory
inventory ──[EVENT_LISTENER]─> orders
```

Hai cạnh tạo thành chu kỳ `orders ↔ inventory`. Việc một cạnh là event listener không làm biến mất cạnh phụ thuộc trong mô hình. `ApplicationModules.verify()` kiểm tra đồ thị phụ thuộc cấp application module và có thể báo vi phạm chu kỳ.

Để phá chu kỳ, hãy xác định chức năng nào cần được gọi đồng bộ và chức năng nào có thể được kích hoạt bằng event. Nếu việc cập nhật tồn kho là phản ứng sau khi đơn hàng hoàn tất, `orders` có thể chỉ phát hành `OrderCompleted`; bỏ lời gọi trực tiếp tới `InventoryManagement`. Khi đó chỉ còn cạnh `inventory → orders`.

## 4. Hai module cùng lắng nghe event của nhau

Chu kỳ cũng có thể hình thành dù không có lời gọi Spring bean trực tiếp. Ví dụ:

- `inventory` lắng nghe `OrderCompleted` do `orders` công bố.
- `orders` lắng nghe `StockReserved` do `inventory` công bố.

Hai event được đặt trong package API của module sở hữu:

```java
package com.example.shop.inventory;

import java.util.UUID;

public record StockReserved(UUID orderId) {
}
```

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {
}
```

Các listener tạo ra hai cạnh:

```text
inventory ──[EVENT_LISTENER: OrderCompleted]──> orders
orders    ──[EVENT_LISTENER: StockReserved]────> inventory
```

Đây là chu kỳ ở cấp module dù cả hai bên chỉ dùng event. Vì vậy, event-driven không đồng nghĩa với dependency-free. Mỗi module tiêu thụ event vẫn phụ thuộc vào hợp đồng event của module phát hành.

Nếu nghiệp vụ thật sự cần trao đổi hai chiều, hãy xem lại quyền sở hữu use case và luồng trạng thái. Có thể một module nên điều phối quy trình, hoặc cần một module điều phối riêng để nhận các sự kiện và quyết định bước tiếp theo. Không nên để hai module liên tục phản ứng lẫn nhau mà không có một hướng điều phối rõ ràng.

## 5. Phân biệt chu kỳ kiến trúc với vòng lặp event lúc runtime

Hai khái niệm có liên quan nhưng không giống nhau:

| Hiện tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| Chu kỳ dependency graph | Có đường phụ thuộc đi từ module A qua module B rồi quay lại A | `orders → inventory → orders` |
| Vòng lặp event runtime | Các listener phát hành event mới khiến chuỗi listener kích hoạt lặp lại | `OrderCompleted` → `StockReserved` → `OrderCompleted` → ... |

Một chu kỳ trong graph không nhất thiết gây vòng lặp vô hạn. Hai module có thể lắng nghe event của nhau nhưng mỗi listener chỉ thực hiện một lần và không phát hành event kích hoạt lại chuỗi.

Ngược lại, vòng lặp event thường là dấu hiệu của một quan hệ phụ thuộc hai chiều, nhưng nguyên nhân trực tiếp là logic handler phát hành event mới không có điều kiện dừng hoặc kiểm soát trạng thái. Chỉ chuyển listener sang xử lý bất đồng bộ không tự giải quyết vòng lặp nghiệp vụ.

Khi thiết kế event, hãy dùng tên thể hiện sự kiện nghiệp vụ đã xảy ra, ví dụ `OrderCompleted`, `StockReserved`, thay vì dùng event như một lời gọi command vòng quanh giữa hai module. Listener nên kiểm tra trạng thái hiện tại, xử lý idempotent và tránh phát hành lại chính sự kiện hoặc sự kiện tương đương nếu không có chuyển trạng thái mới.

## 6. Cách đọc dependency event listener trong model

Ta có thể lọc riêng dependency do event listener tạo ra bằng `getDirectDependencies(...)`:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

class EventDependencyReport {

    void printEventListenerDependencies() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        for (ApplicationModule module : modules) {
            module.getDirectDependencies(modules, DependencyType.EVENT_LISTENER)
                    .stream()
                    .forEach(dependency -> System.out.printf(
                            "%s listens to event from %s: %s%n",
                            module.getIdentifier(),
                            dependency.getTargetModule().getIdentifier(),
                            dependency.getTargetType().getName()));
        }
    }
}
```

Trong kết quả:

- `module.getIdentifier()` là định danh của module khai báo listener, tức phía tạo dependency.
- `dependency.getTargetModule()` là module sở hữu type event.
- `dependency.getTargetType()` là type được tham chiếu, thường là event type.
- `DependencyType.EVENT_LISTENER` lọc riêng các dependency được phát hiện từ listener.

Khi thấy hai module xuất hiện ở cả hai chiều, hãy kiểm tra từng event type và listener method để xác định hợp đồng nào đang tạo cạnh ngược.

## 7. Kiểm tra chu kỳ bằng ApplicationModules.verify()

Spring Modulith cung cấp kiểm tra kiến trúc ở cấp application module. Bài test thường được viết như sau:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Verification bao gồm quy tắc đồ thị module phải không có chu kỳ, truy cập module khác qua API package và các dependency phải nằm trong allow-list nếu module đã khai báo `allowedDependencies`.

Nếu `inventory` lắng nghe event của `orders`, module `inventory` cần được phép phụ thuộc vào module `orders` khi `allowedDependencies` được cấu hình. Event listener không bỏ qua quy tắc cho phép dependency chỉ vì không cần bootstrap module phát hành event.

Ví dụ khai báo ở `inventory/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.example.shop.inventory;
```

Nếu module `orders` cũng phụ thuộc ngược vào `inventory`, allow-list không thể làm chu kỳ biến mất. Allow-list trả lời câu hỏi dependency có được phép hay không; kiểm tra DAG trả lời câu hỏi các quan hệ có tạo thành chu kỳ hay không.

## 8. Cách phá chu kỳ do event listener tạo ra

Khi `verify()` báo chu kỳ có chứa `EVENT_LISTENER`, hãy xử lý theo trình tự:

1. Liệt kê các cạnh trực tiếp của từng module và đánh dấu cạnh `EVENT_LISTENER`, `USES_COMPONENT`, `ENTITY` hoặc `DEFAULT`.
2. Với mỗi cạnh listener, xác định module phát hành event và module tiêu thụ event.
3. Tìm đường đi ngược từ module phát hành về module tiêu thụ. Đường ngược có thể đến từ listener thứ hai, lời gọi component, tham chiếu entity hoặc type API.
4. Xác định module nào nên sở hữu use case và trạng thái nghiệp vụ. Tránh để hai module cùng điều phối một quy trình theo hai chiều.
5. Thay lời gọi trực tiếp không cần thiết bằng event một chiều, hoặc chuyển phần điều phối sang module có trách nhiệm phù hợp.
6. Cập nhật `allowedDependencies` theo hợp đồng còn lại và chạy lại `ApplicationModules.verify()`.
7. Kiểm tra riêng khả năng phát sinh vòng lặp event lúc runtime bằng test cho chuỗi publish/listen và điều kiện dừng.

Một bảng phân tích nhỏ giúp nhìn rõ đường đi tạo chu kỳ:

| Module nguồn | Module đích | Loại dependency | Câu hỏi cần trả lời |
|---|---|---|---|
| `inventory` | `orders` | `EVENT_LISTENER` | Inventory có thực sự cần tiêu thụ event này không? |
| `orders` | `inventory` | `USES_COMPONENT` | Có thể thay lời gọi trực tiếp bằng một event nghiệp vụ không? |
| `orders` | `inventory` | `EVENT_LISTENER` | Orders có đang phản ứng ngược với event của inventory không? |

Không phải mọi dependency hai chiều đều cần được loại bỏ bằng cách chuyển tất cả sang event. Đôi khi ranh giới module đang đặt sai hoặc một use case cần được chuyển về đúng module sở hữu. Hãy sửa hướng phụ thuộc theo trách nhiệm nghiệp vụ thay vì chỉ làm cho kiểm thử qua.

## 9. Thiết kế event một chiều có chủ đích

Một luồng thường dễ duy trì là module sở hữu sự kiện phát hành fact sau khi hoàn tất chuyển trạng thái; các module quan tâm tự đăng ký listener:

```text
                  OrderCompleted
orders ───────────────────────────────────┐
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
               inventory              shipping               loyalty
               (listener)              (listener)             (listener)
```

Module `orders` không cần biết danh sách listener. Mỗi module nhận event xử lý phần việc thuộc trách nhiệm của mình. Nếu một listener cần yêu cầu module khác thực hiện một hành động, hãy cân nhắc một command API có chủ sở hữu rõ ràng hoặc một quy trình điều phối riêng thay vì tạo chuỗi event phản hồi qua lại.

Event publication mặc định của Spring diễn ra đồng bộ; listener bất đồng bộ hoặc transactional có thể thay đổi thời điểm và ranh giới transaction. Các lựa chọn đó ảnh hưởng đến consistency, lỗi và khả năng retry, nhưng không thay đổi hướng dependency kiến trúc mà Spring Modulith suy ra từ event type và listener.

Với listener cần xử lý bền vững, Spring Modulith cung cấp Event Publication Registry cho transactional event listeners để ghi nhận publication và hỗ trợ xử lý các publication chưa hoàn tất. Cơ chế này hỗ trợ độ tin cậy khi xử lý event; nó không thay thế việc thiết kế đồ thị module không chu kỳ.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dùng event thì module không còn dependency | Module listener vẫn phụ thuộc vào module sở hữu event type |
| `EVENT_LISTENER` giống `USES_COMPONENT` | Listener dependency không yêu cầu target module được bootstrap để chạy source module; component dependency thì có |
| Một listener đơn lẻ luôn tạo chu kỳ | Một listener một chiều chỉ tạo một cạnh; cần đường phụ thuộc quay ngược mới có chu kỳ |
| Hai module nghe event của nhau luôn tạo vòng lặp vô hạn | Chúng tạo dependency cycle; runtime loop chỉ xảy ra nếu handler phát hành event kích hoạt chuỗi lặp lại |
| Chuyển listener sang async sẽ xóa dependency cycle | Async thay đổi cách thực thi, không xóa quan hệ module listener |
| Cho phép dependency trong `allowedDependencies` sẽ giải quyết chu kỳ | Allow-list không thay đổi cấu trúc đồ thị và không phá được chu kỳ |

Hãy dùng event để tách module phát hành khỏi danh sách module tiêu thụ, nhưng vẫn kiểm soát hướng phụ thuộc của các listener. Một event listener là một cạnh kiến trúc có chủ đích; khi các cạnh đó quay trở lại module ban đầu, cần xem lại quyền sở hữu use case, hướng event và trách nhiệm điều phối.

Tài liệu tham khảo: [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html), [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html), [DependencyType Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html), [ApplicationModule Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html).
