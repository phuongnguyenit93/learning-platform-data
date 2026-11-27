# Internal package và mục đích che giấu triển khai

Bài này thuộc chương **Application Module** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package của một ứng dụng Spring Boot. Một phần quan trọng của mô hình đó là phân biệt **giao diện mà module cung cấp** với **các package nội bộ chứa cách triển khai giao diện ấy**.

Internal package giúp một application module giữ quyền kiểm soát đối với chi tiết bên trong. Module khác chỉ cần biết hợp đồng công khai để sử dụng chức năng; chúng không cần biết module lưu dữ liệu thế nào, gọi hệ thống ngoài ra sao hoặc tổ chức các lớp hỗ trợ nào.

## 1. Internal package nằm ở đâu trong application module?

Giả sử ứng dụng bán hàng có package gốc là `com.acme.shop`. Bên dưới package gốc có module `order`:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderUseCases.java
│   ├── OrderDetails.java
│   └── internal
│       ├── DefaultOrderUseCases.java
│       ├── OrderRepository.java
│       ├── OrderEntity.java
│       └── OrderMapper.java
└── shipping
    └── ShippingPlanner.java
~~~

Trong mô hình mặc định của Spring Modulith:

- Package gốc của module, ở đây là `com.acme.shop.order`, tạo thành giao diện mặc định (unnamed interface) mà module khác có thể sử dụng.
- Các package con như `order.internal`, `order.persistence` hoặc `order.adapter` là phần nội bộ của module.
- Một package con chỉ trở thành giao diện công khai khi được khai báo rõ ràng, chẳng hạn bằng `@NamedInterface`.

Vì vậy, quy tắc không phụ thuộc vào việc package có tên chính xác là `internal` hay không. Tên `internal` là quy ước dễ đọc dành cho nhóm phát triển; Spring Modulith xem các package con là nội bộ theo cấu trúc module, trừ khi chúng được công khai có chủ đích.

Điều này khác với việc chỉ tạo một thư mục mang tên `internal`. Spring Modulith xây dựng mô hình từ package Java và các khai báo kiến trúc, nên package và package-info.java mới là những yếu tố liên quan.

## 2. Vì sao cần che giấu triển khai?

Giả sử module `order` cung cấp chức năng tra cứu đơn hàng. Module `shipping` cần biết mã đơn và trạng thái đơn để lập kế hoạch giao hàng. Nó không cần biết đơn hàng được lưu trong JPA entity nào hoặc truy vấn qua repository nào.

Nếu module `shipping` phụ thuộc trực tiếp vào `OrderEntity`, `OrderRepository` hoặc `OrderMapper`, chi tiết lưu trữ của đơn hàng đã trở thành một phần phụ thuộc của module giao hàng. Khi nhóm thay đổi cơ chế lưu trữ, đổi ORM hoặc tách một adapter, các module sử dụng chi tiết đó có thể phải sửa theo.

Che giấu triển khai tạo ra một ranh giới ổn định hơn:

- **Giảm liên kết:** module sử dụng phụ thuộc vào hợp đồng cần thiết, không phụ thuộc vào lớp triển khai.
- **Cho phép thay đổi nội bộ:** nhóm có thể thay repository, mapper, entity hoặc thuật toán mà không buộc module khác đổi theo, miễn hợp đồng công khai vẫn được giữ.
- **Bảo vệ mô hình nghiệp vụ:** module sở hữu dữ liệu và quy tắc của mình, hạn chế việc nơi khác thao tác trực tiếp vào cấu trúc nội bộ.
- **Làm rõ trách nhiệm:** người đọc có thể nhận ra đâu là chức năng module cung cấp và đâu là cách module thực hiện chức năng đó.
- **Giảm bề mặt phụ thuộc:** số kiểu mà module khác cần biết ít hơn, giúp kiến trúc dễ hiểu và dễ kiểm chứng.

Mục tiêu không phải giấu mọi lớp khỏi mọi người. Mục tiêu là để module sở hữu quyền thay đổi cách triển khai mà không làm lan truyền thay đổi qua toàn ứng dụng.

## 3. Thiết kế API ở package gốc, đặt triển khai trong package con

Một cách tổ chức phổ biến là đặt hợp đồng công khai ở package gốc của module, còn các lớp triển khai và truy cập dữ liệu ở package con.

Ví dụ, API của module đơn hàng:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public interface OrderUseCases {

    OrderDetails findById(UUID orderId);
}
~~~

Kiểu dữ liệu trả về cũng thuộc API công khai:

~~~java
package com.acme.shop.order;

import java.util.UUID;

public record OrderDetails(UUID id, String status) {
}
~~~

Phần triển khai nằm trong package `internal`:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.order.OrderDetails;
import com.acme.shop.order.OrderUseCases;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
class DefaultOrderUseCases implements OrderUseCases {

    private final OrderRepository repository;

    DefaultOrderUseCases(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public OrderDetails findById(UUID orderId) {
        OrderEntity entity = repository.findById(orderId);
        return new OrderDetails(entity.id(), entity.status());
    }
}
~~~

Các kiểu chỉ phục vụ triển khai có thể nằm cùng package nội bộ và dùng phạm vi truy cập package-private:

~~~java
package com.acme.shop.order.internal;

import java.util.UUID;

interface OrderRepository {

    OrderEntity findById(UUID orderId);
}

record OrderEntity(UUID id, String status) {
}
~~~

Ví dụ trên minh họa cách phân chia trách nhiệm; phần cài đặt repository thực tế có thể dùng Spring Data JPA, JDBC hoặc một adapter khác. Dù lựa chọn nào, module giao hàng vẫn chỉ cần biết `OrderUseCases` và `OrderDetails`.

Module `shipping` sử dụng hợp đồng công khai:

~~~java
package com.acme.shop.shipping;

import com.acme.shop.order.OrderDetails;
import com.acme.shop.order.OrderUseCases;

import java.util.UUID;

class ShippingPlanner {

    private final OrderUseCases orders;

    ShippingPlanner(OrderUseCases orders) {
        this.orders = orders;
    }

    OrderDetails orderForShipping(UUID orderId) {
        return orders.findById(orderId);
    }
}
~~~

Nhìn vào import của `ShippingPlanner`, ta thấy module giao hàng chỉ phụ thuộc vào API của module đơn hàng. Nó không cần import bất kỳ lớp nào trong `com.acme.shop.order.internal`.

## 4. Điều gì xảy ra khi module khác truy cập internal package?

Giả sử một lớp trong module giao hàng cố sử dụng trực tiếp repository của đơn hàng:

~~~java
import com.acme.shop.order.internal.OrderRepository;
~~~

Đây là dấu hiệu vi phạm ranh giới module. Module giao hàng đang phụ thuộc vào một chi tiết triển khai do module đơn hàng sở hữu.

Có hai lớp bảo vệ cần phân biệt:

1. **Ngôn ngữ Java:** nếu kiểu nội bộ có phạm vi package-private thì mã ở package khác không thể truy cập trực tiếp. Nếu kiểu được khai báo `public`, trình biên dịch Java có thể vẫn cho phép import.
2. **Quy tắc kiến trúc Spring Modulith:** dù kiểu nội bộ có thể truy cập ở mức Java, Spring Modulith vẫn mô hình hóa package con là nội bộ và có thể phát hiện module khác phụ thuộc vào package đó khi kiểm chứng kiến trúc.

Do đó, chỉ dùng modifier `public` hoặc `private` chưa đủ để mô tả toàn bộ ranh giới module. Java kiểm soát khả năng truy cập ở cấp ngôn ngữ; Spring Modulith kiểm tra quan hệ phụ thuộc ở cấp kiến trúc ứng dụng.

## 5. Kiểm chứng ranh giới internal package

Có thể tạo một bài kiểm tra kiến trúc để xác minh cấu trúc module:

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

Khi chạy, `verify()` kiểm tra mô hình application module, trong đó có những phụ thuộc vi phạm ranh giới nội bộ và các quy tắc phụ thuộc được khai báo. Nếu module `shipping` tham chiếu trực tiếp đến kiểu trong `order.internal`, kiểm tra kiến trúc có thể báo lỗi.

Nên đặt bài kiểm tra này trong bộ test chạy thường xuyên và trên CI. Nhờ vậy, một thay đổi vô tình tạo phụ thuộc vào internal package sẽ được phát hiện khi thay đổi được kiểm tra, thay vì chỉ xuất hiện thành vấn đề khi một nhóm khác refactor module.

Khi gặp lỗi, hãy xem lại nhu cầu thực sự của module sử dụng:

- Nếu nó cần một hành vi nghiệp vụ, hãy đưa hành vi đó ra hợp đồng công khai phù hợp.
- Nếu nó cần một dữ liệu kết quả, hãy cung cấp kiểu dữ liệu ổn định trong API của module.
- Nếu nhiều module cần một hợp đồng chuyên biệt, cân nhắc tạo named interface.
- Nếu phụ thuộc là không cần thiết, bỏ tham chiếu trực tiếp và để module sở hữu tự xử lý chi tiết của nó.

## 6. Khi nào nên công khai một package con?

Không phải mọi package con đều phải luôn bị đóng. Có trường hợp một module cần công khai một nhóm hợp đồng chuyên biệt mà không muốn đưa tất cả vào package gốc. Spring Modulith hỗ trợ named interface để thể hiện chủ đích đó.

Ví dụ, module đơn hàng cung cấp một hợp đồng tích hợp cho các module khác:

~~~java
@org.springframework.modulith.NamedInterface("integration")
package com.acme.shop.order.integration;
~~~

Các kiểu được đặt trong package `com.acme.shop.order.integration` giờ thuộc named interface có tên `integration`. Module khác có thể phụ thuộc vào giao diện này theo quy tắc được khai báo.

Ở phía module sử dụng, nếu muốn giới hạn các phụ thuộc được phép, có thể khai báo trên package gốc của module đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"order::integration"}
)
package com.acme.shop.shipping;
~~~

Cú pháp `order::integration` chỉ named interface `integration` của module `order`. Tên module và tên giao diện phải khớp với mô hình thực tế của ứng dụng.

Hãy công khai package con khi nó thực sự là một hợp đồng dành cho bên sử dụng, có ý nghĩa ổn định và có chủ sở hữu rõ ràng. Đừng đánh dấu một package là named interface chỉ để làm cho lỗi phụ thuộc biến mất. Việc công khai làm tăng bề mặt API mà module phải duy trì.

## 7. Internal package không phải ranh giới bảo mật hay tiến trình riêng

Cần hiểu đúng giới hạn của cơ chế này:

- Internal package là quy ước và ranh giới kiến trúc ở cấp package; nó không phải sandbox bảo mật.
- Spring Modulith không tự ngăn mọi truy cập bằng reflection hoặc mọi thao tác ở runtime.
- Các module vẫn có thể cùng chạy trong một tiến trình Spring Boot và dùng chung môi trường triển khai.
- `verify()` kiểm tra các quy tắc mà mô hình kiến trúc biểu diễn; nó không thay thế phân tích nghiệp vụ hay thiết kế API tốt.

Vì vậy, internal package giúp kiểm soát sự phụ thuộc trong mã nguồn và giữ quyền sở hữu triển khai cho module. Nếu hệ thống cần cách ly bảo mật hoặc triển khai độc lập, đó là yêu cầu kiến trúc khác cần được giải quyết bằng cơ chế phù hợp.

## Ghi nhớ

Trong Spring Modulith, package gốc của application module là giao diện mặc định; các package con là nội bộ trừ khi được công khai có chủ đích bằng named interface. Đặt repository, entity, mapper và lớp triển khai trong internal package giúp module giữ quyền kiểm soát chi tiết bên trong, còn module khác chỉ phụ thuộc vào hợp đồng ổn định.

Tên `internal` giúp người đọc nhận ra ý định, nhưng ranh giới thực tế đến từ mô hình package và việc kiểm chứng bằng `ApplicationModules.verify()`. Khi thiết kế một module, hãy tự hỏi: module khác thực sự cần gọi hành vi nào, cần nhận dữ liệu nào, và phần nào nên tiếp tục là chi tiết triển khai do module sở hữu?
