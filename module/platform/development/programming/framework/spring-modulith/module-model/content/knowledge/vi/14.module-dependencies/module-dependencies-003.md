# Dependency từ field, parameter và return type

Bài này thuộc chương **Module dependencies** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa ứng dụng Spring Boot thành các application module, xác định API công khai và kiểm tra hướng phụ thuộc giữa chúng. Một module có thể phụ thuộc vào module khác ngay khi kiểu của module đó xuất hiện trong khai báo của mã nguồn.

Ba vị trí quan trọng cần nhận diện là **field**, **parameter** và **return type**. Khi một lớp thuộc module A khai báo field, tham số hoặc kiểu trả về thuộc module B, mô hình kiến trúc có thể ghi nhận quan hệ phụ thuộc từ A đến B. Quan hệ này tồn tại ở cấp kiểu dữ liệu, kể cả khi ta chưa quan sát thấy một lời gọi phương thức cụ thể trong luồng chạy.

## 1. Dependency được hình thành từ tham chiếu kiểu

Giả sử ứng dụng có hai module:

~~~text
com.acme.shop
├── order
│   └── internal
│       └── PlaceOrderHandler.java
└── inventory
    └── availability
        ├── package-info.java
        └── StockAvailability.java
~~~

Module inventory công khai hợp đồng kiểm tra tồn kho:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

~~~java
package com.acme.shop.inventory.availability;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Lớp thuộc module order sử dụng kiểu `StockAvailability`:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.availability.StockAvailability;

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

Từ khai báo field và constructor parameter, ta thấy module order tham chiếu đến một kiểu do inventory cung cấp. Mô hình phụ thuộc có hướng:

~~~text
order  ───────>  inventory
                 availability
~~~

Mũi tên đi từ module sử dụng kiểu sang module sở hữu kiểu. Vì vậy, order phụ thuộc vào inventory; inventory không tự động phụ thuộc ngược lại vào order.

## 2. Field type tạo dependency

Một field có kiểu thuộc module khác là một tham chiếu kiểu giữa hai module:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.availability.StockAvailability;

class PlaceOrderHandler {

    private StockAvailability stockAvailability;
}
~~~

Dù field là `private`, kiểu `StockAvailability` vẫn xuất hiện trong khai báo của lớp. Modifier truy cập của Java không xóa tham chiếu kiểu đó khỏi mô hình kiến trúc.

Điều này thường gặp trong Spring khi dùng constructor injection hoặc field injection. Spring có thể khởi tạo và gán bean ở runtime, nhưng dependency kiến trúc đã được thể hiện trong mã nguồn qua kiểu được khai báo.

Một số điểm cần nhớ:

- Field có thể là `private`, `protected` hoặc `public`; quyền truy cập không quyết định module dependency có tồn tại hay không.
- Field có kiểu từ module khác tạo quan hệ phụ thuộc từ module chứa field đến module sở hữu kiểu.
- Nếu kiểu đó nằm trong package nội bộ của module provider, dependency có thể vi phạm quy tắc encapsulation.
- Field dùng kiểu thuộc cùng module không tạo ra dependency giữa hai application module khác nhau.

Không nên nghĩ rằng chỉ những field được Spring inject mới quan trọng. Một field thông thường cũng là một tham chiếu kiểu trong cấu trúc mã nguồn.

## 3. Parameter type tạo dependency

Tham số của constructor hoặc method cũng có thể tạo dependency. Ví dụ:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.availability.StockAvailability;

class PlaceOrderHandler {

    PlaceOrderHandler(StockAvailability stockAvailability) {
        // ...
    }

    void checkAvailability(StockAvailability stockAvailability) {
        // ...
    }
}
~~~

Cả constructor parameter và method parameter đều khai báo rằng lớp thuộc order cần biết kiểu `StockAvailability` của inventory.

Dependency được hình thành từ chữ ký phương thức. Không cần phải đợi đến khi method được gọi trong một test hoặc một request thật mới có quan hệ kiến trúc.

Một ví dụ khác là module order nhận dữ liệu khách hàng qua một kiểu do module customer công khai:

~~~java
package com.acme.shop.order;

import com.acme.shop.customer.CustomerProfile;

public interface OrderManagement {

    void placeOrder(CustomerProfile customer);
}
~~~

Ở đây, chữ ký của `placeOrder` làm cho module order phụ thuộc vào kiểu `CustomerProfile` thuộc module customer. Nếu đây là hợp đồng có chủ đích, kiểu đó cần nằm trong API công khai phù hợp của customer.

## 4. Return type tạo dependency

Kiểu trả về của method cũng thể hiện một dependency. Ví dụ module payment cung cấp kết quả thanh toán:

~~~java
package com.acme.shop.payment;

public record PaymentReceipt(String transactionId, String status) {
}
~~~

Module order khai báo một method trả về kiểu đó:

~~~java
package com.acme.shop.order;

import com.acme.shop.payment.PaymentReceipt;

public interface OrderPaymentView {

    PaymentReceipt paymentReceipt(String orderId);
}
~~~

Chữ ký này tạo dependency từ order đến payment vì `PaymentReceipt` thuộc module payment.

Điều này có ý nghĩa khi thiết kế API: một module không chỉ phụ thuộc vào những kiểu nó nhận vào, mà còn phụ thuộc vào những kiểu nó trả ra. Nếu API của order trả về entity hoặc DTO nội bộ của payment, chi tiết đó trở thành một phần hợp đồng mà order phải biết.

Hãy xem xét quyền sở hữu của kiểu trả về. Nếu dữ liệu là kết quả nghiệp vụ do payment sở hữu, việc sử dụng kiểu công khai của payment có thể hợp lý. Nếu dữ liệu chỉ là một biểu diễn dành riêng cho order, nhóm có thể định nghĩa một kiểu kết quả thuộc order và chuyển đổi tại ranh giới.

## 5. Tổng hợp ba vị trí tạo dependency

| Vị trí khai báo | Ví dụ | Hướng dependency |
|---|---|---|
| Field type | `private StockAvailability availability;` | Module chứa field → module sở hữu `StockAvailability`. |
| Constructor parameter | `PlaceOrderHandler(StockAvailability availability)` | Module chứa constructor → module sở hữu kiểu parameter. |
| Method parameter | `placeOrder(CustomerProfile customer)` | Module chứa method → module sở hữu `CustomerProfile`. |
| Return type | `PaymentReceipt paymentReceipt()` | Module chứa method → module sở hữu `PaymentReceipt`. |

Một lớp có thể tham chiếu nhiều kiểu từ cùng một module hoặc từ nhiều module khác nhau. Mỗi tham chiếu kiểu là một cạnh ở cấp lớp; ở cấp application module, các cạnh giữa cùng một cặp module thể hiện quan hệ phụ thuộc tương ứng.

Ví dụ:

~~~text
             ┌───────────┐
             │ customer  │
             └─────▲─────┘
                   │ CustomerProfile
┌──────────┐       │
│ payment  │◄──────┤
└──────────┘       │ PaymentReceipt
                   │
             ┌─────┴─────┐
             │   order   │
             └───────────┘
                   │
                   │ StockAvailability
                   ▼
             ┌───────────┐
             │ inventory │
             └───────────┘
~~~

Sơ đồ minh họa order sử dụng các kiểu công khai từ customer, payment và inventory. Nó không có nghĩa các module kia phụ thuộc ngược lại vào order.

## 6. Dependency trong chữ ký có thể tồn tại dù chưa có lời gọi runtime

Hãy xem ví dụ:

~~~java
package com.acme.shop.order;

import com.acme.shop.payment.PaymentReceipt;

public interface PaymentLookup {

    PaymentReceipt findReceipt(String orderId);
}
~~~

Ngay cả khi chưa có lớp triển khai hoặc chưa có nơi nào gọi `findReceipt`, kiểu trả về `PaymentReceipt` vẫn xuất hiện trong chữ ký của interface. Đây là một tham chiếu kiểu mà mô hình kiến trúc cần xem xét.

Tương tự, một field được khai báo nhưng chưa đọc hoặc một method parameter chưa được dùng trong thân hàm vẫn thể hiện sự phụ thuộc ở cấp kiểu.

Vì vậy, khi review kiến trúc, không chỉ tìm các câu lệnh gọi method. Hãy xem cả:

- Kiểu của field.
- Kiểu của tham số constructor.
- Kiểu của tham số method.
- Kiểu trả về của method.
- Các kiểu được dùng trong hợp đồng public của interface hoặc class.

Dependency analysis của Spring Modulith dựa trên cấu trúc tham chiếu kiểu trong codebase, không chỉ dựa trên đường đi của một request cụ thể.

## 7. Kiểu tham chiếu nằm ở API hay package nội bộ?

Một dependency tới module khác chưa chắc đã hợp lệ. Cần kiểm tra kiểu được tham chiếu có nằm trong bề mặt API mà module provider công khai hay không.

Ví dụ inventory có cấu trúc:

~~~text
com.acme.shop.inventory
├── availability
│   ├── package-info.java
│   └── StockAvailability.java
└── internal
    └── persistence
        └── StockRepository.java
~~~

Package `availability` được đánh dấu là named interface:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Order có thể sử dụng `StockAvailability` nếu dependency được cho phép. Nhưng nếu order khai báo field hoặc parameter kiểu `StockRepository` từ package `inventory.internal.persistence`, nó đang phụ thuộc vào chi tiết triển khai nội bộ.

Cả hai trường hợp đều tạo ra quan hệ order → inventory, nhưng chỉ trường hợp dùng hợp đồng công khai mới tuân thủ ranh giới API đã thiết kế.

Đừng nhầm `public` của Java với API công khai của application module. Một lớp có thể là `public` để code Java truy cập được nhưng vẫn thuộc package nội bộ theo mô hình Spring Modulith.

## 8. Khai báo dependency được phép

Nếu order được phép sử dụng named interface availability của inventory, có thể khai báo ở package gốc của order:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory::availability"}
)
package com.acme.shop.order;
~~~

Chuỗi `inventory::availability` biểu thị named interface `availability` của module `inventory`.

Nếu order còn cần API mặc định của customer, có thể khai báo thêm:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::availability",
        "customer",
        "payment"
    }
)
package com.acme.shop.order;
~~~

Danh sách này nên phản ánh những module mà order thực sự cần sử dụng. Không nên thêm một module vào `allowedDependencies` chỉ để làm kiểm tra qua nếu dependency đó chưa có lý do kiến trúc.

Nếu dependency phát sinh từ một field, parameter hoặc return type không mong muốn, hãy xem lại kiểu dữ liệu và quyền sở hữu của nó trước khi mở rộng danh sách cho phép.

## 9. Tránh phụ thuộc ngoài ý muốn trong chữ ký API

Một API có thể vô tình làm lộ dependency qua parameter hoặc return type.

Ví dụ không nên công khai entity nội bộ:

~~~java
package com.acme.shop.order;

import com.acme.shop.customer.internal.CustomerEntity;

public interface OrderManagement {

    CustomerEntity customerForOrder(String orderId);
}
~~~

Trong ví dụ này, module order phụ thuộc vào package nội bộ của customer. Hơn nữa, entity lưu trữ của customer đã trở thành một phần chữ ký API của order.

Có thể thay bằng một kiểu kết quả ổn định được công khai bởi customer:

~~~java
package com.acme.shop.customer;

public record CustomerProfile(String customerId, String displayName) {
}
~~~

~~~java
package com.acme.shop.order;

import com.acme.shop.customer.CustomerProfile;

public interface OrderManagement {

    CustomerProfile customerForOrder(String orderId);
}
~~~

Nếu hai module có ngữ nghĩa khác nhau hoặc cần vòng đời độc lập, có thể định nghĩa DTO riêng trong module sử dụng và chuyển đổi dữ liệu ở ranh giới. Điều quan trọng là không để một kiểu nội bộ trở thành hợp đồng ngầm giữa các module.

## 10. Kiểm chứng dependency bằng ApplicationModules.verify()

Có thể dùng bài kiểm tra kiến trúc để xác minh các dependency được mô hình hóa:

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

Khi kiểm tra, Spring Modulith có thể phát hiện các quan hệ phụ thuộc vi phạm quy tắc module, chẳng hạn:

- Module tham chiếu kiểu thuộc package nội bộ của module khác.
- Module phụ thuộc vào named interface chưa được cho phép.
- Dependency giữa các module không nằm trong danh sách allowed dependencies.
- Quan hệ phụ thuộc tạo thành vòng nếu quy tắc kiến trúc yêu cầu không có chu trình.

Nếu test thất bại, hãy tìm kiểu tạo ra dependency. Kiểm tra nó xuất hiện ở field, parameter, return type hay một tham chiếu kiểu khác. Sau đó xác định module sở hữu kiểu và quyết định nên công khai hợp đồng, chuyển đổi kiểu dữ liệu hay loại bỏ dependency.

## 11. Quy trình review một dependency phát sinh từ type

Khi verification báo module A phụ thuộc module B, hãy thực hiện:

1. **Xác định kiểu được tham chiếu.** Tìm class hoặc interface thuộc module B xuất hiện trong code của module A.
2. **Xác định vị trí khai báo.** Kiểm tra field, constructor parameter, method parameter hoặc return type.
3. **Xác định package sở hữu kiểu.** Kiểu nằm trong API mặc định, named interface hay package nội bộ?
4. **Đánh giá nhu cầu nghiệp vụ.** Module A có thực sự cần biết kiểu này không?
5. **Chọn hợp đồng phù hợp.** Dùng API công khai, tạo DTO ở ranh giới hoặc chuyển đổi dữ liệu nếu hai module có ngữ nghĩa khác nhau.
6. **Cập nhật quy tắc phụ thuộc.** Chỉ khai báo allowed dependency khi quan hệ đó được thiết kế và chấp nhận.
7. **Chạy lại verification.** Đảm bảo dependency đã đúng hướng và không tạo thêm vi phạm khác.

Đừng chỉ xóa một field hoặc đổi kiểu để làm test qua mà không xem xét hành vi nghiệp vụ. Mục tiêu là làm rõ hợp đồng giữa các module và giữ quyền sở hữu của từng capability.

## Ghi nhớ

Field type, constructor/method parameter type và method return type đều có thể tạo ra dependency giữa application module. Hướng phụ thuộc đi từ module chứa khai báo đến module sở hữu kiểu được tham chiếu. Dependency có thể tồn tại ngay trong chữ ký mã nguồn dù chưa có lời gọi runtime cụ thể.

Khi thiết kế API, hãy kiểm tra cả kiểu đầu vào, kiểu trả về và field được inject. Dùng các kiểu thuộc API mặc định hoặc named interface đã công khai, khai báo dependency có chủ đích và chạy `ApplicationModules.verify()` để bảo vệ ranh giới module.
