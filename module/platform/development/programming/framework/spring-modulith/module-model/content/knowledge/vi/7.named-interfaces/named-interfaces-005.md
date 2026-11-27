# Cho phép module khác truy cập package được expose

Theo quy ước mặc định của Spring Modulith, package gốc của một application module là API package mà module khác được phép tham chiếu. Các package con như `internal`, `spi` hoặc `reporting` được xem là nội bộ, trừ khi module chủ động công bố chúng. Khi cần chia sẻ một package con với module khác, bạn có thể đánh dấu package đó bằng `@NamedInterface` để tạo một **named interface**.

Named interface giúp module công bố thêm một phần API có tên và mục đích rõ ràng. Module sử dụng có thể khai báo dependency tới đúng named interface đó bằng cú pháp `module::named-interface` trong `allowedDependencies`. Nhờ vậy, nhóm phát triển kiểm soát được package nào được phép truy cập và tránh mở toàn bộ phần triển khai bên trong module.

Trong `SPRING_MODULITH_MODULE_MODEL`, named interface là cơ chế quan trọng để xác định API công khai và quản lý phụ thuộc giữa các package. Bài học này tập trung vào cách expose một package, cách module khác khai báo quyền sử dụng và cách kiểm chứng ranh giới đó.

## 1. Vì sao cần expose một package?

Giả sử module `order` có cấu trúc:

```text
com.example.shop.order
├── OrderManagement.java
├── spi
│   ├── OrderLookup.java
│   └── package-info.java
└── internal
    ├── OrderManagementImpl.java
    └── OrderRepository.java
```

Theo quy ước mặc định:

- `com.example.shop.order` là package API gốc. Module khác có thể tham chiếu `OrderManagement`.
- `com.example.shop.order.internal` là package nội bộ. Module khác không được tham chiếu `OrderManagementImpl` hoặc `OrderRepository`.
- `com.example.shop.order.spi` cũng là package nội bộ cho đến khi được công bố tường minh.

Giả sử module `billing` cần sử dụng `OrderLookup` trong `order.spi`. Nếu chỉ import lớp này mà không công bố package, Spring Modulith sẽ xem đó là truy cập package nội bộ và báo vi phạm khi kiểm tra kiến trúc.

Named interface giải quyết trường hợp này bằng cách công bố `order.spi` như một hợp đồng có tên, ví dụ `spi`. Module `billing` có thể dùng hợp đồng đó mà không cần truy cập `order.internal`.

## 2. Đánh dấu package bằng `@NamedInterface`

Để expose package `com.example.shop.order.spi`, tạo hoặc cập nhật file `package-info.java` ngay trong package đó:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.order.spi;
```

Annotation gắn tên `spi` cho package. Các kiểu nằm trong package được đánh dấu sẽ thuộc named interface `spi` của module `order`.

Ví dụ, hợp đồng được công bố:

```java
package com.example.shop.order.spi;

public interface OrderLookup {

    boolean exists(String orderId);
}
```

Các module khác có thể tham chiếu `OrderLookup` vì package `order.spi` đã được expose. Tên `spi` mô tả vai trò của nhóm hợp đồng: Service Provider Interface, tức giao diện dành cho tích hợp hoặc mở rộng.

Bạn có thể chọn tên khác tùy mục đích, chẳng hạn `reporting`, `integration` hoặc `events`. Tên nên thể hiện rõ nhóm API mà package cung cấp. Mỗi package cần expose phải được đánh dấu có chủ đích; chỉ đặt tên folder là `api` hoặc `spi` không tự làm package trở thành public interface.

## 3. Khai báo dependency từ module sử dụng

Sau khi `order.spi` được expose, module `billing` có thể khai báo dependency tới named interface đó trong `package-info.java` của module:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::spi"
)
package com.example.shop.billing;
```

Cú pháp `order::spi` gồm hai phần:

- `order`: logical name của application module cung cấp.
- `spi`: tên named interface được công bố bên trong module đó.

Khi khai báo như trên, mã trong module `billing` được phép tham chiếu các kiểu thuộc `order.spi`. Ví dụ:

```java
package com.example.shop.billing.internal;

import com.example.shop.order.spi.OrderLookup;
import org.springframework.stereotype.Service;

@Service
class BillingService {

    private final OrderLookup orderLookup;

    BillingService(OrderLookup orderLookup) {
        this.orderLookup = orderLookup;
    }

    boolean canCreateInvoice(String orderId) {
        return orderLookup.exists(orderId);
    }
}
```

`billing` phụ thuộc vào hợp đồng `OrderLookup`, không phụ thuộc vào repository hoặc lớp triển khai nội bộ của `order`. Module `order` có thể thay đổi cách tìm đơn hàng mà không buộc `billing` biết chi tiết lưu trữ.

`@NamedInterface` chỉ công bố package trong mô hình module. Annotation này không tự tạo Spring bean, không cấu hình component scan và không tự inject implementation. Nếu kiểu được công bố là Spring bean, module sở hữu nó vẫn phải đăng ký bean bằng stereotype hoặc `@Bean` như bình thường.

## 4. Hiểu rõ phạm vi của `allowedDependencies`

Khi một module khai báo `allowedDependencies`, danh sách này xác định các module hoặc named interface mà module đó được phép tham chiếu. Vì vậy, cần chọn đúng phạm vi API mà bên sử dụng thực sự cần.

| Khai báo | Phạm vi được phép từ module `order` |
|---|---|
| `"order::spi"` | Chỉ named interface `spi`; không cho phép package API gốc `order` |
| `"order"` | Package API gốc của module `order` |
| `{ "order", "order::spi" }` | Package API gốc và named interface `spi` |
| `"order::*"` | Tất cả named interface được khai báo tường minh; không bao gồm package API gốc |
| `"order::**"` | Package API gốc và tất cả named interface được khai báo tường minh |

Ví dụ, nếu `billing` cần cả `OrderManagement` ở package gốc và `OrderLookup` trong `order.spi`, có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "order", "order::spi" }
)
package com.example.shop.billing;
```

Hoặc nếu thực sự muốn cho phép dùng tất cả API được expose của `order`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::**"
)
package com.example.shop.billing;
```

`*` và `**` có phạm vi khác nhau: `*` chỉ bao phủ các named interface có tên; `**` bao phủ cả package gốc và mọi named interface. Hãy dùng phạm vi nhỏ nhất đáp ứng nhu cầu của module tiêu thụ để giữ hợp đồng phụ thuộc dễ hiểu.

Nếu module không khai báo danh sách `allowedDependencies` tường minh, các quy tắc mặc định cho phép truy cập package API gốc và các named interface được công bố của module được tham chiếu. Khi đã khai báo danh sách cho phép, hãy liệt kê đúng các package hoặc named interface cần thiết.

## 5. Một module có thể expose nhiều package

Một module có thể công bố nhiều nhóm API với mục đích khác nhau. Ví dụ:

```text
com.example.shop.order
├── OrderManagement.java
├── spi
│   ├── package-info.java       // @NamedInterface("spi")
│   └── OrderLookup.java
├── reporting
│   ├── package-info.java       // @NamedInterface("reporting")
│   └── OrderReportView.java
└── internal
    ├── OrderManagementImpl.java
    └── OrderRepository.java
```

Các file metadata có thể khai báo như sau:

`order/spi/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.order.spi;
```

`order/reporting/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("reporting")
package com.example.shop.order.reporting;
```

Khi đó, module tiêu thụ có thể chỉ phụ thuộc vào một nhóm API:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::reporting"
)
package com.example.shop.analytics;
```

Module `analytics` được phép dùng các kiểu trong `order.reporting`. Module khác có thể chỉ được phép dùng `order::spi`. Các nhóm API này được quản lý độc lập, giúp mỗi module tiêu thụ chỉ nhận quyền truy cập cần thiết.

## 6. Named interface không biến package thành module mới

Một named interface vẫn thuộc application module sở hữu package đó. Ví dụ, `com.example.shop.order.spi` vẫn là một phần của module `order`; tên `spi` chỉ là nhãn của một nhóm API được công bố.

Điều này khác với nested application module:

| Named interface | Nested application module |
|---|---|
| Expose package con như một nhóm API của module cha | Tạo một ranh giới module riêng bên trong cấu trúc module cha theo cơ chế hỗ trợ |
| Dùng `@NamedInterface("spi")` | Dùng `@ApplicationModule` trên package con theo quy tắc nested module của phiên bản tương ứng |
| Dependency tham chiếu `order::spi` | Dependency tham chiếu module theo logical module identifier của nó |
| Không tạo module độc lập | Được mô hình hóa như module lồng nhau |

Nếu package chỉ cần chia sẻ một số interface hoặc DTO, named interface thường là lựa chọn phù hợp. Nếu package đã có trách nhiệm nghiệp vụ, quy tắc phụ thuộc và vòng đời riêng, hãy đánh giá liệu nó nên trở thành nested module.

## 7. Giữ phần nội bộ ở trạng thái encapsulated

Sau khi expose `order.spi`, các package khác của module `order` vẫn được giữ kín theo quy ước:

```text
com.example.shop.order
├── OrderManagement.java       // API mặc định
├── spi                        // named interface được expose
│   ├── package-info.java
│   └── OrderLookup.java
└── internal                   // vẫn là nội bộ
    ├── OrderManagementImpl.java
    └── OrderRepository.java
```

Module `billing` được phép import `OrderLookup` nếu đã khai báo `order::spi`. Nó không được import `OrderRepository` hoặc `OrderManagementImpl` chỉ vì các lớp đó có modifier `public`.

Không nên đánh dấu toàn bộ package `internal` thành named interface để giải quyết nhanh lỗi truy cập. Làm như vậy sẽ công bố cả chi tiết triển khai mà module khác không cần biết. Hãy đưa đúng hợp đồng cần chia sẻ vào package API riêng, giữ repository và implementation bên trong module sở hữu.

## 8. Kiểm chứng named interface và dependency

Spring Modulith có thể kiểm tra các quan hệ module bằng `ApplicationModules.verify()`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class NamedInterfaceTests {

    @Test
    void verifiesNamedInterfaceDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Với cấu trúc ví dụ, kiểm tra sẽ chấp nhận việc `billing` sử dụng `OrderLookup` khi `order.spi` được expose và `billing` khai báo dependency `order::spi`. Nếu `billing` chỉ được phép dùng `order::spi` nhưng lại tham chiếu `OrderManagement` ở package gốc, kiểm tra sẽ báo dependency không được cho phép.

Khi kiểm tra thất bại, hãy xác định:

1. Package chứa kiểu được module tiêu thụ tham chiếu đã được đánh dấu `@NamedInterface` chưa?
2. Tên trong `@NamedInterface` có trùng với phần sau `::` trong `allowedDependencies` không?
3. Logical module name ở phần trước `::` có đúng không?
4. Module tiêu thụ có khai báo đủ package API gốc nếu nó cũng cần dùng API mặc định không?
5. Kiểu đang được tham chiếu có thực sự là hợp đồng cần công bố, hay nên được giữ nội bộ?

Bạn cũng có thể quan sát mô hình module bằng:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Đầu ra giúp kiểm tra module, base package và các thành phần được công bố. Kết hợp quan sát với `verify()` để phát hiện cả cấu trúc expose sai và dependency không phù hợp.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Chỉ cần tạo package tên `spi` là package được expose | Cần đánh dấu package bằng `@NamedInterface` hoặc cơ chế khai báo tương ứng. |
| `@NamedInterface` tạo một application module mới | Named interface chỉ là nhóm API được công bố bên trong module sở hữu package. |
| `allowedDependencies = "order::spi"` cho phép dùng mọi API của `order` | Khai báo này chỉ cho phép named interface `spi`, không bao gồm package API gốc. |
| `order::*` và `order::**` giống nhau | `*` chỉ bao gồm named interfaces; `**` bao gồm cả package gốc và named interfaces. |
| Expose package đồng nghĩa với đăng ký Spring bean | `@NamedInterface` mô tả ranh giới kiến trúc; bean vẫn cần được Spring cấu hình riêng. |
| Lớp `public` ở package nội bộ có thể được import tự do | Java cho phép import nhưng Spring Modulith vẫn có thể phát hiện vi phạm ranh giới module. |
| Có thể expose toàn bộ `internal` để sửa lỗi verify | Chỉ nên công bố các hợp đồng thực sự cần chia sẻ, giữ implementation và repository nội bộ. |

## 10. Checklist expose package

- [ ] Xác định package con nào thực sự cần được module khác sử dụng.
- [ ] Tạo `package-info.java` trong package cần expose.
- [ ] Đánh dấu package bằng `@NamedInterface("ten-giao-dien")`.
- [ ] Đặt các interface, DTO hoặc hợp đồng cần chia sẻ trong package đó.
- [ ] Giữ repository và implementation trong package nội bộ.
- [ ] Ở module tiêu thụ, khai báo `allowedDependencies = "module::named-interface"` nếu dùng whitelist.
- [ ] Thêm dependency tới package API gốc nếu module tiêu thụ cũng cần API mặc định.
- [ ] Chọn `*` hoặc `**` chỉ khi phạm vi truy cập rộng hơn thực sự cần thiết.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra ranh giới.
- [ ] Quan sát mô hình để xác nhận named interface được nhận diện đúng.

## 11. Kết luận

`@NamedInterface` cho phép một application module expose thêm package con như một nhóm API có tên. Module khác tham chiếu nhóm API đó bằng cú pháp `module::named-interface` trong `allowedDependencies`. Cách này mở rộng bề mặt API theo từng phần, đồng thời giữ các package nội bộ khác ở trạng thái encapsulated.

Khi expose package, hãy chọn đúng hợp đồng cần chia sẻ, đặt metadata trong `package-info.java`, khai báo dependency rõ ràng ở phía sử dụng và kiểm chứng bằng `ApplicationModules.verify()`. Named interface giúp các module phối hợp qua những hợp đồng ổn định mà không phải phụ thuộc vào chi tiết triển khai của nhau.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 1.2 — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/1.2/fundamentals.html)
- [Spring Modulith — `NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
