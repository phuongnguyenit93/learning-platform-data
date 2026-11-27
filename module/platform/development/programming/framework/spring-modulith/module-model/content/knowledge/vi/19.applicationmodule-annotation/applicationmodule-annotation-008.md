# Đặt metadata trên type trong trường hợp đặc biệt

Spring Modulith thường đọc metadata của application module từ `package-info.java`. Cách này tự nhiên với Java, nhưng một số ngôn ngữ như Kotlin không hỗ trợ file package-info tương đương. Spring Modulith cung cấp `@PackageInfo` để đánh dấu một type làm nơi chứa metadata của package. Các annotation như `@ApplicationModule` hoặc `@NamedInterface` có thể được đặt trên type đó để mô tả package mà type thuộc về.

Điều quan trọng là phân biệt metadata của cả package với metadata gắn trực tiếp lên một type. Ví dụ, `@PackageInfo` kết hợp `@NamedInterface("spi")` công bố package SPI; còn `@NamedInterface("spi")` đặt trực tiếp trên một interface chỉ gán type đó vào named interface. Bài học này giải thích cách chọn đúng hình thức, vị trí đặt metadata và cách xác nhận Spring Modulith đã nhận diện chúng.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của `package-info.java` trong module metadata.
- Dùng `@PackageInfo` để thay thế package-info bằng một type.
- Đặt `@ApplicationModule` trên metadata type trong package gốc của module.
- Dùng `@PackageInfo` cùng `@NamedInterface` để công bố cả package con.
- Phân biệt package-level named interface với named interface gán trực tiếp cho một type.
- Chọn vị trí metadata phù hợp cho module root, package SPI và package events.
- Hiểu các thuộc tính `id`, `displayName`, `allowedDependencies` và `type` của `@ApplicationModule`.
- Kiểm tra module model để xác nhận metadata được phát hiện đúng.
- Tránh các lỗi do đặt metadata sai package hoặc đặt type metadata ở sai source set.

## Vì sao cần metadata trên type?

Trong Java, `package-info.java` cho phép khai báo annotation trên package. Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory"
)
package com.acme.inventory;
```

File này không khai báo class nghiệp vụ. Nó cung cấp thông tin gắn với package `com.acme.inventory`.

Kotlin không có cơ chế `package-info.java` tương đương. Một số cách tổ chức source code, code generator hoặc ngôn ngữ JVM khác cũng có thể không tạo được package-info theo cách Java mong đợi. Nếu không có giải pháp thay thế, nhóm sẽ khó khai báo package metadata như module type, dependency policy hoặc named interface.

`@PackageInfo` giải quyết trường hợp đó. Đây là annotation đánh dấu một type làm lựa chọn thay thế cho Java `package-info.java`. Khi Spring Modulith tra cứu annotation trên package, type được đánh dấu `@PackageInfo` cũng được xem xét.

```kotlin
package com.acme.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    id = "inventory",
    displayName = "Inventory"
)
class ModuleMetadata
```

`ModuleMetadata` nằm trong package `com.acme.inventory`. Vì có `@PackageInfo`, Spring Modulith có thể dùng các annotation trên type đó như metadata của package.

Nếu một dự án Java dùng code generator không tạo được `package-info.java`, có thể áp dụng cùng cách tiếp cận bằng một type:

```java
package com.acme.inventory;

import org.springframework.modulith.ApplicationModule;
import org.springframework.modulith.PackageInfo;

@PackageInfo
@ApplicationModule(id = "inventory")
class InventoryModuleMetadata {}
```

## `@PackageInfo` hoạt động như thế nào?

`PackageInfo` thuộc package `org.springframework.modulith` và có các đặc điểm:

| Đặc điểm | Giá trị |
|---|---|
| Target | `TYPE` |
| Retention | `RUNTIME` |
| Có từ phiên bản | Spring Modulith 1.2 |
| Vai trò | Đánh dấu type làm thay thế cho `package-info.java` |

Vì target là `TYPE`, không đặt `@PackageInfo` trực tiếp trên package declaration trong Java. Hãy đặt nó trên một class hoặc type metadata nằm trong package cần mô tả.

```kotlin
package com.acme.orders

import org.springframework.modulith.PackageInfo

@PackageInfo
class ModuleMetadata
```

Type metadata thường là một class rỗng, không chứa nghiệp vụ và không cần trở thành Spring bean. Không thêm `@Component` chỉ để Spring Modulith nhìn thấy nó; việc phát hiện metadata dựa trên annotation và class có trong module model, không yêu cầu class phải được đăng ký như bean.

`@PackageInfo` cũng không tự tạo application module, không công bố API và không thay đổi dependency. Nó chỉ giúp Spring Modulith tìm các annotation khác trên type như thể chúng được khai báo cho package.

## Phân biệt ba cách đặt annotation

Một annotation có thể có target `PACKAGE`, `TYPE` hoặc cả hai. Cách đặt và ý nghĩa phụ thuộc vào annotation cụ thể.

| Cách đặt | Ý nghĩa |
|---|---|
| Annotation trong `package-info.java` | Metadata áp dụng cho package theo cơ chế Java |
| Annotation trên type có `@PackageInfo` | Type được dùng như nguồn metadata thay thế cho package-info |
| Annotation trực tiếp trên một type, không có `@PackageInfo` | Annotation có thể chỉ áp dụng cho type đó, tùy API và cách Spring Modulith diễn giải |

Ví dụ, `@NamedInterface` có thể được đặt trên package để công bố toàn package, hoặc đặt trực tiếp trên type để gán type đó vào named interface. Với `@ApplicationModule`, tài liệu Spring Modulith cũng hỗ trợ khai báo trực tiếp trên một type nằm trong root package của module, chẳng hạn để mô tả `allowedDependencies`. Khi cần thể hiện rõ type là nguồn metadata package, dùng `@PackageInfo` cùng annotation tương ứng.

Không nên suy luận rằng mọi annotation đặt trên một class đều tự động trở thành metadata package. Hãy kiểm tra target và quy tắc lookup của annotation đang dùng.

## Đặt `@ApplicationModule` trên metadata type

`@ApplicationModule` tùy chỉnh thông tin của application module. Annotation có thể dùng trên package hoặc type. Các thuộc tính thường gặp gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `id` | Logical identifier của module |
| `displayName` | Tên dễ đọc dùng trong tài liệu và hiển thị |
| `allowedDependencies` | Danh sách module hoặc named interface mà module được phép phụ thuộc |
| `type` | Loại module, thường `CLOSED` hoặc `OPEN` |

Với Java, có thể khai báo trên `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Quản lý tồn kho",
    allowedDependencies = { "orders", "catalog :: products" },
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.inventory;
```

Với Kotlin, đặt metadata type trong đúng root package:

```kotlin
package com.acme.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    id = "inventory",
    displayName = "Quản lý tồn kho",
    allowedDependencies = ["orders", "catalog :: products"],
    type = ApplicationModule.Type.CLOSED
)
class ModuleMetadata
```

Kotlin dùng array literal trong dấu ngoặc vuông cho thuộc tính mảng annotation. Trong Java, thuộc tính `allowedDependencies` dùng cú pháp mảng Java.

### Ý nghĩa các thuộc tính cần lưu ý

`id` là tên logic dùng trong dependency declaration. Ví dụ, consumer tham chiếu `inventory`, không tham chiếu `Quản lý tồn kho`. Identifier không được chứa dấu phân cách `::` dành cho named interface.

`displayName` là nhãn dành cho người đọc. Nó có thể chứa dấu cách hoặc ngôn ngữ tự nhiên và không thay đổi module identifier.

`allowedDependencies` giới hạn các dependency được phép khi module khai báo chính sách này. Ví dụ `orders` cho phép dùng root API của module đó; `catalog :: products` cho phép dùng named interface `products`. Một mảng rỗng có nghĩa không cho phép dependency đến module khác. Để không thiết lập giới hạn tường minh, giữ thuộc tính ở giá trị mặc định.

`type` mặc định là `CLOSED`. Với module `OPEN`, Spring Modulith nới lỏng kiểm tra truy cập internal để hỗ trợ chuyển đổi codebase legacy. Không dùng `OPEN` như một cách thay thế cho việc công bố API có chủ đích.

## Trường hợp Kotlin chỉ khai báo `allowedDependencies`

Tài liệu Spring Modulith minh họa việc đặt `@ApplicationModule` trực tiếp trên một type duy nhất trong root package để khai báo dependency policy:

```kotlin
package com.acme.inventory

import org.springframework.modulith.ApplicationModule

@ApplicationModule(allowedDependencies = ["orders"])
class ModuleMetadata
```

Đây là một cách được hỗ trợ cho module metadata trong root package. Khi muốn sử dụng type rõ ràng như nguồn package metadata cho nhiều annotation, có thể đánh dấu thêm `@PackageInfo`:

```kotlin
package com.acme.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(allowedDependencies = ["orders"])
class ModuleMetadata
```

Điều quan trọng là type phải nằm trong package gốc của module `inventory`. Nếu đặt class trong `com.acme.inventory.internal`, annotation sẽ gắn với type và package con đó, không phải root package `com.acme.inventory`.

## Dùng `@PackageInfo` để công bố named interface cho cả package

Giả sử module `orders` muốn công bố package `com.acme.orders.spi` như một SPI. Trong Java, cách thông thường là tạo `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.orders.spi;
```

Trong Kotlin, tạo metadata type ngay trong package `com.acme.orders.spi`:

```kotlin
package com.acme.orders.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class SpiPackageMetadata
```

Hai cách này có cùng ý định: công bố package `spi` thành named interface tên `spi` của module `orders`.

Các type khác trong package có thể thuộc interface đó:

```kotlin
package com.acme.orders.spi

data class OrderLookupRequest(val orderId: String)

data class OrderSummary(val orderId: String, val status: String)

interface OrderLookup {
    fun find(request: OrderLookupRequest): OrderSummary?
}
```

Consumer có thể giới hạn dependency vào named interface:

```kotlin
package com.acme.reporting

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(allowedDependencies = ["orders :: spi"])
class ModuleMetadata
```

Nhờ vậy, `reporting` được phép dùng các type thuộc `orders.spi` theo hợp đồng đã công bố. Nó không tự động được phép dùng mọi type trong root package hoặc package internal của `orders`.

## Gán named interface trực tiếp cho một type

`@NamedInterface` cũng có target `TYPE`. Khi đặt trực tiếp lên type, annotation gán type đó vào named interface; nó không đồng nghĩa công bố toàn bộ package chứa type.

Ví dụ:

```kotlin
package com.acme.orders.spi

import org.springframework.modulith.NamedInterface

@NamedInterface("spi")
interface OrderLookup
```

Trong cách này, `OrderLookup` được gán vào named interface `spi`. Các class khác trong cùng package không tự động thuộc interface chỉ vì nằm cạnh nó. Nếu contract gồm interface, request và response types, cần gán các type liên quan vào cùng named interface hoặc dùng `@PackageInfo` để công bố cả package.

Có thể gán một type vào nhiều named interface bằng cách cung cấp nhiều tên, khi type thực sự thuộc nhiều hợp đồng:

```kotlin
@NamedInterface("spi")
interface OrderLookup
```

Trong Java, khai báo nhiều tên có thể viết như sau:

```java
@NamedInterface({ "spi", "query-api" })
public interface OrderLookup {}
```

Chỉ nên làm vậy khi hai API có lý do nghiệp vụ riêng. Gán nhiều tên tùy tiện làm khó hiểu phạm vi hợp đồng và dependency policy của consumer.

## Đặt metadata type ở đúng package

Một metadata type mô tả package mà nó thuộc về. Vì vậy, vị trí package là điều kiện quan trọng:

```text
com.acme
├── Application.kt
├── orders
│   ├── ModuleMetadata.kt          # @PackageInfo + @ApplicationModule
│   ├── OrderManagement.kt
│   └── spi
│       ├── SpiPackageMetadata.kt  # @PackageInfo + @NamedInterface
│       └── OrderLookup.kt
└── reporting
    ├── ModuleMetadata.kt          # @PackageInfo + @ApplicationModule
    └── ReportService.kt
```

`orders.ModuleMetadata` mô tả module `orders`. `orders.spi.SpiPackageMetadata` mô tả package `orders.spi`. Không đặt cả hai metadata type trong `com.acme.orders` rồi mong annotation `@NamedInterface` áp dụng cho package `com.acme.orders.spi`.

Nếu dùng cùng tên class `ModuleMetadata` trong nhiều package, điều đó không gây xung đột vì fully qualified name khác nhau. Tuy vậy, có thể chọn tên mô tả mục đích như `OrdersModuleMetadata`, `SpiPackageMetadata` để code dễ tìm hơn.

## Khi nào dùng `package-info.java`, khi nào dùng type metadata?

| Tình huống | Cách phù hợp |
|---|---|
| Module viết bằng Java và hỗ trợ package-info | Dùng `package-info.java` |
| Module viết bằng Kotlin | Dùng type metadata với `@PackageInfo` khi cần package-level lookup |
| Chỉ muốn gán một interface/class cụ thể vào named interface | Đặt `@NamedInterface` trực tiếp trên type |
| Muốn công bố toàn bộ package SPI hoặc events | Dùng `@PackageInfo` + `@NamedInterface` trên metadata type trong package đó |
| Muốn khai báo module dependencies trên type ở root package | Đặt `@ApplicationModule` trên type theo cách Spring Modulith hỗ trợ; dùng `@PackageInfo` khi type đóng vai trò package metadata |
| Muốn khai báo nested module | Đặt `@ApplicationModule` trên package hoặc metadata type thuộc package nested đó |

`package-info.java` vẫn là lựa chọn rõ ràng và quen thuộc trong Java. `@PackageInfo` là cơ chế thay thế khi ngôn ngữ hoặc công cụ không hỗ trợ package-info; không cần tạo metadata type trong Java chỉ để tránh một file package-info đang hoạt động tốt.

## Metadata type có cần là Spring bean không?

Không. `@PackageInfo` là annotation runtime để Spring Modulith nhận diện type khi phân tích package. `ModuleMetadata` không cần `@Component`, `@Service` hay `@Configuration` chỉ để metadata có hiệu lực.

Tránh đưa logic nghiệp vụ vào metadata type. Nếu một class vừa làm package metadata vừa chứa service method, người đọc khó phân biệt phần cấu hình kiến trúc với hành vi ứng dụng. Giữ class metadata đơn giản và ổn định.

Ví dụ nên dùng:

```kotlin
package com.acme.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(id = "inventory")
class InventoryModuleMetadata
```

Không cần:

```kotlin
@Component
@PackageInfo
@ApplicationModule(id = "inventory")
class InventoryModuleMetadata {
    fun reserveStock() {
        // Logic nghiệp vụ không thuộc metadata.
    }
}
```

Đặt logic nghiệp vụ trong bean thuộc module và để metadata type chỉ mô tả cấu trúc.

## Source set và classpath

Spring Modulith phân tích các class có mặt trong classpath khi tạo `ApplicationModules`. Metadata type phải được compile và có mặt trong source set đang được phân tích.

| Nơi đặt metadata type | Khi phù hợp |
|---|---|
| `src/main/kotlin` hoặc `src/main/java` | Metadata cần có trong production runtime, runtime verification hoặc tài liệu sinh từ main artifact |
| `src/test/kotlin` hoặc `src/test/java` | Metadata chỉ phục vụ model test hoặc documentation test trong test classpath |

Nếu runtime verification cần một custom module arrangement hoặc named interface, metadata phải có trong production artifact. Đặt metadata duy nhất trong test source set có thể làm model test nhìn thấy cấu trúc khác với ứng dụng khi chạy thật.

Với module chỉ dùng metadata trong test, có thể đặt type trong test source set nếu application class và classpath test thực sự bao gồm package đó. Hãy giữ cùng cách phát hiện module giữa các test liên quan để kết quả không mâu thuẫn.

## Xác minh metadata được nhận diện

Sau khi tạo metadata type, hãy tạo mô hình module từ application class:

```kotlin
import org.springframework.modulith.core.ApplicationModules

val modules = ApplicationModules.of(Application::class.java)
modules.forEach { println(it) }
```

Đầu ra cho biết logical name, base package và các Spring bean được nhận diện. Kiểm tra module có đúng `id`, `displayName` và base package mong muốn hay không.

Để xác minh dependency:

```kotlin
import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules

class ModularityTests {

    @Test
    fun verifiesModuleStructure() {
        ApplicationModules.of(Application::class.java).verify()
    }
}
```

Với named interface, kiểm tra dependency được khai báo bằng đúng tên:

```kotlin
@PackageInfo
@ApplicationModule(allowedDependencies = ["orders :: spi"])
class ReportingModuleMetadata
```

Nếu consumer vẫn bị báo truy cập package internal, kiểm tra lần lượt:

1. Metadata type có nằm đúng package mà bạn muốn mô tả không?
2. Type có `@PackageInfo` khi mục tiêu là thay thế package-info không?
3. `@NamedInterface` có tên đúng và có nằm trên metadata type của package cần công bố không?
4. Type được consumer import có thực sự nằm trong package named interface đó không?
5. Consumer có khai báo `allowedDependencies` với đúng module identifier và named interface không?
6. Metadata type có trong classpath của test/runtime đang chạy không?

Nếu module model đã đúng nhưng Spring không inject được bean, đó là vấn đề runtime wiring. `@PackageInfo` không đăng ký bean và không thay thế component scanning.

## Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đặt `@PackageInfo` trên package declaration | Annotation chỉ có target `TYPE` | Đặt trên class/type metadata trong package |
| Quên `@PackageInfo` trên metadata type | Type không được dùng như package-info thay thế | Thêm `@PackageInfo` khi cần package-level lookup |
| Đặt metadata type trong package con sai | Annotation mô tả package chứa type đó | Chuyển type vào đúng package root hoặc package named interface |
| Đặt `@NamedInterface` trực tiếp trên một class rồi nghĩ cả package được công bố | Type-level annotation chỉ gán type được đánh dấu | Dùng `@PackageInfo` + `@NamedInterface` để công bố package |
| Dùng `@ApplicationModule` ở package con ngoài ý muốn | Package có thể trở thành nested application module | Kiểm tra base package và đặt annotation đúng nơi |
| Dùng `@PackageInfo` như một annotation công bố API | `@PackageInfo` chỉ đánh dấu nguồn metadata | Kết hợp với `@NamedInterface` khi cần công bố package |
| Đặt metadata type trong test source set nhưng cần runtime metadata | Production classpath không chứa type | Chuyển metadata vào main source set |
| Thêm `@Component` cho metadata type | Nhầm package metadata với Spring bean | Giữ type metadata độc lập, không thêm stereotype không cần thiết |
| Dùng display name làm dependency identifier | `displayName` chỉ dành cho người đọc | Dùng `id` hoặc logical module name trong `allowedDependencies` |
| Nhầm `@PackageInfo` tạo module mới | Annotation không tự phát hiện module | Dùng `@ApplicationModule` và detection strategy phù hợp |

## Quy trình áp dụng

Khi cần đặt metadata trên type, hãy làm theo thứ tự:

1. Xác định package cần mô tả: module root hay package con.
2. Nếu Java hỗ trợ `package-info.java`, quyết định có tiếp tục dùng cơ chế đó hay không.
3. Nếu dùng type metadata, tạo một type riêng trong đúng package.
4. Đánh dấu type bằng `@PackageInfo` khi cần thay thế package-info trong package annotation lookup.
5. Đặt `@ApplicationModule` hoặc `@NamedInterface` tương ứng lên metadata type.
6. Nếu chỉ gán một type vào named interface, có thể đặt `@NamedInterface` trực tiếp trên type đó.
7. Đảm bảo type metadata nằm trong source set phù hợp với nơi cần phân tích module model.
8. In `ApplicationModules` để kiểm tra module và API được phát hiện.
9. Chạy `verify()` để xác nhận dependency và module boundary.
10. Giữ metadata type nhỏ, rõ ràng và không chứa logic nghiệp vụ.

## Bài tập tự đánh giá

Một ứng dụng viết bằng Kotlin có module `orders` và package con `orders.spi`. Nhóm muốn:

- Đặt `id = "orders"` và `displayName = "Quản lý đơn hàng"` cho module root.
- Chỉ cho phép module `orders` phụ thuộc `customers`.
- Công bố toàn bộ package `orders.spi` thành named interface `spi`.
- Cho module `reporting` phụ thuộc riêng vào `orders :: spi`.

Hãy tạo metadata type cho module `orders` và package `orders.spi`, đồng thời cấu hình dependency của `reporting` bằng metadata type riêng. Giải thích vì sao ba type phải nằm trong ba package tương ứng.

Một cách triển khai:

Metadata ở `com.acme.orders`:

```kotlin
package com.acme.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    id = "orders",
    displayName = "Quản lý đơn hàng",
    allowedDependencies = ["customers"]
)
class OrdersModuleMetadata
```

Metadata ở `com.acme.orders.spi`:

```kotlin
package com.acme.orders.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class OrdersSpiMetadata
```

Metadata ở `com.acme.reporting`:

```kotlin
package com.acme.reporting

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(allowedDependencies = ["orders :: spi"])
class ReportingModuleMetadata
```

Ba type nằm trong ba package khác nhau vì mỗi type mô tả metadata cho package chứa nó. Sau khi tạo, in module model và chạy `ApplicationModules.of(Application::class.java).verify()` để kiểm tra kết quả.

## Kết luận

`@PackageInfo` cho phép một type thay thế `package-info.java` khi Spring Modulith tra cứu annotation của package. Đây là lựa chọn quan trọng với Kotlin và các trường hợp không thể dùng package-info. Hãy đặt metadata type trong đúng package cần mô tả, kết hợp `@ApplicationModule` hoặc `@NamedInterface` theo mục tiêu, và phân biệt package-level metadata với annotation gắn trực tiếp lên một type. Kiểm tra module model sau khi thay đổi để bảo đảm metadata được nhận diện đúng trong source set và classpath cần thiết.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals: Open Modules, Explicit Dependencies and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `PackageInfo`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith 1.2 M3 — Support for Package Info Types](https://spring.io/blog/2024/03/22/spring-modulith-1-2-m3-released/)
