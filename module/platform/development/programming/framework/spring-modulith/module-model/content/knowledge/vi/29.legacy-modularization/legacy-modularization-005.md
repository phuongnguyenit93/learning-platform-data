# Đặt named interface cho vùng dùng chung

Khi đưa một hệ thống cũ vào Spring Modulith, thường có những package đã được nhiều module sử dụng từ trước. Chúng có thể chứa contract, kiểu dữ liệu dùng chung, SPI hoặc các abstraction được chia sẻ qua nhiều luồng nghiệp vụ. Nếu đóng tất cả package con thành internal ngay từ đầu, nhiều consumer hiện hữu sẽ vi phạm module boundary. Nếu mở toàn bộ module, mọi chi tiết triển khai lại có thể trở thành thứ mà module khác truy cập được.

Named Interface cho phép công bố có chọn lọc một vùng package hoặc một nhóm type của module. Nhờ đó, nhóm có thể giữ nguyên phần lớn cấu trúc legacy, xác định rõ vùng dùng chung nào là hợp đồng được hỗ trợ và dần thu hẹp những reference còn lại tới implementation nội bộ.

## 1. Bài toán vùng dùng chung trong codebase legacy

Giả sử ứng dụng bán hàng đã có module `order`, nhưng một số module khác đang sử dụng các type nằm trong package con `order.shared`:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── shared
│   │   ├── OrderReference.java
│   │   ├── OrderNumber.java
│   │   └── OrderStatusView.java
│   └── internal
│       ├── OrderRepository.java
│       └── OrderService.java
├── shipping
│   └── ShippingService.java
└── reporting
    └── OrderReportService.java
```

Trong code legacy, `shipping` và `reporting` có thể đã import trực tiếp các class trong `order.shared`. Một số class trong package này là hợp đồng dữ liệu ổn định, nhưng `order.internal` chứa repository và service triển khai riêng của module `order`.

Với một closed application module, package gốc `order` là API mặc định. Các package con như `order.shared` và `order.internal` là internal cho đến khi được công bố. Vì vậy, reference từ `shipping` đến `order.shared.OrderReference` có thể bị `ApplicationModules.verify()` báo vi phạm dù class là `public` và code vẫn biên dịch.

Nhóm cần một cách phân biệt hai nhóm type:

- Các type dùng chung mà module `order` chủ động hỗ trợ như một hợp đồng.
- Các type còn lại chỉ phục vụ implementation của `order` và không được consumer phụ thuộc.

Named Interface giải quyết đúng phần ranh giới công khai này.

## 2. Named Interface là hợp đồng bổ sung của một module

Mỗi application module có package gốc làm API mặc định. Khi cần công bố thêm một package con, module có thể khai báo Named Interface. Một Named Interface là một nhóm type được module chủ động cho phép module khác tham chiếu.

Ví dụ, `order` có thể công bố package `order.shared` với tên interface `shared`. Consumer khi đó phụ thuộc vào `order :: shared`.

```text
order
├── OrderManagement.java          API mặc định của module
├── shared                        Named Interface: shared
│   ├── OrderReference.java
│   ├── OrderNumber.java
│   └── OrderStatusView.java
└── internal                      package nội bộ
    ├── OrderRepository.java
    └── OrderService.java

shipping ------> order :: shared
reporting -----> order :: shared
```

Named Interface không tạo application module mới và cũng không đổi ownership của package. `shared` vẫn thuộc module `order`; tên `shared` chỉ định danh một phần API mà module `order` công bố.

## 3. Công bố toàn bộ package dùng chung bằng `package-info.java`

Nếu các type cần chia sẻ đã được gom trong một package riêng, cách đơn giản nhất là đặt `@NamedInterface` trong `package-info.java` của package đó.

Tạo file `src/main/java/com/acme/shop/order/shared/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("shared")
package com.acme.shop.order.shared;
```

Các type trong package `com.acme.shop.order.shared` nay thuộc Named Interface có tên `shared`. Có thể dùng tên package làm tên mặc định nếu không truyền giá trị, nhưng khai báo tên rõ ràng giúp hợp đồng ít phụ thuộc vào cách đặt tên package.

Các consumer tiếp tục import type theo package hiện tại:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.shared.OrderReference;
import com.acme.shop.order.shared.OrderStatusView;
import org.springframework.stereotype.Service;

@Service
class ShippingService {

    void prepareShipment(OrderReference order, OrderStatusView status) {
        // Dùng contract đã được module order công bố.
    }
}
```

Nếu các class đang nằm trong package này, việc thêm package annotation không cần đổi fully qualified name của chúng. Đây là một bước chuyển đổi nhỏ, phù hợp khi nhóm muốn thiết lập boundary trước rồi mới tái cấu trúc sâu hơn.

Chỉ đặt trong `shared` những type mà consumer thực sự cần. Không đưa repository, JPA entity nội bộ, service triển khai hoặc helper riêng vào Named Interface chỉ vì chúng đang được nhiều nơi import.

## 4. Gắn Named Interface cho từng type khi chưa thể gom package

Trong một codebase lâu năm, các type dùng chung có thể nằm rải rác ở nhiều package. Di chuyển tất cả chúng ngay lập tức có thể gây thay đổi lớn tới import, serialization, reflection hoặc client tích hợp.

Spring Modulith cho phép gắn `@NamedInterface` trực tiếp lên type để đưa type đó vào một Named Interface:

```java
package com.acme.shop.order.legacy;

import org.springframework.modulith.NamedInterface;

import java.util.UUID;

@NamedInterface("shared")
public record OrderReference(UUID value) {
}
```

Một type khác có thể được đưa vào cùng interface:

```java
package com.acme.shop.order.contract;

import org.springframework.modulith.NamedInterface;

@NamedInterface("shared")
public record OrderNumber(String value) {
}
```

Như vậy, `OrderReference` và `OrderNumber` thuộc cùng Named Interface `shared` dù chúng nằm ở hai package khác nhau trong module `order`. Cách này hữu ích khi muốn chọn một tập type nhỏ từ cấu trúc legacy mà chưa thể di chuyển chúng về cùng package.

`@NamedInterface` hỗ trợ target `PACKAGE` và `TYPE`. Với package, annotation công bố package như một vùng API; với type, annotation gán type được chọn vào Named Interface. Có thể dùng nhiều tên interface cho một type nếu type đó thực sự thuộc nhiều hợp đồng.

## 5. Hiểu `propagate` khi gắn annotation lên type

Từ Spring Modulith 2.0, `@NamedInterface` có thuộc tính `propagate`. Giá trị mặc định là `true`: các type xuất hiện trong public method signature (tham số và kiểu trả về) của type được đánh dấu, nếu chúng nằm trong cùng package space, cũng được xem là thuộc Named Interface.

Ví dụ:

```java
package com.acme.shop.order.legacy;

import org.springframework.modulith.NamedInterface;

@NamedInterface("shared")
public interface LegacyOrderLookup {

    OrderStatusView findStatus(OrderReference reference);
}
```

Nếu `OrderStatusView` và `OrderReference` nằm trong cùng package space, cơ chế propagation mặc định có thể đưa chúng vào Named Interface `shared` vì chúng xuất hiện trong chữ ký public của `LegacyOrderLookup`.

Propagation giúp tránh phải đánh dấu từng DTO hoặc value type được dùng trực tiếp trong contract. Tuy nhiên, với code legacy, cần kiểm tra những type được kéo vào để không vô tình mở rộng API quá rộng.

Nếu muốn chỉ công bố type được đánh dấu và tự kiểm soát các type liên quan, có thể tắt propagation:

```java
@NamedInterface(value = "shared", propagate = false)
public interface LegacyOrderLookup {

    OrderStatusView findStatus(OrderReference reference);
}
```

Khi đó, các type liên quan cần được đưa vào Named Interface theo cách rõ ràng nếu consumer phải tham chiếu trực tiếp chúng. Hãy chọn `propagate = false` khi cần giới hạn chặt tập type được công bố và có thể duy trì danh sách contract tường minh.

## 6. Giới hạn dependency ở phía consumer

Sau khi module `order` công bố Named Interface `shared`, module tiêu thụ có thể khai báo chỉ được phép phụ thuộc vào interface đó.

Trong `src/main/java/com/acme/shop/shipping/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: shared"
)
package com.acme.shop.shipping;
```

Với `reporting`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: shared"
)
package com.acme.shop.reporting;
```

Khai báo `order :: shared` gồm logical module name `order`, dấu phân cách `::` và tên Named Interface `shared`. Nó cho phép consumer tham chiếu type trong Named Interface này. Nó không cho phép consumer tham chiếu package `order.internal` hoặc tự động cho phép API mặc định ở package gốc `order`.

Nếu consumer cần cả API mặc định lẫn Named Interface `shared`, hãy khai báo cả hai dependency:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "order",
        "order :: shared"
    }
)
package com.acme.shop.shipping;
```

Đừng thêm dependency rộng hơn mức consumer cần. Allowlist chính là tài liệu thể hiện module nào đang sử dụng hợp đồng nào.

## 7. Phân biệt `*` và `**` trong allowlist

Khi một module có nhiều Named Interface, có thể dùng wildcard để khai báo phạm vi dependency:

| Khai báo | Ý nghĩa |
| --- | --- |
| `order :: shared` | Chỉ Named Interface có tên `shared` |
| `order :: *` | Tất cả Named Interface được khai báo tường minh của `order`, không bao gồm API package gốc |
| `order :: **` | API package gốc và tất cả Named Interface được khai báo của `order` |
| `order` | API package gốc của `order` |

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: *"
)
package com.acme.shop.reporting;
```

Khai báo này hữu ích nếu `reporting` cần tất cả Named Interface của `order`, nhưng không cần API mặc định ở package gốc. Nếu dùng `order :: **`, consumer được phép dùng cả API mặc định và mọi Named Interface đã công bố.

Với mục tiêu modularization, nên bắt đầu bằng tên interface cụ thể. Wildcard làm allowlist dễ duy trì hơn khi có nhiều interface, nhưng cũng khiến consumer tự động được phép dùng những interface mới được thêm sau này.

## 8. Nếu module chưa khai báo `allowedDependencies`

`allowedDependencies` là cơ chế tùy chọn. Nếu module tiêu thụ không khai báo allowlist, Spring Modulith cho phép nó truy cập API package mặc định và các Named Interface được công bố của module đích, đồng thời vẫn từ chối package nội bộ của closed module.

Điều đó có nghĩa việc thêm `@NamedInterface` vẫn có tác dụng ngay cả khi consumer chưa khai báo `allowedDependencies`: package được công bố trở thành một vùng API hợp lệ. Allowlist bổ sung mức kiểm soát chặt hơn bằng cách chỉ định consumer được phép dùng module/interface nào.

Trong quá trình chuyển đổi legacy, nhóm có thể thực hiện theo hai giai đoạn:

1. Đánh dấu Named Interface để làm rõ các vùng được phép truy cập và chạy verification nhằm tìm reference tới internal package.
2. Khi đã hiểu dependency graph, thêm `allowedDependencies` ở consumer để chuyển từ kiểm tra boundary sang kiểm soát rõ từng module/interface.

## 9. Chọn đúng ownership cho vùng dùng chung

Một package có nhiều consumer không tự động có nghĩa nó nên thuộc một module `common`. Trước khi đặt Named Interface, hãy xác định ai sở hữu ý nghĩa nghiệp vụ và ai chịu trách nhiệm duy trì hợp đồng.

| Tình huống | Cách tổ chức nên cân nhắc |
| --- | --- |
| Type mô tả khái niệm do `order` sở hữu nhưng nhiều module cần tham chiếu | Giữ trong module `order` và công bố bằng `order :: shared` hoặc một interface tên sát nghĩa hơn |
| Type là contract tích hợp mà `order` cung cấp cho các consumer | Đặt trong `order.spi`, `order.integration` hoặc package contract phù hợp và công bố bằng Named Interface |
| Type kỹ thuật thật sự dùng chung, không thuộc ownership của một capability cụ thể | Cân nhắc tách application module `shared` có API và trách nhiệm riêng |
| Package `common` chứa nhiều tiện ích không liên quan | Chia lại theo ownership hoặc capability trước khi công bố; tránh biến nó thành kho chứa mọi thứ |

Nếu vùng dùng chung được tách thành application module riêng, bản thân module đó có package gốc là API mặc định. Named Interface chỉ cần khi module `shared` còn muốn chia API thành các hợp đồng nhỏ hơn, ví dụ `shared :: identifiers` và `shared :: money`.

Không nên chọn module `order` làm chủ sở hữu chỉ vì package hiện tại đang nằm dưới `order`. Nếu các type không có ý nghĩa nghiệp vụ thuộc `order`, hãy quyết định ownership trước khi công bố để tránh tạo một dependency sai hướng tồn tại lâu dài.

## 10. Phân biệt Named Interface với `sharedModules`

Hai khái niệm có tên gần giống nhau nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Mục đích |
| --- | --- |
| `@NamedInterface("shared")` | Công bố một phần API của application module để module khác được phép tham chiếu |
| `@Modulithic(sharedModules = "shared")` | Đánh dấu application module dùng chung để luôn được đưa vào bootstrap của `@ApplicationModuleTest` và được tính là dependency được phép |

Named Interface không làm module tự động được nạp vào mọi integration test. Ngược lại, `sharedModules` không công bố mọi package nội bộ của module thành API. Một module được đánh dấu shared vẫn phải tuân thủ API package, Named Interface và internal package boundary.

Nếu cần vừa công bố một contract nhỏ vừa luôn nạp module sở hữu nó trong test, hai cơ chế có thể cùng được dùng, nhưng mỗi cơ chế cần được cấu hình cho đúng mục đích.

## 11. Lộ trình chuyển đổi vùng dùng chung trong hệ thống cũ

Để giảm rủi ro khi áp dụng Named Interface vào codebase hiện hữu, có thể chuyển đổi theo từng bước:

1. **Lập danh sách consumer:** tìm các module đang import hoặc tham chiếu type trong package dùng chung.
2. **Xác định ownership:** quyết định module nào chịu trách nhiệm về semantics và vòng đời của các type.
3. **Phân loại type:** tách contract ổn định khỏi repository, entity nội bộ, helper và implementation detail.
4. **Chọn cách công bố:** dùng package-level annotation nếu các type đã nằm trong một package; dùng type-level annotation nếu cần chọn một tập type rải rác.
5. **Đặt tên interface:** chọn tên mô tả vai trò như `shared`, `spi`, `contracts`, `identifiers` hoặc `events`; tránh tên mơ hồ nếu module có nhiều hợp đồng.
6. **Cập nhật consumer:** khai báo `allowedDependencies` như `order :: shared` khi module dùng allowlist và giữ import chỉ tới các type được công bố.
7. **Chạy verification:** dùng `ApplicationModules.verify()` để tìm reference còn sót tới internal package hoặc dependency ngoài allowlist.
8. **Thu hẹp legacy:** chuyển implementation vào `internal`, bỏ các facade tạm và xóa Named Interface không còn consumer.

Nhóm có thể công bố một interface trước khi di chuyển type để giảm số thay đổi cùng lúc. Khi cần thay đổi package, hãy cân nhắc giữ facade hoặc adapter tương thích trong một giai đoạn chuyển tiếp, rồi loại bỏ khi các consumer đã cập nhật.

## 12. Kiểm tra Named Interface bằng `ApplicationModules.verify()`

Tạo architecture test để kiểm tra module arrangement:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesNamedInterfaceBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi consumer sử dụng type trong `order.shared`, verification sẽ chấp nhận reference nếu package hoặc type đã được công bố bằng Named Interface và dependency được phép theo cấu hình của consumer. Nếu consumer tham chiếu `order.internal.OrderRepository`, verification vẫn báo lỗi.

Nếu một module khai báo `allowedDependencies = "order :: shared"` nhưng lại import `OrderManagement` từ package gốc, reference đó vượt khỏi interface được cho phép. Ngược lại, nếu module chỉ cần `order.shared`, việc thêm `order :: **` có thể làm allowlist rộng hơn mức cần thiết.

Hãy đọc diagnostic theo hai chiều:

- Package/type đích có thuộc Named Interface đã công bố không?
- Module nguồn có được phép sử dụng module/interface đó theo allowlist không?

Hai điều kiện này độc lập. Một package được công bố không có nghĩa mọi consumer đều được phép dùng nó nếu consumer đã khai báo allowlist hẹp.

## 13. Những lỗi thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Đặt `@NamedInterface` ở package gốc của module chỉ để đặt tên API mặc định | Package gốc đã là API mặc định của module | Chỉ tạo Named Interface cho package bổ sung hoặc nhóm type riêng |
| Đánh dấu toàn bộ `common` mà không phân loại type | Contract và implementation bị trộn thành một API rộng | Chọn package/type thực sự cần chia sẻ |
| Chỉ thêm `allowedDependencies` mà không công bố package | Allowlist không biến internal package thành API | Thêm Named Interface ở module sở hữu |
| Công bố package nhưng quên cập nhật allowlist | Consumer có allowlist rõ ràng vẫn không được phép dùng interface mới | Thêm đúng `module :: interface` vào consumer |
| Dùng `order :: **` cho mọi consumer | Consumer được quyền dùng cả API gốc và mọi Named Interface | Dùng tên interface cụ thể nếu chỉ cần một vùng |
| Gắn `@NamedInterface` lên type có propagation mặc định mà không kiểm tra type liên quan | Các type trong public signature cùng package space có thể được đưa vào interface | Kiểm tra phạm vi propagation hoặc dùng `propagate = false` khi cần kiểm soát chặt |
| Xem Named Interface như một application module | Interface chỉ là một phần API bên trong module sở hữu | Dùng package root riêng nếu thực sự cần module mới |
| Nhầm `sharedModules` với Named Interface | Một cấu hình bootstrap test, một cấu hình API boundary | Dùng đúng cơ chế cho mục đích tương ứng |

## 14. Ghi nhớ

Named Interface là cách công bố có chọn lọc một package hoặc nhóm type bổ sung của application module. Với vùng dùng chung đã được gom package, đặt `@NamedInterface("shared")` trong `package-info.java`. Với code legacy chưa thể di chuyển, gắn `@NamedInterface("shared")` trực tiếp lên các type cần công bố; chú ý `propagate` mặc định là `true` từ Spring Modulith 2.0 và có thể kéo thêm type liên quan trong public signature vào cùng interface.

Ở phía consumer, dùng `allowedDependencies = "order :: shared"` để chỉ cho phép dependency tới hợp đồng cần thiết. `*` bao phủ các Named Interface được khai báo, còn `**` bao phủ cả API package gốc và các Named Interface. Named Interface không tạo module mới, không mở package internal và không thay đổi Spring component scanning.

Trong quá trình modularize legacy, hãy xác định ownership trước, phân loại contract khỏi implementation, công bố vùng dùng chung bằng interface nhỏ, cập nhật consumer và chạy `ApplicationModules.verify()`. Khi cấu trúc đã ổn định, tiếp tục thu hẹp package nội bộ và loại bỏ những dependency legacy không còn cần thiết.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `NamedInterface` annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith API — `ApplicationModule` and `allowedDependencies`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
