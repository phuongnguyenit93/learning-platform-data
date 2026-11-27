# Biểu diễn metadata khi ngôn ngữ thiếu package-info.java

Bài này thuộc chương **Explicit detection** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith dùng metadata gắn với package để mô tả application module, named interface và các quy tắc phụ thuộc. Trong Java, metadata cấp package thường được khai báo bằng file `package-info.java`. Tuy nhiên, một số ngôn ngữ JVM như Kotlin không hỗ trợ cách khai báo file đó.

Spring Modulith cung cấp annotation **`@PackageInfo`** để dùng một kiểu Java/Kotlin làm nơi mang metadata thay cho `package-info.java`. Kiểu này được đặt ngay trong package cần mô tả và được đánh dấu bằng `@PackageInfo`, sau đó gắn thêm annotation tương ứng như `@ApplicationModule` hoặc `@NamedInterface`.

## 1. Vấn đề khi ngôn ngữ không có package-info.java

Trong Java, ta có thể khai báo metadata module ở cấp package:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order"
)
package example.inventory;
~~~

Tệp này thường được lưu ở `src/main/java/example/inventory/package-info.java`. Annotation mô tả package `example.inventory`, không mô tả riêng một lớp nghiệp vụ.

Kotlin không có cơ chế tương đương với Java `package-info.java`. Nếu chỉ dựa vào cách khai báo package annotation của Java, nhóm sẽ không có vị trí phù hợp để đặt metadata cho module hoặc named interface.

Vấn đề không nằm ở việc Spring Modulith không hỗ trợ Kotlin. Framework cung cấp một cách biểu diễn khác: đặt một kiểu metadata trong package và đánh dấu kiểu đó bằng `@PackageInfo`.

## 2. @PackageInfo là gì?

`@PackageInfo` là annotation của Spring Modulith dùng để đánh dấu một kiểu như **đại diện thay thế cho package-info.java**. Khi tìm annotation trên package, Spring Modulith cũng xem xét những kiểu được đánh dấu bằng `@PackageInfo`.

Một metadata carrier thường có dạng:

~~~kotlin
package example.inventory

import org.springframework.modulith.PackageInfo

@PackageInfo
class ModuleMetadata
~~~

Trong ví dụ này:

- `ModuleMetadata` là một kiểu nằm trong package `example.inventory`.
- `@PackageInfo` cho Spring Modulith biết kiểu này mang metadata của package chứa nó.
- Các annotation mô tả module có thể được đặt cùng trên kiểu đó.

`ModuleMetadata` là tên lớp theo quy ước dễ hiểu; nhóm có thể chọn tên khác. Điều quan trọng là kiểu phải nằm đúng package cần mô tả và được đánh dấu bằng `@PackageInfo`.

Annotation `@PackageInfo` có retention ở runtime và được giới thiệu từ Spring Modulith 1.2. Vì vậy, nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra phiên bản dependency trước khi áp dụng mẫu này.

## 3. Biểu diễn metadata của application module

Giả sử module inventory cần khai báo các dependency được phép. Trong Java, metadata có thể đặt ở `package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order"
)
package example.inventory;
~~~

Trong Kotlin, đặt một kiểu metadata ngay tại package gốc của module:

~~~kotlin
package example.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(allowedDependencies = "order")
@PackageInfo
class ModuleMetadata
~~~

Hai cách biểu diễn trên mô tả cùng một package metadata. Với Kotlin, `@PackageInfo` đánh dấu kiểu `ModuleMetadata` là nơi thay thế cho `package-info.java`, còn `@ApplicationModule` cung cấp metadata của application module.

Ví dụ khác, module có thể khai báo là OPEN:

~~~kotlin
package example.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(type = ApplicationModule.Type.OPEN)
@PackageInfo
class ModuleMetadata
~~~

Annotation `@ApplicationModule` vẫn có cùng ý nghĩa kiến trúc như khi đặt trên package trong Java. Khác biệt nằm ở nơi lưu annotation: Java dùng package declaration, còn Kotlin dùng một kiểu trong package được đánh dấu `@PackageInfo`.

## 4. Biểu diễn metadata cho named interface

Named interface mô tả một package con được module công khai cho module khác sử dụng. Nếu package đó không có `package-info.java`, có thể đặt một kiểu metadata ngay trong package con.

Ví dụ module order muốn công khai package `example.order.spi` với tên `spi`.

Cách khai báo trong Java:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package example.order.spi;
~~~

Cách khai báo trong Kotlin:

~~~kotlin
package example.order.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
~~~

Ở đây:

- Package được mô tả là `example.order.spi`.
- `@PackageInfo` đánh dấu `ModuleMetadata` là metadata carrier của package đó.
- `@NamedInterface("spi")` đặt tên phần API công khai là `spi`.

Các kiểu hợp đồng nằm trong cùng package, ví dụ:

~~~kotlin
package example.order.spi

interface OrderEventPublisher {
    fun publishOrderPlaced(orderId: String)
}
~~~

Module khác có thể phụ thuộc vào named interface `spi` theo cú pháp `order::spi`. Các package nội bộ khác của order vẫn tuân theo quy tắc encapsulation của module.

## 5. Khai báo dependency tới named interface

Khi provider đã công khai named interface, consumer có thể khai báo dependency cụ thể trong metadata của chính module đó.

Ví dụ module inventory cần dùng SPI của order:

~~~kotlin
package example.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    allowedDependencies = "order :: spi"
)
@PackageInfo
class ModuleMetadata
~~~

Cú pháp `order :: spi` gồm:

- `order`: tên application module cung cấp.
- `spi`: tên named interface được công khai bởi module order.
- `::`: dấu phân cách giữa tên module và tên named interface.

Trong cấu hình Kotlin, Spring Modulith minh họa cú pháp có khoảng trắng quanh `::`; điều quan trọng là tên module và named interface phải khớp với metadata phía provider.

Consumer cần đặt metadata carrier trong package gốc của chính nó. Provider đặt metadata carrier của named interface trong package con được công khai. Hai vị trí này mô tả hai phía khác nhau của hợp đồng.

## 6. Phân biệt @PackageInfo với @ApplicationModule và @NamedInterface

Các annotation có nhiệm vụ riêng, dù thường xuất hiện cùng nhau:

| Annotation | Vai trò |
|---|---|
| `@PackageInfo` | Đánh dấu một kiểu là nơi thay thế `package-info.java` khi Spring Modulith tra cứu metadata của package. |
| `@ApplicationModule` | Khai báo metadata hoặc quy tắc của application module, ví dụ loại module và dependency được phép. |
| `@NamedInterface` | Đặt tên cho một package con được module công khai. |

Có thể hình dung:

~~~text
example.inventory
└── ModuleMetadata
    ├── @PackageInfo
    └── @ApplicationModule(...)

example.order.spi
└── ModuleMetadata
    ├── @PackageInfo
    └── @NamedInterface("spi")
~~~

`@PackageInfo` không tự biến mọi package thành application module và cũng không tự công khai package con. Nó chỉ chỉ ra kiểu nào đại diện cho metadata của package. Ý nghĩa cụ thể đến từ annotation đi kèm.

Tương tự, chỉ thêm `@PackageInfo` vào một lớp mà không gắn `@ApplicationModule` hoặc `@NamedInterface` thì không tự khai báo các quy tắc module hay named interface tương ứng.

## 7. Liên hệ với chiến lược explicit module detection

Spring Modulith mặc định phát hiện module từ các package con trực tiếp của package chứa lớp `@SpringBootApplication`. Khi muốn chỉ phát hiện những package được đánh dấu tường minh, có thể cấu hình chiến lược:

~~~properties
spring.modulith.detection-strategy=explicitly-annotated
~~~

Chiến lược này xem các package được đánh dấu bằng Spring Modulith `@ApplicationModule` hoặc jMolecules `@Module` là module base package.

Trong Kotlin, metadata carrier của module có thể cung cấp annotation đó:

~~~kotlin
package example.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule
@PackageInfo
class ModuleMetadata
~~~

Khi dùng chiến lược `explicitly-annotated`, package inventory được đánh dấu rõ ràng qua `@ApplicationModule` trên kiểu metadata đại diện cho package.

Cần phân biệt hai cơ chế:

- **`@PackageInfo`** giải quyết cách biểu diễn metadata package trong ngôn ngữ không có `package-info.java`.
- **`spring.modulith.detection-strategy=explicitly-annotated`** thay đổi cách Spring Modulith lựa chọn package nào là module.

Có thể dùng metadata carrier mà vẫn giữ chiến lược phát hiện mặc định. Nếu dùng `explicitly-annotated`, cần bảo đảm mọi module muốn được phát hiện đều có khai báo `@ApplicationModule` hoặc `@Module` phù hợp.

## 8. Tổ chức metadata carrier trong dự án Kotlin

Một ứng dụng có thể đặt metadata carrier theo từng package:

~~~text
src/main/kotlin
└── example
    ├── Application.kt
    ├── inventory
    │   ├── ModuleMetadata.kt
    │   ├── StockAvailability.kt
    │   └── internal
    │       └── StockRepository.kt
    └── order
        ├── ModuleMetadata.kt
        ├── OrderManagement.kt
        └── spi
            ├── ModuleMetadata.kt
            └── OrderEventPublisher.kt
~~~

Mỗi `ModuleMetadata.kt` nằm trong package mà nó mô tả:

- `example.inventory.ModuleMetadata` mô tả package gốc module inventory.
- `example.order.ModuleMetadata` mô tả package gốc module order.
- `example.order.spi.ModuleMetadata` mô tả named interface trong package order.spi.

Có thể dùng cùng tên lớp `ModuleMetadata` ở nhiều package vì tên đầy đủ của chúng khác nhau. Cách đặt tên thống nhất giúp người đọc nhanh chóng nhận ra các lớp này chỉ phục vụ metadata kiến trúc.

Không đặt metadata carrier trong một package chung như `example.metadata` rồi mong annotation áp dụng cho các package khác. Kiểu được đánh dấu phải nằm trong package cần mô tả để Spring Modulith tra cứu metadata đúng phạm vi.

## 9. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Annotation trên metadata carrier không được nhận diện | Thiếu `@PackageInfo`. | Đánh dấu kiểu metadata bằng `@PackageInfo`. |
| Module không được phát hiện khi dùng explicit strategy | Package không có `@ApplicationModule` hoặc `@Module` phù hợp. | Thêm metadata module ở package gốc. |
| Named interface không được nhận diện | Metadata carrier nằm sai package hoặc thiếu `@NamedInterface`. | Đặt carrier trong package con và khai báo tên interface. |
| Dependency `module::interface` không hợp lệ | Tên module hoặc tên named interface không khớp. | Đối chiếu tên với metadata phía provider. |
| Metadata của module bị gắn vào package khác | Carrier được đặt ngoài package cần mô tả. | Di chuyển carrier vào đúng package. |
| Dùng `@PackageInfo` như annotation phát hiện module | Nhầm vai trò của marker metadata với annotation module. | Kết hợp `@PackageInfo` với `@ApplicationModule` khi cần khai báo module. |

Khi một package không được nhận diện như mong muốn, hãy kiểm tra lần lượt vị trí package của metadata carrier, annotation `@PackageInfo`, annotation mô tả module/interface và chiến lược detection đang được cấu hình.

## 10. Kiểm chứng metadata sau khi khai báo

Sau khi đặt metadata carrier, có thể yêu cầu Spring Modulith tạo mô hình và xác minh cấu trúc:

~~~kotlin
import org.junit.jupiter.api.Test
import org.springframework.modulith.core.ApplicationModules

class ModularityTests {

    @Test
    fun verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application::class.java).verify()
    }
}
~~~

Nếu dự án dùng Java cho lớp ứng dụng, có thể truyền `Application.class`; nếu dùng Kotlin, cú pháp `Application::class.java` chuyển Kotlin class reference thành Java `Class`.

Ngoài `verify()`, có thể in các module được phát hiện để kiểm tra tên và package base:

~~~kotlin
val modules = ApplicationModules.of(Application::class.java)
modules.forEach { println(it) }
~~~

Kết quả giúp nhóm xác nhận module nào đã được phát hiện và package nào đang được xem là base package. Khi kiểm tra thất bại, hãy đọc thông báo vi phạm và đối chiếu với metadata carrier ở đúng package.

## 11. Quy trình áp dụng

1. **Xác định package cần mô tả.** Phân biệt package gốc của application module và package con cần công khai.
2. **Tạo metadata carrier.** Đặt một lớp như `ModuleMetadata` ngay trong package đó.
3. **Đánh dấu `@PackageInfo`.** Cho Spring Modulith biết kiểu này thay thế `package-info.java`.
4. **Thêm annotation có ý nghĩa.** Dùng `@ApplicationModule` cho metadata module hoặc `@NamedInterface` cho package API được công khai.
5. **Chọn detection strategy phù hợp.** Giữ mặc định nếu cấu trúc package đã phù hợp; dùng `explicitly-annotated` nếu muốn chỉ phát hiện package được đánh dấu.
6. **Khai báo dependency.** Dùng tên module và named interface đã công khai.
7. **Kiểm chứng mô hình.** Chạy `ApplicationModules.verify()` và kiểm tra danh sách module được phát hiện.

Hãy giữ metadata carrier nhỏ, đặt đúng package và chỉ khai báo những thông tin cần thiết. Nếu package có nhiều trách nhiệm khác nhau, hãy xem lại ranh giới module hoặc named interface trước khi bổ sung thêm annotation.

## Ghi nhớ

Khi ngôn ngữ như Kotlin không có `package-info.java`, Spring Modulith cho phép dùng một kiểu trong package làm metadata carrier. Đánh dấu kiểu đó bằng `@PackageInfo`, sau đó kết hợp `@ApplicationModule` để mô tả application module hoặc `@NamedInterface` để mô tả API có tên.

`@PackageInfo` giải quyết vị trí lưu metadata; detection strategy quyết định package nào được chọn làm module. Phân biệt hai trách nhiệm này, đặt metadata carrier đúng package và kiểm chứng bằng `ApplicationModules.verify()` giúp duy trì ranh giới module rõ ràng trong ứng dụng Kotlin/Spring Boot.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — PackageInfo](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html)
