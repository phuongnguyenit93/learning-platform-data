# `@ApplicationModule` và các thuộc tính chính

`@ApplicationModule` là annotation của Spring Modulith dùng để bổ sung metadata và quy tắc cho một application module. Thông qua annotation này, ta có thể đặt định danh và tên hiển thị cho module, giới hạn những module mà nó được phép phụ thuộc, hoặc chọn module ở trạng thái `OPEN` hay `CLOSED`.

Annotation thường được đặt trong `package-info.java` tại package gốc của module. Cách đặt này giúp metadata nằm ngay cạnh ranh giới package mà nó mô tả. Với Kotlin hoặc trường hợp không sử dụng `package-info.java`, có thể đặt annotation trên một type nằm trong package gốc của module.

## 1. Vai trò của `@ApplicationModule`

Giả sử ứng dụng Spring Boot có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   └── internal
├── orders
│   ├── OrderManagement.java
│   └── internal
└── inventory
    ├── StockAvailability.java
    └── internal
```

Theo chiến lược phát hiện mặc định, các package con trực tiếp `catalog`, `orders` và `inventory` được nhận diện là application module. Ta không cần thêm `@ApplicationModule` chỉ để Spring Modulith nhìn thấy chúng. Annotation được dùng khi muốn bổ sung metadata hoặc quy tắc cụ thể cho một module.

Ví dụ, module `orders` cần tên hiển thị dễ đọc và chỉ được phép phụ thuộc vào `catalog` cùng named interface `api` của `inventory`. Ta khai báo trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng",
    allowedDependencies = {"catalog", "inventory::api"}
)
package com.example.shop.orders;
```

Annotation này mô tả metadata của module `orders`. Nó không tạo Spring bean, không tạo tiến trình riêng và không biến package thành Gradle project.

## 2. Các thuộc tính chính

`@ApplicationModule` có bốn thuộc tính thường được dùng:

| Thuộc tính | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `id` | Định danh kỹ thuật của module | Chuỗi rỗng; Spring Modulith suy ra định danh theo mô hình module nếu không khai báo |
| `displayName` | Tên thân thiện dành cho tài liệu và hiển thị | Chuỗi rỗng; tên hiển thị được suy ra từ module nếu không khai báo |
| `allowedDependencies` | Danh sách module hoặc named interface mà module được phép phụ thuộc | Mặc định không giới hạn dependency giữa application module |
| `type` | Loại module, `CLOSED` hoặc `OPEN` | `CLOSED` |

Các thuộc tính có thể được kết hợp trong cùng một annotation. Không cần khai báo thuộc tính nếu muốn dùng hành vi mặc định của nó.

## 3. `id`: định danh kỹ thuật của module

`id` xác định module bằng một định danh ổn định. Định danh này có thể được dùng trong các cấu hình tham chiếu module, chẳng hạn `allowedDependencies`, hoặc trong những tính năng Spring Modulith cần nhận diện module.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    id = "order-processing"
)
package com.example.shop.orders;
```

Ở đây package gốc vẫn là `com.example.shop.orders`, còn định danh logic được đặt thành `order-processing`. Package cho biết vị trí mã nguồn; `id` cho biết tên nhận diện module trong mô hình.

Một số nguyên tắc khi chọn `id`:

- Chọn tên ngắn, rõ nghĩa và ổn định.
- Không chứa dấu `::`, vì dấu này được Spring Modulith dùng để phân tách tên module với tên named interface.
- Không dùng display name làm định danh kỹ thuật.
- Nếu thay đổi `id`, hãy rà soát các cấu hình khác đang tham chiếu tới định danh cũ.

Nếu không khai báo `id`, Spring Modulith sử dụng định danh suy ra từ cấu trúc module. Với module đơn giản, định danh thường tương ứng tên package con, chẳng hạn `orders`.

## 4. `displayName`: tên dành cho người đọc

`displayName` là tên dễ đọc được dùng trong tài liệu và các biểu diễn của mô hình module. Nó cho phép giữ tên package ngắn, ổn định trong mã nguồn nhưng vẫn có nhãn diễn đạt trách nhiệm nghiệp vụ.

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng"
)
package com.example.shop.orders;
```

Khi tạo tài liệu kiến trúc, module có thể được trình bày bằng tên `Quản lý đơn hàng` thay vì chỉ hiển thị `orders`.

`displayName` không quyết định package nào thuộc module và không được dùng thay cho `id` trong `allowedDependencies`. Ta có thể thay đổi cách diễn đạt tên hiển thị mà không cần đổi package hoặc định danh kỹ thuật.

## 5. `allowedDependencies`: giới hạn hướng phụ thuộc

`allowedDependencies` khai báo những application module mà module hiện tại được phép phụ thuộc. Đây là allow-list ở cấp module, giúp biến hướng phụ thuộc mong muốn thành quy tắc có thể kiểm tra.

Ví dụ, `orders` chỉ được phép dùng module `catalog` và named interface `api` của `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"catalog", "inventory::api"}
)
package com.example.shop.orders;
```

Các dạng khai báo thường gặp:

| Giá trị | Phạm vi được phép |
|---|---|
| `"catalog"` | Cho phép phụ thuộc vào API ở base package (unnamed/default interface) của module `catalog` |
| `"inventory::api"` | Chỉ cho phép phụ thuộc vào named interface `api` của module `inventory` |
| `"billing::*"` | Cho phép tất cả named interface được khai báo tường minh của `billing`, không bao gồm base package |
| `"billing::**"` | Cho phép toàn bộ phần được công khai của `billing`, gồm base package và các named interface |

### Phân biệt bỏ qua thuộc tính và khai báo mảng rỗng

Đây là chi tiết quan trọng của `allowedDependencies`:

```java
// Không đặt allow-list: không giới hạn dependency bằng thuộc tính này.
@org.springframework.modulith.ApplicationModule(
    displayName = "Quản lý đơn hàng"
)
package com.example.shop.orders;
```

```java
// Allow-list rỗng tường minh: không cho phép dependency tới application module khác.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {}
)
package com.example.shop.orders;
```

Không khai báo thuộc tính nghĩa là dùng giá trị mặc định, không giới hạn dependency bằng allow-list. Ngược lại, khai báo mảng rỗng một cách tường minh có nghĩa là không cho phép dependency đến module khác. Hai cấu hình này không tương đương nhau.

Các type không được gán vào application module nào, chẳng hạn một số type nằm trực tiếp trong application root package, không được xem là dependency đến một application module khác trong allow-list này. Quy tắc này cũng không thay thế dependency của Java hoặc dependency thư viện bên ngoài.

## 6. `type`: module OPEN và CLOSED

`type` xác định cách Spring Modulith áp dụng quy tắc truy cập package nội bộ:

- `Type.CLOSED` là mặc định. Base package là API mặc định; sub-package được xem là nội bộ, trừ package được công khai bằng named interface.
- `Type.OPEN` nới lỏng việc truy cập các type nội bộ của module. Các type ở sub-package cũng được đưa vào unnamed interface, trừ type hoặc package đã được gán named interface riêng. Open module cũng bị loại khỏi thuật toán phát hiện chu trình phụ thuộc.

Ví dụ khai báo module legacy là open:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.inventory;
```

Với module mới hoặc đã có boundary rõ ràng, nên giữ `CLOSED`. `OPEN` chủ yếu hữu ích khi chuyển đổi codebase hiện hữu theo từng bước, trong đó nhiều module vẫn đang truy cập trực tiếp các package con của nhau.

`OPEN` không thay đổi Java visibility, không tự tạo bean và không bỏ qua mọi quy tắc dependency. Ví dụ, một lớp package-private vẫn không thể được import từ package khác theo quy tắc Java; `allowedDependencies` của module sử dụng cũng tiếp tục có ý nghĩa riêng.

## 7. Đặt annotation ở đâu?

### Java: package-info.java

Với Java, cách phổ biến là đặt annotation trong `package-info.java` tại package gốc của module:

```text
src/main/java/com/example/shop/orders/
├── package-info.java
├── OrderManagement.java
└── internal/
    └── OrderService.java
```

Nội dung `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng",
    allowedDependencies = {"catalog", "inventory::api"},
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.example.shop.orders;
```

Annotation đặt ở package gốc mô tả module `orders` và áp dụng cho module đó. Không đặt nó trong `orders.internal` nếu mục đích là cấu hình toàn module.

### Kotlin: đặt annotation trên type ở module root

Kotlin không có `package-info.java`. Có thể đặt `@ApplicationModule` trên một type nằm trong package gốc của module:

```kotlin
package com.example.shop.orders

import org.springframework.modulith.ApplicationModule

@ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng",
    allowedDependencies = ["catalog", "inventory::api"],
    type = ApplicationModule.Type.CLOSED
)
class ModuleMetadata
```

Type metadata này cần nằm trong module root package để Spring Modulith nhận diện thông tin cho đúng module.

## 8. `@ApplicationModule` và chiến lược phát hiện module

Cần phân biệt việc phát hiện module với việc tùy chỉnh metadata của module:

- Với chiến lược mặc định `direct-subpackages`, các package con trực tiếp của application root package được nhận diện là module. `@ApplicationModule` bổ sung metadata hoặc quy tắc cho những module đó.
- Với chiến lược `explicitly-annotated`, chỉ các package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` mới được nhận diện theo chiến lược tường minh.

Có thể bật explicit detection trong `application.properties`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Do đó, không nên cho rằng chỉ cần thêm `@ApplicationModule` là package ở bất kỳ vị trí nào cũng tự trở thành application module. Phạm vi và cách phát hiện vẫn phụ thuộc detection strategy đang được cấu hình.

## 9. Kiểm tra các thuộc tính bằng ApplicationModules

Sau khi khai báo annotation, ta có thể tạo mô hình và gọi `verify()` trong bài kiểm thử kiến trúc:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleConfiguration() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình đang áp dụng, bao gồm dependency giữa module, truy cập package nội bộ và chu trình phụ thuộc. Nếu module khai báo `allowedDependencies`, các dependency thực tế cần phù hợp với allow-list.

Khi kiểm tra lỗi, hãy xem lại từng thuộc tính theo câu hỏi:

- `id`: module được nhận diện bằng định danh nào và cấu hình tham chiếu đã dùng đúng tên chưa?
- `displayName`: tên hiển thị có diễn đạt đúng trách nhiệm nghiệp vụ không?
- `allowedDependencies`: module có được phép dùng module hoặc named interface đang tham chiếu không?
- `type`: module có nên được đóng kín hay đang cần trạng thái open tạm thời?

## 10. Những lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `displayName` trong `allowedDependencies` | Không khớp tên định danh module | Dùng logical module name mà Spring Modulith nhận diện, không dùng nhãn hiển thị |
| Đặt `id` chứa `::` | Xung đột cú pháp phân tách named interface | Chọn id không có dấu `::` |
| Khai báo `allowedDependencies = {}` khi muốn không giới hạn | Cấm dependency đến mọi application module khác | Bỏ thuộc tính để dùng giá trị mặc định |
| Cho rằng `@ApplicationModule` luôn tự phát hiện module | Package có thể không được chọn bởi detection strategy hiện tại | Kiểm tra `spring.modulith.detection-strategy` và vị trí package |
| Đánh dấu mọi module là `OPEN` | Giảm khả năng bảo vệ internal package và bỏ module khỏi cycle detection | Chỉ dùng OPEN cho nhu cầu chuyển đổi legacy có kế hoạch |
| Đặt annotation ở sub-package nội bộ | Metadata có thể gắn với sai phạm vi module | Đặt ở module root package hoặc type metadata tại đó |

## 11. Quy trình sử dụng

Khi cấu hình một application module, hãy xác định package root và trách nhiệm nghiệp vụ trước. Sau đó chọn `id` ổn định, `displayName` dễ hiểu, chỉ khai báo `allowedDependencies` khi muốn giới hạn hướng phụ thuộc, và giữ `type = CLOSED` trừ khi có lý do chuyển đổi cụ thể.

Đặt annotation ở `package-info.java` của module trong Java hoặc type metadata ở module root trong Kotlin. Cuối cùng, tạo `ApplicationModules` và chạy `verify()` để xác nhận metadata cùng các quy tắc đã khai báo phù hợp với package tree và dependency thực tế.

Tài liệu tham khảo: [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html), [ApplicationModule Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html), [ApplicationModule.Type Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html).
