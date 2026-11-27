# Named interface không được nhận diện

Named Interface là một phần API mà application module chủ động công bố bên cạnh package gốc. Khi một module khác cần sử dụng type trong package con, nhóm có thể đánh dấu package đó bằng `@NamedInterface` và khai báo dependency theo dạng `module :: interface`. Nếu Spring Modulith không nhận diện Named Interface, dependency có thể bị báo là truy cập package nội bộ hoặc tên interface không tồn tại.

Khi xử lý sự cố, cần xác định lỗi nằm ở bước phát hiện package, đọc annotation, xây dựng module model hay kiểm tra allowlist của consumer. Một Named Interface không được nhận diện không nhất thiết có nghĩa annotation sai; đôi khi module gốc chưa được phát hiện, package nằm ngoài module, hoặc custom detection strategy đang thay thế cơ chế phát hiện mặc định.

## 1. Hiểu đúng Named Interface cần được phát hiện

Trong application module đóng mặc định, package gốc là API mặc định. Các package con là phần nội bộ cho đến khi được công bố rõ ràng bằng Named Interface.

Ví dụ:

```text
com.acme.shop
├── ShopApplication.java
├── order                         application module: order
│   ├── OrderManagement.java      API mặc định
│   ├── spi                       Named Interface: spi
│   │   ├── package-info.java
│   │   └── OrderLookup.java
│   └── internal                  package nội bộ
│       └── OrderRepository.java
└── shipping                      application module: shipping
    └── ShippingService.java
```

Module `order` công bố `order.spi` bằng Named Interface tên `spi`. Module `shipping` có thể sử dụng `OrderLookup` qua hợp đồng `order :: spi`, trong khi `order.internal` vẫn được bảo vệ.

Named Interface không tạo application module mới. Nó chỉ công bố một phần API bổ sung thuộc module sở hữu. Nếu `order.spi` bị đánh dấu thành `@ApplicationModule`, package đó có thể trở thành nested application module theo cấu hình discovery, thay vì Named Interface của `order`.

## 2. Kiểm tra package gốc của module trước

Trước khi kiểm tra annotation, xác nhận module sở hữu Named Interface đã xuất hiện trong module model và có base package như mong đợi:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(System.out::println);
```

Tìm module có base package `com.acme.shop.order`. Nếu module không xuất hiện, hãy xử lý module detection trước. `@NamedInterface` không thể công bố một package khi Spring Modulith chưa biết package đó thuộc application module nào.

Theo mặc định, các package con trực tiếp của package chứa lớp `@SpringBootApplication` được xem là application module. Nếu module nằm ngoài package root, kiểm tra `@Modulithic(additionalPackages = …)` hoặc `ApplicationModuleSourceFactory`. Nếu ứng dụng dùng `explicitly-annotated` hoặc custom `ApplicationModuleDetectionStrategy`, package module phải đáp ứng chính strategy đó.

Đừng nhầm `spring.modulith.detection-strategy` với cơ chế phát hiện Named Interface. Property này chọn package nào là module root. Named Interface được phát hiện bên trong từng module đã có.

## 3. Đặt `package-info.java` đúng thư mục và đúng package

Với Java, cách phổ biến nhất là đặt annotation trong `package-info.java` của chính package muốn công bố.

Đường dẫn phải khớp package declaration:

```text
src/main/java/com/acme/shop/order/spi/package-info.java
```

Nội dung:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Các điểm cần kiểm tra:

- Tên file là `package-info.java`, có dấu gạch nối và đúng phần mở rộng.
- File nằm trong source root được biên dịch cùng ứng dụng, thường là `src/main/java`.
- Package declaration là `com.acme.shop.order.spi`, khớp với package chứa các type dự định công bố.
- Annotation được đặt trước package declaration.
- Package này thực sự nằm bên trong base package của module `order`.
- Các type mà consumer cần tham chiếu phải có Java visibility phù hợp, thường là `public`; package annotation không tự đổi modifier của class.

Nếu file nằm ở `src/test/java`, module metadata có thể chỉ xuất hiện trong test classpath hoặc không phản ánh hợp đồng production mà nhóm muốn công bố. Hãy đặt package metadata của API trong production source set.

## 4. Kiểm tra import đúng annotation

Spring Modulith có hai type cùng tên `NamedInterface` ở hai package khác nhau:

| Type | Vai trò |
| --- | --- |
| `org.springframework.modulith.NamedInterface` | Annotation dùng trong `package-info.java` hoặc gắn lên type |
| `org.springframework.modulith.core.NamedInterface` | Class mô hình hóa Named Interface trong module model |

Khi đánh dấu package hoặc class, phải dùng annotation `org.springframework.modulith.NamedInterface`. Import nhầm class trong package `.core` sẽ không tạo package annotation như mong muốn.

Để tránh nhầm lẫn trong `package-info.java`, có thể dùng fully qualified name như ví dụ trên. Nếu dùng import, hãy kiểm tra import thực tế trong IDE.

## 5. Đặt tên interface rõ ràng và khớp với allowlist

Tên Named Interface được dùng trong `allowedDependencies`. Ví dụ:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Consumer khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: spi"
)
package com.acme.shop.shipping;
```

Tên `order` là logical module name; `spi` là tên Named Interface. Hai phần được phân cách bằng `::`. Tên phải khớp chính xác với module model, bao gồm chữ hoa/thường.

Nếu `@NamedInterface` trên package không truyền tên, Spring Modulith dùng local name của package làm tên mặc định. Ví dụ package `com.acme.shop.order.spi` có tên mặc định là `spi`. Để giảm nhầm lẫn, nhất là khi package có tên chung như `api`, `shared` hoặc `integration`, nên khai báo tên rõ ràng.

Một package hoặc type có thể được gán nhiều tên interface khi thực sự thuộc nhiều hợp đồng:

```java
@org.springframework.modulith.NamedInterface({"spi", "legacy-contract"})
package com.acme.shop.order.spi;
```

Khi đó, consumer có thể khai báo dependency đến một trong các tên đã công bố. Hãy kiểm tra danh sách tên trong module model thay vì suy luận từ package name.

## 6. Công bố type riêng lẻ khi chưa thể gom package

Nếu các type dùng chung nằm rải rác trong legacy package, có thể đánh dấu trực tiếp type thay vì chuyển toàn bộ class vào một package mới:

```java
package com.acme.shop.order.legacy;

@org.springframework.modulith.NamedInterface("spi")
public interface LegacyOrderLookup {

    OrderSummary findSummary(OrderId id);
}
```

`@NamedInterface` hỗ trợ target `PACKAGE` và `TYPE`. Khi đặt trên type, annotation gán type đó vào Named Interface. Đây là lựa chọn phù hợp khi chỉ một số type cần được công bố và nhóm chưa thể thay đổi package structure.

Với type-level annotation, nên truyền tên interface rõ ràng. Nếu nhiều type được đánh dấu cùng tên `spi`, chúng sẽ thuộc cùng Named Interface `spi` của module sở hữu.

## 7. Kiểm tra `propagate` của type-level annotation

Từ Spring Modulith 2.0, `@NamedInterface` có thuộc tính `propagate`, mặc định là `true`. Khi bật, các type xuất hiện trong public method signature (tham số hoặc kiểu trả về) của type đã đánh dấu và nằm trong cùng package space cũng được xem là thuộc Named Interface đó.

Ví dụ:

```java
package com.acme.shop.order.legacy;

@org.springframework.modulith.NamedInterface("spi")
public interface LegacyOrderLookup {

    OrderSummary findSummary(OrderId id);
}
```

Nếu `OrderSummary` và `OrderId` nằm trong cùng package space, propagation mặc định có thể đưa chúng vào `spi` cùng với `LegacyOrderLookup`. Nếu type liên quan nằm ngoài package space, đừng giả định annotation sẽ tự công bố type đó.

Khi muốn giới hạn interface chỉ gồm type được đánh dấu, đặt `propagate = false`:

```java
@org.springframework.modulith.NamedInterface(
    value = "spi",
    propagate = false
)
public interface LegacyOrderLookup {

    OrderSummary findSummary(OrderId id);
}
```

Khi tắt propagation, hãy đánh dấu hoặc công bố riêng các DTO/value type mà consumer cần tham chiếu. Nếu method signature trả về một type không thuộc Named Interface, consumer có thể tiếp tục gặp lỗi boundary dù interface chính đã được nhận diện.

## 8. Với Kotlin, dùng `@PackageInfo` trên metadata class

Kotlin không hỗ trợ `package-info.java`. Spring Modulith cho phép biểu diễn package metadata bằng một class được đánh dấu `@PackageInfo`:

```kotlin
package com.acme.shop.order.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
```

Đặt metadata class trong đúng package cần công bố. `@PackageInfo` cho Spring Modulith biết class này mang metadata của package; `@NamedInterface` đặt tên interface. Nếu thiếu `@PackageInfo`, annotation trên class có thể bị hiểu là gán interface cho một type thay vì mô tả package theo ý định.

## 9. Kiểm tra nested package và nested module

Named Interface được gắn cho package cụ thể. Đừng mặc định rằng annotation ở package cha sẽ công bố tất cả package con sâu hơn.

Ví dụ:

```text
order
└── spi
    ├── package-info.java       @NamedInterface("spi")
    ├── OrderLookup.java
    └── internal
        └── LookupImplementation.java
```

Package `order.spi.internal` là package riêng. Không đưa implementation vào hợp đồng chỉ vì nó nằm dưới `spi`. Nếu consumer thực sự cần type trong một package con khác, hãy công bố đúng package hoặc type đó theo chủ đích.

Ngoài ra, nếu package con được đánh dấu `@ApplicationModule`, Spring Modulith có thể nhận diện nó là nested application module. Trong trường hợp đó, package không còn đơn thuần là Named Interface của module cha. Hãy xem module arrangement và base package để xác định ownership trước khi chỉnh annotation.

## 10. Kiểm tra module model đã nhận Named Interface chưa

Không cần suy luận từ source code; có thể xem Named Interface thực tế mà Spring Modulith xây dựng:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class NamedInterfaceInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule order = modules.stream()
                .filter(module -> module.getBasePackage().getName()
                        .equals("com.acme.shop.order"))
                .findFirst()
                .orElseThrow();

        order.getNamedInterfaces().stream().forEach(namedInterface -> {
            System.out.println("Interface: " + namedInterface.getName());

            namedInterface.asJavaClasses()
                    .map(type -> type.getName())
                    .forEach(System.out::println);
        });
    }
}
```

Kết quả cho biết các interface mà module `order` thực sự công bố và danh sách class nằm trong từng interface. `getNamedInterfaces()` trả về cả interface mặc định không tên của package gốc lẫn những Named Interface được khai báo tường minh.

Có thể viết assertion để bảo vệ contract:

Trong test, sau khi tạo `modules` như ví dụ trên, lấy module `order` và xác nhận Named Interface cùng type cần công bố:

```java
import static org.assertj.core.api.Assertions.assertThat;

var order = modules.getModuleByName("order").orElseThrow();
var spi = order.getNamedInterfaces().getByName("spi");

assertThat(spi).isPresent();
assertThat(order.isExposed(OrderLookup.class)).isTrue();
```

Nếu `getByName("spi")` không có giá trị, vấn đề nằm ở quá trình phát hiện Named Interface hoặc tên khai báo. Nếu interface có tồn tại nhưng `OrderLookup` không được expose, kiểm tra type có nằm đúng package hoặc có được gán annotation hay không.

## 11. Kiểm tra custom `ApplicationModuleDetectionStrategy`

Một `ApplicationModuleDetectionStrategy` có thể tùy chỉnh cả cách phát hiện module root lẫn cách phát hiện Named Interface thông qua `detectNamedInterfaces(JavaPackage, ApplicationModuleInformation)`.

Nếu strategy chỉ override `detectNamedInterfaces()` bằng một builder như sau:

Đây là phần override trong một implementation của `ApplicationModuleDetectionStrategy`:

```java
import org.springframework.modulith.core.ApplicationModuleInformation;
import org.springframework.modulith.core.JavaPackage;
import org.springframework.modulith.core.NamedInterfaces;

@Override
public NamedInterfaces detectNamedInterfaces(
        JavaPackage basePackage,
        ApplicationModuleInformation information) {

    return NamedInterfaces.builder(basePackage)
            .recursive()
            .matching("api")
            .build();
}
```

thì thuật toán tùy chỉnh đang chọn các package có tên `api` theo quy tắc đã khai báo. Một package được đánh dấu `@NamedInterface("spi")` nhưng không khớp lựa chọn đó có thể không xuất hiện trong kết quả như nhóm mong đợi.

Nếu không cần quy tắc riêng, hãy giữ cơ chế mặc định để Spring Modulith đọc annotation `@NamedInterface`. Nếu có custom strategy, hãy xem lại implementation của `detectNamedInterfaces()` và bảo đảm nó đưa cả package/type được đánh dấu vào `NamedInterfaces` kết quả. Đừng chỉ kiểm tra `getModuleBasePackages()`; method đó chọn module root, không quyết định Named Interface.

`NamedInterfaces.Builder` hỗ trợ chọn package bằng `matching(…)`, `including(…)`, `recursive()` và loại trừ bằng `excluding(…)`. Khi tự xây dựng danh sách, builder vẫn đưa unnamed interface của package gốc vào kết quả vì đây là interface cần thiết của application module.

## 12. Phân biệt lỗi discovery với lỗi `allowedDependencies`

Hai lỗi này có biểu hiện gần giống nhau nhưng cần xử lý khác nhau:

| Trạng thái | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `getByName("spi")` không tìm thấy interface | Package/type annotation chưa được phát hiện hoặc custom strategy bỏ qua | Sửa package metadata, source set hoặc `detectNamedInterfaces()` |
| Interface `spi` có trong module model nhưng consumer bị báo dependency không được phép | Consumer khai báo allowlist sai hoặc thiếu | Sửa `allowedDependencies` ở package của consumer |
| Consumer dùng được API root nhưng không dùng được `spi` | Allowlist chỉ cho phép module gốc hoặc tên interface chưa được thêm | Khai báo `order :: spi` nếu consumer cần Named Interface này |
| Consumer dùng `spi` được nhưng vẫn bị báo internal access | Type thực tế nằm ngoài interface, trong package khác hoặc trong nested module | Kiểm tra package của target type và danh sách class trong Named Interface |

Ví dụ consumer chỉ được phép dùng `order.spi`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: spi"
)
package com.acme.shop.shipping;
```

Nếu consumer cần API mặc định của `order` và tất cả Named Interface, có thể dùng `order :: **`. `order :: *` chỉ bao phủ các Named Interface được khai báo tường minh, không bao gồm API package gốc. Hãy chọn allowlist hẹp nhất phù hợp với hợp đồng consumer cần.

Nếu consumer không khai báo `allowedDependencies`, các API đã công bố của module đích có thể được sử dụng theo quy tắc mặc định. Vì vậy, một Named Interface được phát hiện nhưng vẫn không sử dụng được thường gợi ý rằng consumer đã khai báo allowlist hoặc type đang nằm ngoài interface thực tế.

## 13. Không dùng `OPEN` để che lỗi Named Interface

Đánh dấu module `OPEN` bằng `@ApplicationModule(type = Type.OPEN)` có thể cho phép truy cập rộng vào các package con. Trong open module, các type trong sub-package được đưa vào unnamed interface trừ khi đã được gán tường minh vào Named Interface.

Điều đó có thể khiến một số reference không còn bị báo internal access, nhưng không chứng minh Named Interface mong muốn đã được nhận diện. Nếu consumer cần `order :: spi`, hãy xác nhận interface `spi` tồn tại thay vì mở toàn bộ module để bỏ qua lỗi.

Open module có thể hữu ích trong quá trình chuyển đổi legacy, nhưng làm giảm khả năng bảo vệ internal package. Hãy dùng nó như quyết định migration có chủ đích, không phải cách sửa mặc định cho annotation hoặc allowlist sai.

## 14. Quy trình chẩn đoán theo thứ tự

Khi Named Interface không được nhận diện, thực hiện lần lượt:

1. **Xác nhận module owner:** tạo `ApplicationModules` và kiểm tra module gốc cùng base package.
2. **Xác nhận vị trí package:** package cần công bố phải nằm trong module owner và không bị nhận diện thành module khác.
3. **Kiểm tra metadata:** với Java, kiểm tra `package-info.java`; với Kotlin, kiểm tra `@PackageInfo` trên metadata class.
4. **Kiểm tra annotation:** dùng đúng `org.springframework.modulith.NamedInterface`, target package hoặc type phù hợp.
5. **Kiểm tra tên:** so sánh `value`/`name` với tên trả về từ `getNamedInterfaces()`; nhớ tên package mặc định nếu không truyền giá trị.
6. **Kiểm tra propagation:** nếu đánh dấu type, xem `propagate` và các type trong public signature.
7. **Kiểm tra custom strategy:** xác nhận `detectNamedInterfaces()` không bỏ qua package annotation.
8. **Kiểm tra consumer allowlist:** xác nhận `allowedDependencies` dùng đúng `module :: interface`.
9. **Chạy verification:** gọi `ApplicationModules.verify()` để xác nhận boundary sau khi sửa.

Nếu đã sửa source nhưng model vẫn hiển thị metadata cũ, xác nhận file đã nằm trong source set được biên dịch và output build phản ánh thay đổi. Sau đó chạy lại architecture test trong môi trường build của dự án để tạo model mới.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy `spi` trong `getNamedInterfaces()` | Thiếu hoặc đặt sai `package-info.java` | Đặt file trong đúng package và source root |
| Annotation có trong source nhưng model không thấy | Import nhầm `core.NamedInterface` hoặc class chưa được biên dịch | Dùng annotation `org.springframework.modulith.NamedInterface` và kiểm tra compiled source |
| Tên interface hiển thị khác mong đợi | Không truyền tên, framework dùng local package name | Khai báo `@NamedInterface("spi")` rõ ràng |
| Package con không được expose | Chỉ đánh dấu package cha hoặc consumer dùng type ở package sâu hơn | Đánh dấu đúng package/type cần công bố hoặc cấu hình custom detection phù hợp |
| DTO trong public signature vẫn bị internal access | `propagate` bị tắt hoặc DTO nằm ngoài package space | Bật propagation hoặc công bố DTO riêng |
| Type được đánh dấu nhưng interface không xuất hiện | Type annotation thiếu tên hoặc custom discovery không chọn type | Gán tên tường minh và kiểm tra strategy |
| `order :: spi` bị báo không tồn tại | Sai logical module name hoặc sai interface name | Đọc tên thực tế từ module model và sửa allowlist consumer |
| `@NamedInterface` không tạo API mới | Đang đánh dấu module root hoặc package ngoài module | Nhớ root package đã là API mặc định; chọn package con thuộc module |
| Reference hết lỗi sau khi module thành `OPEN` | Internal access được nới lỏng trên toàn module | Xác nhận lại Named Interface và cân nhắc đóng module khi hoàn tất migration |

## 16. Ghi nhớ

Named Interface không được nhận diện thường xuất phát từ một trong bốn nhóm nguyên nhân: module owner chưa được phát hiện đúng, package metadata đặt sai vị trí hoặc sai annotation, custom `detectNamedInterfaces()` bỏ qua package/type, hoặc tên interface trong consumer allowlist không khớp với module model.

Với Java, đặt `@NamedInterface` trong `package-info.java` của package cần công bố. Với Kotlin, dùng `@PackageInfo` trên metadata class. Với type rải rác, gắn annotation trực tiếp lên type và kiểm tra `propagate` mặc định là `true` từ Spring Modulith 2.0. Dùng `ApplicationModule.getNamedInterfaces()` để xem tên và các type thực tế được công bố; sau đó kiểm tra `allowedDependencies` ở phía consumer theo cú pháp `module :: interface`.

Named Interface chỉ công bố một phần API của module, không tạo module mới, không mở toàn bộ package nội bộ và không thay thế module detection. Khi chẩn đoán, hãy kiểm tra module owner trước, xác nhận metadata và tên interface tiếp theo, rồi mới sửa allowlist hoặc chạy `ApplicationModules.verify()`.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `NamedInterface` annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith API — `ApplicationModule.getNamedInterfaces()`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API — `NamedInterfaces` and `NamedInterfaces.Builder`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterfaces.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy.detectNamedInterfaces()`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
