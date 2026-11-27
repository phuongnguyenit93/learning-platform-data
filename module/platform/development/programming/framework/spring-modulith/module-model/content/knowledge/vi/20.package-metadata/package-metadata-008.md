# Giữ metadata gần boundary được mô tả

Trong Spring Modulith, package metadata mô tả ranh giới của chính package nơi metadata được khai báo. Metadata của một Application Module thuộc **package gốc của module**; metadata của một Named Interface thuộc **subpackage được công bố**. Đặt annotation ở package cha, package con khác hoặc một thư mục **metadata** dùng chung có thể khiến Spring Modulith đọc sai boundary mà đội ngũ muốn mô tả.

Với Java, package metadata thường được đặt trong **package-info.java** ở đúng thư mục package. Với Kotlin, có thể dùng một class nằm trong package đó và đánh dấu bằng **@PackageInfo**. Bài học này trình bày cách bố trí metadata gần boundary, phân biệt metadata module với metadata Named Interface, nhận diện cách đặt sai và kiểm tra mô hình mà Spring Modulith thực sự phát hiện.

## 1. Package metadata gắn với package nào?

Package metadata là annotation mô tả một package trong mô hình kiến trúc. Spring Modulith sử dụng metadata đó để hiểu module, các giao diện được công bố và những quy tắc liên quan.

Có hai boundary cần phân biệt:

- **Application Module boundary**: package gốc (base package) đại diện cho một module. **@ApplicationModule** mô tả module đó, chẳng hạn identifier, display name, loại OPEN/CLOSED hoặc allowed dependencies.
- **Named Interface boundary**: một subpackage được công bố thành API bổ sung của module. **@NamedInterface** mô tả chính subpackage đó.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders                         <- module boundary
│   ├── package-info.java          <- @ApplicationModule
│   ├── OrderManagement.java
│   ├── spi                        <- named interface boundary
│   │   ├── package-info.java      <- @NamedInterface("spi")
│   │   └── OrderPricingPolicy.java
│   └── internal                   <- implementation detail
│       └── JpaOrderRepository.java
└── inventory                      <- module boundary
    ├── package-info.java          <- @ApplicationModule
    └── InventoryService.java
~~~

Metadata được đặt ngay tại package mà nó mô tả. File **orders/package-info.java** mô tả module **orders**; file **orders/spi/package-info.java** mô tả Named Interface **spi** thuộc module đó.

## 2. Vì sao phải đặt metadata đúng vị trí?

Annotation package-level gắn với một package cụ thể. Nó không tự động được kế thừa xuống mọi subpackage.

Ví dụ, khai báo **@ApplicationModule** trong **com.acme.shop.orders** mô tả module **orders**. Nó không tự biến **com.acme.shop.orders.spi** thành Named Interface. Muốn công bố **spi**, cần metadata ngay trong package **com.acme.shop.orders.spi**.

Tương tự, nếu đặt **@NamedInterface("spi")** trong package **com.acme.shop.orders** thì annotation đang mô tả package gốc **orders**, không phải subpackage **orders.spi**. Điều đó không thể thay thế metadata tại boundary **spi**.

Đặt metadata xa package được mô tả còn làm người bảo trì khó trả lời các câu hỏi:

- Package nào đang được công bố?
- Module nào sở hữu Named Interface?
- Annotation có còn đúng sau khi package được di chuyển?
- Một package con có đang vô tình dùng metadata của package khác?

Giữ metadata cùng package boundary giúp cấu trúc source code tự giải thích kiến trúc của nó.

## 3. Đặt metadata Application Module trong Java

Với Java, tạo file **package-info.java** trong thư mục tương ứng với base package của module.

Đường dẫn:

~~~text
src/main/java/com/acme/shop/orders/package-info.java
~~~

Nội dung:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Orders"
)
package com.acme.shop.orders;
~~~

File này mô tả module **orders**. Các thuộc tính module như **id**, **displayName**, **type** hoặc **allowedDependencies** được khai báo tại boundary này vì chúng mô tả module, không phải một class triển khai riêng lẻ.

Ví dụ module **inventory** giới hạn dependency ở API mặc định của **orders**:

~~~text
src/main/java/com/acme/shop/inventory/package-info.java
~~~

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.inventory;
~~~

**allowedDependencies** là quy tắc của module tiêu thụ **inventory**, vì vậy annotation được đặt ở package gốc **inventory**. Không đặt allowlist này trong package **orders** chỉ vì **orders** là module được tham chiếu.

## 4. Đặt metadata Named Interface trong đúng subpackage

Giả sử **orders** muốn công bố một SPI để module khác triển khai chính sách tính giá. Type nằm trong:

~~~text
com.acme.shop.orders.spi.OrderPricingPolicy
~~~

Tạo file:

~~~text
src/main/java/com/acme/shop/orders/spi/package-info.java
~~~

Nội dung:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Giờ đây, package **orders.spi** được công bố thành Named Interface có tên **spi**. Consumer có thể khai báo dependency tới giao diện đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.inventory;
~~~

Nếu module **orders** còn công bố event contract trong package **orders.events**, hãy tạo metadata riêng tại:

~~~text
src/main/java/com/acme/shop/orders/events/package-info.java
~~~

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Mỗi Named Interface được mô tả tại package của chính nó. Annotation ở **orders.spi** không công bố **orders.events**; hai boundary cần metadata độc lập.

## 5. Dùng @PackageInfo thay cho package-info.java trong Kotlin

Kotlin không hỗ trợ Java **package-info.java**. Spring Modulith cung cấp **@PackageInfo** để đánh dấu một type là đại diện cho package metadata. Type đó phải nằm trong đúng package mà annotation mô tả.

Metadata cho module **orders**:

~~~kotlin
package com.acme.shop.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    id = "orders",
    displayName = "Orders"
)
@PackageInfo
class ModuleMetadata
~~~

Metadata cho Named Interface **spi**:

~~~kotlin
package com.acme.shop.orders.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
~~~

Hai class có cùng tên **ModuleMetadata** nhưng thuộc hai package khác nhau. Mỗi class đánh dấu metadata cho package đang chứa nó.

Metadata cho consumer **inventory** cũng nằm trong package gốc của consumer:

~~~kotlin
package com.acme.shop.inventory

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    allowedDependencies = "orders :: spi"
)
@PackageInfo
class ModuleMetadata
~~~

Không đặt class metadata Kotlin trong một package chung như **com.acme.shop.metadata** rồi kỳ vọng annotation của nó mô tả **orders**, **orders.spi** hoặc **inventory**. Package của class là package mà Spring Modulith đọc metadata.

## 6. Phân biệt metadata module, Named Interface và application root

Không phải annotation nào cũng thuộc cùng một boundary:

| Metadata | Vị trí | Nó mô tả |
|---|---|---|
| **@Modulithic** | Class ứng dụng Spring Boot | Cấu hình tổng thể của modulith, ví dụ additional packages và module naming |
| **@ApplicationModule** | Package gốc của module | Danh tính, loại module và quy tắc dependency của module |
| **@NamedInterface** | Package con được công bố | Một API boundary bổ sung của module |
| **@PackageInfo** | Type metadata trong package đích (Kotlin) | Đánh dấu type thay thế **package-info.java** để đọc package annotations |

Ví dụ, **@Modulithic** trên class **ShopApplication** cấu hình application model. Nó không thay thế **@ApplicationModule** trong **orders** hoặc **inventory**, và cũng không thay thế **@NamedInterface** trong **orders.spi**.

Giữ từng loại metadata ở đúng cấp giúp người đọc biết thay đổi nào ảnh hưởng toàn ứng dụng, thay đổi nào chỉ ảnh hưởng một module và thay đổi nào chỉ công bố một subpackage.

## 7. Những cách đặt metadata sai thường gặp

### Đặt Named Interface ở package cha

~~~java
// File: com/acme/shop/orders/package-info.java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders;
~~~

Annotation này mô tả package **orders**. Nếu mục tiêu là công bố **orders.spi**, phải chuyển annotation sang **orders/spi/package-info.java**.

### Đặt metadata trong package metadata dùng chung

~~~text
com.acme.shop
├── metadata
│   └── ModuleMetadata.java
├── orders
└── inventory
~~~

Class nằm trong **com.acme.shop.metadata** nên annotation package metadata gắn với package đó. Nó không mô tả **orders** hoặc **inventory**.

### Đặt Kotlin ModuleMetadata ở sai package

~~~kotlin
package com.acme.shop.orders.internal

@PackageInfo
@ApplicationModule(type = ApplicationModule.Type.OPEN)
class ModuleMetadata
~~~

Nếu ý định là cấu hình module **orders**, metadata này nằm quá sâu trong **orders.internal**. Hãy chuyển type metadata về package gốc **com.acme.shop.orders**.

### Dùng một Named Interface cho nhiều boundary không liên quan

Nếu **orders.spi** và **inventory.spi** là hai nhóm hợp đồng riêng, mỗi package cần metadata của chính nó. Không gom annotation vào một package cha rồi giả định tất cả subpackage có cùng tên sẽ được công bố.

### Đổi package nhưng quên di chuyển metadata

Khi refactor **orders.spi** sang **orders.integration.spi**, phải di chuyển **package-info.java** hoặc Kotlin metadata type và cập nhật package declaration. Nếu chỉ chuyển source type mà để metadata ở package cũ, boundary mới có thể không còn được công bố như dự định.

## 8. Metadata không thay thế Java visibility hoặc component scanning

Package metadata của Spring Modulith mô tả kiến trúc module. Nó không tự thay đổi modifier của Java hoặc cấu hình khởi tạo bean.

- **@NamedInterface** không biến class package-private thành public.
- **@ApplicationModule** không tự đăng ký class thành Spring bean.
- **@PackageInfo** chỉ đánh dấu type dùng làm package metadata; không phải annotation component.
- **@ComponentScan** và cấu hình JPA entity scan vẫn là cơ chế riêng của Spring Boot/Spring Framework.

Một Named Interface thường chứa các type public để module khác có thể tham chiếu. Sau đó, Spring Modulith kiểm tra xem dependency thực tế có đi qua boundary được công bố hay không.

## 9. Kiểm tra metadata mà Spring Modulith thực sự phát hiện

Sau khi bố trí package metadata, có thể kiểm tra mô hình:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class PackageMetadataTests {

    @Test
    void detectsModuleAndNamedInterfaceAtTheirPackages() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        var orders = modules.getModuleByName("orders").orElseThrow();

        assertThat(orders.getBasePackage().getName())
            .isEqualTo("com.acme.shop.orders");

        assertThat(orders.getNamedInterfaces().getByName("spi"))
            .isPresent();

        modules.verify();
    }
}
~~~

Test kiểm tra ba điều:

1. Module **orders** được phát hiện từ đúng base package.
2. Named Interface **spi** xuất hiện trong module sở hữu nó.
3. Các dependency và access rule của application model vẫn hợp lệ.

Có thể in toàn bộ Named Interface để điều tra:

~~~java
modules.stream().forEach(module -> {
    System.out.println("Module: " + module.getIdentifier());
    System.out.println("Base package: " + module.getBasePackage().getName());

    module.getNamedInterfaces().stream()
        .forEach(namedInterface ->
            System.out.println("Interface: " + namedInterface.getName()));
});
~~~

Nếu **spi** không xuất hiện, hãy kiểm tra package declaration và vị trí file metadata trước khi sửa **allowedDependencies**. Consumer không thể tham chiếu một Named Interface mà provider chưa công bố trong mô hình.

## 10. Quy trình giữ metadata gần boundary

Khi tạo module hoặc refactor package, thực hiện theo trình tự:

1. Xác định package gốc đại diện cho Application Module.
2. Đặt **package-info.java** hoặc Kotlin metadata type ngay trong package gốc đó.
3. Khai báo **@ApplicationModule** tại module boundary nếu cần metadata module tường minh.
4. Xác định từng subpackage cần công bố thành API bổ sung.
5. Đặt **@NamedInterface** hoặc Kotlin **@PackageInfo** ngay trong từng subpackage được công bố.
6. Đặt **allowedDependencies** ở package gốc của module tiêu thụ.
7. Khi đổi package, di chuyển metadata cùng package boundary và sửa package declaration.
8. Kiểm tra base package và danh sách Named Interface bằng **ApplicationModules**.
9. Chạy **ApplicationModules.verify()** để xác nhận các dependency thực tế tuân thủ boundary.

Một quy tắc dễ duy trì là: **metadata nằm cùng package mà nó mô tả**. Module metadata đi cùng base package; Named Interface metadata đi cùng package được công bố; metadata ứng dụng đi cùng class ứng dụng. Khi source code và metadata di chuyển cùng nhau, ranh giới kiến trúc ít bị lệch sau các lần refactor.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): vị trí **@ApplicationModule**, **@NamedInterface**, Java **package-info.java** và Kotlin **@PackageInfo**.
- [Spring Modulith Javadoc — PackageInfo](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/PackageInfo.html): **@PackageInfo** đánh dấu type thay thế Java **package-info.java** khi tra cứu package annotations.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html): metadata mô tả Application Module.
- [Spring Modulith Javadoc — NamedInterface](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html): metadata công bố package hoặc gán type vào Named Interface.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): **getBasePackage()** và **getNamedInterfaces()** để kiểm tra mô hình đã phát hiện.
