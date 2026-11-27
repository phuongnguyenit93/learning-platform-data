# Event type ở API package

Trong modular monolith, một module có thể phát sự kiện để thông báo rằng một việc nghiệp vụ đã xảy ra. Module khác đăng ký lắng nghe sự kiện và tự thực hiện phần việc của mình. Cách giao tiếp này giảm sự phụ thuộc gọi trực tiếp giữa các module, nhưng kiểu dữ liệu của sự kiện vẫn là một phần hợp đồng mà bên phát và bên nhận cùng sử dụng.

Với Spring Modulith, nếu sự kiện được tiêu thụ từ module khác, kiểu event phải nằm trong API mà module phát công khai. Ta có thể đặt event trong package gốc của module hoặc trong một named interface được đánh dấu bằng `@NamedInterface`. Đặt event trong package `internal` sẽ tạo phụ thuộc vào chi tiết nội bộ và vi phạm ranh giới module khi module khác tham chiếu kiểu đó.

## 1. Vì sao event type thuộc API của module phát?

Giả sử module `orders` phát thông báo khi đơn hàng hoàn tất. Module `billing` cần nhận thông tin để tạo hóa đơn, còn module `notifications` cần gửi email xác nhận.

```text
com.example
├── orders
│   ├── api
│   │   └── OrderCompleted.java
│   └── internal
│       └── OrderService.java
├── billing
│   └── BillingEventHandler.java
└── notifications
    └── NotificationEventHandler.java
```

Event `OrderCompleted` là hợp đồng do `orders` sở hữu. Module tiêu thụ chỉ cần biết những dữ liệu mà hợp đồng công bố, ví dụ mã đơn hàng, tổng tiền và thời điểm hoàn tất. Chúng không cần biết `OrderService` lưu đơn hàng thế nào, entity được ánh xạ ra sao hoặc transaction nội bộ được tổ chức như thế nào.

Vì vậy, hãy đặt kiểu event trong API package của module phát. Điều này giúp Spring Modulith nhận diện phụ thuộc vào một giao diện được công khai và cho phép kiểm tra kiến trúc bằng `ApplicationModules.verify()`.

## 2. Công khai event bằng named interface

Một cách tổ chức rõ ràng là tạo package `api` trong module `orders` và đánh dấu nó là named interface. Tạo file `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.example.orders.api;
```

Khai báo event trong cùng package:

```java
package com.example.orders.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderCompleted(
        UUID orderId,
        BigDecimal total,
        Instant completedAt
) {}
```

`OrderCompleted` là một Java record nên các thành phần dữ liệu được công khai qua accessor và không thể gán lại sau khi khởi tạo. Đây là dạng phù hợp cho event mang dữ liệu bất biến. Tính bất biến của record chỉ áp dụng trực tiếp cho các tham chiếu thành phần; nếu event chứa collection hoặc object có thể thay đổi, cần tạo bản sao bất biến hoặc chỉ đưa dữ liệu giá trị cần thiết vào event.

Named interface `api` công khai event cho module khác. Những kiểu như `OrderEntity`, repository hoặc service triển khai vẫn có thể nằm trong package nội bộ và không cần xuất hiện trong hợp đồng này.

## 3. Phát event từ module sở hữu

Module `orders` dùng `ApplicationEventPublisher` để phát event sau khi hoàn tất thao tác nghiệp vụ:

```java
package com.example.orders.internal;

import com.example.orders.api.OrderCompleted;
import java.time.Instant;
import java.util.UUID;
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
    public void completeOrder(UUID orderId) {
        // Kiểm tra và cập nhật trạng thái đơn hàng trong module orders.

        events.publishEvent(new OrderCompleted(
                orderId,
                new java.math.BigDecimal("125.00"),
                Instant.now()
        ));
    }
}
```

Đoạn mã dùng tổng tiền minh họa để tập trung vào cấu trúc event. Trong ứng dụng thực tế, module `orders` lấy tổng tiền từ kết quả nghiệp vụ đã được tính toán và chỉ phát event sau khi các điều kiện hoàn tất đơn hàng được đáp ứng.

Event được tạo và phát bởi module sở hữu hợp đồng. Module khác không nên tự tạo `OrderCompleted` để yêu cầu module `orders` thực hiện một thao tác; event mô tả điều đã xảy ra. Nếu cần yêu cầu xử lý và nhận kết quả, hãy dùng API đồng bộ phù hợp.

## 4. Lắng nghe event từ module khác

Module `billing` import event từ named interface `orders::api` và đăng ký listener:

```java
package com.example.billing;

import com.example.orders.api.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class BillingEventHandler {

    @ApplicationModuleListener
    public void on(OrderCompleted event) {
        // Tạo yêu cầu lập hóa đơn dựa trên dữ liệu event.
    }
}
```

`@ApplicationModuleListener` là listener dành cho giao tiếp giữa các application module. Theo cấu hình mặc định, annotation kết hợp xử lý bất đồng bộ với `@TransactionalEventListener` ở pha `AFTER_COMMIT` và một transaction mới cho listener. Vì vậy, event được xử lý sau khi transaction phát event commit thành công; listener không chạy đồng bộ trong cùng luồng với nơi phát event. Nếu phát event ngoài transaction, transactional listener mặc định không được gọi trừ khi cấu hình fallback phù hợp.

Nếu cần xử lý thông báo, module `notifications` có thể đăng ký một listener khác nhận cùng kiểu `OrderCompleted`. Module phát không cần biết có bao nhiêu listener đang đăng ký.

## 5. Giới hạn phụ thuộc vào named interface

Trong `package-info.java` của module `billing`, khai báo chỉ cho phép phụ thuộc vào named interface `api` của `orders`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::api"
)
package com.example.billing;
```

Giá trị `orders::api` xác định rõ module đích và named interface được phép sử dụng. Khi đó `BillingEventHandler` có thể tham chiếu `OrderCompleted` vì kiểu này nằm trong API đã công khai.

Nếu `OrderCompleted` được chuyển vào `com.example.orders.internal`, `billing` sẽ tham chiếu một kiểu nội bộ. Spring Modulith có thể phát hiện vi phạm khi kiểm tra cấu trúc module, dù lớp Java có thể biên dịch nếu kiểu được khai báo `public` và Spring có thể khởi tạo listener.

Nếu không cần named interface riêng, có thể đặt event trực tiếp trong package gốc `com.example.orders`. Package gốc là API công khai mặc định của module. Khi đó module tiêu thụ có thể khai báo `allowedDependencies = "orders"` nếu muốn giới hạn phụ thuộc theo module thay vì theo named interface.

## 6. Chọn dữ liệu phù hợp cho event contract

Event công khai là hợp đồng có thể được nhiều module sử dụng và có thể tồn tại lâu hơn một lần triển khai. Thiết kế event nên ổn định, mô tả sự kiện nghiệp vụ và chỉ mang dữ liệu cần thiết cho bên nhận.

- Ưu tiên mã định danh, giá trị, thời điểm và dữ liệu mô tả sự kiện. Bên nhận có thể dùng ID để truy vấn thêm thông tin qua API phù hợp nếu cần.
- Tránh công khai JPA entity, Hibernate proxy, repository hoặc service nội bộ. Những kiểu này làm hợp đồng phụ thuộc vào cách triển khai và vòng đời persistence.
- Không đưa object mutable dùng chung giữa các module vào event. Dùng record với kiểu dữ liệu giá trị, hoặc sao chép collection thành dạng bất biến.
- Đặt tên event theo sự kiện đã xảy ra, ví dụ `OrderCompleted`, `PaymentReceived` hoặc `ShipmentDispatched`.
- Khi thay đổi cấu trúc event, xem xét các listener hiện có. Thêm field có thể có giá trị mặc định hoặc cách tương thích rõ ràng; đổi tên hay xóa field có thể làm hỏng consumer.

Ví dụ, event chỉ chứa `orderId` có thể phù hợp nếu consumer có quyền gọi một API công khai để lấy chi tiết đơn hàng. Nếu consumer cần tổng tiền đúng tại thời điểm hoàn tất, đưa `total` vào event giúp giữ lại sự kiện tại thời điểm đó mà không phụ thuộc vào trạng thái đơn hàng có thể thay đổi sau này.

## 7. Kiểm chứng ranh giới module

Tạo bài test kiến trúc để xác nhận event type được sử dụng thông qua API công khai:

```java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void applicationModulesRespectTheirBoundaries() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Kiểm tra này phân tích các phụ thuộc giữa module, bao gồm tham chiếu kiểu `OrderCompleted` trong listener. Nếu event được đặt trong package nội bộ hoặc module `billing` tham chiếu một named interface không được cho phép, kiểm tra sẽ báo vi phạm tương ứng.

Khi thiết kế event contract, hãy kiểm tra cả hai phía: module phát sở hữu và công khai kiểu event; module nhận chỉ tham chiếu phần API được phép. Việc đăng ký listener thành công ở ApplicationContext không thay thế kiểm tra kiến trúc này.

## 8. Bài tập thực hành

1. Tạo module `orders` và package `orders.api`.
2. Đánh dấu `orders.api` bằng `@NamedInterface("api")` và khai báo record `OrderCompleted`.
3. Phát event bằng `ApplicationEventPublisher` sau khi thao tác hoàn tất đơn hàng thành công.
4. Tạo listener trong module `billing` bằng `@ApplicationModuleListener`.
5. Giới hạn `billing` chỉ phụ thuộc vào `orders::api` bằng `allowedDependencies`.
6. Chạy `ApplicationModules.of(Application.class).verify()` để kiểm tra kiến trúc.
7. Thử chuyển `OrderCompleted` vào package `orders.internal`, quan sát vi phạm và đưa event trở lại API package.

Sau bài tập, bạn cần giải thích được vì sao event type là một phần API của module phát, vì sao consumer phải phụ thuộc vào named interface hoặc package gốc được công khai, và vì sao không nên đưa entity hay service nội bộ vào event contract.

## Tài liệu tham khảo

- [Application Modules – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Events – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/events.html)
- [NamedInterface API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)
