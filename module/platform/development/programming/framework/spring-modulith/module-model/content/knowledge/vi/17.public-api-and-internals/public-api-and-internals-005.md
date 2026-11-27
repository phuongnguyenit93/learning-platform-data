# Đưa interface ra API và giữ implementation bên trong

Một application module cần công bố đủ hợp đồng để module khác sử dụng, đồng thời giữ các chi tiết triển khai trong phạm vi sở hữu của chính nó. Với Spring Modulith, package gốc của module được xem là API mặc định; các package con được xem là nội bộ. Nếu cần công bố thêm một package, bạn có thể đánh dấu package đó bằng `@NamedInterface`.

Thiết kế này cho phép module khác phụ thuộc vào interface nghiệp vụ ổn định mà không phải biết service được triển khai ra sao, dữ liệu được lưu thế nào hoặc adapter nào đang được sử dụng. Bài học này hướng dẫn cách bố trí API và implementation, cách công bố named interface, cách giới hạn dependency và cách kiểm chứng boundary.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt API công khai với implementation nội bộ của application module.
- Tổ chức package để interface nằm ở API và implementation nằm trong package `internal`.
- Giải thích vai trò của Java visibility và kiểm tra kiến trúc Spring Modulith.
- Công bố một package bổ sung bằng `@NamedInterface`.
- Giới hạn dependency đến một named interface bằng `@ApplicationModule`.
- Tránh để API làm lộ repository, entity hoặc chi tiết hạ tầng của module.
- Dùng `ApplicationModules.verify()` để phát hiện module khác truy cập implementation nội bộ.

## API và implementation trong một application module

Một application module thường có ba phần:

- **API được cung cấp:** các Spring bean và application event mà module công bố cho module khác sử dụng.
- **Implementation nội bộ:** các thành phần triển khai không dành cho module khác truy cập.
- **API được yêu cầu:** các API hoặc event do module khác cung cấp mà module hiện tại sử dụng.

Ví dụ, module `orders` cung cấp chức năng tạo đơn hàng. Module khác cần biết cách yêu cầu tạo đơn và nhận kết quả, nhưng không cần biết `orders` dùng repository nào hay lưu trạng thái ra sao.

```text
com.acme
├── Application.java
├── orders
│   ├── OrderManagement.java          # API công khai
│   └── internal
│       ├── DefaultOrderManagement.java
│       └── OrderRepository.java
└── shipping
    └── ShippingService.java
```

Theo quy ước mặc định của Spring Modulith:

- `com.acme.orders` là package API của module `orders`.
- `com.acme.orders.internal` và các package con khác là nội bộ của module.
- Module `shipping` được phép phụ thuộc vào type thuộc package gốc `orders`.
- Module `shipping` không được phụ thuộc vào type thuộc `orders.internal`.

Quy tắc này được áp dụng trong quá trình xác minh mô hình module. Nó giúp nhóm duy trì ranh giới khi codebase lớn dần và nhiều người cùng phát triển.

## Đưa interface vào package API

Đặt interface mô tả khả năng nghiệp vụ mà module cung cấp trong package gốc. Ví dụ:

```java
package com.acme.orders;

import java.util.UUID;

public interface OrderManagement {

    UUID placeOrder(CreateOrderCommand command);
}
```

`CreateOrderCommand` là một kiểu dữ liệu công khai của hợp đồng, ví dụ:

```java
package com.acme.orders;

import java.util.UUID;

public record CreateOrderCommand(UUID customerId) {}
```

`OrderManagement` mô tả hành động mà bên gọi cần thực hiện. Nó không chứa logic lưu đơn hàng và không phụ thuộc vào implementation cụ thể.

Implementation nằm trong package nội bộ:

```java
package com.acme.orders.internal;

import java.util.UUID;

import com.acme.orders.CreateOrderCommand;
import com.acme.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
public class DefaultOrderManagement implements OrderManagement {

    private final OrderRepository repository;

    DefaultOrderManagement(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public UUID placeOrder(CreateOrderCommand command) {
        // Kiểm tra quy tắc nghiệp vụ và lưu đơn hàng.
        return repository.save(Order.create(command)).getId();
    }
}
```

Các type như `OrderRepository` và `Order` cũng có thể nằm trong package `internal`. Chúng phục vụ implementation của `orders`, không phải hợp đồng mà module khác cần biết.

Module `shipping` chỉ phụ thuộc vào interface:

```java
package com.acme.shipping;

import com.acme.orders.CreateOrderCommand;
import com.acme.orders.OrderManagement;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    private final OrderManagement orderManagement;

    ShippingService(OrderManagement orderManagement) {
        this.orderManagement = orderManagement;
    }

    void createOrder(CreateOrderCommand command) {
        orderManagement.placeOrder(command);
    }
}
```

Spring inject bean triển khai `OrderManagement` vào `ShippingService`. Bên gọi chỉ biết hợp đồng công khai; việc thay `DefaultOrderManagement` bằng một implementation khác không buộc `shipping` phải thay đổi, miễn là hợp đồng vẫn giữ tương thích.

Trong ví dụ, `CreateOrderCommand` cũng là một phần của hợp đồng. Mọi kiểu dữ liệu xuất hiện trong chữ ký API cần được xem xét như một phần của public contract. Nếu command chứa JPA entity hoặc type chỉ tồn tại trong `internal`, module sử dụng API sẽ bị kéo vào chi tiết triển khai. Hãy dùng DTO, command, query hoặc value object có ý nghĩa ổn định và thuộc phạm vi API.

## Package `internal` không phải rào chắn của Java compiler

Java phân biệt `public`, `protected`, package-private và `private`. Nhưng package con như `com.acme.orders.internal` là một package Java riêng so với `com.acme.orders`. Một class `public` trong package con có thể được code của package khác import về mặt ngôn ngữ.

Điều này thường cần thiết khi một implementation nội bộ phải được Spring hoặc một type khác trong module tham chiếu. Vì vậy, chỉ đặt tên package là `internal` chưa đủ để ngăn module khác sử dụng nó.

Spring Modulith bổ sung kiểm tra kiến trúc: type trong package con không được xem là API công khai mặc định. Nếu `shipping` import `com.acme.orders.internal.DefaultOrderManagement`, `ApplicationModules.verify()` sẽ báo vi phạm dependency vào implementation nội bộ.

Java visibility vẫn có giá trị. Dùng package-private hoặc `private` khi có thể để giảm khả năng truy cập ngay ở cấp ngôn ngữ. Nhưng với những type buộc phải `public`, hãy dựa vào quy tắc module và kiểm thử kiến trúc để giữ boundary.

Spring Modulith kiểm tra cấu trúc và dependency trong mô hình module; nó không thay thế hệ thống phân quyền runtime, không ngăn truy cập reflection và không tự động biến package thành Java module. Đừng coi `internal` như một cơ chế bảo mật.

## Khi cần công bố interface trong package con

Một module có thể cần công bố nhiều nhóm API, chẳng hạn API nghiệp vụ chính và một SPI dành cho extension. Thay vì đưa tất cả type vào package gốc, hãy tạo package riêng và đánh dấu nó bằng `@NamedInterface`.

Ví dụ cấu trúc:

```text
com.acme.orders
├── OrderManagement.java
├── spi
│   ├── package-info.java
│   └── OrderFulfillmentPolicy.java
└── internal
    ├── DefaultOrderManagement.java
    └── JpaOrderRepository.java
```

File `com.acme.orders.spi/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.orders.spi;
```

Interface được công bố trong package này:

```java
package com.acme.orders.spi;

public interface OrderFulfillmentPolicy {

    boolean canFulfill(OrderRequest request);
}
```

Khi package `spi` được đánh dấu là named interface, code thuộc module khác có thể tham chiếu các type trong package đó. Package `internal` vẫn được giữ kín theo quy tắc mặc định.

Named interface là một hợp đồng kiến trúc có tên, không phải một loại Java interface đặc biệt. `@NamedInterface` đánh dấu package hoặc type để Spring Modulith đưa các type tương ứng vào phần API được công bố. Tên `spi` giúp người đọc hiểu mục đích của nhóm API và cho phép module khác khai báo dependency chính xác.

## Giới hạn dependency đến đúng named interface

Module tiêu thụ có thể khai báo rõ những module và named interface được phép sử dụng bằng `@ApplicationModule`. Ví dụ, `shipping` chỉ cần SPI của `orders`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shipping;
```

Khi khai báo dependency cụ thể này, `shipping` được phép tham chiếu các type thuộc `orders::spi`. Nó không được tham chiếu `OrderManagement` ở package gốc hoặc type trong `orders.internal` theo cấu hình trên. Nếu module cần cả API gốc lẫn named interface `spi`, hãy khai báo cả hai dependency, ví dụ `allowedDependencies = { "orders", "orders :: spi" }`.

Spring Modulith cũng hỗ trợ ký hiệu:

- `orders :: *`: cho phép tất cả named interface được khai báo tường minh của `orders`, không bao gồm package gốc.
- `orders :: **`: cho phép package gốc và tất cả named interface được công bố của `orders`.

Chỉ dùng wildcard khi module thực sự cần toàn bộ bề mặt API đó. Khai báo dependency cụ thể giúp review dễ thấy module đang phụ thuộc vào hợp đồng nào và giảm nguy cơ vô tình sử dụng API mới mà không có quyết định kiến trúc.

Nếu một module không khai báo `allowedDependencies`, các package API được công bố mặc định có thể được tham chiếu theo quy tắc của Spring Modulith. Khi dự án muốn kiểm soát chặt hơn, hãy khai báo dependency rõ ràng và kiểm tra bằng `verify()`.

## Phân biệt API công khai với chi tiết triển khai

Một interface chỉ nên được công bố khi nó diễn tả khả năng mà module cam kết cung cấp. Không nên đưa toàn bộ class hiện có ra API chỉ vì module khác đang cần dùng chúng.

| Nên công bố | Nên giữ nội bộ |
|---|---|
| Interface mô tả use case hoặc capability | Service triển khai use case |
| Command, query, result và value object ổn định | JPA entity và repository |
| Event nghiệp vụ mà module khác cần lắng nghe | Event handler và listener implementation |
| SPI mà module cho phép module khác mở rộng | Adapter, client và cấu hình hạ tầng |
| Exception thuộc hợp đồng nghiệp vụ | Exception kỹ thuật của persistence hoặc HTTP client |

Ví dụ, `OrderManagement.placeOrder(CreateOrderCommand)` là hợp đồng có ý nghĩa nghiệp vụ. `JpaOrderRepository.save(OrderEntity)` là chi tiết lưu trữ. Nếu API nhận `OrderEntity` hoặc trả về một đối tượng repository, bên gọi sẽ bị ràng buộc với cách `orders` triển khai persistence.

Hãy kiểm tra cả chữ ký gián tiếp. Một API có thể không nhắc đến class nội bộ ở tên method nhưng vẫn làm lộ chúng qua generic type, superclass, annotation hoặc exception. Các type công khai nên nằm trong package API hoặc một named interface được công bố có chủ đích.

## Kiểm chứng boundary bằng Spring Modulith

Tạo bài kiểm thử kiến trúc để xác minh module arrangement:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

Kiểm thử này giúp phát hiện module khác truy cập type nội bộ, dependency không được cho phép và các vi phạm kiến trúc khác. Hãy chạy nó trong CI để thay đổi import hoặc package không vô tình mở rộng API.

Khi cần tìm hiểu mô hình mà Spring Modulith phát hiện, có thể in các module ra log trong test:

```java
var modules = ApplicationModules.of(Application.class);
modules.forEach(System.out::println);
```

Thông tin hiển thị giúp nhận biết module base package, Spring bean và visibility của các thành phần. Dùng nó để xác nhận `OrderManagement` được xem là API, còn `DefaultOrderManagement` và repository nằm trong phần nội bộ.

Kiểm thử kiến trúc cần sử dụng đúng application class và cấu hình detection của ứng dụng. Nếu module được mở bằng `@ApplicationModule(type = Type.OPEN)`, các type trong package con có thể được xem là có thể truy cập từ module khác. Cơ chế open chủ yếu hỗ trợ codebase cũ trong quá trình chuyển đổi; với module đã được thiết kế ranh giới rõ, hãy giữ mô hình đóng và công bố từng package cần thiết bằng named interface.

## Quy trình thiết kế API và internal

Khi tạo hoặc tái cấu trúc một module, hãy thực hiện theo trình tự:

1. Xác định capability mà module cung cấp và các use case module khác cần gọi.
2. Định nghĩa interface hoặc event thể hiện hợp đồng nghiệp vụ trong package gốc.
3. Đặt implementation, repository, adapter và cấu hình trong package con như `internal`, `persistence` hoặc `integration`.
4. Kiểm tra chữ ký API để tránh làm lộ entity, repository và type hạ tầng.
5. Nếu có nhóm API bổ sung, tạo package riêng và đánh dấu bằng `@NamedInterface` với tên diễn đạt đúng mục đích.
6. Ở module tiêu thụ, khai báo `allowedDependencies` đến đúng module hoặc named interface cần dùng khi dự án yêu cầu dependency tường minh.
7. Chạy `ApplicationModules.verify()` và xem lại module arrangement trong CI.
8. Khi thay đổi API, đánh giá tác động tương thích với các module đang sử dụng hợp đồng đó.

## Những lỗi thường gặp

| Lỗi thiết kế | Hậu quả | Cách xử lý |
|---|---|---|
| Đưa repository hoặc entity ra package gốc | Module khác bị ràng buộc với persistence | Công bố interface nghiệp vụ và DTO ổn định |
| Để implementation trong package gốc | Implementation vô tình trở thành một phần API mặc định | Chuyển implementation vào package con |
| Cho module khác import class `internal` vì class đó `public` | Dependency vượt qua ranh giới kiến trúc | Chỉ dùng API được công bố và bật `verify()` trong CI |
| Tạo `spi` nhưng quên `@NamedInterface` | Package con vẫn bị xem là nội bộ | Đánh dấu package bằng `package-info.java` |
| Khai báo `orders :: **` dù chỉ cần một SPI | Module tiêu thụ được phép dùng nhiều API hơn nhu cầu | Khai báo `orders :: spi` hoặc dependency cụ thể |
| API trả về type nội bộ | Implementation bị lộ gián tiếp qua chữ ký | Chuyển type kết quả vào API hoặc named interface |
| Mở module bằng `Type.OPEN` để bỏ qua lỗi truy cập | Các package con có thể trở nên truy cập được rộng rãi | Công bố đúng package cần thiết bằng named interface |

## Bài tập tự đánh giá

Module `billing` cung cấp chức năng tính hóa đơn. Hiện tại, module `orders` đang import `billing.internal.JpaInvoiceRepository` để truy vấn hóa đơn và `billing.internal.InvoiceEntity` để hiển thị dữ liệu. Nhóm muốn chuyển sang API rõ ràng nhưng vẫn cần hỗ trợ một module báo cáo mở rộng cách tính phí.

Hãy thiết kế lại:

1. Interface nào nên nằm trong package gốc `billing` để `orders` yêu cầu tính hóa đơn?
2. Những type nào nên ở `billing.internal`?
3. Nếu module báo cáo cần cung cấp một chiến lược tính phí cho `billing`, package nào nên chứa SPI và cần annotation gì?
4. `billing` và `reporting` cần phụ thuộc vào named interface nào để không phải import implementation của nhau?
5. Bạn sẽ viết `allowedDependencies` thế nào để chỉ cho phép module cần dùng đúng hợp đồng?
6. Kiểm thử nào sẽ phát hiện nếu `orders` tiếp tục import `JpaInvoiceRepository`?

Một hướng thiết kế là công bố `InvoiceManagement` trong package gốc `billing`, giữ `JpaInvoiceRepository` và `InvoiceEntity` trong `billing.internal`, rồi tạo package `billing.spi` với `@NamedInterface("spi")` nếu module cần một extension point. API và SPI cần sử dụng command, result hoặc value object ổn định. Sau khi cấu hình dependency, `ApplicationModules.verify()` phải phát hiện mọi tham chiếu từ `orders` đến repository nội bộ.

## Kết luận

API công khai xác định những gì module cam kết cung cấp; package nội bộ chứa cách module thực hiện cam kết đó. Đặt interface và hợp đồng ổn định ở package gốc hoặc named interface, giữ service triển khai và chi tiết hạ tầng trong package con, rồi dùng `ApplicationModules.verify()` để kiểm soát dependency. Ranh giới rõ ràng giúp module có thể thay đổi implementation mà không buộc các module tiêu thụ thay đổi theo.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals: Simple and Advanced Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.named-interfaces)
- [Spring Modulith API — `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
