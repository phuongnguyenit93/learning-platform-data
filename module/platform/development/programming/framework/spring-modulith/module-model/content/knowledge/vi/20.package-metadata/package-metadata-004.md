# @ApplicationModule trên package metadata

Spring Modulith cho phép đặt metadata của một application module ngay trên package gốc thông qua `package-info.java`. Đây là vị trí phù hợp để khai báo identifier, tên hiển thị, các module được phép phụ thuộc và kiểu module. Khi đọc package tree, developer có thể nhìn thấy quy ước kiến trúc nằm cạnh chính package mà nó điều chỉnh.

`@ApplicationModule` có thể được đặt trên package hoặc type (`@Target({ PACKAGE, TYPE })`). Annotation có retention ở runtime (`@Retention(RUNTIME)`), nên Spring Modulith có thể đọc metadata đã biên dịch khi xây dựng `ApplicationModules` và kiểm tra kiến trúc. Trong Java, cách thông dụng là đặt annotation trên `package-info.java` của package gốc module.

## 1. package-info.java là metadata của package

Trong Java, `package-info.java` là file dành cho package annotation và package documentation. File phải nằm trong thư mục tương ứng với package:

```text
src/main/java
└── com/acme/shop
    ├── ShopApplication.java
    ├── orders
    │   ├── package-info.java
    │   ├── OrderManagement.java
    │   └── internal
    │       └── OrderRepository.java
    └── catalog
        ├── package-info.java
        └── ProductManagement.java
```

Ví dụ, file `src/main/java/com/acme/shop/orders/package-info.java` có nội dung:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Order Management"
)
package com.acme.shop.orders;
```

Package declaration xác định chính xác package mà annotation áp dụng. Vì package annotation được khai báo trước câu lệnh `package`, ví dụ dùng tên đầy đủ `org.springframework.modulith.ApplicationModule` để tránh đặt import sai vị trí.

Khi biên dịch, compiler tạo metadata package trong `package-info.class`. Đặt file sai thư mục, sai tên package hoặc ngoài source set được biên dịch có thể khiến metadata không xuất hiện trong mô hình mà Spring Modulith phân tích.

## 2. Các thuộc tính của @ApplicationModule

Annotation `org.springframework.modulith.ApplicationModule` hiện cung cấp bốn thuộc tính chính:

| Thuộc tính | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `id` | Identifier logic của module | Chuỗi rỗng, Spring Modulith suy ra tên từ package |
| `displayName` | Tên dễ đọc dùng trong tài liệu và hiển thị | Chuỗi rỗng |
| `allowedDependencies` | Danh sách module hoặc named interface mà module được phép phụ thuộc | Không giới hạn allowlist tường minh |
| `type` | Kiểu module, `CLOSED` hoặc `OPEN` | `CLOSED` |

Có thể khai báo nhiều thuộc tính cùng lúc trong một package metadata:

```java
@org.springframework.modulith.ApplicationModule(
        id = "orders",
        displayName = "Order Management",
        allowedDependencies = {
                "catalog",
                "customers::customer-api"
        },
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.orders;
```

Trong ví dụ này, module có identifier `orders`, tên hiển thị `Order Management`, được phép phụ thuộc API gốc của `catalog` và named interface `customer-api` của `customers`. Kiểu `CLOSED` giữ các package nội bộ ở trạng thái không được module khác truy cập.

`id` là tên kỹ thuật dùng trong các cấu hình tham chiếu module; không dùng `displayName` trong `allowedDependencies`. Identifier không được chứa `::`, vì dấu phân cách này dành cho cú pháp `module::named-interface`.

Nếu bỏ `allowedDependencies`, module không bật allowlist tường minh. Nếu khai báo mảng rỗng, module không được phép phụ thuộc module khác (ngoại trừ các quy tắc shared module áp dụng ở cấp ứng dụng). Nếu khai báo một hoặc nhiều entry, các phụ thuộc tới module khác phải khớp danh sách được cho phép.

Tên module trong allowlist là tên cục bộ theo mặc định. Nếu ứng dụng bật `@Modulithic(useFullyQualifiedModuleNames = true)`, hãy dùng tên package đầy đủ; nếu module có `id` tường minh, hãy dùng identifier đó. Với named interface, phần sau `::` phải khớp tên đã khai báo trong `@NamedInterface`.

## 3. Metadata điều chỉnh module đã được phát hiện

Theo chiến lược mặc định, Spring Modulith xem mỗi package con trực tiếp của package chứa lớp Spring Boot application là một application module. Ví dụ `com.acme.shop.orders` được phát hiện là module `orders`.

`package-info.java` của `com.acme.shop.orders` bổ sung thông tin cho module có base package đó. Nó không tạo một module mới có tên `package-info`, cũng không biến `orders.internal` thành module riêng chỉ vì package metadata tồn tại.

```text
com.acme.shop
├── ShopApplication.java
├── orders                  ← application module
│   ├── package-info.java   ← metadata của orders
│   ├── OrderManagement.java
│   └── internal            ← package nội bộ của orders
│       └── OrderRepository.java
└── catalog                 ← application module
    ├── package-info.java   ← metadata của catalog
    └── ProductManagement.java
```

Nếu ứng dụng dùng detection strategy `explicitly-annotated`, `@ApplicationModule` còn đóng vai trò đánh dấu package được chọn làm module. Với strategy mặc định, module được suy ra từ vị trí package; annotation trên package gốc bổ sung metadata và các quy tắc cho module đó.

## 4. CLOSED và OPEN module

`type` quyết định cách Spring Modulith xử lý khả năng truy cập tới phần nội bộ của module.

### CLOSED: giữ ranh giới API và internal

`CLOSED` là giá trị mặc định. Module chỉ expose API đã được chọn, thường là các public type trong package gốc và các named interface được khai báo. Các package con như `orders.internal` được xem là nội bộ; module khác không được tham chiếu các type ở đó.

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.orders;
```

Khai báo tường minh `CLOSED` thường không bắt buộc vì đó đã là mặc định, nhưng có thể giúp ý định kiến trúc dễ nhận biết khi đọc package metadata.

### OPEN: cho phép truy cập rộng vào internal

`OPEN` cho phép module khác truy cập các type nội bộ của module. Các type trong package gốc và các package con được đưa vào unnamed interface, trừ những type đã được gán rõ vào named interface. Điều này làm bề mặt được truy cập rộng hơn và giảm khả năng dùng cấu trúc package để bảo vệ internal.

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.legacy;
```

`OPEN` chủ yếu hữu ích khi đưa một codebase cũ vào Spring Modulith theo từng bước, trong lúc chưa thể tách ngay tất cả package nội bộ. Với module mới đã có ranh giới rõ, hãy ưu tiên `CLOSED` và expose đúng hợp đồng cần thiết qua named interface.

## 5. Đặt allowedDependencies trên package metadata

`allowedDependencies` được khai báo trên package gốc module tiêu thụ. Ví dụ module `orders` chỉ được phép dùng API của `catalog` và named interface `customer-api` của `customers`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
                "catalog",
                "customers::customer-api"
        }
)
package com.acme.shop.orders;
```

Module `customers` công khai named interface tương ứng trong package API:

```java
@org.springframework.modulith.NamedInterface("customer-api")
package com.acme.shop.customers.api;
```

`orders` có thể tham chiếu type trong `customers.api`, nhưng không được tham chiếu các package nội bộ khác của `customers`. Nếu cần cho phép mọi named interface, selector `customers::*` bao phủ các named interface đã khai báo; `customers::**` bao phủ cả API gốc và tất cả named interface.

Khai báo allowlist tại package metadata có ưu điểm là quy tắc được đặt ở phía module tiêu thụ, gần với ranh giới mà nó bảo vệ. Khi dependency mới được thêm, developer có thể cập nhật danh sách và để `ApplicationModules.verify()` phát hiện những tham chiếu ngoài chính sách.

## 6. Nested application module cũng dùng package metadata

Từ Spring Modulith 1.3, một application module có thể chứa nested module. Để tách một phần bên trong module cha thành module con, đặt `@ApplicationModule` trên package con muốn trở thành nested module.

Ví dụ:

```text
com.acme.shop
└── inventory
    ├── InventoryManagement.java
    ├── internal
    │   └── InventoryRepository.java
    └── replenishment
        ├── package-info.java   ← @ApplicationModule
        ├── ReplenishmentService.java
        └── internal
            └── SupplierGateway.java
```

File `inventory/replenishment/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Inventory Replenishment"
)
package com.acme.shop.inventory.replenishment;
```

`replenishment` trở thành nested module bên trong `inventory`. Code của nested module có thể truy cập module cha, kể cả phần internal của cha. Ngược lại, phần còn lại của ứng dụng chỉ được truy cập API được expose của nested module theo các quy tắc module. Cách này giúp phân tách nội bộ một module lớn mà vẫn giữ mối quan hệ cha-con rõ ràng.

## 7. Trường hợp không thể dùng package-info.java

Java hỗ trợ package annotation thông qua `package-info.java`. Một số ngôn ngữ JVM như Kotlin không có cơ chế package-info tương đương. Trong trường hợp đó, Spring Modulith cung cấp `@PackageInfo` để đánh dấu một type metadata thay thế.

Ví dụ Kotlin:

```kotlin
package com.acme.shop.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    displayName = "Order Management",
    allowedDependencies = ["catalog"]
)
@PackageInfo
class ModuleMetadata
```

Type metadata cần nằm trong package gốc của module. `@PackageInfo` cho Spring Modulith biết type đó đại diện cho package metadata, thay vì được xem như một component nghiệp vụ thông thường.

Trong Java, ưu tiên `package-info.java` để metadata gắn trực tiếp với package. Không cần tạo một class `ModuleMetadata` chỉ để thay thế cơ chế package annotation sẵn có của Java.

## 8. Kiểm tra metadata đã được áp dụng

Sau khi khai báo package metadata, tạo mô hình từ lớp ứng dụng và in các module:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(System.out::println);
```

Đầu ra mô hình hiển thị logical name, base package và các Spring bean được nhận diện. Có thể dùng cách này để xác nhận package gốc và metadata đã được đọc đúng.

Sau đó thêm kiểm thử kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesPackageMetadata() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc cấu trúc module, bao gồm chu trình phụ thuộc, truy cập API/internal và các phụ thuộc bị giới hạn bởi `allowedDependencies`. Nếu annotation không được áp dụng, hãy kiểm tra vị trí `package-info.java`, package declaration, source set và phiên bản Spring Modulith đang sử dụng.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt `package-info.java` sai thư mục | Annotation gắn với package khác hoặc không xuất hiện trong mô hình | Đặt file trong đúng đường dẫn package và kiểm tra package declaration |
| Viết sai tên package | Metadata không áp dụng cho module mong muốn | So khớp package declaration với base package của module |
| Dùng `displayName` trong `allowedDependencies` | Selector không khớp module identifier | Dùng `id` hoặc tên module được suy ra |
| Đặt `@ApplicationModule` trên class nghiệp vụ bất kỳ | Metadata có thể không được nhận như package metadata của module | Dùng package-info hoặc type metadata nằm trong package gốc |
| Đặt `OPEN` để sửa nhanh lỗi truy cập internal | Bề mặt API bị mở rộng và quy tắc che giấu internal suy yếu | Expose named interface hoặc tổ chức lại package nếu có thể |
| Nghĩ package con có `package-info.java` luôn là named interface | `@ApplicationModule` đánh dấu module; `@NamedInterface` đánh dấu API package | Chọn đúng annotation theo mục đích |
| Quên nested module cần được đánh dấu | Package con vẫn thuộc cấu trúc module cha theo quy tắc hiện hành | Đặt `@ApplicationModule` tại package con muốn tách thành nested module |
| Chỉ kiểm tra compile thành công | Java compile không xác nhận quy tắc module | Chạy `ApplicationModules.verify()` |

## 10. Checklist khai báo package metadata

- [ ] Đã xác định package gốc của application module.
- [ ] File `package-info.java` nằm trong đúng thư mục package ở source set phù hợp.
- [ ] Package declaration khớp với base package cần cấu hình.
- [ ] `id` và `displayName` được dùng đúng mục đích.
- [ ] `allowedDependencies` chỉ liệt kê module hoặc named interface cần thiết.
- [ ] `type` là `CLOSED` trừ khi có lý do chuyển tiếp rõ ràng để dùng `OPEN`.
- [ ] Nested module được đánh dấu tại package con tương ứng nếu cần tách module cha.
- [ ] `ApplicationModules.of(...).verify()` được chạy trong kiểm thử kiến trúc.

Đặt `@ApplicationModule` trên package metadata giúp quy ước module được khai báo tập trung, dễ đọc và có thể kiểm chứng. Kết hợp `package-info.java`, named interface và `verify()` giúp giữ ranh giới giữa API, internal và các phụ thuộc được cho phép trong suốt quá trình phát triển.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [ApplicationModule.Type API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html)
- [PackageInfo annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
