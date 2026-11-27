# `package-info.java` và vai trò trong module model

`package-info.java` là file Java dùng để mô tả package và khai báo annotation ở cấp package. Trong Spring Modulith, file này là nơi thuận tiện để gắn metadata cho application module và các package API của module. Ví dụ, `@ApplicationModule` có thể khai báo quy tắc của module tại package gốc, còn `@NamedInterface` có thể đánh dấu một package con là giao diện được công khai.

Nhờ package metadata, ý định kiến trúc nằm ngay cạnh mã nguồn mà nó mô tả. Spring Modulith đọc metadata này khi xây dựng module model để xác định module type, allowed dependencies và named interfaces. Tuy nhiên, `package-info.java` không phải module descriptor của Java Platform Module System (JPMS), cũng không tự thay đổi quyền truy cập của Java hay cấu hình Spring bean.

Sau bài học, bạn có thể:

- Giải thích mục đích của `package-info.java` trong Java.
- Đặt package-level annotation đúng vị trí và đúng package.
- Dùng `@ApplicationModule` để khai báo metadata cho module.
- Dùng `@NamedInterface` để công khai một package con.
- Phân biệt package metadata với `module-info.java`, Java visibility và runtime behavior.
- Kiểm tra metadata đã được Spring Modulith nhận diện bằng `ApplicationModules`.

## 1. `package-info.java` là gì?

Java cho phép khai báo annotation và tài liệu ở cấp package. Để làm điều đó, một package có thể có file nguồn tên chính xác là `package-info.java`. File này không chứa class hay interface thông thường; nó chứa package declaration, package annotations và thường có Javadoc mô tả package.

Ví dụ, package `com.acme.shop.inventory` có thể có cấu trúc:

```text
src/main/java
└── com/acme/shop/inventory
    ├── package-info.java
    ├── InventoryManagement.java
    ├── Reservation.java
    └── internal
        └── StockRepository.java
```

Nội dung tối thiểu của `package-info.java`:

```java
/**
 * Quản lý tồn kho và giữ hàng cho các đơn đặt hàng.
 */
package com.acme.shop.inventory;
```

Javadoc ở đầu file mô tả package và có thể được dùng khi tạo tài liệu JavaDoc. Khi cần metadata kiến trúc, bạn đặt package-level annotation trước câu lệnh `package`:

```java
/**
 * Module sở hữu tồn kho và quy trình giữ hàng.
 */
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
```

Annotation xuất hiện trước package declaration vì nó áp dụng cho chính package được khai báo bên dưới. Tên package phải khớp với package của các source file trong thư mục đó.

## 2. Vì sao Spring Modulith dùng package metadata?

Spring Modulith mô hình hóa ứng dụng theo package. Package gốc của một application module là điểm neo để nhận diện module; các package con có thể chứa implementation nội bộ hoặc named interface được công khai.

Package metadata cho phép khai báo các quyết định kiến trúc ngay tại vị trí tương ứng:

| Annotation | Vị trí thường dùng | Vai trò trong module model |
|---|---|---|
| `@ApplicationModule` | `package-info.java` của package gốc module | Khai báo metadata như module type và allowed dependencies |
| `@NamedInterface` | `package-info.java` của package API con | Đánh dấu package là named interface được module công khai |
| jMolecules `@Module` | Package gốc module | Có thể được dùng làm dấu hiệu module khi chọn chiến lược `explicitly-annotated` |

Nếu dùng detection strategy mặc định `direct-subpackages`, package con trực tiếp của root package có thể được nhận diện là module mà không cần `@ApplicationModule`. Khi đó, `package-info.java` vẫn hữu ích để bổ sung metadata như `allowedDependencies` hoặc `type`.

Nếu dùng `explicitly-annotated`, package module phải được đánh dấu bằng `@ApplicationModule` hoặc annotation `@Module` của jMolecules để được chọn làm module. Vì thế, sự hiện diện của `package-info.java` có thể mang ý nghĩa quyết định đối với module detection tùy cấu hình của ứng dụng.

## 3. Khai báo metadata module bằng `@ApplicationModule`

Đặt `@ApplicationModule` trong `package-info.java` của package gốc module. Ví dụ, module `inventory` chỉ cho phép phụ thuộc vào module `catalog`:

```java
/**
 * Quản lý tồn kho và giữ hàng.
 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog"
)
package com.acme.shop.inventory;
```

Annotation này gắn metadata với package `com.acme.shop.inventory`. Spring Modulith đọc `allowedDependencies` khi tạo module model và kiểm tra phụ thuộc. Nếu mã trong `inventory` tham chiếu một module khác ngoài `catalog` mà không được cho phép theo quy tắc tương ứng, `ApplicationModules.verify()` có thể báo vi phạm.

Bạn cũng có thể khai báo kiểu module tường minh:

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED,
        allowedDependencies = "catalog"
)
package com.acme.shop.inventory;
```

`CLOSED` là kiểu mặc định. Module đóng giới hạn quyền truy cập từ module khác vào package gốc và các named interface được công khai. Dùng `OPEN` khi có lý do chuyển đổi codebase cũ hoặc cần semantics mở rộng package access; việc đó ảnh hưởng đến ranh giới truy cập và cycle detection.

`@ApplicationModule` mô tả quy tắc cho module. Annotation không tự ngăn Java compiler biên dịch một số tham chiếu `public` vi phạm quy tắc kiến trúc. Hãy chạy `ApplicationModules.verify()` trong architecture test để thực thi các quy tắc đó.

## 4. Khai báo named interface bằng `@NamedInterface`

Một module có thể công khai một phần API nằm trong package con. Tạo `package-info.java` ngay trong package con đó và gắn `@NamedInterface`.

Ví dụ, module `inventory` có package `spi` chứa hợp đồng tích hợp:

```text
com.acme.shop.inventory
├── package-info.java
├── InventoryManagement.java
├── internal
│   └── DefaultInventoryService.java
└── spi
    ├── package-info.java
    ├── StockReservation.java
    └── ReservationResult.java
```

Trong `src/main/java/com/acme/shop/inventory/spi/package-info.java`:

```java
/**
 * Hợp đồng tích hợp được module inventory công khai.
 */
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Kiểu được công khai trong package:

```java
package com.acme.shop.inventory.spi;

public interface StockReservation {

    ReservationResult reserve(String sku, int quantity);
}
```

Module khác có thể khai báo phụ thuộc vào named interface này bằng identifier `inventory::spi`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::spi"
)
package com.acme.shop.checkout;
```

Phần trước `::` là tên module; phần sau là tên named interface. Package `inventory.spi` được đánh dấu là một giao diện có tên `spi`, vì vậy module tiêu thụ có thể tham chiếu hợp đồng qua named interface thay vì truy cập package nội bộ bất kỳ.

`@NamedInterface` cũng có thể đặt trực tiếp trên type khi chỉ muốn gắn một hoặc một nhóm type cụ thể vào named interface. Đánh dấu ở cấp package bằng `package-info.java` phù hợp khi toàn bộ package là một hợp đồng được công khai.

## 5. Nhiều package có thể có nhiều file `package-info.java`

Mỗi package có thể có file `package-info.java` riêng. File metadata của package gốc và file metadata của package con phục vụ các mục đích khác nhau.

```text
com.acme.shop.inventory
├── package-info.java           <- @ApplicationModule
├── InventoryManagement.java
├── internal
│   ├── package-info.java       <- Javadoc/metadata nội bộ nếu cần
│   └── StockRepository.java
└── spi
    ├── package-info.java      <- @NamedInterface("spi")
    └── StockReservation.java
```

Ví dụ, file ở package gốc:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog"
)
package com.acme.shop.inventory;
```

File ở package `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Hai annotation gắn vào hai package khác nhau. `@ApplicationModule` mô tả module `inventory`; `@NamedInterface` đánh dấu package con `inventory.spi` là API được module sở hữu công khai. Không đặt cả hai annotation vào một file rồi kỳ vọng chúng áp dụng cho hai package khác nhau: một `package-info.java` chỉ khai báo một package.

## 6. Cú pháp package annotation và tên đầy đủ

Trong Java, package annotations nằm trước package declaration. Import declaration nằm sau package declaration, nên không thể viết một lệnh `import` thông thường ở đầu `package-info.java` rồi mới dùng tên annotation rút gọn phía trước câu lệnh package.

Vì vậy, cách rõ ràng và an toàn là dùng tên đầy đủ của annotation:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Nếu có nhiều package annotations, đặt chúng liên tiếp trước package declaration:

```java
@org.springframework.lang.NonNullApi
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
```

Ví dụ này đồng thời áp dụng nullability metadata của Spring và named interface metadata cho cùng package. Chỉ thêm annotation mà dự án thực sự sử dụng và đã có dependency phù hợp.

## 7. `package-info.java` khác `module-info.java`

Hai file có tên gần giống nhưng vai trò khác nhau:

| Tiêu chí | `package-info.java` | `module-info.java` |
|---|---|---|
| Phạm vi | Một Java package | Một Java Platform Module System module |
| Mục đích | Javadoc và package-level annotations | Khai báo JPMS module, `requires`, `exports`, `opens`, `uses`, `provides` |
| Spring Modulith | Gắn metadata cho application module và named interface | Không phải cách thông thường để khai báo application module của Spring Modulith |
| Tác động đến Java visibility | Không tự thay đổi access modifier | Có thể giới hạn khả năng truy cập package qua JPMS exports/opens |
| Số lượng | Có thể có một file cho mỗi package | Một module descriptor cho một JPMS module |

Spring Modulith tổ chức module ở cấp ứng dụng dựa trên package và metadata. Bạn không cần tạo `module-info.java` để một package con trực tiếp được nhận diện là application module theo detection strategy mặc định.

## 8. Package metadata không thay thế Java visibility

`@NamedInterface` đánh dấu một package là API trong mô hình kiến trúc. Nó không biến lớp package-private thành `public`, không làm method private có thể được gọi từ package khác và không thay đổi quy tắc truy cập của Java.

Ví dụ, type cần được module khác import phải có visibility phù hợp:

```java
package com.acme.shop.inventory.spi;

public interface StockReservation {
    boolean reserve(String sku, int quantity);
}
```

Nếu khai báo interface top-level không có `public`, mã trong package `checkout` không thể import nó theo quy tắc Java, dù package đã được đánh dấu `@NamedInterface("spi")`.

Ngược lại, một lớp `public` trong package `inventory.internal` vẫn có thể được Java compiler cho phép import từ package khác. Nếu module `inventory` là `CLOSED`, Spring Modulith có thể phát hiện và báo vi phạm ranh giới module. Vì vậy, Java visibility và module visibility là hai lớp quy tắc cần được hiểu cùng nhau.

## 9. Metadata được đưa vào module model như thế nào?

`package-info.java` được biên dịch thành metadata package trong bytecode. Annotation có retention phù hợp có thể được framework đọc khi phân tích package. Spring Modulith dùng metadata này cùng package structure và type references để xây dựng application module arrangement.

Bạn có thể quan sát kết quả bằng `ApplicationModules`:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleMetadataInspection {

    void inspect() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(module -> {
            System.out.println(module.getIdentifier());
            System.out.println(module.getBasePackage());
            System.out.println(module.getNamedInterfaces());
        });

        modules.verify();
    }
}
```

Đầu ra cho phép kiểm tra logical identifier, package cơ sở và các named interface mà Spring Modulith nhận diện. `verify()` tiếp tục kiểm tra quy tắc module như phụ thuộc, truy cập package và chu trình.

Trong architecture test, dùng lớp ứng dụng chính:

```java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesPackageMetadata() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu metadata không được nhận diện, hãy kiểm tra file có đúng tên `package-info.java`, câu lệnh package có đúng với đường dẫn và annotation có nằm trước package declaration hay không. Cũng cần bảo đảm file thuộc source set được biên dịch vào classpath của bài kiểm tra.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@ApplicationModule` không được nhận diện | File nằm sai package hoặc package declaration sai | Đặt `package-info.java` trong đúng thư mục và kiểm tra tên package |
| Named interface không xuất hiện | `@NamedInterface` đặt ở package khác với package chứa API | Đặt annotation trong `package-info.java` của đúng package API |
| Dùng tên annotation rút gọn không biên dịch | Import không thể đứng trước package declaration | Dùng fully qualified annotation name |
| Lớp trong named interface không import được | Type top-level không có `public` | Khai báo `public` cho type cần được sử dụng ngoài package |
| Module khác vẫn truy cập được lớp `public` nội bộ trong IDE | Java compiler không tự hiểu quy tắc module của Spring Modulith | Chạy `ApplicationModules.verify()` để kiểm tra module boundary |
| Module không được phát hiện khi dùng `explicitly-annotated` | Package module thiếu `@ApplicationModule` hoặc jMolecules `@Module` | Bổ sung annotation phù hợp |
| Nghĩ rằng `package-info.java` thay thế `module-info.java` | Nhầm package metadata với JPMS descriptor | Chọn cơ chế theo đúng mục tiêu: Spring Modulith module model hay Java platform module |

## 11. Ghi nhớ

`package-info.java` mô tả một Java package bằng Javadoc và package-level annotations. Trong Spring Modulith, `@ApplicationModule` ở package gốc khai báo metadata module; `@NamedInterface` ở package con đánh dấu API được công khai. Mỗi package có file metadata riêng, và annotation phải đặt trước package declaration. Package metadata được đọc khi xây dựng module model nhưng không thay đổi Java visibility, không tạo Spring bean và không thay thế `module-info.java`. Hãy kết hợp metadata với `ApplicationModules.verify()` để kiểm tra ranh giới kiến trúc.

## Tài liệu tham khảo

- [Java Language Specification – Package Declarations và Package Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
- [Java API – Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html)
- [Spring Modulith Fundamentals – Application Modules và Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API – `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API – `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Spring Modulith API – `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
