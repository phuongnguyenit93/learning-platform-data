# Class dependency được thu nhận thế nào?

Bài này thuộc chương **Dependency types** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith xây dựng mô hình các application module trong ứng dụng Spring Boot để làm rõ module nào sử dụng kiểu và hợp đồng do module nào sở hữu. Để làm được điều đó, framework cần thu thập các quan hệ phụ thuộc ở cấp lớp trước, sau đó quy chúng về quan hệ giữa các module.

Việc thu thập dựa trên phân tích cấu trúc mã nguồn đã biên dịch thông qua ArchUnit. Vì vậy, dependency không chỉ là một lời gọi method khi ứng dụng chạy. Một lớp có thể phụ thuộc vào lớp khác qua kiểu field, tham số, kiểu trả về, kế thừa, annotation hoặc các tham chiếu bytecode khác.

## 1. Từ class dependency đến module dependency

Giả sử ứng dụng bán hàng có hai module:

~~~text
com.acme.shop
├── order
│   └── internal
│       └── PlaceOrderHandler.java
└── inventory
    └── availability
        └── StockAvailability.java
~~~

Module inventory công khai hợp đồng:

~~~java
package com.acme.shop.inventory.availability;

public interface StockAvailability {

    boolean isAvailable(String productCode, int quantity);
}
~~~

Lớp trong module order sử dụng hợp đồng đó:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.availability.StockAvailability;

class PlaceOrderHandler {

    private final StockAvailability availability;

    PlaceOrderHandler(StockAvailability availability) {
        this.availability = availability;
    }

    boolean canPlace(String productCode, int quantity) {
        return availability.isAvailable(productCode, quantity);
    }
}
~~~

Ở cấp lớp, `PlaceOrderHandler` phụ thuộc vào `StockAvailability`. Ở cấp module, Spring Modulith quy quan hệ đó thành:

~~~text
order  ─────────>  inventory
        StockAvailability
~~~

Mũi tên đi từ module chứa lớp sử dụng sang module sở hữu lớp được tham chiếu. Một module có thể tạo nhiều class dependency tới các lớp khác nhau; những quan hệ này tạo thành đồ thị dependency giữa các application module.

## 2. Spring Modulith thu thập dependency bằng cách nào?

Khi gọi:

~~~java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
~~~

Spring Modulith dùng lớp ứng dụng làm điểm bắt đầu, khám phá các module theo cấu trúc package và phân tích các lớp thuộc phạm vi ứng dụng. Phần phân tích mã nguồn được hỗ trợ bởi ArchUnit.

Có thể hình dung quy trình như sau:

~~~text
Lớp ứng dụng và cấu trúc package
               |
               v
      Khám phá application module
               |
               v
       Nhập mô hình các Java class
          bằng ArchUnit
               |
               v
      Thu thập class dependency
       (source type -> target type)
               |
               v
      Xác định module sở hữu từng type
               |
               v
      Tổng hợp module dependency
               |
               v
     verify các quy tắc kiến trúc
~~~

ArchUnit đọc thông tin từ bytecode của các lớp được nhập để xây dựng mô hình về kiểu, thành viên và quan hệ giữa chúng. Spring Modulith dùng mô hình đó để xác định class dependency nào nối hai application module.

Quá trình này là phân tích cấu trúc tĩnh. Nó không cần khởi chạy toàn bộ ứng dụng Spring Boot để quan sát từng request hoặc từng luồng xử lý thực tế.

## 3. Những quan hệ nào tạo ra class dependency?

Theo mô hình dependency của ArchUnit, một lớp có thể phụ thuộc vào lớp khác qua nhiều dạng quan hệ.

| Dạng tham chiếu | Ví dụ | Ý nghĩa |
|---|---|---|
| Field access | Đọc hoặc ghi field của lớp khác. | Lớp sử dụng truy cập trạng thái do lớp kia khai báo. |
| Method call | Gọi method của lớp khác. | Lớp sử dụng gọi hành vi được cung cấp. |
| Constructor call | Tạo instance của lớp khác. | Lớp sử dụng khởi tạo kiểu kia. |
| Inheritance | `extends BaseOrder`. | Lớp phụ thuộc vào lớp cha. |
| Interface implementation | `implements StockAvailability`. | Lớp phụ thuộc vào hợp đồng interface. |
| Field type | `private StockAvailability availability;`. | Kiểu field tham chiếu tới lớp hoặc interface khác. |
| Parameter/return type | Method nhận hoặc trả về `CustomerProfile`. | Chữ ký method phụ thuộc vào kiểu đó. |
| Generic type | `List<CustomerProfile>`. | Chữ ký generic tham chiếu tới kiểu phần tử. |
| Annotation | `@Transactional` hoặc annotation có thuộc tính kiểu khác. | Kiểu annotation hoặc kiểu được dùng trong thuộc tính annotation được tham chiếu. |
| Throws/catch | `throws PaymentFailedException`. | Lớp tham chiếu tới kiểu exception. |
| Class literal/instanceof | `PaymentEvent.class`, `value instanceof PaymentEvent`. | Mã nguồn tham chiếu trực tiếp tới kiểu đó. |

Danh sách này cho thấy class dependency rộng hơn lời gọi method. Một lớp có thể phụ thuộc vào kiểu khác ngay trong khai báo field, chữ ký method, generic signature hoặc annotation, dù không gọi một method nào của kiểu đó.

## 4. Field, parameter và return type được ghi nhận

Ví dụ module order dùng ba kiểu từ các module khác nhau:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.customer.CustomerProfile;
import com.acme.shop.inventory.availability.StockAvailability;
import com.acme.shop.payment.PaymentReceipt;

class PlaceOrderHandler {

    private final StockAvailability availability;

    PlaceOrderHandler(StockAvailability availability) {
        this.availability = availability;
    }

    PaymentReceipt placeOrder(CustomerProfile customer) {
        if (!availability.isAvailable("SKU-1", 1)) {
            throw new IllegalStateException("Out of stock");
        }

        return new PaymentReceipt("TX-100", "PENDING");
    }
}
~~~

Trong ví dụ:

- Field `availability` tạo tham chiếu tới `StockAvailability`.
- Constructor parameter cũng tham chiếu tới `StockAvailability`.
- Method parameter `customer` tham chiếu tới `CustomerProfile`.
- Return type `PaymentReceipt` tham chiếu tới kiểu của module payment.

Các quan hệ này có thể làm phát sinh dependency từ order tới inventory, customer và payment. Nếu một kiểu xuất hiện ở nhiều vị trí, mô hình vẫn có thể ghi nhận nhiều chi tiết class dependency tương ứng.

Điều quan trọng là dependency được thu nhận từ cấu trúc khai báo và bytecode, không phụ thuộc vào việc biến có được đọc trong một lần chạy cụ thể hay không.

## 5. Lời gọi method và truy cập field cũng được thu nhận

Ngoài các kiểu trong chữ ký, ArchUnit còn phân tích các thao tác truy cập thành viên của lớp khác.

Ví dụ:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.StockRepository;

class InventoryInspector {

    private final StockRepository repository;

    InventoryInspector(StockRepository repository) {
        this.repository = repository;
    }

    int availableQuantity(String productCode) {
        return repository.findQuantity(productCode);
    }
}
~~~

Đoạn mã có thể tạo các tham chiếu ở nhiều cấp:

- Kiểu field và constructor parameter là `StockRepository`.
- Method body gọi `findQuantity` trên repository.
- Kiểu trả về của `findQuantity` có thể tạo thêm tham chiếu nếu nó thuộc module khác.

Một dependency không nhất thiết tương ứng với một dòng import duy nhất. Một class dependency có thể được hình thành từ nhiều vị trí trong cùng một lớp.

## 6. Import không đồng nghĩa với dependency thực tế

Dòng `import` giúp trình biên dịch Java phân giải tên kiểu. Bản thân một import không sử dụng không nhất thiết tạo ra quan hệ dependency trong bytecode.

Ví dụ:

~~~java
import com.acme.shop.payment.PaymentReceipt;

class OrderFormatter {

    String format(String orderId) {
        return "Order " + orderId;
    }
}
~~~

Nếu `PaymentReceipt` không được sử dụng ở bất kỳ khai báo hay thao tác nào, chỉ có dòng import không đủ để kết luận lớp phụ thuộc vào kiểu đó.

Ngược lại, một kiểu có thể được tham chiếu mà không cần import tường minh, ví dụ dùng tên đầy đủ:

~~~java
class OrderFormatter {

    com.acme.shop.payment.PaymentReceipt receipt;
}
~~~

Trong trường hợp này, field type tạo ra tham chiếu kiểu dù không có dòng import riêng.

Vì vậy, khi điều tra dependency, hãy tìm các tham chiếu kiểu và thao tác thực tế trong mã nguồn hoặc bytecode, thay vì chỉ đếm dòng import.

## 7. Từ source type và target type đến ApplicationModuleDependency

ArchUnit mô tả một class dependency bằng lớp nguồn và lớp đích. Spring Modulith dùng thông tin này để tạo quan hệ giữa các application module.

Trong API Spring Modulith, `ApplicationModuleDependency` cung cấp các thông tin chính:

| Phương thức | Trả về |
|---|---|
| `getSourceType()` | Java type tạo ra dependency. |
| `getTargetType()` | Java type được tham chiếu. |
| `getTargetModule()` | Application module sở hữu target type. |
| `getDependencyType()` | Loại dependency được phân loại. |

Ví dụ, có thể duyệt các dependency trực tiếp của module order:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule order = modules.getModuleByName("order")
        .orElseThrow();

order.getDirectDependencies(modules)
        .stream()
        .forEach(dependency -> System.out.printf(
                "%s -> %s [%s]%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName(),
                dependency.getDependencyType()
        ));
~~~

Kết quả giúp truy ngược từ một cạnh module dependency về cặp lớp cụ thể đã tạo ra nó. Đây là thông tin hữu ích khi verification báo module A đang phụ thuộc module B và nhóm cần tìm vị trí phát sinh quan hệ.

## 8. DependencyType phân loại quan hệ ở cấp module

Spring Modulith không chỉ ghi nhận module nào phụ thuộc module nào. Nó còn phân loại một số quan hệ bằng `DependencyType`.

| Loại | Ý nghĩa |
|---|---|
| `DEFAULT` | Dependency thông thường được suy ra từ tham chiếu giữa các kiểu. |
| `ENTITY` | Một module tham chiếu tới entity của module khác. |
| `EVENT_LISTENER` | Một module khai báo listener cho event được module khác công bố. |
| `USES_COMPONENT` | Một module phụ thuộc vào component của module khác; module được dùng cần được bootstrap để chạy module sử dụng. |

Ví dụ, một listener trong module payment nhận event do order công bố:

~~~java
package com.acme.shop.payment;

import com.acme.shop.order.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedHandler {

    @EventListener
    void on(OrderConfirmed event) {
        // Khởi tạo xử lý thanh toán sau khi đơn được xác nhận.
    }
}
~~~

Quan hệ listener có thể được phân loại là `EVENT_LISTENER`. Khác với dependency component thông thường, event listener không có nghĩa module phát event phải được bootstrap chỉ để module nhận event chạy.

Các loại này giúp mô tả bản chất quan hệ module, nhưng không thay thế thông tin source type và target type. Khi điều tra một dependency cụ thể, hãy xem cả hai khía cạnh: lớp nào tạo quan hệ và quan hệ được phân loại ra sao.

## 9. Class dependency bên trong một module và giữa các module

Không phải mọi class dependency đều trở thành module dependency.

| Trường hợp | Kết quả ở cấp module |
|---|---|
| Lớp A tham chiếu lớp B trong cùng application module. | Class dependency nội bộ; không tạo cạnh giữa hai application module khác nhau. |
| Lớp A thuộc module order tham chiếu kiểu thuộc module inventory. | Tạo quan hệ order → inventory. |
| Lớp A tham chiếu kiểu thuộc JDK hoặc thư viện ngoài. | Có class dependency tới kiểu ngoài, nhưng không tạo cạnh tới application module nếu kiểu đó không thuộc module được mô hình hóa. |
| Lớp A tham chiếu kiểu trong package nội bộ của module B. | Vẫn là dependency tới module B; verification có thể báo vi phạm encapsulation. |

Điều này rất quan trọng khi đọc đồ thị module. Đồ thị không phải danh sách mọi import trong toàn bộ dự án; nó biểu diễn quan hệ giữa các application module được Spring Modulith nhận diện.

## 10. Dependency được thu nhận tĩnh, không phải theo luồng chạy

Spring Modulith và ArchUnit phân tích các quan hệ thể hiện trong code đã biên dịch. Do đó:

- Một method chưa từng được gọi vẫn có thể tạo dependency qua parameter hoặc return type.
- Một field chưa được đọc vẫn thể hiện dependency qua kiểu field.
- Một method call trong nhánh điều kiện ít khi chạy vẫn được ghi nhận từ bytecode.
- Dependency không cho biết tần suất, thứ tự hoặc điều kiện một lời gọi xảy ra trong production.
- Reflection, tên class được tạo từ chuỗi hoặc wiring động có thể không thể hiện đầy đủ như tham chiếu kiểu tĩnh thông thường.

Vì vậy, class dependency trả lời câu hỏi **“Mã nguồn có quan hệ tham chiếu nào?”**, chứ không trả lời **“Trong production, module nào đã gọi module nào bao nhiêu lần?”**. Muốn quan sát tương tác runtime, cần dùng cơ chế quan sát và tracing phù hợp.

## 11. Dùng dependency để tìm vi phạm kiến trúc

Khi một dependency được thu nhận, Spring Modulith có thể đối chiếu nó với quy tắc module:

- Module consumer có được phép phụ thuộc module provider không?
- Kiểu đích có nằm trong API mặc định hoặc named interface được công khai không?
- Dependency có tạo chu trình giữa các application module không?
- Module consumer có đang tham chiếu trực tiếp entity hoặc package nội bộ không?

Ví dụ order phụ thuộc vào package nội bộ của inventory:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.StockRepository;

class PlaceOrderHandler {

    private final StockRepository repository;

    PlaceOrderHandler(StockRepository repository) {
        this.repository = repository;
    }
}
~~~

Quan hệ order → inventory vẫn được thu nhận. Tuy nhiên, target type nằm trong package nội bộ của inventory nên có thể vi phạm quy tắc truy cập API của module.

Cách xử lý nên xuất phát từ nhu cầu nghiệp vụ:

1. Xác định hành vi hoặc dữ liệu order thực sự cần.
2. Yêu cầu inventory cung cấp hợp đồng công khai phù hợp.
3. Đặt hợp đồng ở package gốc hoặc named interface.
4. Chuyển consumer sang dùng hợp đồng đó.
5. Chạy lại verification để xác nhận ranh giới được tuân thủ.

## 12. Kiểm chứng mô hình dependency

Có thể tạo bài test kiến trúc:

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

`verify()` kiểm tra các quy tắc như không có vòng phụ thuộc module, truy cập module khác qua API được công khai và tuân thủ danh sách dependency được phép nếu đã khai báo.

Khi test thất bại, hãy đọc thông báo để tìm source type, target type và module liên quan. Sau đó lần theo khai báo field, chữ ký method, kế thừa, annotation hoặc lời gọi thành viên đã tạo ra class dependency.

## 13. Quy trình điều tra một class dependency

1. **Xác định module nguồn.** Tìm package và application module chứa lớp phát sinh tham chiếu.
2. **Xác định target type.** Tìm kiểu được tham chiếu và package sở hữu nó.
3. **Tìm vị trí tạo tham chiếu.** Kiểm tra field, parameter, return type, generic, annotation, inheritance và method/constructor access.
4. **Xác định module đích.** Dùng cấu trúc package để biết module nào sở hữu target type.
5. **Xem loại dependency.** Phân biệt dependency thông thường, entity, event listener hoặc component dependency.
6. **Kiểm tra API boundary.** Xác định target type có nằm trong API được công khai hay trong package nội bộ.
7. **Đối chiếu allowedDependencies.** Kiểm tra consumer có được phép phụ thuộc module hoặc named interface đó không.
8. **Sửa hợp đồng hoặc hướng phụ thuộc.** Thay đổi thiết kế theo quyền sở hữu nghiệp vụ.
9. **Chạy verification lại.** Xác nhận dependency đã tuân thủ các quy tắc kiến trúc.

## Ghi nhớ

Spring Modulith thu nhận class dependency thông qua mô hình mã nguồn do ArchUnit phân tích. Quan hệ có thể xuất phát từ field, parameter, return type, generic, annotation, inheritance, method/constructor call, field access và nhiều tham chiếu kiểu khác.

Từ source type và target type, Spring Modulith xác định module nguồn, module đích và loại dependency để xây dựng đồ thị module. Khi hiểu cách thu thập này, nhóm có thể truy ngược một cạnh kiến trúc về đúng lớp và khai báo đã tạo ra nó, rồi dùng `ApplicationModules.verify()` để bảo vệ ranh giới modular monolith.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModuleDependency API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html)
- [Spring Modulith — DependencyType API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [ArchUnit — Dependency API](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/Dependency.html)
- [ArchUnit — User Guide](https://www.archunit.org/userguide/html/000_Index.html)
