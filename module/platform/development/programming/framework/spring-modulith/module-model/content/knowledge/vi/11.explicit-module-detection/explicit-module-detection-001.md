# Detection strategy `explicitly-annotated`

Spring Modulith mặc định nhận diện application module từ các package con trực tiếp của package chứa lớp ứng dụng Spring Boot. Cách này thuận tiện khi cấu trúc package đã được tổ chức theo nghiệp vụ. Với codebase lớn hoặc hệ thống cũ, có thể có nhiều package cấp cao chỉ phục vụ kỹ thuật, package dùng chung hoặc package chưa nên trở thành module độc lập. Trong trường hợp đó, chiến lược `explicitly-annotated` cho phép nhóm phát triển chỉ định rõ package nào là module.

Chiến lược này chỉ xem các package được đánh dấu tường minh bằng `@ApplicationModule` của Spring Modulith hoặc `@Module` của jMolecules là package gốc application module. Nhờ đó, việc phát hiện module dựa trên metadata kiến trúc do nhóm phát triển khai báo, thay vì tự động chọn mọi package con trực tiếp.

Trong `SPRING_MODULITH_MODULE_MODEL`, lựa chọn detection strategy ảnh hưởng trực tiếp đến cách Spring Modulith xây dựng ranh giới nghiệp vụ, API công khai và đồ thị phụ thuộc. Bài học này trình bày cách bật `explicitly-annotated`, đánh dấu module, tổ chức package và kiểm tra kết quả.

## 1. Khi nào cần phát hiện module tường minh?

Giả sử package gốc ứng dụng là `com.example.shop` và codebase có cấu trúc:

```text
com.example.shop
├── ShopApplication.java
├── inventory
├── order
├── payment
├── common
├── configuration
└── support
```

Với chiến lược mặc định `direct-sub-packages`, tất cả package con trực tiếp đều có thể được nhận diện thành module, bao gồm `common`, `configuration` và `support`. Nhưng trong thiết kế thực tế, ba package sau có thể chỉ là hạ tầng dùng chung hoặc cấu hình ứng dụng, không phải module nghiệp vụ độc lập.

Nếu chỉ muốn `inventory`, `order` và `payment` là các module, có thể đánh dấu chúng tường minh. Cách này hữu ích khi:

- Package cấp cao chứa nhiều thành phần kỹ thuật không phải module nghiệp vụ.
- Codebase legacy có cấu trúc package chưa thể tái tổ chức ngay.
- Nhóm muốn quyết định rõ package nào thuộc mô hình module và kiểm soát thay đổi đó qua code review.
- Ứng dụng có quy ước module riêng không phù hợp với cách phát hiện theo mọi package con trực tiếp.

## 2. Bật chiến lược `explicitly-annotated`

Đặt thuộc tính `spring.modulith.detection-strategy` thành `explicitly-annotated` trong cấu hình ứng dụng.

Với `application.properties`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Hoặc với `application.yml`:

```yaml
spring:
  modulith:
    detection-strategy: explicitly-annotated
```

Sau khi cấu hình, Spring Modulith chỉ chọn những package được đánh dấu bằng annotation module mà nó hỗ trợ. Các package con trực tiếp không được đánh dấu sẽ không tự động trở thành application module chỉ vì chúng nằm ngay dưới package gốc.

Thuộc tính này thay đổi chiến lược phát hiện module của mô hình Spring Modulith. Nó không thay đổi component scan của Spring Boot và không tự đăng ký hoặc loại bỏ Spring bean.

## 3. Đánh dấu module bằng `@ApplicationModule`

Với Java, cách thông dụng là tạo file `package-info.java` tại package gốc của module và gắn `@ApplicationModule`:

```java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

Ví dụ cấu trúc sau khi đánh dấu:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java       // @ApplicationModule
│   ├── InventoryManagement.java
│   └── internal
│       └── InventoryRepository.java
├── order
│   ├── package-info.java       // @ApplicationModule
│   └── OrderManagement.java
├── payment
│   ├── package-info.java       // @ApplicationModule
│   └── PaymentManagement.java
├── common
└── configuration
```

Với `explicitly-annotated`, ba package `inventory`, `order` và `payment` được chọn làm module. `common` và `configuration` không được tạo thành module độc lập nếu chúng không có annotation module phù hợp.

Annotation cần nằm đúng package mà bạn muốn làm module. Đặt `@ApplicationModule` trong `com.example.shop.inventory` sẽ đánh dấu package đó, không đánh dấu package gốc `com.example.shop` hay một package anh em khác.

### Kết hợp metadata module

`@ApplicationModule` vừa đánh dấu package là module vừa có thể khai báo metadata như tên hiển thị, loại module và các dependency được phép:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management",
    allowedDependencies = { "catalog", "pricing" }
)
package com.example.shop.inventory;
```

Trong ví dụ, `inventory` được phát hiện tường minh, có tên hiển thị dễ đọc và khai báo whitelist các module mà nó được phép phụ thuộc. Các package con như `inventory.internal` tiếp tục thuộc module `inventory`, trừ khi được đánh dấu riêng để tạo nested module theo khả năng của phiên bản Spring Modulith đang dùng.

## 4. Dùng annotation `@Module` của jMolecules

Ngoài `@ApplicationModule`, Spring Modulith cũng nhận diện package được đánh dấu bằng `@Module` của jMolecules khi sử dụng chiến lược `explicitly-annotated`.

Ví dụ trong `package-info.java`:

```java
@org.jmolecules.ddd.annotation.Module
package com.example.shop.customer;
```

Annotation này thuộc artifact `org.jmolecules:jmolecules-ddd`. Nếu chọn cách đánh dấu này, dự án cần khai báo dependency tương ứng và quản lý phiên bản theo BOM hoặc dependency management đang dùng.

```xml
<dependency>
    <groupId>org.jmolecules</groupId>
    <artifactId>jmolecules-ddd</artifactId>
</dependency>
```

`@Module` là một phần từ vựng kiến trúc DDD của jMolecules. `@ApplicationModule` là annotation do Spring Modulith cung cấp và có các thuộc tính riêng để mô tả module trong mô hình Modulith. Nếu dự án không sử dụng jMolecules, chỉ cần dùng `@ApplicationModule`; không cần thêm dependency chỉ để bật chiến lược explicit.

## 5. So sánh `direct-sub-packages` và `explicitly-annotated`

| Tiêu chí | `direct-sub-packages` | `explicitly-annotated` |
|---|---|---|
| Cách chọn module | Chọn mọi package con trực tiếp của root package | Chọn package được đánh dấu bằng annotation module được hỗ trợ |
| Cần annotation để phát hiện module cấp cao nhất? | Không | Có |
| Package kỹ thuật cấp trực tiếp | Có thể bị nhận diện thành module | Không được chọn nếu không đánh dấu |
| Khai báo module mới | Tạo package con trực tiếp trong phạm vi quét | Tạo package và đánh dấu tường minh |
| Kiểm soát ý định kiến trúc | Dựa nhiều vào vị trí package | Thể hiện trực tiếp trong metadata package |
| Phù hợp | Ứng dụng có package cấp cao đã phản ánh module | Codebase legacy hoặc ứng dụng cần chọn module có chủ đích |

Ví dụ với cùng package tree:

```text
com.example.shop
├── inventory          // @ApplicationModule
├── order              // @ApplicationModule
├── payment            // @ApplicationModule
├── common             // không đánh dấu
└── configuration      // không đánh dấu
```

- Với `direct-sub-packages`, năm package con trực tiếp đều có thể được nhận diện thành module.
- Với `explicitly-annotated`, chỉ `inventory`, `order` và `payment` được nhận diện theo các annotation đã khai báo.

## 6. Package không được đánh dấu được xử lý thế nào?

Khi dùng `explicitly-annotated`, package không có annotation module không tự trở thành module độc lập. Vai trò của nó phụ thuộc vào vị trí trong cây package:

- Nếu nó nằm bên dưới một module đã được nhận diện, nó thuộc cây package của module gần nhất và được xử lý theo quy tắc encapsulation của module đó.
- Nếu nó nằm trực tiếp dưới root package và không thuộc một module được nhận diện, nó không được tạo thành module độc lập bởi chiến lược explicit.
- Nếu package đó chứa code được module khác tham chiếu, hãy xem lại vị trí và quyền sở hữu. Một package chưa được gán vào module không nên trở thành nơi chia sẻ API nghiệp vụ tùy tiện.

Ví dụ:

```text
com.example.shop
├── inventory                 // @ApplicationModule
│   ├── InventoryManagement.java
│   └── internal              // không đánh dấu: thuộc inventory
├── order                     // @ApplicationModule
│   └── OrderManagement.java
└── common                    // không đánh dấu: không là module riêng
```

Trong cấu trúc này, `inventory.internal` không cần annotation riêng nếu nó chỉ là package nội bộ của `inventory`. Package `common` không được tự tạo thành module chỉ vì nó là package con trực tiếp. Nếu `common` thực sự là một module dùng chung, hãy đánh dấu nó và xác định rõ API cũng như các dependency của nó.

## 7. Nested module cũng cần được đánh dấu rõ ràng

Từ Spring Modulith 1.3, một module có thể chứa nested application module. Khi muốn một package con trở thành ranh giới module lồng bên trong module cha, đánh dấu package con đó bằng `@ApplicationModule`:

```text
com.example.shop
└── inventory                 // @ApplicationModule
    ├── InventoryManagement.java
    ├── internal               // package nội bộ
    └── replenishment          // @ApplicationModule
        ├── package-info.java
        └── ReplenishmentApi.java
```

`inventory.replenishment` được đánh dấu riêng nên có thể được mô hình hóa như nested module. Nếu không có annotation ở package con, nó vẫn thuộc module `inventory`.

Đừng đánh dấu mọi package con chỉ để làm cấu trúc trông đồng nhất. Chỉ tạo nested module khi package đó có trách nhiệm nghiệp vụ và ranh giới phụ thuộc đủ rõ để quản lý độc lập.

## 8. Đánh dấu module trong Kotlin

Kotlin không hỗ trợ `package-info.java`. Với module Kotlin, có thể đặt `@ApplicationModule` trên một kiểu nằm trong package gốc module:

```kotlin
package com.example.shop.inventory

import org.springframework.modulith.ApplicationModule

@ApplicationModule(
    displayName = "Inventory Management"
)
class ModuleMetadata
```

Kiểu `ModuleMetadata` đóng vai trò nơi lưu metadata module. Nó cần nằm trong package gốc của module mà bạn muốn đánh dấu. Nếu dùng chiến lược `explicitly-annotated`, Spring Modulith có thể dựa vào annotation trên kiểu đó để nhận diện package tương ứng.

Với Java, tiếp tục ưu tiên `package-info.java` vì annotation gắn trực tiếp với package và dễ quan sát trong cấu trúc source.

## 9. Kiểm tra kết quả phát hiện

Sau khi bật chiến lược explicit và đánh dấu các package, tạo mô hình bằng `ApplicationModules`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Bạn có thể kiểm tra module theo logical name:

```java
var inventory = modules.getModuleByName("inventory")
        .orElseThrow(() -> new IllegalStateException("inventory module not found"));

System.out.println(inventory.getIdentifier());
System.out.println(inventory.getBasePackage());
```

Nếu package không được phát hiện, hãy kiểm tra:

1. `spring.modulith.detection-strategy` đã được cấu hình đúng thành `explicitly-annotated` chưa?
2. `package-info.java` có nằm đúng thư mục source và đúng package không?
3. File `package-info.java` có được biên dịch và xuất hiện trên classpath đang được phân tích không?
4. Annotation có phải `@ApplicationModule` hoặc `@Module` của jMolecules mà Spring Modulith hỗ trợ không?
5. Package có nằm dưới root package đang được phân tích hoặc thuộc một root bổ sung đã cấu hình không?
6. Nếu dùng Kotlin, annotation có nằm trên một kiểu trong package gốc module không?

## 10. Kiểm tra dependency và ranh giới module

Phát hiện module đúng chưa đủ; cần kiểm tra các dependency có tuân thủ API và quy tắc kiến trúc hay không:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesExplicitlyDetectedModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc trên mô hình đã phát hiện, bao gồm truy cập package nội bộ, phụ thuộc vòng và dependency không được cho phép khi module khai báo whitelist. Nếu một module bị bỏ sót vì thiếu annotation, hãy bổ sung metadata hoặc điều chỉnh root package và detection strategy theo ý định kiến trúc.

Không nên đánh dấu một package thành module chỉ để làm cho một lỗi dependency biến mất. Hãy xác định package đó có trách nhiệm nghiệp vụ độc lập không, ai sở hữu API và hướng phụ thuộc nào là hợp lý.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `explicitly-annotated` vẫn tự chọn mọi package con trực tiếp | Chiến lược này chỉ chọn package được đánh dấu bằng annotation module được hỗ trợ. |
| Chỉ `@ApplicationModule` mới được chấp nhận | Spring Modulith cũng hỗ trợ jMolecules `@Module` khi dependency tương ứng có mặt. |
| Package không đánh dấu luôn bị xóa khỏi mô hình code | Nó không trở thành module độc lập; package con dưới một module đã nhận diện vẫn thuộc cây package của module đó. |
| Phải đánh dấu cả package `internal` | Không cần nếu package đó chỉ là phần triển khai nội bộ của module cha. |
| Annotation tự đăng ký Spring bean | Annotation dùng cho module detection và metadata; component scan vẫn là cơ chế riêng. |
| Bật explicit strategy làm thay đổi Java package | Nó thay đổi cách chọn package gốc module, không đổi tên hoặc vị trí package trong source code. |
| `verify()` tự tìm và đánh dấu module còn thiếu | Detection strategy và annotation quyết định module; `verify()` kiểm tra mô hình đã tạo. |

## 12. Checklist bật `explicitly-annotated`

- [ ] Xác định package gốc ứng dụng được dùng để phát hiện module.
- [ ] Bật `spring.modulith.detection-strategy=explicitly-annotated`.
- [ ] Đánh dấu từng package gốc module bằng `@ApplicationModule` hoặc jMolecules `@Module`.
- [ ] Đặt annotation trong `package-info.java` đối với Java.
- [ ] Với Kotlin, đặt `@ApplicationModule` trên một kiểu trong package gốc module.
- [ ] Không đánh dấu package con chỉ phục vụ triển khai nếu không muốn tạo nested module.
- [ ] Xem xét package trực tiếp dưới root nhưng không được đánh dấu; chúng không tự thành module.
- [ ] Xác nhận package metadata được biên dịch và hiện diện trên classpath.
- [ ] Quan sát kết quả bằng `ApplicationModules.of(...).forEach(...)`.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra dependency và encapsulation.

## 13. Kết luận

Detection strategy `explicitly-annotated` yêu cầu package được đánh dấu tường minh bằng `@ApplicationModule` của Spring Modulith hoặc `@Module` của jMolecules mới được chọn làm package gốc application module. Cấu hình này giúp kiểm soát chính xác module nào xuất hiện trong mô hình, đặc biệt hữu ích với codebase legacy hoặc cấu trúc có nhiều package kỹ thuật cấp cao.

Khi sử dụng chiến lược này, hãy đánh dấu đúng package gốc của từng module, giữ các package triển khai bên trong module sở hữu và chỉ tạo nested module khi có ranh giới nghiệp vụ thực sự. Kết hợp `ApplicationModules` để quan sát kết quả và `verify()` để kiểm tra dependency, từ đó giữ mô hình package nhất quán với kiến trúc modular monolith.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 1.2 — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/1.2/fundamentals.html)
- [Spring Modulith — `ApplicationModuleDetectionStrategy` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [jMolecules — GitHub project and DDD annotations](https://github.com/xmolecules/jmolecules)
