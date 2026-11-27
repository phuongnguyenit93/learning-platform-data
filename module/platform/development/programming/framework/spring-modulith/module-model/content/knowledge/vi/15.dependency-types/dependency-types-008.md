# Dependency cùng module và dependency ra ngoài

Bài này thuộc chương **Dependency types** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa ứng dụng Spring Boot thành các application module, giúp nhóm nhìn thấy ranh giới nghiệp vụ, API công khai và hướng phụ thuộc giữa các capability. Khi đọc mô hình này, cần phân biệt hai phạm vi: **dependency giữa các lớp trong cùng một module** và **dependency đi từ module này sang module khác**.

Cả hai đều có thể tồn tại trong mã nguồn, nhưng ý nghĩa ở cấp kiến trúc khác nhau. Dependency cùng module là quan hệ nội bộ trong một ranh giới sở hữu; dependency ra ngoài tạo ra một cạnh trong đồ thị application module và cần tuân thủ API cùng quy tắc phụ thuộc đã thiết kế.

## 1. Hai phạm vi dependency

Giả sử ứng dụng bán hàng có các module order và inventory:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── application
│       │   └── PlaceOrderHandler.java
│       ├── domain
│       │   └── Order.java
│       └── persistence
│           └── OrderRepository.java
└── inventory
    ├── StockAvailability.java
    └── internal
        └── StockRepository.java
~~~

Các package con trực tiếp `order` và `inventory` là application module theo chiến lược phát hiện mặc định. Những package lồng bên trong `order` thuộc cấu trúc nội bộ của cùng module order.

Trong cấu trúc này có hai loại quan hệ:

- **Dependency cùng module:** `PlaceOrderHandler` sử dụng `Order` hoặc `OrderRepository`. Cả hai đầu đều thuộc module order.
- **Dependency ra ngoài:** `PlaceOrderHandler` sử dụng `StockAvailability`. Lớp nguồn thuộc order, còn kiểu đích thuộc inventory.

Có thể hình dung:

~~~text
             Module order
       ┌──────────────────────┐
       │ PlaceOrderHandler    │
       │       │              │
       │       ├──> Order     │  dependency cùng module
       │       │              │
       │       └──────────────┼──────────┐
       └──────────────────────┘          │
                                         v
                               Module inventory
                               ┌──────────────────┐
                               │ StockAvailability│
                               └──────────────────┘
                                  dependency ra ngoài
~~~

Cả hai quan hệ đều là tham chiếu giữa các kiểu. Điểm phân biệt là hai kiểu được sở hữu bởi cùng một application module hay bởi hai module khác nhau.

## 2. Dependency cùng module là gì?

Dependency cùng module xuất hiện khi một kiểu trong module tham chiếu đến kiểu khác cũng thuộc module đó.

Ví dụ:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.order.internal.domain.Order;
import com.acme.shop.order.internal.persistence.OrderRepository;

class PlaceOrderHandler {

    private final OrderRepository orders;

    PlaceOrderHandler(OrderRepository orders) {
        this.orders = orders;
    }

    Order place(String orderId) {
        Order order = orders.findById(orderId);
        order.confirm();
        return order;
    }
}
~~~

`PlaceOrderHandler`, `Order` và `OrderRepository` nằm trong các package con của `com.acme.shop.order`. Theo mô hình mặc định, chúng đều thuộc application module order.

Quan hệ giữa các lớp vẫn tồn tại và có thể được phân tích ở cấp class. Tuy nhiên, khi tổng hợp thành đồ thị application module, nó không tạo ra một cạnh từ order sang một module khác, vì source type và target type cùng thuộc order.

Điều này cho phép module tổ chức nội bộ thành nhiều lớp và package: application service có thể gọi domain object, domain service có thể phối hợp các kiểu trong cùng module, adapter persistence có thể triển khai repository mà module sở hữu.

## 3. Dependency ra ngoài là gì?

Dependency ra ngoài xuất hiện khi một kiểu thuộc module A tham chiếu đến kiểu thuộc module B.

Ví dụ, order cần kiểm tra khả năng cung ứng hàng từ inventory:

~~~java
package com.acme.shop.inventory;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Lớp xử lý đơn hàng sử dụng hợp đồng này:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.inventory.StockAvailability;

class PlaceOrderHandler {

    private final StockAvailability stockAvailability;

    PlaceOrderHandler(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    boolean canPlace(String productCode, int quantity) {
        return stockAvailability.hasAvailableStock(productCode, quantity);
    }
}
~~~

Ở đây, source type thuộc order và target type thuộc inventory. Vì hai kiểu nằm trong hai application module khác nhau, Spring Modulith ghi nhận dependency ra ngoài:

~~~text
order  ─────────>  inventory
       StockAvailability
~~~

Mũi tên đi từ module sử dụng kiểu sang module sở hữu kiểu. Nó không tự tạo ra chiều ngược lại: inventory không phụ thuộc order chỉ vì order đang gọi inventory.

## 4. So sánh dependency cùng module và dependency ra ngoài

| Tiêu chí | Cùng module | Ra ngoài |
|---|---|---|
| Source và target | Thuộc cùng application module. | Thuộc hai application module khác nhau. |
| Phạm vi | Nội bộ một ranh giới module. | Đi qua ranh giới module. |
| Đồ thị module | Không tạo cạnh giữa hai module khác nhau. | Tạo cạnh từ module nguồn tới module đích. |
| API công khai | Không cần mở API module cho chính các lớp nội bộ đó. | Cần dùng API mặc định hoặc named interface được công khai. |
| Quy tắc phụ thuộc | Không phải dependency giữa hai module. | Có thể cần khai báo trong `allowedDependencies`. |
| Rủi ro chính | Liên kết nội bộ quá chặt, trách nhiệm không rõ. | Phụ thuộc chéo, vi phạm encapsulation hoặc tạo chu trình. |

Không nên hiểu “cùng module” là không có dependency. Quan hệ giữa các lớp vẫn có thật; chỉ là nó không vượt qua ranh giới application module.

Ngược lại, dependency ra ngoài không tự động là sai. Một modular monolith cần các module phối hợp với nhau. Điều cần kiểm soát là module sử dụng phụ thuộc vào hợp đồng nào, theo hướng nào và có được phép hay không.

## 5. Package lồng nhau không tự tạo module mới

Với chiến lược phát hiện mặc định, các package con trực tiếp của application base package là module cấp cao. Package lồng sâu hơn thuộc module chứa nó, trừ khi ứng dụng dùng chiến lược phát hiện khác để xác định ranh giới.

Ví dụ:

~~~text
com.acme.shop
├── order
│   ├── internal
│   │   ├── application
│   │   ├── domain
│   │   └── persistence
│   └── reporting
└── inventory
    ├── internal
    │   └── persistence
    └── availability
~~~

Nếu `order` và `inventory` là module cấp cao, các package `order.internal.domain`, `order.reporting` và `inventory.internal.persistence` vẫn thuộc module cha tương ứng.

Do đó:

- `order.internal.application.PlaceOrderHandler` sử dụng `order.internal.domain.Order`: dependency cùng module.
- `order.internal.application.PlaceOrderHandler` sử dụng `inventory.availability.StockAvailability`: dependency ra ngoài.
- `inventory.internal.persistence.StockRepository` sử dụng `inventory.availability.StockAvailability`: dependency cùng module.

Tên package như `internal`, `domain` hoặc `persistence` không tự xác định một application module mới. Hãy dựa vào module base package được Spring Modulith phát hiện.

## 6. Dependency cùng module không bị ràng buộc bởi API công khai của module

API mặc định của module thường nằm ở package gốc; package con được xem là nội bộ trừ khi được công khai bằng named interface. Quy tắc này chủ yếu kiểm soát việc module khác truy cập vào module.

Các lớp bên trong cùng module có thể phối hợp với nhau qua các package nội bộ theo thiết kế của module. Ví dụ, `PlaceOrderHandler` có thể dùng `OrderRepository` trong `order.internal.persistence` mà không cần biến repository đó thành named interface cho toàn ứng dụng.

Điều này không có nghĩa mọi lớp nội bộ nên truy cập tùy ý mọi lớp khác. Nhóm vẫn cần giữ cấu trúc bên trong dễ hiểu:

- Application layer điều phối use case.
- Domain layer giữ quy tắc nghiệp vụ.
- Persistence adapter thực hiện lưu trữ.
- Web adapter xử lý giao thức HTTP.
- Các package nội bộ trao đổi qua hợp đồng phù hợp với thiết kế của module.

Spring Modulith giúp bảo vệ ranh giới giữa các application module. Việc tổ chức chi tiết bên trong một module có thể cần thêm quy ước hoặc kiểm tra kiến trúc ở cấp package nếu nhóm muốn giới hạn sâu hơn.

## 7. Dependency ra ngoài phải đi qua API được công khai

Giả sử inventory có cấu trúc:

~~~text
com.acme.shop.inventory
├── StockAvailability.java
└── internal
    └── persistence
        └── StockRepository.java
~~~

Order nên phụ thuộc vào `StockAvailability` ở package gốc hoặc một named interface được công khai. Order không nên tham chiếu trực tiếp `StockRepository` trong package nội bộ.

Nếu hợp đồng nằm trong package con, provider có thể công khai bằng `@NamedInterface`:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Consumer khai báo dependency được phép tại package gốc của module order:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory::availability"}
)
package com.acme.shop.order;
~~~

Chuỗi `inventory::availability` biểu thị named interface availability của module inventory. Cấu hình này ghi lại chủ đích rằng order chỉ cần capability kiểm tra khả năng cung ứng.

Nếu consumer truy cập package nội bộ, quan hệ module vẫn là order → inventory, nhưng có thể vi phạm quy tắc API boundary. Vì vậy, cần phân biệt hai câu hỏi:

1. Dependency đi tới module nào?
2. Kiểu được tham chiếu có thuộc phần API mà module đó công khai không?

## 8. Thư viện bên ngoài không phải application module

Một lớp có thể tham chiếu kiểu của JDK hoặc thư viện ngoài:

~~~java
package com.acme.shop.order.internal;

import java.time.Instant;
import java.util.UUID;

class OrderIdentity {

    private final UUID id;
    private final Instant createdAt;
}
~~~

Các tham chiếu tới `UUID` và `Instant` là dependency ở cấp lớp. Tuy nhiên, chúng không tạo cạnh tới application module trong ứng dụng, vì JDK không phải module nghiệp vụ được Spring Modulith khám phá trong mô hình này.

Tương tự, kiểu từ thư viện ngoài như logging, persistence framework hoặc HTTP client có thể xuất hiện trong bytecode mà không trở thành dependency giữa hai application module của ứng dụng.

Khi đọc đồ thị module, hãy tập trung vào quan hệ giữa các module nội bộ được phát hiện. Đồ thị đó không phải danh sách toàn bộ thư viện mà mỗi lớp đang sử dụng.

## 9. Dependency cùng module vẫn có thể là dấu hiệu thiết kế cần xem lại

Dù không tạo cạnh module dependency, các quan hệ nội bộ vẫn ảnh hưởng đến khả năng bảo trì.

Ví dụ, một lớp application service phụ thuộc trực tiếp vào nhiều entity và repository có thể làm luồng use case khó kiểm thử. Một package domain phụ thuộc vào adapter persistence có thể khiến quy tắc nghiệp vụ bị gắn với công nghệ lưu trữ.

Những vấn đề này không nhất thiết được thể hiện như vi phạm ranh giới giữa hai application module. Nhóm có thể cần quy ước package riêng hoặc kiểm tra ArchUnit bổ sung để bảo vệ hướng phụ thuộc bên trong module.

Một số dấu hiệu cần review:

- Domain layer phụ thuộc vào web hoặc persistence adapter.
- Nhiều lớp gọi trực tiếp repository của nhau và bỏ qua use case.
- Một package nội bộ trở thành nơi chứa mọi trách nhiệm.
- Một module có quá nhiều kiểu phụ thuộc vòng ở cấp lớp.
- Các package con không thể giải thích bằng một trách nhiệm rõ ràng.

Mục tiêu là giữ module có cấu trúc nội bộ dễ hiểu, ngay cả khi Spring Modulith không biểu diễn từng quan hệ đó thành cạnh giữa module.

## 10. Chu trình dependency chỉ có ý nghĩa ở đúng phạm vi

Một module có thể có nhiều dependency nội bộ giữa các lớp. Những tham chiếu này không tạo thành chu trình giữa các application module nếu cả hai đầu vẫn thuộc cùng module.

Ví dụ:

~~~text
order.internal.application.PlaceOrderHandler
                 |
                 v
order.internal.domain.Order
                 |
                 v
order.internal.policy.OrderPolicy
                 |
                 └────────> PlaceOrderHandler
~~~

Đây có thể là một chu trình ở cấp lớp nếu các kiểu tham chiếu quay lại nhau. Tuy nhiên, ở cấp application module, tất cả các kiểu đều thuộc order, nên không có chu trình giữa order và một module khác được tạo ra từ các cạnh đó.

Ngược lại, nếu order phụ thuộc inventory và inventory phụ thuộc order, đồ thị application module có chu trình:

~~~text
order  ─────>  inventory
  ^                 |
  └─────────────────┘
~~~

Chu trình giữa các module thường là dấu hiệu cần xem lại quyền sở hữu và hướng phối hợp. Có thể một hợp đồng đang được đặt sai module, hai module đang biết quá nhiều chi tiết của nhau hoặc cần một cách phối hợp khác như application event.

## 11. Kiểm tra module dependency bằng ApplicationModules.verify()

Có thể yêu cầu Spring Modulith xác minh các quy tắc kiến trúc:

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

Kiểm tra này tập trung vào mô hình application module: các module có phụ thuộc vào package nội bộ của module khác hay không, các dependency có được phép không và có chu trình giữa các module hay không theo quy tắc được áp dụng.

Một dependency cùng module không phải lý do để khai báo `allowedDependencies` giữa hai module, vì nó không vượt ranh giới application module. Ngược lại, dependency ra ngoài cần được xem xét theo API và quy tắc phụ thuộc.

Nếu muốn kiểm tra sâu hơn cấu trúc bên trong module, nhóm có thể bổ sung các quy tắc ArchUnit riêng. Không nên kỳ vọng `ApplicationModules.verify()` thay thế mọi kiểm tra về layering nội bộ.

## 12. Quy trình phân loại một dependency

Khi thấy lớp A tham chiếu lớp B, hãy thực hiện:

1. **Tìm package của lớp A và B.** Dùng package đầy đủ để tránh nhầm package con với module riêng.
2. **Xác định module base package.** Xem module nào sở hữu từng lớp theo chiến lược detection đang dùng.
3. **So sánh hai module sở hữu.** Nếu cùng module, đó là dependency nội bộ; nếu khác module, đó là dependency ra ngoài.
4. **Nếu ra ngoài, kiểm tra API boundary.** Target type nằm trong package gốc, named interface hay package nội bộ?
5. **Kiểm tra hướng phụ thuộc.** Module nguồn có nên sử dụng capability của module đích không?
6. **Đối chiếu quy tắc cho phép.** Xem khai báo `allowedDependencies` có thể hiện đúng chủ đích không.
7. **Kiểm tra chu trình.** Xem dependency có tạo vòng giữa các application module không.
8. **Chạy verification.** Dùng `ApplicationModules.verify()` để kiểm tra mô hình sau khi điều chỉnh.

## Ghi nhớ

Dependency cùng module là tham chiếu giữa các lớp thuộc một application module; nó góp phần tạo cấu trúc nội bộ nhưng không tạo cạnh giữa các module khác nhau. Dependency ra ngoài nối một lớp của module nguồn tới kiểu thuộc module đích và tạo quan hệ có hướng trong đồ thị application module.

Khi phân tích một tham chiếu, trước hết xác định module sở hữu hai kiểu. Nếu cùng module, review cấu trúc nội bộ theo quy ước của nhóm. Nếu khác module, kiểm tra API công khai, named interface, hướng phụ thuộc và `allowedDependencies`, sau đó dùng `ApplicationModules.verify()` để bảo vệ ranh giới modular monolith.
