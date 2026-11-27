# jMolecules `@Module` và quan hệ với Modulith

jMolecules và Spring Modulith cùng mô tả ranh giới module trong một ứng dụng Java, nhưng chúng xuất phát từ hai mục tiêu khác nhau. jMolecules cung cấp ngôn ngữ kiến trúc theo Domain-Driven Design (DDD), trong đó `@Module` đánh dấu một package là module nghiệp vụ. Spring Modulith xây dựng mô hình application module cho ứng dụng Spring Boot, rồi dùng mô hình đó để kiểm tra phụ thuộc, tài liệu hóa cấu trúc và hỗ trợ kiểm thử từng module.

Spring Modulith hiểu annotation `org.jmolecules.ddd.annotation.Module` của jMolecules. Nhờ vậy, ta có thể dùng `@Module` làm dấu hiệu nhận diện module khi chọn chiến lược phát hiện tường minh. Điểm quan trọng là phải bật đúng detection strategy; chỉ thêm annotation vào package không tự thay đổi chiến lược phát hiện mặc định.

## 1. jMolecules `@Module` biểu đạt điều gì?

Trong DDD, module là cách nhóm các khái niệm và trách nhiệm liên quan trong một mô hình miền. `@Module` của jMolecules cung cấp metadata để công cụ có thể nhận biết package nào đại diện cho module đó.

Annotation nằm trong artifact `org.jmolecules:jmolecules-ddd`, có package:

```java
org.jmolecules.ddd.annotation.Module
```

`@Module` được thiết kế để đặt trên package, thường thông qua `package-info.java`:

```java
@org.jmolecules.ddd.annotation.Module(
    id = "catalog",
    name = "Danh mục sản phẩm",
    description = "Quản lý thông tin và vòng đời sản phẩm"
)
package com.example.shop.catalog;
```

Các thuộc tính có ý nghĩa như sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| `id` | Định danh ổn định của module. Nếu bỏ trống, công cụ có thể suy ra định danh từ phần tử được đánh dấu, thường là package. |
| `name` | Tên module dễ đọc dành cho con người. |
| `value` | Bí danh của `name`; nên chọn một trong hai thuộc tính. |
| `description` | Mô tả ngắn về trách nhiệm của module cho các công cụ hiểu metadata jMolecules. |

Nên chọn `id` ngắn, ổn định và có ý nghĩa trong phạm vi ứng dụng. Tên hiển thị có thể thay đổi theo cách diễn đạt hoặc ngôn ngữ tài liệu mà không cần đổi định danh kỹ thuật.

`@Module` là metadata kiến trúc. Nó không tạo Spring bean, không tạo tiến trình riêng và không biến package thành Gradle project. Một application module được phát hiện vẫn có thể chạy cùng các module khác trong một Spring Boot application duy nhất.

## 2. Spring Modulith hỗ trợ jMolecules như thế nào?

Spring Modulith có lớp tích hợp metadata dành cho jMolecules `@Module`. Khi phân tích package, Spring Modulith có thể sử dụng annotation này để lấy thông tin module, chẳng hạn display name và định danh module, thay vì chỉ suy luận mọi thứ từ tên package.

Quan hệ giữa hai thư viện có thể hiểu theo ba phần:

- **jMolecules cung cấp từ vựng DDD:** `@Module` nói rằng package này đại diện cho một module trong mô hình miền.
- **Spring Modulith chọn module để đưa vào mô hình:** detection strategy quyết định package nào được coi là application module.
- **Spring Modulith kiểm tra và sử dụng mô hình:** `ApplicationModules` tạo danh sách module, xác định các quan hệ phụ thuộc và thực thi quy tắc kiến trúc khi gọi `verify()`.

Như vậy, jMolecules giúp diễn đạt ý định ở mã nguồn; Spring Modulith dùng ý định đó để xây dựng mô hình modular monolith có thể kiểm tra.

## 3. Phân biệt chiến lược phát hiện mặc định và phát hiện tường minh

Spring Modulith mặc định sử dụng chiến lược `direct-subpackages`: các package con trực tiếp của package chứa lớp `@SpringBootApplication` được nhận diện là application module.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── catalog       # Được phát hiện theo vị trí package
├── orders        # Được phát hiện theo vị trí package
└── inventory     # Được phát hiện theo vị trí package
```

Với chiến lược mặc định, các package trên được nhận diện dù có hay không có `@Module`. Vì vậy, thêm `@Module` không phải điều kiện bắt buộc để Spring Modulith phát hiện những package con trực tiếp.

Nếu muốn chỉ những package được đánh dấu mới trở thành application module, hãy bật chiến lược `explicitly-annotated` trong `application.properties`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Chiến lược này nhận các package được đánh dấu bằng một trong hai annotation:

- Spring Modulith `@ApplicationModule`.
- jMolecules `@Module`.

Khi đó, package không có annotation phù hợp sẽ không tự động trở thành application module chỉ vì nó là package con trực tiếp của application root. Đây là khác biệt quan trọng khi chuyển từ cách tổ chức mặc định sang phát hiện tường minh.

## 4. Khai báo module bằng jMolecules `@Module`

Giả sử ứng dụng bán hàng có ba module nghiệp vụ `catalog`, `orders` và `inventory`. Ta đánh dấu từng package bằng `@Module` trong `package-info.java`.

`catalog/package-info.java`:

```java
@org.jmolecules.ddd.annotation.Module(
    id = "catalog",
    name = "Danh mục sản phẩm",
    description = "Quản lý thông tin sản phẩm"
)
package com.example.shop.catalog;
```

`orders/package-info.java`:

```java
@org.jmolecules.ddd.annotation.Module(
    id = "orders",
    name = "Đơn hàng",
    description = "Tiếp nhận và xử lý đơn hàng"
)
package com.example.shop.orders;
```

`inventory/package-info.java`:

```java
@org.jmolecules.ddd.annotation.Module(
    id = "inventory",
    name = "Tồn kho",
    description = "Theo dõi số lượng và khả năng cung ứng"
)
package com.example.shop.inventory;
```

Với cấu hình `explicitly-annotated`, Spring Modulith sử dụng các package đã đánh dấu để xây dựng application module model:

```text
com.example.shop
├── ShopApplication.java
├── catalog       @Module(id = "catalog")
├── orders        @Module(id = "orders")
└── inventory     @Module(id = "inventory")
```

Định danh `catalog`, `orders` và `inventory` có thể được dùng trong mô hình module và các cấu hình phụ thuộc. Tên hiển thị như `Danh mục sản phẩm` phục vụ tài liệu và người đọc; không nên dùng display name làm tên dependency.

## 5. jMolecules `@Module` khác Spring Modulith `@ApplicationModule` thế nào?

Hai annotation có phần giao nhau nhưng không thay thế hoàn toàn cho nhau.

| Tiêu chí | jMolecules `@Module` | Spring Modulith `@ApplicationModule` |
|---|---|---|
| Mục tiêu | Đánh dấu module theo từ vựng DDD | Cấu hình application module của Spring Modulith |
| Vị trí dùng | Package hoặc annotation type, thường là `package-info.java` | Package hoặc type trong package gốc module |
| Metadata tên | `id`, `name`/`value`, `description` | `id`, `displayName` và các metadata Modulith khác |
| Quy định module được phép phụ thuộc | Không có thuộc tính `allowedDependencies` tương đương | Có `allowedDependencies` |
| Chọn trạng thái open/closed | Không có thuộc tính `type` tương đương | Có `type = Type.OPEN` hoặc `Type.CLOSED` |
| Dùng làm dấu hiệu explicit detection | Có | Có |

Chọn `@Module` khi muốn diễn đạt DDD module bằng ngôn ngữ jMolecules và chia sẻ metadata đó với các công cụ trong hệ sinh thái jMolecules. Chọn `@ApplicationModule` khi cần cấu hình trực tiếp các chính sách riêng của Spring Modulith như allow-list dependency hoặc trạng thái open/closed.

Không nên giả định `@Module` tự cung cấp mọi tính năng của `@ApplicationModule`. Nếu ứng dụng cần các chính sách phụ thuộc cụ thể, hãy cấu hình bằng cơ chế Spring Modulith và kiểm tra kết quả trên mô hình thực tế. Tránh khai báo hai bộ metadata chồng lấn mà không xác minh annotation nào đang được dùng để tạo thông tin module.

## 6. Tạo mô hình và xác minh các module được đánh dấu

Sau khi khai báo annotation và bật detection strategy, ta có thể dùng `ApplicationModules` để quan sát các module được phát hiện:

```java
package com.example.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionExample {

    void printModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        for (ApplicationModule module : modules) {
            System.out.printf(
                    "id=%s, displayName=%s, basePackage=%s%n",
                    module.getIdentifier(),
                    module.getDisplayName(),
                    module.getBasePackage().getName());
        }
    }
}
```

Đoạn mã cho biết định danh, tên hiển thị và base package mà Spring Modulith đã gán cho từng module. Nếu module không xuất hiện, hãy kiểm tra package có được đánh dấu đúng hay chưa, annotation có nằm trong `package-info.java` tương ứng hay không và detection strategy đã được cấu hình trong môi trường kiểm thử chưa.

Tiếp theo, gọi `verify()` để kiểm tra cấu trúc phụ thuộc:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesExplicitlyDetectedModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc của Spring Modulith, chẳng hạn chu trình phụ thuộc, truy cập package nội bộ và allow-list nếu module đã khai báo. Annotation jMolecules giúp xác định module và cung cấp metadata; nó không tự thay thế bước kiểm tra kiến trúc.

## 7. Lưu ý về dependency và Kotlin

Để dùng annotation Java `org.jmolecules.ddd.annotation.Module`, ứng dụng cần có artifact `org.jmolecules:jmolecules-ddd` trên classpath. Spring Modulith nhận diện annotation khi artifact này có mặt và hỗ trợ metadata tương ứng.

```kotlin
dependencies {
    implementation("org.jmolecules:jmolecules-ddd:<jmolecules-version>")
}
```

Chọn phiên bản jMolecules tương thích với nền tảng Spring Boot và dependency management của dự án. Không cần thêm một annotation tự tạo có tên `Module` nếu đã dùng annotation chính thức.

Một lưu ý với Kotlin: artifact `kmolecules-ddd` cung cấp phần lớn từ vựng DDD tương ứng, nhưng hiện không cung cấp annotation `org.jmolecules.ddd.annotation.Module`. Vì vậy, nếu cần explicit detection trong Kotlin, có thể dùng `@ApplicationModule` trên một type nằm ở module root package theo cách Spring Modulith hỗ trợ, hoặc chọn một chiến lược phát hiện tùy chỉnh phù hợp.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Thêm `@Module` là Spring Modulith tự chuyển sang explicit detection | Phải cấu hình `spring.modulith.detection-strategy=explicitly-annotated` |
| `@Module` và `@ApplicationModule` là cùng một annotation | Chúng có mục tiêu và thuộc tính khác nhau, dù cả hai đều có thể đánh dấu module để discovery |
| Mọi package đều cần `@Module` khi dùng chiến lược mặc định | `direct-subpackages` phát hiện module theo vị trí package |
| `@Module` tự kiểm tra dependency giữa các module | Spring Modulith thực hiện kiểm tra bằng `ApplicationModules.verify()` |
| `@Module` tạo một Spring bean hoặc một service độc lập | Annotation chỉ mô tả metadata kiến trúc cho package |
| `@Module` có thể thay thế `allowedDependencies` và `Type.OPEN` | Các chính sách này thuộc cấu hình Spring Modulith `@ApplicationModule` |

## 9. Quy trình áp dụng trong modular monolith

Khi muốn dùng jMolecules cùng Spring Modulith, hãy bắt đầu bằng việc xác định các module theo năng lực nghiệp vụ. Đánh dấu package bằng `@Module` nếu nhóm muốn sử dụng từ vựng DDD của jMolecules, sau đó bật `explicitly-annotated` để Spring Modulith chỉ nhận các package đã được khai báo rõ.

Tiếp theo, tạo mô hình bằng `ApplicationModules.of(ShopApplication.class)`, kiểm tra tên và base package của từng module, rồi gọi `verify()` để phát hiện dependency không hợp lệ. Nếu cần giới hạn module được phép phụ thuộc hoặc mở module legacy, dùng các thuộc tính chuyên biệt của `@ApplicationModule` và kiểm thử lại cấu hình.

Cách kết hợp này giúp metadata DDD được thể hiện ngay trong mã nguồn, còn Spring Modulith đảm nhiệm việc dựng mô hình application module và kiểm tra ranh giới của modular monolith.

Tài liệu tham khảo: [Spring Modulith – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.customizing-detection), [Spring Modulith – ApplicationModuleInformationFactory.JMoleculesModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleInformationFactory.JMoleculesModule.html), [jMolecules – Module annotation source](https://github.com/xmolecules/jmolecules/blob/main/jmolecules-ddd/src/main/java/org/jmolecules/ddd/annotation/Module.java).
