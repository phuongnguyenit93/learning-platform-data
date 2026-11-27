# Đổi package nhưng bảo toàn hợp đồng module

Bài này thuộc chương **Module identifier** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith mô hình hóa một ứng dụng Spring Boot thành các application module có ranh giới, API công khai và quan hệ phụ thuộc rõ ràng. Trong quá trình tái cấu trúc, nhóm có thể cần đổi tên hoặc di chuyển package của một module. Nếu tên module được suy ra trực tiếp từ package, thay đổi cấu trúc mã nguồn có thể kéo theo thay đổi tên logic mà các module khác đang tham chiếu.

Spring Modulith cho phép khai báo **logical module identifier** bằng thuộc tính `id` của `@ApplicationModule`. Nhờ đó, nhóm có thể thay đổi module base package nhưng giữ định danh logic ổn định, tiếp tục dùng tên đó trong `allowedDependencies` và các hợp đồng kiến trúc liên quan.

## 1. Package name và module identifier là hai khái niệm khác nhau

Một application module có ít nhất hai thông tin cần phân biệt:

- **Module base package** xác định package gốc và phạm vi các kiểu thuộc module.
- **Module identifier** là tên logic dùng để nhận diện module trong mô hình Spring Modulith.

Nếu không khai báo identifier tường minh, Spring Modulith tạo tên module dựa trên vị trí package tương đối với application base package. Ví dụ, khi ứng dụng quét từ `com.acme`, module ở `com.acme.foo.bar` có thể được đặt tên là `foo.bar`.

Điều đó có nghĩa đổi package từ `com.acme.shop.order` sang `com.acme.shop.orders` có thể làm tên module suy ra thay đổi từ `order` thành `orders`.

Có thể khai báo định danh logic độc lập với package:

~~~java
@org.springframework.modulith.ApplicationModule(id = "order")
package com.acme.shop.order;
~~~

Trong ví dụ này:

- `com.acme.shop.order` là module base package.
- `order` là logical module identifier.
- Các package con thuộc phạm vi module order theo quy tắc phát hiện đang sử dụng.

Khi package thay đổi, nhóm có thể giữ nguyên `id = "order"` để tên logic của module tiếp tục ổn định.

## 2. Đổi package nhưng giữ nguyên id

Giả sử ban đầu module order có cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── api
│       ├── package-info.java
│       └── OrderQuery.java
└── shipping
    └── package-info.java
~~~

File `order/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "order",
    displayName = "Order Management"
)
package com.acme.shop.order;
~~~

Package API được công khai với tên `api`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.order.api;
~~~

Module shipping được phép sử dụng API đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::api"
)
package com.acme.shop.shipping;
~~~

Sau khi tái cấu trúc, nhóm đổi module base package từ `com.acme.shop.order` thành `com.acme.shop.orders`:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── api
│       ├── package-info.java
│       └── OrderQuery.java
└── shipping
    └── package-info.java
~~~

File metadata mới:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "order",
    displayName = "Order Management"
)
package com.acme.shop.orders;
~~~

Named interface giữ tên `api`, nhưng package declaration chuyển theo package mới:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.orders.api;
~~~

Module shipping vẫn có thể khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order::api"
)
package com.acme.shop.shipping;
~~~

Tên logic `order` và tên named interface `api` không đổi, nên chuỗi dependency `order::api` vẫn giữ nguyên. Đây là lợi ích chính của việc tách logical identifier khỏi package name.

## 3. @ApplicationModule(id) khai báo điều gì?

Thuộc tính `id` của `@ApplicationModule` đặt identifier cho application module. Nếu bỏ qua thuộc tính này, giá trị mặc định là chuỗi rỗng và framework sử dụng quy tắc đặt tên dựa trên package/module source.

Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "order"
)
package com.acme.shop.orders;
~~~

Các điểm cần nhớ:

- `id` là tên logic của module.
- `id` không phải tên package Java.
- `id` có thể giữ ổn định qua thay đổi tên module base package.
- Giá trị `id` không được chứa dấu phân cách `::`, vì ký hiệu này được dùng để tham chiếu named interface.
- Mỗi module trong cùng mô hình cần có identifier riêng, không trùng với module khác.

Nếu cần tên hiển thị thân thiện trong tài liệu hoặc sơ đồ, dùng `displayName`:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "order",
    displayName = "Order Management"
)
package com.acme.shop.orders;
~~~

`id` phục vụ nhận diện logic; `displayName` phục vụ trình bày cho con người. Có thể đổi display name mà không cần đổi identifier.

## 4. Dependency tới module sử dụng logical identifier

Khi một module khai báo `allowedDependencies`, phần tên module trong chuỗi dependency cần khớp với logical identifier mà module cung cấp đã khai báo.

Ví dụ, inventory công khai named interface `availability`:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Module inventory có thể khai báo identifier riêng:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "inventory"
)
package com.acme.shop.inventory;
~~~

Module order cho phép phụ thuộc vào named interface đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "order",
    allowedDependencies = "inventory::availability"
)
package com.acme.shop.orders;
~~~

Cấu trúc dependency có thể được đọc như sau:

| Phần | Ý nghĩa |
|---|---|
| `inventory` | Logical identifier của module cung cấp. |
| `::` | Dấu phân cách module và named interface. |
| `availability` | Tên named interface được module cung cấp công khai. |

Nếu package inventory được đổi tên nhưng `id = "inventory"` và `@NamedInterface("availability")` được giữ nguyên, consumer vẫn tham chiếu `inventory::availability`.

Ngược lại, nếu đổi `id` thành `stock`, các consumer đang khai báo `inventory::availability` cần được cập nhật thành `stock::availability`.

## 5. Phân biệt id, displayName, package name và named interface name

Bốn loại tên này có vai trò khác nhau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Module base package | `com.acme.shop.orders` | Xác định phạm vi package và các kiểu thuộc module. |
| Logical module identifier | `order` | Định danh module trong mô hình và dependency declarations. |
| Display name | `Order Management` | Tên hiển thị trong tài liệu hoặc sơ đồ. |
| Named interface name | `api` | Định danh nhóm API công khai trong một module. |

Không nên dùng `displayName` thay cho `id`. Đổi display name chỉ thay đổi cách module được trình bày; nó không phải cách giữ hoặc thay đổi tên logic được tham chiếu trong dependency.

Tương tự, giữ nguyên `id` không làm package Java cũ tiếp tục tồn tại. Package base và tên đầy đủ của các class vẫn thay đổi theo refactor.

## 6. id không thay thế việc phát hiện module

Khai báo `@ApplicationModule(id = "order")` chỉ đặt định danh cho module đã được phát hiện. Nó không tự chọn package bất kỳ làm module base package và không tự mở rộng phạm vi quét của ứng dụng.

Với chiến lược mặc định, Spring Modulith tìm các application module trong package con trực tiếp của package chứa lớp `@SpringBootApplication`. Vì vậy, khi đổi package:

- Nếu package mới vẫn nằm đúng vị trí mà chiến lược phát hiện mặc định mong đợi, module tiếp tục được phát hiện theo quy ước đó.
- Nếu package mới chuyển sang vị trí lồng sâu hơn, nhóm cần xem xét chiến lược phát hiện module, nested module hoặc cách đánh dấu tường minh phù hợp.
- Nếu package mới nằm ngoài application base package, cần xem lại phạm vi khám phá module và cấu hình component scanning của Spring Boot.

Ví dụ, đổi `com.acme.shop.order` thành `com.acme.shop.orders` vẫn giữ module ở cấp package con trực tiếp của `com.acme.shop`. Nhưng chuyển thành `com.acme.shop.business.orders` có thể cần điều chỉnh cách phát hiện, vì `business` trở thành package con trực tiếp.

Do đó, hãy xử lý hai câu hỏi riêng:

1. Package mới có được Spring Modulith phát hiện là module base package không?
2. Sau khi được phát hiện, module có giữ logical identifier mong muốn không?

## 7. id không bảo toàn tên đầy đủ của class Java

Giữ `id` ổn định chỉ bảo toàn logical module identifier. Nó không giữ nguyên fully qualified class name, package declaration hoặc import của Java.

Ví dụ trước khi đổi package:

~~~java
import com.acme.shop.order.api.OrderQuery;
~~~

Sau khi chuyển sang package mới:

~~~java
import com.acme.shop.orders.api.OrderQuery;
~~~

Các phần sau vẫn cần được cập nhật theo package mới:

- `package` declaration trong file Java.
- `import` trong các consumer.
- `package-info.java` của module và named interface.
- Cấu hình component scanning, entity scanning hoặc cấu hình tích hợp dựa trên package nếu dự án có sử dụng.
- Reflection, serialization mapping hoặc cấu hình bên ngoài tham chiếu fully qualified class name.
- Test, fixture và tài liệu có ghi tên package cũ.

Logical identifier không phải bí danh package và không tạo ra lớp tương thích thay cho class đã di chuyển.

## 8. Kotlin có thể khai báo id bằng metadata carrier

Nếu dự án dùng Kotlin và không có `package-info.java`, đặt metadata trong một kiểu tại package gốc, đánh dấu bằng `@PackageInfo`:

~~~kotlin
package com.acme.shop.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    id = "order",
    displayName = "Order Management"
)
@PackageInfo
class ModuleMetadata
~~~

Named interface trong package con cũng có thể dùng metadata carrier:

~~~kotlin
package com.acme.shop.orders.api

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@NamedInterface("api")
@PackageInfo
class ModuleMetadata
~~~

Kiểu metadata carrier phải nằm trong đúng package mà nó mô tả. `@PackageInfo` cho Spring Modulith biết kiểu đó đại diện metadata package; `@ApplicationModule` đặt identifier module, còn `@NamedInterface` đặt tên API công khai.

## 9. Quy trình đổi package mà giữ hợp đồng module

Có thể thực hiện refactor theo trình tự:

1. **Ghi nhận identifier hiện tại.** Xác định logical id và display name của module.
2. **Ghi nhận các consumer.** Tìm các khai báo `allowedDependencies` đang tham chiếu module hoặc named interface.
3. **Chốt package đích.** Đảm bảo vị trí mới vẫn được module detection strategy nhận diện.
4. **Khai báo id tường minh.** Thêm `@ApplicationModule(id = "...")` trước hoặc trong cùng thay đổi đổi package.
5. **Di chuyển module và metadata.** Cập nhật package declaration của các class, package metadata và named interface.
6. **Giữ tên named interface nếu hợp đồng không đổi.** Nếu capability API vẫn giống nhau, tiếp tục dùng cùng tên như `api`, `availability` hoặc `spi`.
7. **Cập nhật Java references.** Sửa import, component scanning, reflection và cấu hình phụ thuộc vào package.
8. **Giữ dependency declarations.** Nếu logical id và named interface name không đổi, các chuỗi như `order::api` có thể giữ nguyên.
9. **Kiểm chứng mô hình.** Xác nhận module được phát hiện ở package mới, có identifier mong muốn và không vi phạm dependency rules.
10. **Cập nhật tài liệu.** Đồng bộ sơ đồ, package tree và hướng dẫn phát triển với vị trí mới.

Nếu chủ đích là đổi cả tên logic module, hãy coi đó là một thay đổi hợp đồng riêng: cập nhật tất cả consumer tham chiếu identifier cũ trong cùng kế hoạch migration.

## 10. Kiểm chứng module identifier sau khi đổi package

Sau khi di chuyển package, dùng `ApplicationModules` để xác minh cấu trúc:

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

API mô hình của Spring Modulith cung cấp `ApplicationModule.getIdentifier()` để đọc logical identifier và `getBasePackage()` để đọc module base package. Khi kiểm tra bằng code hoặc debugger, hai giá trị này giúp xác nhận package mới đã được gắn với identifier mong muốn.

Có thể dùng đoạn mã sau để quan sát mô hình:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

for (ApplicationModule module : modules) {
    System.out.printf(
        "id=%s, basePackage=%s%n",
        module.getIdentifier(),
        module.getBasePackage()
    );
}
~~~

Kết quả mong đợi sau refactor có dạng:

~~~text
id=order, basePackage=com.acme.shop.orders
id=inventory, basePackage=com.acme.shop.inventory
~~~

Tên package đã thay đổi nhưng logical identifier của order vẫn là `order`. Sau đó, `verify()` kiểm tra các dependency và quy tắc encapsulation theo mô hình mới.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Module có identifier mới ngoài dự kiến | Không khai báo `id`, nên tên được suy ra từ package mới. | Khai báo `@ApplicationModule(id = "...")` ổn định. |
| Module biến mất sau khi đổi package | Package mới không còn được detection strategy nhận diện. | Kiểm tra application base package và chiến lược phát hiện. |
| Consumer không còn dependency hợp lệ | `id` hoặc named interface name đã thay đổi nhưng `allowedDependencies` chưa cập nhật. | Đồng bộ identifier và chuỗi `module::interface`. |
| Java không biên dịch sau refactor | Import hoặc package declaration vẫn dùng tên cũ. | Cập nhật fully qualified class names. |
| Spring không tạo bean | Package mới nằm ngoài phạm vi component scanning hoặc cấu hình quét. | Kiểm tra component scan và cấu hình liên quan. |
| Hai module dùng cùng id | Identifier không còn phân biệt duy nhất module. | Chọn identifier riêng cho từng module. |
| Dùng displayName để giữ dependency | Nhầm tên hiển thị với logical identifier. | Dùng thuộc tính `id` cho tên logic. |

## Ghi nhớ

Package name xác định vị trí và phạm vi mã nguồn của application module; logical identifier xác định tên module trong mô hình Spring Modulith. Khi đổi package, khai báo `@ApplicationModule(id = "order")` giúp giữ identifier ổn định để các dependency như `order::api` tiếp tục tham chiếu đúng module và named interface.

Tuy nhiên, `id` không thay thế module detection, không giữ nguyên Java fully qualified class name và không tự cập nhật component scanning. Hãy giữ identifier cùng tên named interface nếu hợp đồng logic không đổi, cập nhật các tham chiếu package cần thiết và chạy `ApplicationModules.verify()` để xác nhận mô hình sau refactor.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — ApplicationModuleIdentifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html)
- [Spring Modulith — ApplicationModuleSource API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleSource.html)
