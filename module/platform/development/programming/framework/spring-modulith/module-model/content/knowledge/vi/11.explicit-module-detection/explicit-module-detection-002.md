# `@ApplicationModule` để đánh dấu package tường minh

Spring Modulith cần biết package nào đại diện cho một application module trước khi có thể xây dựng module model và kiểm tra dependency. Mặc định, framework xem các package con trực tiếp của package chứa lớp Spring Boot application là module. Với codebase có cấu trúc package không theo quy tắc đó, ta có thể chọn chiến lược phát hiện tường minh: chỉ những package được đánh dấu bằng `@ApplicationModule` hoặc annotation `@Module` của jMolecules mới được xem là module.

Trong Java, cách trực tiếp để đánh dấu một package là khai báo annotation trong file `package-info.java` của package đó. Khi kết hợp với cấu hình `spring.modulith.detection-strategy=explicitly-annotated`, marker này trở thành tín hiệu để Spring Modulith chọn package làm root của application module.

Điểm cần phân biệt là `@ApplicationModule` vừa mang metadata của module (chẳng hạn loại module và dependency được phép), vừa có thể đóng vai trò marker cho explicit detection. Chỉ thêm annotation mà không bật chiến lược explicit không có nghĩa toàn bộ cách phát hiện mặc định đã được thay thế.

## 1. Hai cách phát hiện module

Giả sử lớp khởi chạy nằm trong package `com.acme.shop`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Với chiến lược mặc định `direct-sub-packages`, Spring Modulith xem các package con trực tiếp của `com.acme.shop` là module:

```text
com.acme.shop
├── ShopApplication.java
├── order             -> application module
│   └── internal
├── inventory         -> application module
│   └── internal
└── customer          -> application module
    └── internal
```

Đây là lựa chọn thuận tiện khi mọi module đều nằm ngay dưới package ứng dụng. Tuy nhiên, có những dự án tổ chức package theo namespace hoặc theo nhiều nhóm chức năng:

```text
com.acme.shop
├── ShopApplication.java
├── business
│   ├── order
│   ├── inventory
│   └── customer
├── integration
│   ├── shipping
│   └── payment
└── support
    └── monitoring
```

Nếu giữ chiến lược mặc định, các package con trực tiếp như `business`, `integration` và `support` có thể trở thành module cấp cao. Điều đó có thể không phản ánh các capability mà nhóm muốn quản lý.

Explicit detection cho phép đánh dấu các package thực sự là module, ví dụ `business.order`, `business.inventory`, `business.customer`, `integration.shipping` và `integration.payment`. Những package nhóm như `business` hay `integration` không cần trở thành application module nếu chúng chỉ đóng vai trò namespace.

## 2. Đánh dấu package bằng `package-info.java`

Trong Java, package annotation được khai báo trong file `package-info.java` đặt ngay trong package tương ứng. Ví dụ, để đánh dấu `com.acme.shop.business.order` là một application module, tạo file:

`src/main/java/com/acme/shop/business/order/package-info.java`

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.business.order;
```

Tương tự, đánh dấu module `inventory`:

`src/main/java/com/acme/shop/business/inventory/package-info.java`

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.business.inventory;
```

Khi dùng chiến lược explicit, annotation là dấu hiệu để framework nhận diện package làm module root. Việc đánh dấu package cũng giúp metadata của module nằm cạnh code mà nó mô tả, thay vì phải duy trì một danh sách tên package ở nơi khác.

Không đặt file `package-info.java` ở package cha nếu ý định là đánh dấu package con. Ví dụ, `business/package-info.java` đánh dấu package `com.acme.shop.business`; nó không tự đánh dấu tất cả package con `order`, `inventory` và `customer` thành các module độc lập.

## 3. Bật chiến lược `explicitly-annotated`

Sau khi đánh dấu các package module, cấu hình chiến lược phát hiện trong cấu hình Spring Boot:

```yaml
spring:
  modulith:
    detection-strategy: explicitly-annotated
```

Hoặc dùng dạng properties:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Khi chiến lược này được sử dụng, Spring Modulith chỉ chọn những package được đánh dấu rõ ràng bằng `@ApplicationModule` hoặc annotation `@Module` của jMolecules làm module base package. Các package con trực tiếp không được đánh dấu không tự động trở thành module như trong chiến lược mặc định.

Ví dụ, với cây package:

```text
com.acme.shop
├── ShopApplication.java
├── business
│   ├── order
│   │   └── package-info.java       // @ApplicationModule
│   ├── inventory
│   │   └── package-info.java       // @ApplicationModule
│   └── customer
│       └── package-info.java       // @ApplicationModule
└── integration
    ├── shipping
    │   └── package-info.java       // @ApplicationModule
    └── payment
        └── package-info.java       // @ApplicationModule
```

Module model được xây dựng từ năm package đã đánh dấu. `business` và `integration` chỉ là namespace trong ví dụ này, không tự trở thành module chỉ vì chúng là package con trực tiếp của application root.

## 4. `@ApplicationModule` còn khai báo metadata của module

Annotation không chỉ đánh dấu package. Nó còn cho phép khai báo metadata kiến trúc ngay tại root package của module. Ví dụ, `order` có thể công bố tên hiển thị và danh sách dependency được phép:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Order management",
    allowedDependencies = {
        "inventory",
        "customer"
    }
)
package com.acme.shop.business.order;
```

Khi dùng explicit detection, package này được nhận diện là module nhờ annotation; `displayName` và `allowedDependencies` cung cấp thêm thông tin cho module model và quá trình verification.

Trong cấu hình package lồng nhau, tên module dùng trong `allowedDependencies` cần khớp với tên module mà Spring Modulith nhận diện. Hãy quan sát module model thực tế sau khi bật explicit detection thay vì tự suy luận tên từ tên thư mục.

## 5. Đánh dấu module lồng nhau

Spring Modulith hỗ trợ nested application modules. Tính năng này hữu ích khi một capability lớn có các phần con đủ độc lập để cần boundary riêng.

Ví dụ, module `inventory` có phần quản lý tồn kho và một nhóm chức năng reservation cần tách riêng:

```text
com.acme.shop
└── inventory
    ├── package-info.java             // module inventory
    ├── InventoryManagement.java
    └── reservation
        ├── package-info.java         // nested module reservation
        ├── ReservationManagement.java
        └── internal
            └── ReservationRepository.java
```

Đánh dấu package cha:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
```

Đánh dấu package lồng nhau:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory.reservation;
```

Khi dùng explicit detection, hãy đánh dấu rõ các package dự định làm module, bao gồm cả module cha và module lồng nhau nếu cả hai cần tồn tại như các đơn vị trong module model. Module lồng nhau giúp quản lý cấu trúc nội bộ của capability lớn mà vẫn giữ được quan hệ cha-con trong mô hình.

Không nên tách nested module chỉ vì package có nhiều lớp. Hãy tạo boundary riêng khi phần đó có trách nhiệm, API và dependency đủ rõ để được quản lý độc lập.

## 6. `@ApplicationModule` khác `@Modulithic` như thế nào?

Hai annotation này xuất hiện ở hai cấp khác nhau:

| Annotation | Vị trí thường dùng | Vai trò |
| --- | --- | --- |
| `@Modulithic` | Lớp ứng dụng hoặc lớp cấu hình gốc | Khai báo ứng dụng Modulith và các thiết lập ở cấp toàn ứng dụng, như `systemName` hoặc `additionalPackages` |
| `@ApplicationModule` | `package-info.java` của package module | Đánh dấu module và khai báo metadata của module như `displayName`, `type` hoặc `allowedDependencies` |

`@Modulithic` không thay thế marker `@ApplicationModule` khi chiến lược đang dùng là `explicitly-annotated`. Nó có thể giúp cấu hình các package root bổ sung, nhưng explicit strategy vẫn cần biết package nào trong phạm vi quét là module thông qua annotation module tương ứng.

## 7. Explicit detection và custom detection strategy

Explicit detection phù hợp khi nhóm muốn đánh dấu từng module trong source. Nếu quy tắc tổ chức phức tạp hơn, chẳng hạn module được xác định theo naming convention hoặc nằm ở nhiều package root, Spring Modulith còn cung cấp `ApplicationModuleDetectionStrategy` để tùy biến.

Strategy interface nhận package gốc và trả về các package được xem là module base package:

```java
package com.acme.shop;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

class CustomModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        // Chọn module base package theo quy ước của ứng dụng.
        return rootPackage.getDirectSubPackages().stream()
                .filter(pkg -> pkg.getName().endsWith(".module"));
    }
}
```

Đăng ký class strategy bằng thuộc tính `spring.modulith.detection-strategy` với tên đầy đủ của class. Ví dụ:

```properties
spring.modulith.detection-strategy=com.acme.shop.CustomModuleDetectionStrategy
```

Đoạn code trên chỉ minh họa cấu trúc triển khai; quy tắc lọc package phải phù hợp với naming convention thật của ứng dụng. Nếu strategy tùy chỉnh chỉ dùng trong test để kiểm tra hoặc tạo tài liệu, đăng ký nó trong test context. Nếu các thành phần runtime của Spring Modulith cũng cần sử dụng strategy đó, cần bảo đảm cấu hình và dependency runtime tương ứng có mặt.

Không nên tạo custom strategy khi `explicitly-annotated` đã đáp ứng nhu cầu. Custom strategy làm tăng code hạ tầng cần duy trì và kiểm thử.

## 8. Kiểm tra các module đã được phát hiện

Sau khi cấu hình explicit detection và thêm package annotation, tạo mô hình `ApplicationModules` để quan sát kết quả:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void printsDetectedModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra hai việc riêng biệt:

- **Detection:** các package dự định có được nhận diện thành module không? Có package nào vô tình bị bỏ sót hoặc được đánh dấu thừa không?
- **Verification:** các module đã phát hiện có tuân thủ quy tắc truy cập API, `allowedDependencies` và dependency cycle không?

Nếu module không xuất hiện, kiểm tra annotation có nằm đúng package, file `package-info.java` có đúng tên package và cấu hình `spring.modulith.detection-strategy` có được nạp trong test context hay không.

Nếu module xuất hiện nhưng verification thất bại, đọc violation để xác định dependency hoặc package boundary cần sửa. Đừng thay đổi chiến lược detection chỉ để làm mất lỗi verification; hai giai đoạn này trả lời hai câu hỏi khác nhau.

## 9. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có module nào được phát hiện theo explicit strategy | Các package module chưa được đánh dấu | Thêm `@ApplicationModule` hoặc `@Module` vào package dự định làm module |
| Package nhóm như `business` bị nhận diện thành module không mong muốn | Ứng dụng vẫn dùng chiến lược mặc định `direct-sub-packages` | Cấu hình `spring.modulith.detection-strategy=explicitly-annotated` nếu muốn chọn module bằng annotation |
| Annotation không có tác dụng | `package-info.java` khai báo sai tên package hoặc nằm sai thư mục source | Đối chiếu package declaration với đường dẫn source và package cần đánh dấu |
| Module cha có nhưng nested module không xuất hiện | Package con chưa được đánh dấu hoặc cấu hình discovery chưa phù hợp | Đánh dấu package lồng nhau bằng `@ApplicationModule` và kiểm tra module model |
| Test và runtime phát hiện module khác nhau | Test/runtime nạp cấu hình detection khác nhau | Đồng bộ property và strategy registration ở các môi trường cần dùng |
| Verification báo dependency mới sau khi chuyển sang explicit detection | Module boundary mới làm rõ quan hệ trước đây bị gom vào package nhóm | Kiểm tra ownership, API và `allowedDependencies` của các module mới |

## 10. Khi nào nên dùng explicit detection?

| Cấu trúc ứng dụng | Chiến lược phù hợp |
| --- | --- |
| Các module nằm trực tiếp dưới package ứng dụng | `direct-sub-packages` mặc định thường đơn giản nhất |
| Module nằm sâu dưới các package namespace như `business.order` | `explicitly-annotated` giúp đánh dấu chính xác package module |
| Có nested module bên trong capability lớn | Đánh dấu package nested bằng `@ApplicationModule`; chọn detection strategy phù hợp với toàn bộ module model |
| Module nằm ở nhiều package root hoặc theo quy tắc tên riêng | Cân nhắc `additionalPackages`, `ApplicationModuleSourceFactory` hoặc custom `ApplicationModuleDetectionStrategy` tùy phạm vi |

Explicit detection hữu ích khi cấu trúc package không thể hiện module bằng vị trí package con trực tiếp. Nó cũng làm ranh giới module hiện rõ ngay trong source. Đổi lại, nhóm phải duy trì marker cho tất cả module dự kiến và bảo đảm các môi trường dùng cùng cấu hình detection.

## 11. Ghi nhớ

`@ApplicationModule` có thể được dùng làm marker để Spring Modulith nhận diện một package là application module. Trong Java, đặt annotation ở `package-info.java` của package muốn đánh dấu. Để chỉ nhận các package đã đánh dấu, cấu hình `spring.modulith.detection-strategy=explicitly-annotated`; chiến lược này nhận diện package có `@ApplicationModule` hoặc annotation `@Module` của jMolecules.

Hãy phân biệt chiến lược mặc định `direct-sub-packages` với explicit detection: mặc định chọn package con trực tiếp của application root, còn explicit strategy yêu cầu marker. `@ApplicationModule` đồng thời có thể khai báo metadata module như `allowedDependencies`, `displayName` và `type`. Sau khi đánh dấu, hãy tạo `ApplicationModules` để xác nhận module được phát hiện và chạy `verify()` để kiểm tra boundary. Chọn explicit detection khi nó phản ánh cấu trúc package thật của ứng dụng và giúp nhóm kiểm soát module ownership rõ ràng hơn.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
