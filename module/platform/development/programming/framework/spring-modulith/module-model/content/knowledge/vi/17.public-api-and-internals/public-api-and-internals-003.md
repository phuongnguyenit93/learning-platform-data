# Reference tới class internal bị báo vi phạm

Trong một modular monolith, module có thể chứa nhiều class `public` để các package khác nhau bên trong cùng module sử dụng. Nhưng `public` của Java chỉ quyết định khả năng truy cập ở cấp ngôn ngữ; nó không có nghĩa class đó đã trở thành API mà module khác được phép phụ thuộc.

Với application module đóng mặc định của Spring Modulith, package gốc là API mặc định. Các package con không được công bố là Named Interface được xem là phần triển khai nội bộ. Vì vậy, một module khác có thể biên dịch thành công khi import class `public` từ package `internal`, nhưng `ApplicationModules.verify()` vẫn báo vi phạm kiến trúc.

## 1. `public` không đồng nghĩa với public API của module

Giả sử ứng dụng có hai module `order` và `shipping`:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       ├── OrderRepository.java
│       └── OrderService.java
└── shipping
    └── ShippingService.java
```

`OrderManagement` nằm trong package gốc `com.acme.shop.order`, nên thuộc API mặc định của module `order`. `OrderRepository` và `OrderService` nằm trong package con `order.internal`; chúng là chi tiết triển khai của module.

Một class trong package con có thể cần modifier `public` để class ở package khác nhưng vẫn thuộc cùng module sử dụng nó. Java không xem package con là cùng package với package cha. Do đó, package-private trong `com.acme.shop.order` không tự mở rộng sang `com.acme.shop.order.internal`.

```java
package com.acme.shop.order.internal;

public class OrderRepository {
    // Chi tiết truy cập dữ liệu của module order.
}
```

Modifier `public` cho phép code Java bên ngoài package `order.internal` tham chiếu class này. Tuy nhiên, trong module model của Spring Modulith, package `order.internal` vẫn là package nội bộ vì module `order` chưa công bố nó.

## 2. Một reference tới internal class tạo vi phạm như thế nào?

Giả sử `shipping` inject trực tiếp repository của `order`:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.internal.OrderRepository;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final OrderRepository orders;

    ShippingService(OrderRepository orders) {
        this.orders = orders;
    }
}
```

Code trên có thể biên dịch nếu `OrderRepository` là `public` và dependency Java đã có trên classpath. Nhưng module `shipping` đang tham chiếu type trong package nội bộ của module `order`.

Spring Modulith kiểm tra dependency giữa các module và từ chối việc module tiêu thụ truy cập type thuộc package nội bộ của module cung cấp. Vi phạm không phụ thuộc vào việc class được đánh dấu `public` hay package-private; điều quyết định là type nằm trong package nào và package đó có được công bố hay không.

Reference tới internal class có thể xuất hiện ở nhiều vị trí:

- Field hoặc constructor parameter của một Spring bean.
- Kiểu tham số hoặc kiểu trả về của method.
- Kiểu generic như `List<OrderEntity>` hoặc `Optional<InternalResult>`.
- Kiểu cha hoặc interface mà class ở module khác kế thừa hoặc triển khai.
- Annotation, record component hoặc chữ ký API công khai có nhắc tới type nội bộ.
- Import trực tiếp được dùng trong code nghiệp vụ hoặc test thuộc module khác.

Không chỉ lời gọi method mới tạo coupling. Chỉ cần một type nội bộ xuất hiện trong chữ ký mà module khác phụ thuộc, module đó đã biết đến chi tiết triển khai của module sở hữu type.

## 3. `ApplicationModules.verify()` phát hiện vi phạm

Tạo module model từ lớp Spring Boot application và chạy verification:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Trong quá trình kiểm tra, Spring Modulith xác định module nguồn, module đích và package chứa type được tham chiếu. Nếu module nguồn truy cập package nội bộ của một closed module, verification tạo architectural violation và test thất bại.

Có thể lấy tập vi phạm để xem hoặc xử lý trước khi quyết định ném exception:

```java
var violations = ApplicationModules.of(ShopApplication.class)
        .detectViolations();

violations.throwIfPresent();
```

Diagnostic thường cho biết module nào tạo reference và type/package nào đang bị truy cập. Khi đọc kết quả, hãy lần theo cả source type và target type để tìm đúng chữ ký hoặc import gây coupling.

`verify()` là kiểm tra kiến trúc trên module model. Nó không thay Java compiler và không ngăn compiler tạo bytecode cho reference đó. Vì vậy, “project biên dịch được” không chứng minh rằng module đang sử dụng API hợp lệ.

## 4. Phân biệt lỗi internal access với lỗi `allowedDependencies`

Hai quy tắc này độc lập và có thể cùng xuất hiện:

| Quy tắc | Câu hỏi được kiểm tra | Ví dụ vi phạm |
| --- | --- | --- |
| API package boundary | Module nguồn có truy cập type trong package nội bộ của module đích không? | `shipping` import `order.internal.OrderRepository` |
| `allowedDependencies` | Module nguồn có được phép phụ thuộc vào module đích không? | `shipping` gọi `order.OrderManagement` nhưng allowlist không có `order` |

Giả sử `shipping` khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order"
)
package com.acme.shop.shipping;
```

Khai báo này cho phép dependency tới API mặc định của module `order`. Nó không mở package `order.internal`. Nếu `ShippingService` vẫn import `OrderRepository`, verification tiếp tục báo vi phạm internal access.

Ngược lại, nếu `shipping` sử dụng đúng `OrderManagement` ở package gốc nhưng chưa được phép phụ thuộc `order`, lỗi nằm ở allowlist. Khi đó, cần quyết định quan hệ `shipping -> order` có đúng thiết kế không rồi mới cập nhật `allowedDependencies`.

## 5. Cách sửa ưu tiên: công bố một API theo nhu cầu nghiệp vụ

Nếu `shipping` cần truy vấn thông tin đơn hàng, module `order` nên công bố một hợp đồng mô tả đúng nhu cầu đó:

```java
package com.acme.shop.order;

import java.util.Optional;

public interface OrderLookup {

    Optional<OrderSummary> findSummary(OrderId id);
}
```

Implementation vẫn nằm trong package nội bộ:

```java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderLookup;
import com.acme.shop.order.OrderId;
import com.acme.shop.order.OrderSummary;
import org.springframework.stereotype.Service;

import java.util.Optional;

@Service
class OrderLookupService implements OrderLookup {

    private final OrderRepository orders;

    OrderLookupService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public Optional<OrderSummary> findSummary(OrderId id) {
        return orders.findById(id).map(OrderSummary::from);
    }
}
```

Module `shipping` chỉ phụ thuộc vào abstraction công khai:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.OrderLookup;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final OrderLookup orders;

    ShippingService(OrderLookup orders) {
        this.orders = orders;
    }
}
```

Kết quả là `order` vẫn sở hữu repository và cách truy vấn dữ liệu. `shipping` chỉ biết hợp đồng `OrderLookup` và DTO `OrderSummary` mà module `order` chủ động công bố. Module sở hữu có thể thay đổi JPA, query hoặc schema mà không buộc consumer biết chi tiết đó.

## 6. Khi nào nên dùng Named Interface?

Nếu module có nhiều nhóm API nằm trong package con, có thể công bố đúng package cần thiết bằng `@NamedInterface` thay vì chuyển tất cả type lên root package.

Ví dụ, module `order` có package tích hợp:

```text
order
├── OrderManagement.java
├── integration
│   ├── package-info.java
│   ├── OrderLookup.java
│   └── OrderSummary.java
└── internal
    └── OrderRepository.java
```

Đánh dấu package `integration`:

```java
@org.springframework.modulith.NamedInterface("integration")
package com.acme.shop.order.integration;
```

Module `shipping` chỉ cần phụ thuộc vào Named Interface này:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: integration"
)
package com.acme.shop.shipping;
```

Consumer được phép sử dụng type trong package `order.integration`, nhưng vẫn không được truy cập `order.internal`. Named Interface giúp thể hiện rõ một hợp đồng phụ chuyên biệt mà module cung cấp.

Không nên công bố một package chỉ vì một consumer đang import nhầm class nội bộ. Trước khi tạo Named Interface, hãy xác định type đó có thực sự là hợp đồng cần hỗ trợ lâu dài hay chỉ là chi tiết triển khai nên được thay bằng API nhỏ hơn.

## 7. Dùng application event nếu consumer chỉ cần phản ứng với sự kiện

Có trường hợp module khác không cần gọi repository hoặc truy vấn trực tiếp. Nó chỉ cần biết một sự thật nghiệp vụ đã xảy ra. Khi đó, module sở hữu có thể công bố event:

```java
package com.acme.shop.order.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
```

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Module `shipping` đăng ký listener cho event:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderEvents {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Chuẩn bị giao hàng bằng orderId.
    }
}
```

Với cách này, `shipping` phụ thuộc vào event contract `order :: events`, không phụ thuộc vào repository hoặc service nội bộ của `order`. Đây là lựa chọn phù hợp khi consumer cần phản ứng sau khi nghiệp vụ hoàn tất và không cần kết quả đồng bộ từ module phát event.

## 8. Những cách sửa không giải quyết đúng boundary

Một số thay đổi có thể làm code biên dịch hoặc verification bớt lỗi nhưng không cải thiện thiết kế:

| Cách làm | Vì sao chưa phù hợp |
| --- | --- |
| Đổi class internal thành `public` | Java cho phép truy cập, nhưng package vẫn là internal của closed module |
| Thêm module vào `allowedDependencies` | Allowlist không công bố package nội bộ |
| Đưa repository vào package gốc chỉ để import được | Repository có thể trở thành API công khai ngoài ý muốn |
| Đánh dấu module `OPEN` để mọi consumer truy cập internals | Mở rộng quyền truy cập toàn module và làm giảm encapsulation; đây không phải cách sửa mặc định cho một reference sai |
| Tạo Named Interface cho toàn bộ package nội bộ | Biến nhiều chi tiết triển khai thành hợp đồng công khai mà không có nhu cầu rõ ràng |

Nếu module được đánh dấu `Type.OPEN`, Spring Modulith cho phép truy cập các package con của module đó trong kiểm tra boundary. Điều này có thể hữu ích khi chuyển đổi một codebase legacy, nhưng làm giảm khả năng bảo vệ internal package. Hãy dùng nó có chủ đích và có kế hoạch đóng module lại.

## 9. Cách lần theo và xử lý một violation

Khi `verify()` báo module đang tham chiếu class internal, xử lý theo trình tự:

1. Xác định module nguồn và module đích trong diagnostic.
2. Tìm source type đang tham chiếu target type, kể cả reference trong constructor, field, generic hoặc method signature.
3. Xác nhận target type nằm trong package gốc, Named Interface hay package nội bộ của module đích.
4. Hỏi module nguồn thực sự cần thao tác nghiệp vụ, dữ liệu truy vấn hay chỉ cần nhận event.
5. Chọn API package gốc, Named Interface hoặc event contract phù hợp.
6. Nếu quan hệ module là chủ đích, khai báo `allowedDependencies` ở module tiêu thụ.
7. Chạy lại `ApplicationModules.verify()` và các test hành vi liên quan.

Nếu một class nội bộ được nhiều module khác sử dụng, đừng vội công bố nguyên class đó. Hãy tìm phần trách nhiệm mà các consumer thực sự cần và thiết kế một hợp đồng nhỏ hơn. Một API hẹp thường ổn định hơn một repository hoặc service implementation bị mở ra cho nhiều module.

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Class `public` luôn là public API của module. | Java visibility và module API boundary là hai khái niệm khác nhau. |
| Package con là một phần của package cha. | Java xem mỗi package là một namespace riêng; package-private không tự mở rộng sang package con. |
| Import internal class biên dịch được thì architecture hợp lệ. | `ApplicationModules.verify()` kiểm tra package boundary ở cấp module. |
| `allowedDependencies` cho phép truy cập mọi class của module đích. | Nó cho phép dependency đến module/interface đã chỉ định; package nội bộ vẫn được bảo vệ. |
| Chỉ method call mới tạo vi phạm. | Type trong field, constructor, generic, inheritance hoặc method signature cũng có thể tạo reference. |
| Mở module là cách sửa nhanh và an toàn. | `OPEN` nới lỏng internal boundary của cả module và nên được cân nhắc như một bước chuyển tiếp. |
| Named Interface chỉ là tên package. | Nó là hợp đồng được module công bố, cần có mục đích và consumer rõ ràng. |

## 11. Ghi nhớ

Reference tới class internal bị Spring Modulith báo vi phạm khi module nguồn tham chiếu type nằm trong package con chưa được công bố của một closed module. Class có thể là `public` và code vẫn biên dịch, nhưng điều đó không biến package nội bộ thành API của module.

Khi gặp lỗi, hãy xác định source type, target type và package sở hữu target. Thay reference tới repository hoặc service nội bộ bằng API nghiệp vụ ở package gốc, Named Interface hẹp hoặc event contract tùy nhu cầu. `allowedDependencies` chỉ kiểm soát module nào được phép sử dụng; nó không mở package nội bộ. Cuối cùng, chạy `ApplicationModules.verify()` để xác nhận boundary đã được khôi phục.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith Reference — Advanced Application Modules and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
