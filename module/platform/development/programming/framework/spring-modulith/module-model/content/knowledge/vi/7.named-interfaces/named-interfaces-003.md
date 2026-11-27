# `@PackageInfo` khi cần biểu diễn metadata

Trong Spring Modulith, metadata của một package có thể được khai báo bằng `package-info.java`. Cách này phù hợp với Java, nhưng Kotlin không có cơ chế tương đương. Khi cần mô tả một package bằng Kotlin, ta có thể tạo một class nằm ngay trong package đó và đánh dấu class bằng `@PackageInfo`.

`@PackageInfo` cho Spring Modulith biết rằng class được đánh dấu là nơi đại diện cho metadata của package chứa nó. Các annotation trên class này cũng được xem xét khi Spring Modulith tra cứu annotation của package. Nhờ vậy, ta có thể khai báo `@NamedInterface`, `@ApplicationModule` và các metadata liên quan trên một class thông thường.

Sau bài học, bạn có thể:

- Giải thích vai trò của `@PackageInfo` và mối quan hệ giữa class metadata với package chứa class.
- Dùng `@PackageInfo` cùng `@NamedInterface` để khai báo một named interface bằng Kotlin.
- Dùng class metadata để khai báo cấu hình module khi không thể hoặc không muốn dùng `package-info.java`.
- Nhận biết những trường hợp `@PackageInfo` không cần thiết và các lỗi cấu hình thường gặp.

## 1. Vì sao cần `@PackageInfo`?

Spring Modulith cần biết package nào là API được phép sử dụng từ module khác, package nào là phần triển khai nội bộ và module được phép phụ thuộc vào những named interface nào. Các thông tin này thường được khai báo bằng annotation ở cấp package.

Trong Java, file `package-info.java` là nơi tự nhiên để đặt annotation cho package:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.order.spi;
```

Annotation ở đầu file áp dụng cho package `com.acme.shop.order.spi`. Spring Modulith có thể đọc metadata đó khi xây dựng mô hình module.

Kotlin không hỗ trợ `package-info.java`. Nếu chỉ đặt `@NamedInterface` lên một class Kotlin thông thường, class đó đơn thuần là một type được đánh dấu. Spring Modulith cần một dấu hiệu cho biết class này đang đại diện cho metadata của cả package. `@PackageInfo` cung cấp dấu hiệu đó.

```kotlin
package com.acme.shop.order.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
```

Class `ModuleMetadata` nằm trong package `com.acme.shop.order.spi`. `@PackageInfo` đánh dấu class là đại diện metadata của package; `@NamedInterface("spi")` cung cấp nội dung metadata, tức tên của named interface. Các type khác trong cùng package, chẳng hạn `OrderPricingPort`, thuộc named interface `spi` theo quy tắc package của Spring Modulith.

Điểm cần nhớ: **`@PackageInfo` không tự tạo named interface và cũng không tự mở quyền truy cập package.** Nó xác định class nào được dùng làm nơi khai báo metadata. Annotation như `@NamedInterface` mới xác định package được công bố dưới tên nào.

## 2. `@PackageInfo` hoạt động như thế nào?

`org.springframework.modulith.PackageInfo` là annotation có các đặc điểm sau:

| Đặc điểm | Ý nghĩa |
|---|---|
| `@Target(TYPE)` | Được đặt trên một type, thường là class metadata. |
| `@Retention(RUNTIME)` | Annotation còn tồn tại lúc chạy để Spring Modulith có thể tra cứu. |
| Có từ Spring Modulith 1.2 | Dự án cần dùng phiên bản Spring Modulith có hỗ trợ annotation này. |
| Vai trò | Đánh dấu type là phương án thay thế `package-info.java`; annotation trên type cũng được xem xét khi tra metadata của package. |

Class metadata phải thuộc đúng package cần mô tả. Ví dụ, class ở `com.acme.shop.order.spi` đại diện cho metadata của package `com.acme.shop.order.spi`; đặt class đó ở `com.acme.shop.order` sẽ làm metadata gắn với package khác.

Một class metadata thường không chứa nghiệp vụ. Nó chỉ gom các khai báo kiến trúc liên quan đến package. Đặt tên rõ nghĩa như `ModuleMetadata` hoặc `PackageMetadata` giúp người đọc nhận ra mục đích của class.

## 3. Khai báo named interface bằng Kotlin

Giả sử module `order` có một hợp đồng SPI để module khác có thể cung cấp hoặc sử dụng chức năng định giá đơn hàng. Ta muốn công bố hợp đồng đó nhưng vẫn giữ phần triển khai nội bộ ở bên trong module.

```text
com.acme.shop
├── ShopApplication.kt
├── order
│   ├── OrderManagement.kt
│   ├── spi
│   │   ├── ModuleMetadata.kt
│   │   └── OrderPricingPort.kt
│   └── internal
│       └── DefaultOrderPricingService.kt
└── inventory
    └── InventoryService.kt
```

`OrderPricingPort.kt` khai báo hợp đồng cần công bố:

```kotlin
package com.acme.shop.order.spi

interface OrderPricingPort {
    fun calculateTotal(orderId: String): Long
}
```

`ModuleMetadata.kt` khai báo named interface cho package đó:

```kotlin
package com.acme.shop.order.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
```

Khi phân tích cấu trúc ứng dụng, Spring Modulith nhận diện `com.acme.shop.order.spi` là named interface có tên `spi`. Vì vậy, module khác có thể tham chiếu các type thuộc package này theo quy tắc phụ thuộc của Spring Modulith.

Trong khi đó, `com.acme.shop.order.internal` vẫn là package nội bộ theo cấu trúc module thông thường. Việc đặt một type là `public` trong ngôn ngữ không đồng nghĩa type đó được công bố như API của module. Quy tắc kiến trúc của Spring Modulith mới xác định module khác có được phép phụ thuộc vào package đó hay không.

### So sánh hai cách khai báo

| Ngôn ngữ/cách tổ chức | Nơi đặt metadata | Cách đánh dấu |
|---|---|---|
| Java | `package-info.java` trong package cần mô tả | Đặt `@NamedInterface("spi")` trực tiếp lên package. |
| Kotlin | Một class như `ModuleMetadata` trong package cần mô tả | Đặt cả `@PackageInfo` và `@NamedInterface("spi")` lên class. |

Hai cách biểu diễn cùng một ý nghĩa kiến trúc. Nếu package đã có `package-info.java` phù hợp trong Java, không cần tạo thêm class metadata chỉ để dùng `@PackageInfo`.

## 4. Dùng class metadata cho cấu hình module

`@PackageInfo` cũng có thể kết hợp với `@ApplicationModule` khi cần khai báo metadata ở package gốc của một module. Ví dụ, module `inventory` chỉ được phép phụ thuộc vào named interface `spi` của module `order`:

```kotlin
package com.acme.shop.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(allowedDependencies = ["order :: spi"])
class ModuleMetadata
```

Chuỗi `order :: spi` gồm tên module `order`, dấu phân cách `::` và tên named interface `spi`. Khai báo này giới hạn phụ thuộc được phép của `inventory` vào phần giao diện đã công bố của `order`.

Nếu module `inventory` dùng Java, metadata tương đương có thể đặt trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: spi"
)
package com.acme.shop.inventory;
```

Không nên hiểu `@PackageInfo` là annotation thay thế `@ApplicationModule` hoặc `@NamedInterface`. Mỗi annotation có trách nhiệm riêng: `@PackageInfo` xác định class đại diện metadata; `@ApplicationModule` cấu hình module; `@NamedInterface` công bố một package dưới tên giao diện được chỉ định.

## 5. Khi nào nên dùng?

Dùng `@PackageInfo` khi cần khai báo metadata gắn với package nhưng dự án không sử dụng được `package-info.java`, đặc biệt trong mã Kotlin. Nó cũng hữu ích khi nhóm muốn giữ metadata kiến trúc ngay cạnh các type của package dưới dạng một class dễ tìm.

Không cần thêm `@PackageInfo` nếu Java package đã được mô tả trực tiếp bằng `package-info.java`. Cũng không cần tạo class metadata cho mọi package. Chỉ tạo nó ở package có metadata cần khai báo, chẳng hạn package của named interface hoặc package gốc có cấu hình `@ApplicationModule`.

Khi thiết kế class metadata, nên tuân theo các nguyên tắc sau:

- Đặt class trong chính package cần mô tả.
- Dùng một class chuyên biệt, tên rõ nghĩa và không chứa logic nghiệp vụ.
- Đặt `@PackageInfo` cùng các annotation mô tả package trên class đó.
- Giữ tên named interface nhất quán với giá trị dùng trong `allowedDependencies`.
- Kiểm tra phiên bản `spring-modulith-core` mà dự án đang sử dụng có cung cấp `PackageInfo`.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Named interface không xuất hiện như mong đợi | Class metadata thiếu `@PackageInfo` hoặc đặt sai package. | Thêm `@PackageInfo` và chuyển class vào đúng package cần mô tả. |
| Module khác không được phép tham chiếu type trong SPI | Package chưa được đánh dấu bằng `@NamedInterface`, hoặc module sử dụng chưa khai báo dependency phù hợp. | Kiểm tra `@NamedInterface("spi")` và `allowedDependencies = ["order :: spi"]`. |
| Nghĩ rằng thêm `@PackageInfo` là đủ để công bố API | `@PackageInfo` chỉ đánh dấu nơi chứa metadata, không định nghĩa named interface. | Bổ sung annotation có ý nghĩa kiến trúc, ví dụ `@NamedInterface("spi")`. |
| Metadata không tác động đến package dự kiến | Class metadata nằm trong package khác với package cần cấu hình. | Kiểm tra dòng `package` ở đầu file và cấu trúc thư mục nguồn. |
| Không tìm thấy `PackageInfo` khi biên dịch | Phiên bản Spring Modulith đang dùng chưa có annotation này hoặc thiếu dependency phù hợp. | Dùng Spring Modulith từ phiên bản 1.2 trở lên và kiểm tra dependency `spring-modulith-core`. |

## 7. Kiểm chứng cấu trúc module

Sau khi khai báo metadata, hãy kiểm chứng mô hình module bằng `ApplicationModules`. Bài kiểm tra kiến trúc dưới đây yêu cầu Spring Modulith phân tích ứng dụng và xác nhận các quy tắc phụ thuộc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu dùng Kotlin, có thể viết lời gọi tương đương:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules

class ModularityTests {

    @Test
    fun verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication::class.java).verify()
    }
}
```

Khi bài kiểm tra thất bại, hãy đọc thông báo để xác định package hoặc dependency vi phạm. Nếu `inventory` cần dùng `OrderPricingPort`, hãy kiểm tra type đó thực sự nằm trong `com.acme.shop.order.spi`, package có `@PackageInfo` và `@NamedInterface("spi")`, đồng thời cấu hình dependency của `inventory` tham chiếu đúng `order :: spi`.

## 8. Ghi nhớ

`@PackageInfo` là cầu nối để Spring Modulith đọc metadata package từ một class. Nó đặc biệt hữu ích trong Kotlin, nơi không có `package-info.java`. Hãy đặt class metadata trong package cần mô tả và kết hợp `@PackageInfo` với annotation mang ý nghĩa cụ thể như `@NamedInterface` hoặc `@ApplicationModule`. Sau đó dùng `ApplicationModules.verify()` để kiểm tra các ranh giới và quy tắc phụ thuộc có đúng với thiết kế hay không.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API – `PackageInfo`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html)
