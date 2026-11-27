# API package và cách module khác được phép truy cập

Trong Spring Modulith, mỗi Application Module có một phần giao diện công khai (API) để module khác sử dụng và một phần triển khai nội bộ để giữ kín chi tiết nghiệp vụ. Quy tắc mặc định dựa trên package: **package gốc của module là API package; các subpackage là nội bộ**. Khi cần công khai thêm một nhóm kiểu dữ liệu ở subpackage, ta khai báo Named Interface bằng **@NamedInterface**.

Bài học này giải thích cách xác định API package, cách module tiêu thụ API của module khác, cách giới hạn phụ thuộc bằng **allowedDependencies** và cách kiểm chứng các ranh giới đó.

## 1. API package mặc định của một module

Theo cấu trúc mặc định, Spring Modulith lấy package chứa lớp ứng dụng Spring Boot làm package gốc. Mỗi package con trực tiếp của package gốc được xem là một Application Module.

Ví dụ, ứng dụng có package gốc **com.acme.shop** và hai module **orders**, **inventory**:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── CreateOrder.java
│   ├── OrderId.java
│   └── internal
│       └── JpaOrderRepository.java
└── inventory
    └── InventoryReservationService.java
~~~

Trong cấu trúc này:

- **com.acme.shop.orders** là package gốc (base package) của module **orders**. Các kiểu public đặt trực tiếp trong package này tạo nên API mặc định của module.
- **com.acme.shop.orders.internal** là subpackage. Spring Modulith xem đây là phần triển khai nội bộ của **orders**.
- **com.acme.shop.inventory** là package gốc của module **inventory**.

Nếu module có subpackage, chỉ package gốc được mở cho module khác theo mặc định. Việc đặt một lớp vào subpackage không làm lớp đó trở thành API, kể cả khi lớp được khai báo **public**.

| Vị trí | Vai trò mặc định | Module khác được tham chiếu? |
|---|---|---|
| **orders** | API package | Có, với các kiểu có thể truy cập theo Java |
| **orders.internal** | Triển khai nội bộ | Không |
| **orders.persistence** | Triển khai nội bộ | Không |
| **orders.spi** | Nội bộ cho đến khi được khai báo Named Interface | Không |

### Vì sao từ khóa public chưa đủ?

Java kiểm soát khả năng truy cập ở cấp ngôn ngữ. Một lớp **public** trong **orders.internal** có thể được mã nguồn của **inventory** import và biên dịch thành công. Nhưng điều đó không có nghĩa lớp ấy thuộc API của module **orders**.

Spring Modulith áp dụng thêm quy tắc kiến trúc: module khác chỉ được tham chiếu package API đã công bố. Vì vậy, một tham chiếu đến **orders.internal.JpaOrderRepository** có thể qua được bước biên dịch Java nhưng sẽ bị phát hiện khi chạy kiểm chứng cấu trúc module.

Điều này cho phép module giữ các lớp public để những package bên trong cùng module sử dụng, đồng thời vẫn bảo vệ chúng khỏi phụ thuộc từ module khác.

## 2. Module khác sử dụng API như thế nào?

Module tiêu thụ API bằng cách tham chiếu các kiểu được công bố trong package gốc của module cung cấp. Với Spring bean, cách sử dụng thường là constructor injection.

Ví dụ, module **orders** công bố hợp đồng nghiệp vụ:

~~~java
package com.acme.shop.orders;

public interface OrderManagement {

    OrderId placeOrder(CreateOrder command);
}
~~~

Các kiểu **OrderId** và **CreateOrder** cũng nằm trong package **com.acme.shop.orders** và được công bố như một phần của hợp đồng. Mỗi kiểu public được đặt trong file Java riêng:

~~~java
package com.acme.shop.orders;

public record OrderId(String value) {}
~~~

~~~java
package com.acme.shop.orders;

public record CreateOrder(String customerId) {}
~~~

Module **orders** có thể đặt lớp triển khai trong subpackage nội bộ:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderManagement;
import com.acme.shop.orders.OrderId;
import com.acme.shop.orders.CreateOrder;
import org.springframework.stereotype.Service;

@Service
public class DefaultOrderManagement implements OrderManagement {

    @Override
    public OrderId placeOrder(CreateOrder command) {
        // Ví dụ rút gọn: ứng dụng thực tế thực hiện nghiệp vụ và lưu đơn hàng.
        return new OrderId("demo");
    }
}
~~~

Module **inventory** chỉ cần biết hợp đồng **OrderManagement**:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {

    private final OrderManagement orderManagement;

    public InventoryReservationService(OrderManagement orderManagement) {
        this.orderManagement = orderManagement;
    }
}
~~~

Spring Dependency Injection tìm bean triển khai **OrderManagement** khi khởi tạo **InventoryReservationService**. Module **inventory** không cần biết **DefaultOrderManagement** được đặt ở đâu, dùng repository nào hoặc lưu dữ liệu ra sao. Các chi tiết đó thuộc quyền sở hữu của **orders**.

Một Application Module cũng có thể công bố application event như một phần giao diện được cung cấp. Khi module khác chỉ cần phản ứng với một sự kiện nghiệp vụ, module phát sự kiện có thể công bố kiểu event trong package API; module nhận đăng ký listener theo kiểu event đó. Cách này giúp giảm phụ thuộc trực tiếp vào service của module phát sự kiện. Kiểu event dùng liên module vẫn phải nằm trong package được công bố.

## 3. Công khai thêm package bằng Named Interface

Đôi khi package gốc không đủ để tổ chức các hợp đồng công khai. Ví dụ, module **orders** muốn cung cấp một nhóm kiểu dành cho tích hợp mà không đưa chúng vào package gốc. Ta có thể đánh dấu subpackage đó bằng **@NamedInterface**.

Tạo file **package-info.java** trong **com.acme.shop.orders.spi**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Sau khai báo này, **com.acme.shop.orders.spi** trở thành một Named Interface có tên **spi**. Các kiểu trong package đó có thể được module khác tham chiếu theo hợp đồng đã công bố.

Ví dụ, module **orders** đặt một kiểu đọc trạng thái đơn hàng trong package này:

~~~java
package com.acme.shop.orders.spi;

import java.util.UUID;

public record OrderStatusView(UUID orderId, String status) {}
~~~

Module **inventory** có thể import **OrderStatusView** nếu phụ thuộc của nó cho phép Named Interface **spi**:

~~~java
import com.acme.shop.orders.spi.OrderStatusView;
~~~

Named Interface vẫn thuộc module **orders**; nó không tạo ra một Application Module mới. Nó chỉ công bố thêm một vùng API có tên, giúp phân biệt các hợp đồng mà module cung cấp. Có thể dùng các tên như **spi**, **integration** hoặc **events** tùy ý nghĩa của hợp đồng.

Với Java, khai báo thường được đặt trong **package-info.java** của package cần công bố. Kotlin không có **package-info.java**; Spring Modulith hỗ trợ cách khai báo tương ứng bằng **@PackageInfo** và một lớp metadata trong package.

## 4. Giới hạn module được phép phụ thuộc bằng allowedDependencies

Mặc định, một module có thể tham chiếu các API đã công bố của những module khác. Nếu muốn khai báo rõ module nào được phép phụ thuộc, hãy đặt **@ApplicationModule(allowedDependencies = ...)** trên package gốc của **module tiêu thụ**.

Ví dụ, **inventory** chỉ được phép dùng API mặc định của **orders**. Tạo hoặc cập nhật **package-info.java** trong **com.acme.shop.inventory**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.inventory;
~~~

Tên **orders** là logical name mặc định của module có base package **com.acme.shop.orders**. Với cấu hình này, **inventory** được phép tham chiếu package API gốc của **orders**; nó không được tự ý truy cập các package nội bộ hoặc Named Interface chưa được cho phép.

Khi chỉ muốn cho phép một Named Interface, dùng cú pháp **module :: interface**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.inventory;
~~~

Các dạng khai báo thường gặp:

| Giá trị | Phạm vi được phép |
|---|---|
| **"orders"** | API package gốc của **orders** |
| **"orders :: spi"** | Named Interface có tên **spi** của **orders** |
| **"orders :: &#42;"** | Tất cả Named Interface đã khai báo của **orders**, không bao gồm API package gốc |
| **"orders :: &#42;&#42;"** | API package gốc và tất cả Named Interface đã khai báo của **orders** |
| **{ "orders", "orders :: spi" }** | API package gốc và riêng Named Interface **spi** |

Nếu module cần cả API mặc định lẫn Named Interface **spi**, có thể khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "orders :: spi" }
)
package com.acme.shop.inventory;
~~~

Điểm quan trọng là **allowedDependencies** mô tả quyền phụ thuộc của module tiêu thụ. Khai báo này không làm package nội bộ của module cung cấp trở thành API. Nó chỉ chọn những module và giao diện công khai mà module tiêu thụ được phép dùng.

## 5. Kiểm chứng ranh giới bằng ApplicationModules.verify()

Các quy tắc package giúp mô tả ý định, còn kiểm chứng kiến trúc giúp phát hiện khi mã nguồn đi lệch khỏi ý định đó. Spring Modulith cung cấp **ApplicationModules** để phân tích cấu trúc ứng dụng và **verify()** để kiểm tra các ràng buộc.

Có thể tạo một bài kiểm thử kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Khi chạy bài kiểm thử, Spring Modulith kiểm tra các vấn đề chính:

1. Không có chu trình phụ thuộc giữa các Application Module.
2. Module không tham chiếu kiểu thuộc package nội bộ của module khác.
3. Nếu module khai báo **allowedDependencies**, các phụ thuộc thực tế phải nằm trong danh sách được cho phép.

Nếu phát hiện vi phạm, **verify()** ném exception để bài kiểm thử thất bại. Nhờ đó, quy tắc kiến trúc trở thành một phần của vòng đời kiểm thử và có thể được chạy tự động trong CI.

## 6. Những lỗi thiết kế thường gặp

**Đặt API trong subpackage nhưng quên khai báo Named Interface.** Một kiểu như **orders.api.OrderManagement** vẫn thuộc package nội bộ theo mặc định. Hãy thêm **@NamedInterface** vào package đó hoặc chuyển hợp đồng về package gốc nếu nó là API chính của module.

**Cho module khác gọi thẳng repository hoặc lớp triển khai.** Việc import một lớp public từ **orders.internal** tạo phụ thuộc vào chi tiết triển khai. Hãy công bố một hợp đồng nghiệp vụ trong API package và để module sở hữu tự thực hiện hợp đồng đó.

**Chỉ khai báo allowedDependencies ở module cung cấp.** Danh sách này cần đặt ở module tiêu thụ vì nó mô tả module đó được phép phụ thuộc vào đâu.

**Dùng Named Interface cho mọi package.** Mỗi Named Interface làm tăng bề mặt API mà module phải duy trì. Chỉ công bố những hợp đồng thực sự cần dùng từ bên ngoài; các package còn lại nên tiếp tục là nội bộ.

**Mở toàn bộ module để bỏ qua vi phạm.** Spring Modulith có hỗ trợ Open Application Module, thường hữu ích khi chuyển đổi một hệ thống cũ. Tuy nhiên, cách này cho phép truy cập rộng vào các kiểu nội bộ và làm yếu ranh giới module. Với module mới hoặc đã được phân chia rõ ràng, nên ưu tiên API package và Named Interface tường minh.

## 7. Quy trình áp dụng

Khi một module cần sử dụng chức năng của module khác, hãy đi theo các bước sau:

1. Xác định module sở hữu nghiệp vụ và package gốc của module đó.
2. Kiểm tra hợp đồng cần dùng đã nằm trong API package hay chưa.
3. Nếu hợp đồng thuộc một subpackage, quyết định có cần công khai nó bằng **@NamedInterface** hay nên chuyển hợp đồng về API package.
4. Khai báo **allowedDependencies** trong package gốc của module tiêu thụ nếu dự án đang quản lý phụ thuộc tường minh.
5. Chạy **ApplicationModules.of(ShopApplication.class).verify()** để xác nhận không có tham chiếu nội bộ, phụ thuộc ngoài danh sách hoặc chu trình module.

Ranh giới tốt giúp module cung cấp tự thay đổi cách triển khai mà không buộc module tiêu thụ thay đổi theo. API package và Named Interface chính là phần hợp đồng mà module cam kết duy trì; các package còn lại là không gian để module tự do tổ chức mã nguồn.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): Application Modules, API package, Named Interfaces và **allowedDependencies**.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc và cách chạy kiểm chứng bằng **ApplicationModules.verify()**.
