# Chu kỳ trực tiếp giữa hai module

Trong modular monolith, dependency graph ở cấp Application Module cần là đồ thị có hướng không chu trình (directed acyclic graph – DAG). Một chu kỳ trực tiếp giữa hai module xuất hiện khi **module A phụ thuộc module B, đồng thời module B cũng phụ thuộc module A**. Hai module có thể chỉ tham chiếu API công khai của nhau và vẫn tạo ra chu kỳ; việc dùng interface hoặc khai báo **allowedDependencies** không tự loại bỏ được quan hệ hai chiều đó.

Spring Modulith phát hiện chu kỳ ở cấp module khi chạy **ApplicationModules.verify()**. Bài học này phân tích một chu kỳ A ↔ B, giải thích vì sao nó làm ranh giới module khó thay đổi và trình bày các cách đưa dependency trở lại một chiều.

## 1. Chu kỳ trực tiếp là gì?

Giả sử ứng dụng có hai Application Module:

- **orders**: quản lý đơn hàng.
- **inventory**: quản lý số lượng và giữ hàng.

Nếu **orders** gọi API của **inventory** để giữ hàng, ta có cạnh:

~~~text
orders ─────> inventory
~~~

Nếu **inventory** đồng thời gọi API của **orders** để tra cứu thông tin đơn hàng, ta có cạnh ngược:

~~~text
inventory ─────> orders
~~~

Kết hợp hai cạnh:

~~~text
orders ─────────> inventory
   ^                  |
   |                  |
   └──────────────────┘
~~~

Đây là chu kỳ trực tiếp có hai đỉnh và hai cạnh. Mỗi module vừa là consumer của module kia, vừa là provider mà module kia cần.

Trong dependency graph, mũi tên đi từ module chứa mã nguồn tham chiếu tới module sở hữu type được tham chiếu. Vì vậy, hãy đọc **A → B** là “A phụ thuộc B”, không phải “A gọi B lúc runtime trong mọi trường hợp”.

## 2. Ví dụ tạo chu kỳ bằng API công khai

Giả sử **inventory** công bố API giữ hàng trong root package:

~~~java
package com.acme.shop.inventory;

public interface InventoryReservation {

    boolean reserve(String orderId);
}
~~~

Module **orders** sử dụng API này trong phần triển khai:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.inventory.InventoryReservation;
import org.springframework.stereotype.Service;

@Service
class OrderPlacementService {

    private final InventoryReservation inventoryReservation;

    OrderPlacementService(InventoryReservation inventoryReservation) {
        this.inventoryReservation = inventoryReservation;
    }

    boolean placeOrder(String orderId) {
        return inventoryReservation.reserve(orderId);
    }
}
~~~

Ở chiều ngược lại, **orders** công bố API tra cứu đơn hàng:

~~~java
package com.acme.shop.orders;

public interface OrderLookup {

    boolean exists(String orderId);
}
~~~

Module **inventory** sử dụng API đó:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.OrderLookup;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final OrderLookup orderLookup;

    InventoryService(OrderLookup orderLookup) {
        this.orderLookup = orderLookup;
    }

    boolean canReserveFor(String orderId) {
        return orderLookup.exists(orderId);
    }
}
~~~

Hai import đều trỏ tới root package được công bố. Không có tham chiếu vào internal của module kia, nhưng dependency graph vẫn là:

~~~text
orders ─────> inventory
   ^              |
   └──────────────┘
~~~

Điều này cho thấy **API công khai không đồng nghĩa với dependency một chiều**. Một module có thể công bố API tốt nhưng hai module vẫn bị ghép chặt nếu chúng cần API của nhau.

## 3. allowedDependencies không sửa được chu kỳ

Các allowlist dưới đây có thể mô tả hai cạnh là dependency được phép:

Trong **com.acme.shop.orders/package-info.java**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.orders;
~~~

Trong **com.acme.shop.inventory/package-info.java**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.inventory;
~~~

Hai khai báo cho phép **orders** phụ thuộc **inventory** và **inventory** phụ thuộc **orders**. Chúng chỉ trả lời câu hỏi “module này được phép phụ thuộc vào đâu?”. Chúng không làm dependency graph trở thành DAG.

Spring Modulith kiểm tra chu kỳ ở cấp Application Module như một quy tắc độc lập. Vì vậy, dù cả hai cạnh đều nằm trong **allowedDependencies**, verification vẫn phát hiện chu kỳ trực tiếp.

## 4. Kiểm chứng bằng ApplicationModules.verify()

Tạo một bài test kiến trúc:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi có chu kỳ **orders ↔ inventory**, **verify()** ném exception vì dependency graph không còn là DAG. Thông báo vi phạm giúp xác định các module nằm trong chu kỳ để lần theo import tạo ra từng cạnh.

Nếu muốn thu thập vi phạm trước khi quyết định cách xử lý, có thể dùng:

~~~java
var violations = ApplicationModules.of(ShopApplication.class)
    .detectViolations();
~~~

**detectViolations()** trả về tập hợp các vi phạm kiến trúc để có thể xem xét hoặc xử lý tiếp. Trong test bảo vệ kiến trúc, **verify()** thường là cách trực tiếp để làm bài test thất bại khi phát hiện chu kỳ.

## 5. Vì sao chu kỳ trực tiếp là vấn đề?

Chu kỳ khiến hai module không còn có thể được hiểu và thay đổi độc lập theo hướng phụ thuộc rõ ràng:

- **Khó xác định quyền sở hữu nghiệp vụ:** mỗi module cần biết một phần trách nhiệm của module kia.
- **Thay đổi lan truyền:** đổi API tra cứu đơn hàng có thể ảnh hưởng **inventory**; đổi API giữ hàng có thể ảnh hưởng **orders**.
- **Khó kiểm thử độc lập:** khi bootstrap một module riêng, các bean của module kia có thể trở thành dependency cần được mock hoặc đưa thêm vào context.
- **Khó tái sử dụng:** tách một module thành service riêng hoặc thay implementation có thể kéo theo cả module còn lại.
- **Dễ phát sinh vòng lặp trách nhiệm:** mỗi module có thể tiếp tục bổ sung API để đáp ứng nhu cầu ngược chiều, làm ranh giới ngày càng mờ.

Chu kỳ ở cấp module cũng cần được phân biệt với circular dependency giữa Spring bean. Hai bean có thể tham chiếu vòng nhau trong cùng một module mà không tạo chu kỳ giữa Application Module. Ngược lại, hai module có thể tạo chu kỳ trong dependency graph qua type import dù Spring chưa gặp lỗi khởi tạo bean.

## 6. Cách 1: Đưa điều phối vào module thứ ba

Nếu một use case cần phối hợp cả đơn hàng và tồn kho, có thể để một module điều phối đứng phía trên hai module:

~~~text
             checkout
              /    \
             v      v
          orders  inventory
~~~

Module **checkout** gọi API của cả **orders** và **inventory**. Hai module nghiệp vụ không cần gọi ngược lẫn nhau.

Ví dụ:

~~~java
package com.acme.shop.orders;

public interface OrderManagement {

    void confirm(String orderId);
}
~~~

~~~java
package com.acme.shop.checkout;

import com.acme.shop.inventory.InventoryReservation;
import com.acme.shop.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
class CheckoutService {

    private final OrderManagement orderManagement;
    private final InventoryReservation inventoryReservation;

    CheckoutService(
            OrderManagement orderManagement,
            InventoryReservation inventoryReservation) {
        this.orderManagement = orderManagement;
        this.inventoryReservation = inventoryReservation;
    }

    boolean checkout(String orderId) {
        if (!inventoryReservation.reserve(orderId)) {
            return false;
        }

        orderManagement.confirm(orderId);
        return true;
    }
}
~~~

**checkout** sở hữu quy trình phối hợp. **orders** sở hữu vòng đời đơn hàng; **inventory** sở hữu việc giữ hàng. Dependency graph có hai cạnh đi ra từ **checkout** và không có cạnh quay ngược từ hai module nghiệp vụ về **checkout**.

Chỉ nên thêm module điều phối nếu use case thực sự thuộc về một capability riêng. Tránh tạo một module **common** hoặc **orchestrator** chung chung chỉ để gom các lời gọi mà không có quyền sở hữu nghiệp vụ rõ ràng.

## 7. Cách 2: Dùng application event để bỏ chiều phụ thuộc ngược

Nếu **inventory** chỉ cần phản ứng khi đơn hàng được tạo, **orders** có thể công bố event:

~~~java
package com.acme.shop.orders.events;

public record OrderPlaced(String orderId) {
}
~~~

Để event type được dùng liên module, công bố package event bằng Named Interface:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Module **inventory** khai báo chỉ phụ thuộc vào giao diện event:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.acme.shop.inventory;
~~~

Module **orders** phát event sau khi hoàn tất nghiệp vụ:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
class OrderPlacementService {

    private final ApplicationEventPublisher events;

    OrderPlacementService(ApplicationEventPublisher events) {
        this.events = events;
    }

    void placeOrder(String orderId) {
        // Lưu đơn hàng và hoàn tất các quy tắc cần thiết.
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

**inventory** lắng nghe event được công bố:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Tạo yêu cầu giữ hàng cho đơn hàng vừa được đặt.
    }
}
~~~

Ở mức mã nguồn, **inventory** tham chiếu event type thuộc **orders**, nên có cạnh:

~~~text
inventory ─────> orders
~~~

Ở runtime, event đi từ publisher **orders** tới listener **inventory**. Đây là hai góc nhìn khác nhau: dependency graph theo hướng type được import, còn event flow theo hướng thông điệp được phát.

Event không mặc nhiên có nghĩa mọi xử lý đều bất đồng bộ. Spring application event được phát đồng bộ theo mặc định; **@ApplicationModuleListener** là cách khai báo listener theo mô hình tích hợp module của Spring Modulith, với xử lý transactional và asynchronous theo cấu hình mặc định của annotation. Khi chuyển từ lời gọi trực tiếp sang event, hãy xác định rõ thời điểm listener chạy, ranh giới transaction và cách xử lý khi listener thất bại. Điều này thay đổi semantics của use case, dù mục tiêu kiến trúc là loại bỏ một cạnh dependency.

Để loại bỏ chu kỳ, **orders** không được tiếp tục import API của **inventory** trong cùng dependency graph. Nếu **orders** vẫn gọi **InventoryReservation** trực tiếp, cạnh **orders → inventory** còn tồn tại và chu kỳ chưa được giải quyết.

## 8. Cách 3: Đảo chiều phụ thuộc bằng SPI

Nếu **orders** cần một hành vi giữ hàng nhưng không nên biết module nào cung cấp hành vi đó, **orders** có thể định nghĩa một SPI thuộc quyền sở hữu của mình:

~~~java
package com.acme.shop.orders.spi;

public interface InventoryReservation {

    boolean reserve(String orderId);
}
~~~

Công bố package SPI:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Module **orders** sử dụng interface của chính nó:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.spi.InventoryReservation;
import org.springframework.stereotype.Service;

@Service
class OrderPlacementService {

    private final InventoryReservation reservation;

    OrderPlacementService(InventoryReservation reservation) {
        this.reservation = reservation;
    }
}
~~~

Module **inventory** triển khai SPI:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.spi.InventoryReservation;
import org.springframework.stereotype.Component;

@Component
class InventoryReservationAdapter implements InventoryReservation {

    @Override
    public boolean reserve(String orderId) {
        // Thực hiện giữ hàng bằng mô hình dữ liệu của inventory.
        return true;
    }
}
~~~

Dependency mã nguồn lúc này đi từ **inventory** tới **orders :: spi**, vì implementation trong **inventory** import interface do **orders** sở hữu. Spring inject implementation vào **orders** lúc runtime; điều đó không tạo import ngược từ **orders** sang **inventory**.

Module **inventory** giới hạn dependency của nó ở SPI được công bố:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.inventory;
~~~

SPI phù hợp khi module sở hữu use case định nghĩa được điểm mở rộng ổn định. Không nên tạo SPI chỉ để che một thiết kế chưa rõ quyền sở hữu; hãy xác định trước module nào sở hữu hợp đồng và ai có trách nhiệm cung cấp implementation.

## 9. Cách 4: Tách hợp đồng dùng chung thành module độc lập

Đôi khi hai module thực sự cần cùng một khái niệm hoặc hợp đồng ổn định. Có thể chuyển hợp đồng đó vào một module nền tảng nhỏ, độc lập với cả hai:

~~~text
orders ───────> commerce-contracts

inventory ────> commerce-contracts
~~~

Module **commerce-contracts** chỉ chứa các type hợp đồng cần chia sẻ và không phụ thuộc ngược vào **orders** hoặc **inventory**. Nhờ vậy, hai module nghiệp vụ cùng phụ thuộc vào một module nền tảng, thay vì phụ thuộc lẫn nhau.

Không nên chuyển toàn bộ entity hoặc service của hai module vào một module dùng chung. Chỉ đưa những abstraction thực sự ổn định và có nhiều consumer vào đó. Nếu module hợp đồng bắt đầu chứa logic nghiệp vụ của cả hai phía, chu kỳ có thể chỉ bị che bằng một ranh giới mới.

## 10. Quy trình tìm và phá chu kỳ trực tiếp

Khi **ApplicationModules.verify()** báo chu kỳ giữa hai module, thực hiện:

1. Ghi lại hai module và hai cạnh trong chu kỳ, ví dụ **orders → inventory** và **inventory → orders**.
2. Tìm các import tạo ra từng cạnh; phân biệt type thuộc API root package, Named Interface hay package nội bộ.
3. Xác định use case nào thực sự cần phối hợp hai module và module nào nên sở hữu quy trình đó.
4. Chọn cách tái cấu trúc phù hợp: module điều phối, application event, SPI hoặc module hợp đồng dùng chung.
5. Xóa ít nhất một chiều phụ thuộc mã nguồn để dependency graph không còn chu trình.
6. Điều chỉnh **allowedDependencies** theo các cạnh mới còn lại.
7. Chạy lại **ApplicationModules.verify()** và kiểm tra các module consumer liên quan.

Đừng chỉ xóa một import hoặc chuyển class sang package khác mà không xem xét quyền sở hữu nghiệp vụ. Mục tiêu là tạo một hướng phụ thuộc có ý nghĩa, để mỗi module có thể thay đổi implementation mà không buộc module kia thay đổi theo.

## 11. Kiểm chứng kết quả sau tái cấu trúc

Sau khi sửa, giữ bài test kiến trúc trong test suite:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void keepsApplicationModuleGraphAcyclic() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Ngoài việc test PASS, hãy kiểm tra dependency graph được sinh ra hoặc danh sách dependency trực tiếp để xác nhận:

- Không còn cạnh quay ngược tạo thành chu kỳ **A ↔ B**.
- Consumer chỉ tham chiếu API package hoặc Named Interface được công bố.
- **allowedDependencies** vẫn cho phép các cạnh có chủ đích.
- Các event hoặc SPI mới phản ánh đúng quyền sở hữu hợp đồng.

**verify()** bảo vệ quy tắc kiến trúc của toàn bộ mô hình được phân tích. Unit test và module integration test vẫn cần thiết để kiểm tra hành vi nghiệp vụ sau khi thay đổi cách phối hợp giữa các module.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): quy tắc dependency graph phải là directed acyclic graph và cách gọi **ApplicationModules.verify()**.
- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): Application Module, API package và Named Interface.
- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): công bố event và tích hợp giữa các module qua application events.
