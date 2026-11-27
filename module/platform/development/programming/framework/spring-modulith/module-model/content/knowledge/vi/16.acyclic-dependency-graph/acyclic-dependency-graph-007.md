# Đưa dependency về abstraction hoặc named interface

Bài này thuộc chương **Acyclic graph** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các application module trong một ứng dụng Spring Boot. Một trong những mục tiêu quan trọng của modular monolith là giữ đồ thị phụ thuộc có hướng và không có chu trình.

Khi hai module phụ thuộc trực tiếp lẫn nhau, thay đổi ở module này dễ lan sang module kia và ranh giới sở hữu trở nên khó hiểu. Có thể xử lý bằng cách **đưa quan hệ phụ thuộc qua một abstraction (port/interface) do bên cần năng lực sở hữu**, hoặc **công khai đúng hợp đồng qua named interface**. Hai kỹ thuật liên quan nhưng giải quyết hai vấn đề khác nhau: abstraction thay đổi hướng phụ thuộc; named interface xác định phần API được phép sử dụng.

## 1. Vì sao dependency hai chiều tạo ra vấn đề?

Giả sử module order cần gọi inventory để giữ hàng. Đồng thời, inventory lại gọi trực tiếp order để kiểm tra trạng thái đơn trước khi giữ hàng.

~~~text
order  ─────────>  inventory
  ^                    |
  |                    |
  └────────────────────┘
~~~

Ví dụ code có thể được tổ chức như sau:

~~~java
// Trong module order
package com.acme.shop.order.internal;

import com.acme.shop.inventory.StockReservation;

class PlaceOrderHandler {

    private final StockReservation stockReservation;

    PlaceOrderHandler(StockReservation stockReservation) {
        this.stockReservation = stockReservation;
    }
}
~~~

~~~java
// Trong module inventory
package com.acme.shop.inventory.internal;

import com.acme.shop.order.OrderQuery;

class ReservationService {

    private final OrderQuery orderQuery;

    ReservationService(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }
}
~~~

Quan hệ đầu tiên là order → inventory vì order tham chiếu `StockReservation`. Quan hệ thứ hai là inventory → order vì inventory tham chiếu `OrderQuery`.

Khi tổng hợp hai cạnh, đồ thị có chu trình. Hệ quả thường gặp:

- Khó xác định module nào sở hữu quy tắc phối hợp.
- Thay đổi hợp đồng ở một phía buộc phía còn lại thay đổi theo.
- Khó kiểm thử hoặc tái sử dụng riêng từng module.
- Các module dần biết quá nhiều về cấu trúc nội bộ của nhau.
- Kiểm tra kiến trúc có thể báo vòng phụ thuộc giữa application module.

Mục tiêu khi refactor là giữ nhu cầu nghiệp vụ nhưng thay đổi cách các module biết về nhau, để đồ thị trở thành một chiều.

## 2. Đưa dependency qua abstraction là gì?

Abstraction là một hợp đồng mô tả điều bên sử dụng cần, chẳng hạn một interface hoặc port. Bên cần một khả năng phụ thuộc vào hợp đồng; một adapter ở phía cung cấp triển khai hợp đồng đó.

Quy tắc quan trọng của Dependency Inversion Principle là: **đặt abstraction ở phía sở hữu nhu cầu**, để chi tiết triển khai phụ thuộc vào abstraction thay vì buộc abstraction phụ thuộc vào chi tiết.

Ví dụ, inventory cần biết một đơn hàng có được xác nhận hay không. Thay vì import trực tiếp `OrderQuery` của module order, inventory định nghĩa một port mô tả thông tin mà nó cần:

~~~java
package com.acme.shop.inventory.spi;

public interface OrderReservationContext {

    boolean isOrderConfirmed(String orderId);
}
~~~

Phần triển khai sẽ do module order cung cấp. Inventory chỉ biết interface `OrderReservationContext`; nó không biết lớp adapter cụ thể, repository hay entity của order.

Khi đó, mã nguồn module inventory phụ thuộc vào abstraction thuộc chính module inventory. Module order phụ thuộc vào abstraction này để triển khai adapter. Hướng phụ thuộc ở cấp module trở thành order → inventory thay vì inventory → order.

## 3. Ví dụ đảo chiều phụ thuộc bằng port

Giả sử inventory công khai chức năng giữ hàng:

~~~java
package com.acme.shop.inventory;

public interface StockReservation {

    void reserve(String orderId, String productCode, int quantity);
}
~~~

Module inventory định nghĩa port cần thiết trong package `spi`:

~~~java
package com.acme.shop.inventory.spi;

public interface OrderReservationContext {

    boolean isOrderConfirmed(String orderId);
}
~~~

Service nội bộ của inventory chỉ phụ thuộc vào port:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.spi.OrderReservationContext;
import org.springframework.stereotype.Component;

@Component
class ReservationService {

    private final OrderReservationContext orderContext;

    ReservationService(OrderReservationContext orderContext) {
        this.orderContext = orderContext;
    }

    void reserve(String orderId, String productCode, int quantity) {
        if (!orderContext.isOrderConfirmed(orderId)) {
            throw new IllegalStateException("Order is not confirmed");
        }

        // Áp dụng quy tắc giữ hàng và cập nhật tồn kho.
    }
}
~~~

Module order cung cấp adapter triển khai port. Adapter có thể gọi các thành phần nội bộ của order vì chúng thuộc cùng module:

~~~java
package com.acme.shop.order.internal.integration;

import com.acme.shop.inventory.spi.OrderReservationContext;
import com.acme.shop.order.internal.OrderQueryService;
import org.springframework.stereotype.Component;

@Component
class OrderReservationContextAdapter implements OrderReservationContext {

    private final OrderQueryService orderQueryService;

    OrderReservationContextAdapter(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Override
    public boolean isOrderConfirmed(String orderId) {
        return orderQueryService.isConfirmed(orderId);
    }
}
~~~

Quan hệ phụ thuộc sau khi đảo chiều:

~~~text
order ─────────────> inventory
  │                       ▲
  │ implements            │ owns
  │                       │
  └── OrderReservationContext
       (port / abstraction)
~~~

Diễn giải:

- Inventory sở hữu port vì inventory là module cần thông tin trạng thái đơn.
- ReservationService chỉ biết interface trong module inventory.
- Order adapter triển khai interface đó và dùng OrderQueryService nội bộ.
- Module inventory không import hoặc tham chiếu kiểu của module order.
- Module order phụ thuộc vào inventory để dùng hợp đồng SPI.

Trong Spring, adapter có thể được đăng ký thành bean và được inject vào service của inventory. Cần bảo đảm cấu hình component scanning và điều kiện khởi tạo bean của ứng dụng phù hợp với cách tổ chức module.

## 4. Đồ thị trước và sau khi đảo chiều

| Trước refactor | Sau refactor |
|---|---|
| order → inventory | order → inventory |
| inventory → order | Không còn dependency mã nguồn inventory → order |
| Có chu trình order ↔ inventory | Đồ thị chỉ còn một chiều order → inventory |
| Inventory tham chiếu trực tiếp OrderQuery | Inventory tham chiếu port OrderReservationContext do chính nó sở hữu |
| Order và inventory biết chi tiết của nhau | Order cung cấp adapter cho hợp đồng của inventory |

Việc đảo chiều không làm biến mất nhu cầu phối hợp ở runtime. Inventory vẫn nhận được câu trả lời từ adapter của order. Điều thay đổi là dependency trong mã nguồn và quyền sở hữu hợp đồng: module cần thông tin định nghĩa điều nó cần; module khác triển khai hợp đồng đó.

Cách này đặc biệt phù hợp khi một module cần gọi đồng bộ một capability hoặc cần truy vấn thông tin từ module khác, nhưng muốn giữ hướng dependency không quay ngược lại.

## 5. Named interface giải quyết phần nào?

Named interface là cơ chế Spring Modulith dùng để **công khai một package con như một phần API có tên** của application module. Nó giúp module consumer phụ thuộc vào đúng hợp đồng mà provider chủ động mở.

Ví dụ, package SPI của inventory được công khai với tên `reservation-spi`:

~~~java
@org.springframework.modulith.NamedInterface("reservation-spi")
package com.acme.shop.inventory.spi;
~~~

Module order cần triển khai port này có thể khai báo dependency được phép:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "inventory::reservation-spi"
    }
)
package com.acme.shop.order;
~~~

Trong đó:

- `inventory` cho phép order sử dụng API mặc định của inventory, ví dụ `StockReservation`.
- `inventory::reservation-spi` cho phép order tham chiếu interface `OrderReservationContext` trong named interface.
- Tên sau dấu `::` phải khớp với giá trị trong `@NamedInterface`.

Named interface giúp thể hiện hợp đồng rõ ràng và giữ các package nội bộ khác được đóng kín. Nó phù hợp khi một module muốn công khai một nhóm interface hoặc kiểu dữ liệu chuyên biệt cho module khác.

## 6. Named interface không tự phá chu trình

Cần phân biệt rõ hai mục tiêu:

- **Abstraction/port** thay đổi nơi đặt hợp đồng và hướng phụ thuộc giữa các module.
- **Named interface** công khai một package con để module khác có thể phụ thuộc vào hợp đồng trong đó.

Nếu order vẫn tham chiếu API của inventory và inventory vẫn tham chiếu API của order, việc chuyển cả hai package thành named interface không làm mất hai cạnh. Đồ thị vẫn là:

~~~text
order  ─────────> inventory
  ^                    |
  |                    |
  └────────────────────┘
~~~

Named interface chỉ làm rõ rằng các cạnh đi qua API được công khai. Để loại bỏ chu trình, nhóm vẫn phải thay đổi hướng phụ thuộc, chẳng hạn đưa một port về module sở hữu nhu cầu, chuyển một tương tác thành event hoặc tách một hợp đồng thực sự dùng chung.

Đừng dùng `@NamedInterface` như một cách “bỏ qua” lỗi cycle. Nó là cơ chế quản lý bề mặt API, không phải thuật toán tự động đảo chiều dependency.

## 7. Khi nào nên dùng abstraction, named interface hoặc module hợp đồng chung?

| Tình huống | Hướng xử lý |
|---|---|
| Module A cần một hành vi hoặc dữ liệu từ B, nhưng B cũng đang gọi trực tiếp A. | Xác định nhu cầu của B và đưa port vào module sở hữu nhu cầu; A triển khai port nếu phù hợp. |
| Module cung cấp đã có một nhóm API ổn định trong package con. | Đánh dấu package bằng `@NamedInterface` và giới hạn dependency tới named interface đó. |
| Nhiều module thực sự chia sẻ cùng một khái niệm hoặc hợp đồng ổn định. | Cân nhắc một module hợp đồng nhỏ mà các bên cùng phụ thuộc. |
| Một module chỉ cần thông báo sự kiện đã xảy ra, không cần gọi đồng bộ module kia. | Cân nhắc application event để bên phát không phải tham chiếu listener. |
| Hai module có khái niệm cùng tên nhưng ngữ nghĩa khác nhau. | Giữ mô hình riêng trong từng module và chuyển đổi tại ranh giới. |

Một module hợp đồng chung chỉ nên chứa những abstraction thực sự ổn định và có chủ sở hữu rõ ràng. Không gom entity, repository hoặc helper tùy tiện vào package `common` vì điều đó dễ tạo ra một module dùng chung quá lớn.

## 8. Một cách khác: dùng event để loại bỏ lời gọi ngược

Nếu module inventory chỉ cần thông báo rằng hàng đã được giữ, nó có thể công bố event mà không gọi trực tiếp module order.

Ví dụ, inventory định nghĩa và phát event của mình:

~~~java
package com.acme.shop.inventory;

public record StockReserved(
    String orderId,
    String productCode,
    int quantity
) {
}
~~~

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.StockReserved;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class StockReservationPublisher {

    private final ApplicationEventPublisher events;

    StockReservationPublisher(ApplicationEventPublisher events) {
        this.events = events;
    }

    void publishReservation(String orderId, String productCode, int quantity) {
        events.publishEvent(new StockReserved(orderId, productCode, quantity));
    }
}
~~~

Module order lắng nghe event:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.StockReserved;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class StockReservedHandler {

    @EventListener
    void on(StockReserved event) {
        // Cập nhật trạng thái xử lý đơn theo sự kiện giữ hàng.
    }
}
~~~

Trong trường hợp này, order tham chiếu kiểu event do inventory công khai, tạo dependency order → inventory. Inventory không cần import handler của order; nó chỉ phát event thuộc quyền sở hữu của mình.

Event phù hợp khi bên phát chỉ cần thông báo một sự kiện nghiệp vụ. Nếu bên phát cần một câu trả lời đồng bộ để quyết định tiếp tục hay dừng, một port/interface có thể phù hợp hơn. Cần xem xét thêm semantics giao dịch, xử lý lặp và tính nhất quán dữ liệu khi dùng event.

## 9. Tránh những cách refactor làm cycle khó hiểu hơn

**Chỉ chuyển interface sang package common mà không xác định quyền sở hữu.** Nếu package chung chứa mọi interface của ứng dụng, nó có thể trở thành một điểm phụ thuộc tập trung và khó thay đổi.

**Để interface phụ thuộc vào implementation.** Một abstraction không còn hữu ích nếu chữ ký của nó trả về entity hoặc repository nội bộ của module triển khai.

**Công khai toàn bộ package để làm verification qua.** Việc mở rộng API có thể che đi vấn đề encapsulation mà không loại bỏ chu trình.

**Giữ cả lời gọi trực tiếp và port mới.** Sau khi chuyển consumer sang abstraction, hãy gỡ đường phụ thuộc cũ nếu nó không còn cần thiết; nếu không, chu trình vẫn tồn tại.

**Tách module quá sớm.** Không phải mọi interface dùng chung đều cần một application module mới. Chỉ tách khi hợp đồng có ý nghĩa độc lập và có quyền sở hữu rõ ràng.

**Tạo adapter chỉ để chuyển tiếp mà không có ranh giới rõ.** Adapter nên là nơi chuyển đổi giữa mô hình hoặc giao thức, không chỉ thêm một lớp trung gian làm code khó lần theo.

## 10. Kiểm tra dependency sau khi refactor

Sau khi thay đổi hợp đồng và hướng phụ thuộc, chạy kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Có thể xem các dependency trực tiếp của module để xác nhận đồ thị sau refactor:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule order = modules.getModuleByName("order")
        .orElseThrow();

order.getDirectDependencies(modules).forEach(dependency ->
        System.out.printf(
                "%s -> %s%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName()
        )
);
~~~

Khi verification thất bại, hãy tìm source type và target type tạo ra cạnh. Xác định dependency còn lại đến từ field, parameter, return type, method call hay một tham chiếu khác. Sau đó xem xét liệu hợp đồng nên được chuyển về port, công khai bằng named interface hay thay bằng event.

`verify()` kiểm tra các quy tắc mà mô hình Spring Modulith biểu diễn. Nó không tự đánh giá abstraction có đúng quyền sở hữu nghiệp vụ hay event có semantics phù hợp; các quyết định đó cần được review.

## 11. Quy trình đưa dependency về abstraction hoặc named interface

1. **Vẽ chu trình hiện tại.** Ghi rõ module nguồn, module đích và lớp tạo ra từng cạnh.
2. **Xác định nhu cầu ở mỗi chiều.** Module nào cần hành vi, dữ liệu hoặc thông báo từ module kia?
3. **Chọn bên sở hữu abstraction.** Đặt port tại module có nhu cầu và định nghĩa hợp đồng tối thiểu.
4. **Đưa implementation về adapter.** Module còn lại triển khai port và chuyển đổi sang mô hình nội bộ của nó.
5. **Công khai đúng package.** Nếu adapter ở module khác cần tham chiếu port trong package con, dùng `@NamedInterface`.
6. **Khai báo dependency được phép.** Dùng `allowedDependencies` theo dạng `module::interface` khi phù hợp.
7. **Gỡ tham chiếu trực tiếp cũ.** Xóa đường dependency ngược đã được thay thế.
8. **Kiểm tra đồ thị.** Chạy `ApplicationModules.verify()` và xem lại các dependency trực tiếp.
9. **Kiểm tra hành vi.** Chạy test use case để bảo đảm việc đảo chiều không làm thay đổi quy tắc nghiệp vụ ngoài dự kiến.

Sau refactor, đồ thị module nên có hướng phụ thuộc đơn giản và có thể giải thích được. Nếu vẫn còn chu trình, hãy xem liệu một hợp đồng khác hoặc một tương tác event có thể thay thế cạnh còn lại hay không.

## Ghi nhớ

Đưa dependency về abstraction giúp module sở hữu nhu cầu định nghĩa port mà nó cần; module khác có thể triển khai port đó qua adapter. Cách này đảo chiều phụ thuộc ở cấp mã nguồn và có thể biến đồ thị hai chiều thành một chiều.

Named interface giúp công khai đúng package chứa hợp đồng và giới hạn module consumer được phép tham chiếu. Nó không tự loại bỏ chu trình nếu hai module vẫn tham chiếu lẫn nhau. Hãy kết hợp đúng hai kỹ thuật: dùng abstraction để định hướng lại dependency, dùng named interface để biểu diễn bề mặt API, rồi kiểm chứng đồ thị bằng `ApplicationModules.verify()`.
