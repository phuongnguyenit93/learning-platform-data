# `@NamedInterface` trên package metadata

Trong Spring Modulith, package gốc của application module là API package mặc định. Các package con thường được giữ nội bộ để module có thể thay đổi implementation mà không làm ảnh hưởng consumer. Khi cần công bố một package con như một phần API có tên, có thể gắn `@NamedInterface` vào metadata của package bằng file `package-info.java`.

Named interface tạo ra một bề mặt API có thể tham chiếu rõ ràng. Ví dụ, module `inventory` có thể công bố package `spi` bằng tên `spi`; module `order` sau đó chỉ cần phụ thuộc vào `inventory::spi`. Cách này giúp expose đúng nhóm hợp đồng cần chia sẻ, giữ các package khác như `internal` hoặc `persistence` ở trạng thái đóng.

Trong `SPRING_MODULITH_MODULE_MODEL`, `@NamedInterface` là công cụ quan trọng để xác định API công khai và kiểm soát dependency giữa các module trong một modular monolith.

## 1. Vì sao cần Named Interface?

Giả sử module `inventory` có cấu trúc:

```text
com.example.shop.inventory
├── InventoryAvailability.java
├── spi
│   ├── package-info.java
│   └── StockReservation.java
├── reporting
│   ├── package-info.java
│   └── InventoryReport.java
└── internal
    ├── InventoryRepository.java
    └── DefaultInventoryAvailability.java
```

Module `inventory` có thể muốn công bố hai nhóm hợp đồng:

- `spi`: các kiểu phục vụ tích hợp giữa module hoặc với adapter bên ngoài.
- `reporting`: các kiểu truy vấn hoặc dữ liệu phục vụ báo cáo.

Các lớp trong `internal` vẫn là chi tiết triển khai. Nếu không có named interface, các module khác không thể tham chiếu trực tiếp những package con này khi provider là closed module.

`@NamedInterface` giải quyết nhu cầu công bố có chọn lọc: module cung cấp quyết định package nào được xem là API bổ sung, và module tiêu thụ có thể tham chiếu đúng named interface đó trong quy tắc dependency.

## 2. Named Interface là gì?

Named interface là một nhóm kiểu Java được expose từ một application module dưới một tên logic. Nhóm này thường tương ứng với một package con và được khai báo bằng `@NamedInterface`.

Một application module có thể có:

1. **API package gốc:** các kiểu được đặt trực tiếp trong package gốc của module.
2. **Named interface:** một package con được expose với tên riêng.
3. **Internal packages:** các package con khác chưa được công bố.

Ví dụ:

```text
inventory module
├── base package API
├── spi             // named interface: spi
├── reporting       // named interface: reporting
└── internal        // internal package
```

Named interface vẫn thuộc module `inventory`; nó không tạo application module mới. Tên `spi` là tên giao diện được dùng trong metadata dependency, còn package đầy đủ vẫn là `com.example.shop.inventory.spi`.

## 3. Khai báo `@NamedInterface` trong `package-info.java`

Với Java, cách phổ biến để công bố toàn bộ một package con là tạo `package-info.java` trong package đó và đặt `@NamedInterface` trước package declaration.

Ví dụ, file:

```text
src/main/java/com/example/shop/inventory/spi/package-info.java
```

Nội dung:

```java
/**
 * Các hợp đồng SPI được công bố bởi module inventory.
 */
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Annotation có tên `spi`, vì vậy package `com.example.shop.inventory.spi` được expose như named interface `spi` của module `inventory`.

Một package khác có thể công bố tên `reporting`:

```java
/**
 * Các hợp đồng phục vụ truy vấn và báo cáo tồn kho.
 */
@org.springframework.modulith.NamedInterface("reporting")
package com.example.shop.inventory.reporting;
```

Mỗi file phải khai báo đúng package tương ứng với thư mục. `package-info.java` phải nằm trong source set được biên dịch và metadata package phải có mặt trên classpath mà Spring Modulith phân tích.

## 4. Cấu trúc hoàn chỉnh của provider

Ví dụ module `inventory` công bố API package gốc và hai named interfaces:

```text
src/main/java/com/example/shop/inventory
├── InventoryAvailability.java
├── package-info.java
├── spi
│   ├── package-info.java       // @NamedInterface("spi")
│   └── StockReservation.java
├── reporting
│   ├── package-info.java       // @NamedInterface("reporting")
│   └── InventoryReport.java
└── internal
    ├── InventoryRepository.java
    └── DefaultInventoryAvailability.java
```

Package gốc có thể mang metadata module riêng:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Package `spi` và `reporting` được expose nhờ annotation riêng tại từng package. Package `internal` không có `@NamedInterface`, nên tiếp tục là internal package của module `inventory`.

Lưu ý vị trí annotation:

- `@ApplicationModule` được đặt tại package gốc module.
- `@NamedInterface` được đặt tại package con cần expose.

Không đặt `@NamedInterface` ở package gốc với ý định biến toàn bộ module thành một named interface. Package gốc vốn đã là API package mặc định của module.

## 5. Dùng Named Interface trong `allowedDependencies`

Sau khi provider công bố named interface, consumer có thể tham chiếu nó bằng cú pháp:

```text
module-identifier::named-interface-name
```

Ví dụ, module `order` chỉ cần hợp đồng `StockReservation` từ `inventory.spi`. Đặt whitelist trong `package-info.java` của `order`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Hai phần của giá trị:

- `inventory`: identifier của application module cung cấp.
- `spi`: tên được khai báo trong `@NamedInterface("spi")`.

Mã trong `order` có thể import hợp đồng:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.spi.StockReservation;

class PlaceOrderService {

    private final StockReservation reservation;

    PlaceOrderService(StockReservation reservation) {
        this.reservation = reservation;
    }
}
```

Consumer phụ thuộc vào hợp đồng đã công bố, không cần biết repository hoặc implementation của `inventory` được tổ chức ra sao.

## 6. Phân biệt module identifier và tên Named Interface

Trong `inventory::spi`, `inventory` và `spi` có vai trò khác nhau:

| Thành phần | Lấy từ đâu? | Ví dụ |
|---|---|---|
| Module identifier | Tên logic của application module, mặc định thường suy ra từ package gốc hoặc được đặt bằng `id` | `inventory` |
| Named interface name | Giá trị của `@NamedInterface` trên package được expose | `spi` |
| Fully qualified package | Package declaration trong Java | `com.example.shop.inventory.spi` |

Không dùng tên package đầy đủ thay cho cú pháp `inventory::spi` trong `allowedDependencies`. Nếu module có identifier tường minh, phần trước `::` phải dùng identifier đó.

Ví dụ provider có package `com.example.shop.stock` nhưng khai báo `@ApplicationModule(id = "inventory")`, consumer vẫn tham chiếu `inventory::spi` nếu named interface của provider mang tên `spi`.

## 7. API package gốc và Named Interface là hai phạm vi riêng

Khai báo dependency tới module identifier đơn giản cho phép sử dụng API package gốc. Dependency tới named interface cho phép sử dụng package con đã được công bố với tên tương ứng.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "inventory::spi"
    }
)
package com.example.shop.order;
```

Trong cấu hình trên, `order` được phép sử dụng:

- API ở package gốc `com.example.shop.inventory`.
- Các kiểu thuộc named interface `spi` của `inventory`.

Nếu chỉ khai báo `inventory::spi`, consumer được giới hạn vào named interface đó. Nếu chỉ khai báo `inventory`, consumer được phép phụ thuộc vào API package gốc theo whitelist đã đặt. Các package nội bộ khác như `inventory.internal` vẫn không được expose.

## 8. Wildcard với Named Interface

Khi provider có nhiều named interface và consumer cần sử dụng tất cả, có thể dùng wildcard `*`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::*"
)
package com.example.shop.order;
```

`inventory::*` cho phép tất cả named interfaces được công bố của module `inventory`, nhưng không bao gồm API package gốc.

Nếu consumer cần cả package gốc và tất cả named interfaces, dùng `**`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::**"
)
package com.example.shop.order;
```

Bảng so sánh:

| Khai báo | API package gốc | Named Interface |
|---|---:|---:|
| `inventory` | Có | Không |
| `inventory::spi` | Không | Chỉ `spi` |
| `inventory::*` | Không | Tất cả named interfaces |
| `inventory::**` | Có | Tất cả named interfaces |

Wildcard chỉ mở rộng phạm vi trong module được nêu trước `::`. Nó không cấp quyền phụ thuộc vào mọi module trong ứng dụng và không expose các package internal chưa được công bố.

## 9. Một Named Interface có thể được sử dụng bởi nhiều consumer

Named interface là hợp đồng do provider công bố. Nhiều consumer có thể phụ thuộc vào cùng một named interface nếu nhu cầu nghiệp vụ phù hợp.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Và:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.warehouseintegration;
```

Cả `order` và `warehouseintegration` đều được phép tham chiếu hợp đồng trong `inventory.spi`. Provider vẫn sở hữu interface và có thể thay đổi implementation nội bộ miễn là giữ tương thích hợp đồng đã công bố.

Việc nhiều consumer cùng dùng một named interface không có nghĩa provider phải expose mọi kiểu trong module. Chỉ những kiểu thuộc package được công bố mới nằm trong bề mặt API tương ứng.

## 10. Named Interface không tạo application module mới

Một package được đánh dấu `@NamedInterface` vẫn thuộc application module cha. Ví dụ:

```text
com.example.shop.inventory
├── InventoryAvailability.java
├── spi                         // @NamedInterface("spi")
│   └── StockReservation.java
└── internal
    └── InventoryRepository.java
```

`inventory.spi` là một nhóm API của module `inventory`, không phải module `spi` độc lập. Nó không có đồ thị dependency riêng và không thay thế identifier của module cha.

Nếu muốn một package con trở thành nested application module, cần sử dụng cơ chế module detection và annotation module tương ứng. Không nhầm `@NamedInterface` với `@ApplicationModule`.

## 11. Named Interface khác Open Module

Named interface công bố có chọn lọc package con; Open module mở toàn bộ package thuộc module theo quy tắc Spring Modulith.

| Tiêu chí | Closed + Named Interface | Open module |
|---|---|---|
| API package gốc | Được expose | Được expose |
| Package con được chọn | Được expose theo tên | Được expose |
| Package con chưa chọn | Vẫn internal | Cũng được expose |
| Phạm vi công bố | Có giới hạn | Rộng trên toàn module |
| Cách khai báo | `@NamedInterface("spi")` trên package con | `@ApplicationModule(type = Type.OPEN)` tại package gốc |

Ví dụ Open module:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.legacyinventory;
```

Chỉ dùng Open module khi toàn bộ package của provider thực sự được thiết kế để consumer sử dụng hoặc trong một giai đoạn chuyển đổi có chủ đích. Nếu chỉ cần chia sẻ `spi`, Named Interface giữ encapsulation tốt hơn.

## 12. Named Interface không thay đổi Java visibility

`@NamedInterface` là metadata kiến trúc, không thay thế modifier truy cập của Java. Nếu consumer ở package khác cần import một interface, interface đó vẫn phải có visibility phù hợp, thường là `public`.

Ví dụ:

```java
package com.example.shop.inventory.spi;

public interface StockReservation {

    boolean reserve(String sku, int quantity);
}
```

Annotation package:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Hai điều kiện bổ sung cho nhau:

- Java visibility cho phép mã consumer truy cập kiểu ở cấp ngôn ngữ.
- Spring Modulith metadata cho phép kiểu đó được sử dụng qua ranh giới module.

Một lớp `public` trong package chưa được expose vẫn có thể bị `ApplicationModules.verify()` chặn. Ngược lại, package được expose không biến lớp package-private thành `public`.

## 13. Những lỗi thường gặp khi khai báo package metadata

| Lỗi | Nguyên nhân và cách xử lý |
|---|---|
| Đặt `@NamedInterface` trong package gốc module | Đặt annotation tại package con cần expose; package gốc vốn là API mặc định. |
| File khai báo sai package | Đảm bảo `package ...;` khớp chính xác đường dẫn thư mục. |
| Dùng sai tên trong `allowedDependencies` | Phần trước `::` phải là module identifier; phần sau phải khớp tên trong `@NamedInterface`. |
| Consumer import package con chưa expose | Thêm `@NamedInterface` ở provider nếu đó là API cần công bố, hoặc chuyển consumer sang API package gốc. |
| Nghĩ rằng annotation đăng ký Spring bean | `@NamedInterface` chỉ mô tả API module; bean vẫn cần stereotype hoặc `@Bean`. |
| Nghĩ rằng `public` tự động công bố package | Java visibility không thay thế module metadata. |
| Package metadata không được nhận diện | Kiểm tra file `package-info.java` có được biên dịch và nằm trên classpath phân tích không. |
| Dùng `@NamedInterface` để tạo nested module | Named interface là nhóm API thuộc module cha; nested module cần module annotation và detection phù hợp. |

## 14. Kiểm tra Named Interface bằng `ApplicationModules.verify()`

Sau khi khai báo package metadata và dependency ở consumer, hãy đưa kiểm tra kiến trúc vào test suite:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesNamedInterfaceDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu consumer khai báo `inventory::spi` nhưng provider chưa công bố named interface `spi`, hoặc consumer tham chiếu một package không thuộc named interface đó, kiểm tra kiến trúc sẽ báo lỗi tương ứng.

Khi test thất bại, hãy xác nhận lần lượt:

1. Provider có `package-info.java` ở đúng package con không?
2. Annotation có đúng tên `@NamedInterface("spi")` không?
3. Consumer có dùng đúng module identifier không?
4. Tên sau `::` có trùng tên named interface không?
5. Kiểu được tham chiếu có thực sự nằm trong package được công bố không?
6. Kiểu Java có visibility phù hợp để consumer sử dụng không?

`verify()` kiểm tra ranh giới module và dependency. Nó không thay thế Spring context test để xác nhận bean được đăng ký và inject thành công.

## 15. Quy trình công bố một package con

Khi cần chia sẻ package con từ module provider, thực hiện theo trình tự:

1. **Xác định hợp đồng cần chia sẻ.** Chỉ chọn các kiểu consumer thực sự cần.
2. **Chọn package phù hợp.** Gom các hợp đồng có cùng mục đích vào một package con dễ hiểu.
3. **Tạo package metadata.** Thêm `package-info.java` vào đúng package.
4. **Đánh dấu `@NamedInterface`.** Dùng tên ngắn, ổn định và có ý nghĩa, ví dụ `spi` hoặc `reporting`.
5. **Đảm bảo Java visibility.** Các kiểu consumer cần import phải có modifier phù hợp.
6. **Khai báo dependency ở consumer.** Dùng `provider::interface` trong `allowedDependencies` khi module áp dụng whitelist.
7. **Giữ implementation nội bộ.** Không đưa repository hoặc adapter vào named interface nếu chúng không phải hợp đồng cần chia sẻ.
8. **Kiểm tra kiến trúc.** Chạy `ApplicationModules.verify()` để xác nhận package và dependency được mô hình hóa đúng.
9. **Kiểm tra runtime khi cần.** Dùng Spring context test để xác nhận bean cung cấp hợp đồng được đăng ký và inject thành công.

## 16. Checklist sử dụng `@NamedInterface`

- [ ] Xác định module provider và package con cần công bố.
- [ ] Giữ API package gốc cho các hợp đồng chính của module.
- [ ] Tạo `package-info.java` trong package con cần expose.
- [ ] Đặt `@NamedInterface("...")` trước package declaration.
- [ ] Đảm bảo file package metadata được biên dịch và có trên classpath.
- [ ] Đặt tên named interface ngắn, ổn định và phản ánh mục đích API.
- [ ] Giữ package `internal`, `persistence` và implementation khác ở trạng thái đóng.
- [ ] Đảm bảo kiểu được chia sẻ có Java visibility phù hợp.
- [ ] Khai báo `provider::interface` tại consumer nếu dùng `allowedDependencies`.
- [ ] Không nhầm named interface với nested application module hoặc Open module.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra dependency và encapsulation.

## 17. Kết luận

`@NamedInterface` trên package metadata cho phép module công bố một package con như một nhóm API có tên. Với Java, annotation thường được đặt trong `package-info.java` của package cần expose. Consumer tham chiếu nhóm API đó bằng cú pháp `module-identifier::named-interface` trong `allowedDependencies` khi áp dụng whitelist.

Named interface vẫn thuộc module provider, không tạo application module mới và không thay đổi Java visibility hoặc bean registration. Nó giúp công bố có chọn lọc một phần API trong khi các package chưa được đánh dấu tiếp tục là internal của closed module. Hãy chọn package và tên interface theo hợp đồng thực sự cần chia sẻ, khai báo dependency ở phía consumer và dùng `ApplicationModules.verify()` để bảo vệ ranh giới đã thiết kế.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `@NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
