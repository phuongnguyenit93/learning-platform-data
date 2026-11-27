# Cycle xuất hiện sau khi thêm event listener

## Vì sao thêm listener có thể tạo dependency cycle?

Trong Spring Modulith, application event giúp module phát thông báo về một sự kiện nghiệp vụ mà không cần gọi trực tiếp từng consumer. Tuy vậy, listener vẫn tạo ra một quan hệ phụ thuộc trong mô hình module: module chứa listener phải biết kiểu event mà nó nhận.

Vì vậy, khi thêm listener, đồ thị phụ thuộc có thể thay đổi dù module phát event không thêm lời gọi trực tiếp nào đến module nhận event.

Một chu trình thường xuất hiện khi hai module đã có một phụ thuộc trực tiếp theo một chiều, sau đó listener tạo thêm phụ thuộc theo chiều ngược lại. Ví dụ:

- Module **orders** gọi API của **inventory** để kiểm tra hoặc giữ hàng trước khi xác nhận đơn.
- Module **inventory** đăng ký listener nhận event **OrderCompleted** do **orders** công bố.
- Listener tham chiếu kiểu event thuộc **orders**, nên mô hình ghi nhận **inventory** phụ thuộc vào **orders**.
- Lời gọi API trước đó tạo chiều phụ thuộc **orders** sang **inventory**.

Kết quả là hai module tạo thành một chu trình. Phương thức ApplicationModules.verify() có thể phát hiện chu trình này và làm kiểm chứng kiến trúc thất bại.

## Hiểu hướng phụ thuộc do event listener tạo ra

Giả sử event được khai báo trong module orders:

~~~java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {}
~~~

Module inventory có listener:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho cho đơn hàng đã hoàn tất.
    }
}
~~~

Mã trong inventory import OrderCompleted từ orders. Do đó, hướng phụ thuộc trong mô hình module là:

~~~mermaid
flowchart LR
    I["inventory<br/>event listener"] -->|"tham chiếu OrderCompleted"| O["orders<br/>event contract"]
~~~

Hướng này có thể gây nhầm lẫn nếu chỉ nhìn vào luồng chạy. Lúc runtime, orders phát event và inventory nhận event. Nhưng quan hệ phụ thuộc tĩnh được suy ra từ mã nguồn đi từ module có listener đến module sở hữu kiểu event.

Module phát event không cần import listener. Vì thế, việc phát event tự nó không tạo một dependency ngược từ orders đến inventory. Dependency ngược có thể đã tồn tại do orders gọi API, import type hoặc sử dụng bean của inventory.

## Ví dụ đầy đủ tạo thành chu trình

Giả sử orders cần kiểm tra lượng hàng còn lại trước khi nhận đơn. Nó inject API của inventory:

~~~java
package com.acme.shop.orders;

import com.acme.shop.inventory.api.StockAvailability;
import org.springframework.stereotype.Service;

@Service
class OrderAcceptance {

    private final StockAvailability stock;

    OrderAcceptance(StockAvailability stock) {
        this.stock = stock;
    }

    void accept(String productCode, int quantity) {
        if (!stock.isAvailable(productCode, quantity)) {
            throw new IllegalStateException("Insufficient stock");
        }

        // Xác nhận đơn hàng và phát OrderCompleted khi nghiệp vụ hoàn tất.
    }
}
~~~

API tồn kho được công bố từ inventory:

~~~java
package com.acme.shop.inventory.api;

public interface StockAvailability {
    boolean isAvailable(String productCode, int quantity);
}
~~~

Package API được đánh dấu named interface:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
~~~

Module orders khai báo phụ thuộc vào API này:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
~~~

Ở chiều ngược lại, listener trong inventory nhận OrderCompleted từ orders. Đồ thị phụ thuộc trở thành:

~~~mermaid
flowchart LR
    O["orders"] -->|"StockAvailability"| I["inventory"]
    I -->|"OrderCompleted listener"| O
~~~

Hai mũi tên tạo thành chu trình orders → inventory → orders. Việc mỗi chiều đều sử dụng một API công khai không làm chu trình biến mất. Named interface giới hạn package được phép truy cập; nó không thay đổi hướng dependency giữa hai module.

## Xác nhận nguyên nhân từ thông báo verification

Khi gặp lỗi sau khi thêm listener, hãy chạy kiểm chứng trên mô hình module:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đọc toàn bộ thông báo vi phạm và xác định:

1. Module nào là điểm bắt đầu của dependency?
2. Module nào là đích của dependency?
3. Quan hệ đó đến từ lời gọi bean/API, import kiểu dữ liệu hay event listener?
4. Listener đang tham chiếu event type thuộc package nào?
5. Có đường đi nào khác tạo thành chu trình giữa hai module hay không?

Có thể dùng detectViolations() để xem danh sách vi phạm khi đang điều tra:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);

modules.detectViolations()
    .forEach(System.out::println);
~~~

Đừng kết luận listener là nguyên nhân duy nhất chỉ vì lỗi xuất hiện ngay sau khi thêm listener. Listener có thể chỉ làm lộ một dependency ngược đã tồn tại trong codebase. Hãy kiểm tra cả hai chiều của đồ thị và những kiểu được tham chiếu gián tiếp trong event payload.

## Kiểm tra cả event payload và các kiểu lồng nhau

Một event có thể tạo dependency thông qua kiểu event chính và các kiểu xuất hiện trong payload. Ví dụ:

~~~java
public record OrderCompleted(
    Order order,
    List<OrderLine> lines
) {}
~~~

Nếu Order hoặc OrderLine thuộc package nội bộ của orders, listener bên ngoài có thể kéo theo các phụ thuộc vào phần triển khai nội bộ. Điều này làm hợp đồng event rộng hơn nhu cầu của consumer.

Nên định nghĩa payload bằng các kiểu công khai, ổn định:

~~~java
package com.acme.shop.orders.events;

import java.util.List;
import java.util.UUID;

public record OrderCompleted(
    UUID orderId,
    List<CompletedOrderLine> lines
) {
    public OrderCompleted {
        lines = List.copyOf(lines);
    }
}
~~~

~~~java
package com.acme.shop.orders.events;

public record CompletedOrderLine(
    String productCode,
    int quantity
) {}
~~~

Việc chuyển payload sang DTO công khai không tự xóa dependency từ listener đến module chứa event. Nó giúp dependency chỉ đi qua hợp đồng ổn định và tránh làm lộ entity hoặc package nội bộ. Muốn loại bỏ chu trình, cần xử lý cả hướng dependency ngược còn lại.

## Cách 1: Bỏ lời gọi ngược và dùng event choreography

Nếu orders không cần nhận kết quả tồn kho ngay trong cùng lời gọi nghiệp vụ, có thể chuyển tương tác sang quy trình event hai chiều.

Ví dụ:

1. orders phát OrderPlaced.
2. inventory lắng nghe OrderPlaced và xử lý giữ hàng.
3. inventory phát StockReserved hoặc StockRejected.
4. orders lắng nghe kết quả và cập nhật trạng thái đơn hàng.

Đồ thị dependency khi event contract được đặt ở module độc lập:

~~~mermaid
flowchart LR
    O["orders"] --> C["ordercontracts"]
    I["inventory"] --> C
~~~

Trong mô hình thực tế, có thể đặt các event contract trong module sở hữu chúng hoặc trong một module hợp đồng độc lập. Điểm quan trọng là không giữ một lời gọi trực tiếp ngược chiều chỉ để lấy kết quả đồng bộ nếu nghiệp vụ có thể xử lý theo trạng thái và sự kiện.

Cách này thay đổi semantics của nghiệp vụ. Đơn hàng có thể ở trạng thái PENDING_STOCK trong khi chờ kết quả. Cần thiết kế rõ:

- Trạng thái trung gian và chuyển trạng thái hợp lệ.
- Xử lý event trùng lặp theo hướng idempotent.
- Retry khi consumer tạm thời thất bại.
- Timeout hoặc quy trình xử lý khi không nhận được kết quả.
- Hoàn tác hoặc giải phóng reservation nếu đơn hàng bị hủy.
- Theo dõi publication và trạng thái xử lý khi cần độ tin cậy cao.

Event choreography phù hợp khi nghiệp vụ chấp nhận eventual consistency và các module có thể phối hợp qua các trạng thái rõ ràng.

## Cách 2: Đưa event contract vào module độc lập

Nếu orders cần tiếp tục gọi API inventory đồng bộ, nhưng inventory cũng cần nhận thông báo về đơn hàng, có thể tách kiểu event sang một module hợp đồng độc lập.

Ví dụ cấu trúc:

~~~text
com.acme.shop
├── orders
│   └── OrderManagement.java
├── inventory
│   ├── api
│   │   └── StockAvailability.java
│   └── OrderCompletedListener.java
└── ordercontracts
    └── OrderCompleted.java
~~~

Event type được đặt trong module ordercontracts:

~~~java
package com.acme.shop.ordercontracts;

import java.util.UUID;

public record OrderCompleted(UUID orderId) {}
~~~

Cả orders và inventory đều sử dụng kiểu event từ module hợp đồng. Module inventory đăng ký listener:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.ordercontracts.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Cập nhật tồn kho.
    }
}
~~~

Module orders phát cùng kiểu event:

~~~java
package com.acme.shop.orders;

import com.acme.shop.ordercontracts.OrderCompleted;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final ApplicationEventPublisher events;

    OrderEventPublisher(ApplicationEventPublisher events) {
        this.events = events;
    }

    void publishCompleted(java.util.UUID orderId) {
        events.publishEvent(new OrderCompleted(orderId));
    }
}
~~~

Các quan hệ lúc này là:

- orders phụ thuộc inventory::api để gọi StockAvailability.
- orders phụ thuộc ordercontracts để tạo event.
- inventory phụ thuộc ordercontracts để nhận event.

Không còn dependency inventory → orders chỉ vì listener tham chiếu kiểu event, nên chu trình orders ↔ inventory được loại bỏ nếu không còn một quan hệ ngược khác.

~~~mermaid
flowchart TD
    O["orders"] -->|"API tồn kho"| I["inventory"]
    O --> C["ordercontracts"]
    I --> C
~~~

Module ordercontracts cần giữ vai trò hợp đồng thuần, không phụ thuộc ngược vào orders hoặc inventory. Chỉ đưa vào đó các event type và kiểu dữ liệu công khai cần thiết. Tránh biến module này thành một package dùng chung chứa entity hoặc logic nghiệp vụ của nhiều module.

## Cách 3: Dùng dependency inversion cho lời gọi đồng bộ

Nếu orders cần gọi một khả năng tồn kho đồng bộ, hãy xem xét đặt port tại phía module sử dụng khả năng đó. Module inventory cung cấp implementation cho port.

Ví dụ, orders sở hữu interface:

~~~java
package com.acme.shop.orders.api;

public interface StockReservation {
    boolean reserve(String productCode, int quantity);
}
~~~

Module inventory triển khai interface:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.api.StockReservation;
import org.springframework.stereotype.Component;

@Component
class InventoryStockReservation implements StockReservation {

    @Override
    public boolean reserve(String productCode, int quantity) {
        // Thực hiện quy tắc giữ hàng của inventory.
        return true;
    }
}
~~~

orders gọi interface do chính nó sở hữu:

~~~java
package com.acme.shop.orders;

import com.acme.shop.orders.api.StockReservation;
import org.springframework.stereotype.Service;

@Service
class OrderAcceptance {

    private final StockReservation reservation;

    OrderAcceptance(StockReservation reservation) {
        this.reservation = reservation;
    }
}
~~~

Về dependency tĩnh, inventory phụ thuộc vào hợp đồng do orders công bố; orders không cần phụ thuộc ngược vào package inventory. Spring có thể inject implementation từ inventory vào bean của orders khi cả hai module được khởi tạo trong cùng application context.

Cách này phù hợp khi port biểu đạt nhu cầu của orders và inventory có thể triển khai hợp đồng đó mà không làm sai quyền sở hữu nghiệp vụ. Nếu interface thực sự là API mà inventory sở hữu và các module khác cần sử dụng, đừng chuyển nó sang orders chỉ để làm đồ thị hết cycle. Hãy chọn chủ sở hữu theo ngữ nghĩa domain.

Nếu inventory còn listener nhận event từ orders, cả hai quan hệ tĩnh đều đi từ inventory về orders. Dependency graph không còn chu trình miễn là orders không tiếp tục import một kiểu hoặc bean khác từ inventory.

## Cách 4: Gộp module khi ranh giới nghiệp vụ không độc lập

Đôi khi chu trình cho thấy hai nhóm package thực chất thuộc cùng một capability. Nếu orders và inventory luôn cần gọi trực tiếp nhau, chia sẻ cùng quy tắc nhất quán và không có hợp đồng độc lập rõ ràng, hãy xem xét gộp chúng thành một module.

Việc gộp cần dựa trên quyền sở hữu nghiệp vụ, dữ liệu và vòng đời thay đổi. Không gộp chỉ để làm verification xanh. Sau khi gộp, hãy xác định lại API nội bộ và những module bên ngoài được phép sử dụng.

Nếu hai module vẫn có trách nhiệm độc lập, ưu tiên tách hợp đồng hoặc đảo chiều dependency phù hợp hơn.

## Vì sao không nên chỉ nới quy tắc để bỏ qua cycle?

Một số thay đổi không giải quyết nguyên nhân:

- Thêm module vào allowedDependencies ở cả hai phía không loại bỏ chu trình; nó chỉ cho phép các cạnh dependency đó.
- Đánh dấu module là OPEN mở rộng quyền truy cập package, nhưng không thay đổi hướng dependency.
- Đưa event type vào named interface của chính module orders vẫn khiến listener phụ thuộc vào orders.
- Bắt lỗi hoặc bỏ qua test verification làm mất tín hiệu về cấu trúc module.
- Đổi tên package mà không thay đổi module sở hữu kiểu cũng không làm thay đổi dependency graph.

allowedDependencies là allowlist cho dependency đi ra của module. Nó không phải công cụ xóa cạnh hoặc hợp nhất các module. Nếu hai chiều phụ thuộc đều có lý do, hãy thay đổi thiết kế để một chiều được loại bỏ hoặc chuyển qua một hợp đồng độc lập.

## Quy trình điều tra và sửa lỗi

Khi cycle xuất hiện sau khi thêm listener, hãy làm theo thứ tự:

1. Xác nhận module chứa listener và module sở hữu event type.
2. Xác định dependency do listener tạo ra từ consumer đến event owner.
3. Tìm dependency ngược, thường là lời gọi service, import API hoặc kiểu dữ liệu khác.
4. Xem event payload có tham chiếu entity hoặc type nội bộ không.
5. Xác định nghiệp vụ cần phản hồi đồng bộ hay chấp nhận event choreography.
6. Chọn cách sửa: bỏ lời gọi ngược, tách event contract, dùng dependency inversion hoặc gộp module.
7. Chạy lại ApplicationModules.verify() và đọc toàn bộ kết quả.
8. Kiểm tra các test module và luồng event bị ảnh hưởng.
9. Giữ bài kiểm chứng kiến trúc trong CI để phát hiện chu trình tái xuất hiện.

Không thêm nhiều thay đổi cùng lúc. Hãy sửa một quan hệ, kiểm chứng lại đồ thị rồi mới tiếp tục. Cách này giúp xác định chính xác thay đổi nào đã loại bỏ chu trình.

## Bài tập vận dụng

Một ứng dụng có hai module orders và inventory:

- OrderService inject StockAvailability từ inventory.api.
- InventoryOrderCompletedListener nhận OrderCompleted từ package orders.events.
- ApplicationModules.verify() báo dependency cycle.

Hãy thực hiện:

1. Vẽ hai cạnh dependency và xác định cạnh do listener tạo ra.
2. Xác nhận orders có cần gọi StockAvailability đồng bộ hay không.
3. Nếu có thể chấp nhận eventual consistency, thiết kế OrderPlaced, StockReserved và StockRejected.
4. Nếu vẫn cần gọi đồng bộ, cân nhắc đưa event vào module ordercontracts độc lập hoặc đặt port tại phía sở hữu nhu cầu.
5. Xác nhận event payload không chứa Order entity hoặc kiểu internal.
6. Chạy lại verification và giải thích vì sao đồ thị mới không còn chu trình.

Kết quả mong đợi: nhóm chỉ ra được dependency ngược do event listener, chọn cách thay đổi dựa trên semantics nghiệp vụ và giữ các hợp đồng event/API trong package được công bố rõ ràng.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích vì sao listener tạo dependency từ module nhận event đến module sở hữu event type, nhận diện cạnh ngược tạo thành cycle, kiểm tra payload lồng nhau, chọn giữa event choreography, contract module, dependency inversion hoặc gộp module, và xác nhận thay đổi bằng ApplicationModules.verify().

Tài liệu tham khảo:

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
