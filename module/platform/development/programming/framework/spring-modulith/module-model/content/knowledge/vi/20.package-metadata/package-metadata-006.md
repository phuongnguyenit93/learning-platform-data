# Quản lý metadata khi đổi tên package

Trong Spring Modulith, package không chỉ là nơi đặt class. Cấu trúc package còn giúp framework nhận diện application module, xác định package nào là API và kiểm tra dependency giữa các module. Các annotation đặt trong `package-info.java` bổ sung metadata cho những ranh giới đó.

Khi đổi tên hoặc di chuyển package, cần cập nhật cả cấu trúc mã nguồn lẫn metadata gắn với package. Một refactor chỉ đổi đường dẫn thư mục hoặc package declaration có thể khiến annotation không còn gắn với package dự kiến, module identifier thay đổi hoặc các khai báo dependency dạng chuỗi trở nên lỗi thời.

Bài này tập trung vào cách giữ metadata nhất quán khi đổi tên package của một application module hoặc một package con trong module.

## 1. Package metadata được lưu ở đâu?

Java cho phép khai báo annotation và Javadoc ở cấp package thông qua file `package-info.java`. File này thường nằm ngay trong thư mục tương ứng với package:

~~~text
src/main/java
└── com
    └── acme
        └── shop
            └── inventory
                ├── package-info.java
                ├── InventoryManagement.java
                ├── internal
                └── spi
~~~

Ví dụ `package-info.java` của module `inventory`:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory",
    allowedDependencies = "catalog::api"
)
package com.acme.shop.inventory;
~~~

Annotation `@ApplicationModule` gắn metadata module vào package `com.acme.shop.inventory`. Trong đó:

- `displayName` là tên dễ đọc dùng khi mô tả module.
- `allowedDependencies` khai báo các module hoặc named interface mà module được phép phụ thuộc.
- Các thuộc tính khác của annotation có thể mô tả identifier hoặc loại module tùy theo cấu hình và phiên bản Spring Modulith đang dùng.

Một package con có thể có `package-info.java` riêng để công bố named interface:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
~~~

File `package-info.java` là một phần của mã nguồn Java. Package declaration trong file phải khớp với package mà file đại diện. Khi đổi tên package, hãy di chuyển file này cùng package và cập nhật dòng `package`.

## 2. Metadata và tên package có quan hệ như thế nào?

Không phải mọi metadata đều phụ thuộc trực tiếp vào tên package. Cần phân biệt các loại tên:

| Thành phần | Ví dụ | Ý nghĩa khi đổi package |
| --- | --- | --- |
| Base package | `com.acme.shop.inventory` | Thay đổi khi module được di chuyển hoặc đổi tên package gốc |
| Module identifier mặc định | `inventory` | Có thể thay đổi nếu tên module được suy ra từ tên package |
| Explicit module identifier | `id = "inventory"` | Giữ ổn định nếu không chủ động đổi giá trị |
| Display name | `Inventory` | Không tự đổi theo package |
| Named interface name | `spi` | Giữ ổn định nếu vẫn khai báo cùng tên tường minh |
| Java fully qualified class name | `com.acme.shop.inventory.InventoryManagement` | Thay đổi khi class chuyển package |
| Dependency declaration | `inventory::spi` | Thay đổi nếu module identifier hoặc named interface name thay đổi |

Điểm quan trọng là package path, module identifier và display name là ba khái niệm riêng. Đổi package không nhất thiết phải đổi identifier hoặc tên hiển thị, nhưng nếu identifier được suy ra từ package thì cần đánh giá ảnh hưởng đến những module đang phụ thuộc.

## 3. Trước khi đổi tên package, xác định phạm vi refactor

Hãy xác định package nào đang được đổi:

1. **Đổi base package của module:** ví dụ `com.acme.shop.inventory` thành `com.acme.platform.stock`.
2. **Đổi package con nội bộ:** ví dụ `inventory.internal.persistence` thành `inventory.storage`.
3. **Di chuyển package con có named interface:** ví dụ `inventory.spi` thành `inventory.integration`.

Ba trường hợp này có ảnh hưởng khác nhau. Đổi base package có thể tác động đến cách Spring Modulith nhận diện module và module identifier mặc định. Đổi package con nội bộ chủ yếu tác động đến class name, import và cấu hình tham chiếu đến package đó. Đổi package con có named interface còn cần giữ hoặc cập nhật tên giao diện mà module tiêu thụ đang dùng.

Trước khi refactor, ghi nhận:

- Base package hiện tại của module.
- `@ApplicationModule` đang khai báo trong `package-info.java`.
- Các `@NamedInterface` trên package con.
- Những `allowedDependencies` ở module cung cấp và module sử dụng.
- Các package name được khai báo dưới dạng chuỗi trong cấu hình ứng dụng.

Việc này giúp xác định phần metadata cần được giữ nguyên và phần cần đổi theo thiết kế mới.

## 4. Đổi base package nhưng giữ module identifier

Giả sử module hiện có package:

~~~text
com.acme.shop.inventory
~~~

và `package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory",
    allowedDependencies = "catalog::api"
)
package com.acme.shop.inventory;
~~~

Nhóm quyết định chuyển module sang namespace `com.acme.platform.stock`. Nếu muốn tên logic của module tiếp tục là `inventory`, có thể khai báo identifier tường minh:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory",
    allowedDependencies = "catalog::api"
)
package com.acme.platform.stock;
~~~

Khi đó:

- Base package mới là `com.acme.platform.stock`.
- Module identifier được giữ là `inventory`.
- Display name vẫn là `Inventory`.
- Dependency từ module khác có thể tiếp tục dùng `inventory` nếu các điều kiện khác của hợp đồng không thay đổi.

`id` tách định danh logic của module khỏi tên package. Cách này hữu ích khi tổ chức muốn sắp xếp lại namespace Java mà không muốn đổi tên module mà các module khác đang tham chiếu.

Nếu không khai báo identifier tường minh, Spring Modulith có thể dùng tên module dựa trên package. Khi tên package hoặc vị trí module thay đổi, identifier được suy ra cũng có thể thay đổi. Hãy kiểm tra identifier thực tế sau refactor thay vì giả định nó vẫn như cũ.

## 5. Nếu module identifier thay đổi, cập nhật dependency ở phía sử dụng

Giả sử trước khi refactor, module `order` được phép phụ thuộc vào named interface `spi` của module `inventory`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.acme.shop.order;
~~~

Nếu module đích được đổi identifier từ `inventory` thành `stock`, khai báo của module sử dụng cần được cập nhật:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "stock::spi"
)
package com.acme.shop.order;
~~~

Chuỗi `inventory::spi` gồm hai phần:

- `inventory` là module identifier.
- `spi` là tên named interface được công bố bởi module đó.

Vì vậy, hãy kiểm tra cả hai phần. Đổi tên module identifier nhưng quên cập nhật `allowedDependencies` có thể làm kiểm chứng kiến trúc thất bại hoặc khiến cấu hình không còn mô tả đúng hợp đồng dự định.

Một module có thể được nhiều module khác sử dụng. Khi identifier thay đổi, hãy tìm tất cả khai báo dependency trỏ đến identifier cũ, không chỉ sửa module gần nhất trong luồng nghiệp vụ.

## 6. Giữ named interface ổn định khi di chuyển package con

Giả sử package `inventory.spi` đang được công bố như sau:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
~~~

Module `order` sử dụng named interface bằng dependency `inventory::spi`.

Nhóm muốn di chuyển package sang `inventory.integration`. Có thể giữ tên giao diện `spi` nếu hợp đồng logic vẫn là SPI cũ:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.integration;
~~~

Khi đó package path đổi, nhưng tên named interface vẫn là `spi`. Module sử dụng tiếp tục tham chiếu `inventory::spi`, miễn là module identifier cũng được giữ nguyên.

Nếu mục đích thiết kế thay đổi và nhóm muốn đổi tên giao diện thành `integration`, hãy cập nhật annotation:

~~~java
@org.springframework.modulith.NamedInterface("integration")
package com.acme.shop.inventory.integration;
~~~

Sau đó cập nhật dependency của module sử dụng từ `inventory::spi` thành `inventory::integration`.

Tên tường minh trong `@NamedInterface("...")` giúp nhóm kiểm soát tên hợp đồng độc lập với package path. Hãy chọn tên phản ánh vai trò của giao diện và chỉ đổi tên khi muốn thay đổi hợp đồng logic đó.

## 7. Những tham chiếu dạng chuỗi cần rà soát

Refactor package thường cập nhật được import và package declaration. Các giá trị tên package được lưu dưới dạng chuỗi có thể không được IDE tự động thay đổi.

Hãy rà soát các vị trí sau:

| Vị trí | Ví dụ | Cần làm gì? |
| --- | --- | --- |
| `@Modulithic` | `additionalPackages = "com.acme.fulfillment"` | Cập nhật nếu package gốc được di chuyển |
| `@ApplicationModule` | `allowedDependencies = "inventory::spi"` | Cập nhật nếu module identifier hoặc named interface name thay đổi |
| `@NamedInterface` | `@NamedInterface("spi")` | Giữ nguyên nếu tên hợp đồng vẫn là `spi`; đổi nếu chủ ý đổi tên |
| Spring scan configuration | `basePackages = "com.acme.shop.inventory"` | Cập nhật package path |
| JPA hoặc repository scan | `packages = "com.acme.shop.inventory.persistence"` | Cập nhật package path |
| Test và tài liệu tùy chỉnh | Chuỗi fully qualified package | Cập nhật theo cấu trúc mới |

Đặc biệt, `additionalPackages` của `@Modulithic` là các tên package được khai báo dưới dạng chuỗi. Nếu package gốc được di chuyển mà chuỗi này không được cập nhật, Spring Modulith có thể không phát hiện module ở vị trí mới như dự định.

`allowedDependencies` lại dùng module identifier và named interface identifier, không phải Java fully qualified package name. Không thay chuỗi này bằng package path chỉ vì package đã đổi tên.

## 8. Quy trình refactor package có kiểm soát

Có thể thực hiện theo trình tự sau:

### Bước 1: Chụp lại metadata hiện tại

Ghi nhận nội dung `package-info.java` ở base package và các package con có named interface. Xác định module identifier hiện tại và các dependency được khai báo.

### Bước 2: Quyết định identifier sau khi đổi package

Chọn một trong hai hướng:

- Giữ module identifier hiện tại bằng `@ApplicationModule(id = "...")` nếu package mới chỉ là thay đổi tổ chức mã nguồn.
- Đổi identifier nếu tên module logic cũng cần thay đổi, sau đó chuẩn bị cập nhật tất cả module tiêu thụ.

Không dùng `displayName` để thay thế identifier. `displayName` phục vụ cách hiển thị, còn identifier được dùng trong mô hình và khai báo dependency.

### Bước 3: Di chuyển package và `package-info.java`

Dùng chức năng refactor package của IDE hoặc công cụ refactor tương đương để di chuyển source file. Kiểm tra `package-info.java` đã nằm ở đúng thư mục mới và dòng `package` đã đổi theo package path mới.

Nếu package cũ có `@ApplicationModule`, annotation phải tiếp tục gắn với base package mới. Nếu package con có `@NamedInterface`, hãy di chuyển file metadata đó cùng package và giữ hoặc đổi tên giao diện theo quyết định ở bước trước.

### Bước 4: Cập nhật các tham chiếu

Rà soát import, fully qualified class name, component scan, repository scan, `additionalPackages`, `allowedDependencies` và các cấu hình khác có lưu tên package hoặc identifier dưới dạng chuỗi.

Phân loại từng giá trị trước khi sửa:

- Package path cần đổi theo Java package mới.
- Module identifier chỉ đổi khi tên logic của module thay đổi hoặc identifier mặc định bị thay đổi.
- Named interface name chỉ đổi khi hợp đồng được đổi tên.
- Display name chỉ đổi khi muốn đổi cách hiển thị.

### Bước 5: Kiểm tra package metadata

Mở từng `package-info.java` liên quan và xác nhận:

- Dòng `package` khớp với đường dẫn source.
- `@ApplicationModule` vẫn nằm trên base package dự kiến.
- `@NamedInterface` vẫn nằm trên package được công bố.
- Các thuộc tính identifier và dependency phản ánh đúng tên module/giao diện mới.
- Javadoc cấp package vẫn mô tả đúng trách nhiệm hiện tại.

### Bước 6: Kiểm chứng mô hình module

Tạo mô hình từ lớp ứng dụng và chạy kiểm tra:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructureAfterPackageRefactoring() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này giúp phát hiện module không được nhận diện như dự kiến, dependency đến package nội bộ, dependency không được cho phép và các vi phạm ranh giới khác.

### Bước 7: Tạo lại tài liệu module

Nếu dự án sinh Application Module Canvas hoặc tài liệu kiến trúc từ Spring Modulith, hãy tạo lại sau refactor. So sánh base package, module identifier, named interface và dependency được hiển thị để phát hiện metadata cũ còn sót lại.

## 9. Những lỗi thường gặp khi đổi tên package

**Di chuyển class nhưng để `package-info.java` ở vị trí cũ.** Annotation cấp package tiếp tục gắn với package cũ hoặc không còn mô tả package mới. Hãy di chuyển và cập nhật file metadata cùng package.

**Chỉ sửa import mà quên package declaration.** Import của class khác có thể đã được cập nhật, nhưng `package-info.java` vẫn khai báo package cũ. Kiểm tra cả đường dẫn file lẫn dòng `package`.

**Đổi package và vô tình đổi module identifier.** Nếu identifier được suy ra từ tên package, thay đổi package có thể ảnh hưởng đến dependency của module khác. Dùng identifier tường minh khi cần giữ tên logic ổn định.

**Đổi `displayName` với kỳ vọng sửa dependency.** `displayName` là tên hiển thị. Dependency dùng module identifier và named interface identifier.

**Cập nhật package path trong `allowedDependencies`.** Chuỗi `allowedDependencies` tham chiếu module identifier, có thể kèm named interface bằng cú pháp `module::interface`. Nó không phải nơi khai báo Java package.

**Đổi tên package con nhưng bỏ quên tên named interface.** Nếu hợp đồng được đổi tên, các module sử dụng cần cập nhật dependency đến tên giao diện mới. Nếu chỉ di chuyển package và giữ tên giao diện tường minh, dependency có thể giữ nguyên.

**Tin rằng IDE tự sửa mọi chuỗi cấu hình.** Công cụ refactor thường xử lý package declaration và import tốt hơn các giá trị chuỗi trong annotation hoặc cấu hình. Hãy rà soát các tham chiếu dạng chuỗi bằng tìm kiếm trong source được phép.

## 10. Checklist trước khi kết thúc refactor

- [ ] Xác định rõ đang đổi base package, package con nội bộ hay package có named interface.
- [ ] Di chuyển `package-info.java` cùng package và cập nhật package declaration.
- [ ] Xác nhận `@ApplicationModule` vẫn gắn với base package mới.
- [ ] Quyết định giữ hay đổi module identifier; dùng `id` tường minh khi cần ổn định tên logic.
- [ ] Xác nhận `displayName` vẫn phù hợp với tên module mới.
- [ ] Kiểm tra các `@NamedInterface` và tên giao diện được module khác sử dụng.
- [ ] Cập nhật `allowedDependencies` nếu module identifier hoặc named interface name thay đổi.
- [ ] Cập nhật `@Modulithic(additionalPackages = ...)` nếu package gốc được khai báo bằng chuỗi và đã di chuyển.
- [ ] Rà soát các cấu hình scan, import và fully qualified class name có chứa package cũ.
- [ ] Chạy `ApplicationModules.of(ShopApplication.class).verify()`.
- [ ] Sinh lại Application Module Canvas hoặc tài liệu kiến trúc nếu dự án sử dụng.

## 11. Kết luận

Đổi tên package trong một ứng dụng Spring Modulith là thay đổi cả cấu trúc mã nguồn và metadata mô tả ranh giới module. Hãy di chuyển `package-info.java` cùng package, cập nhật package declaration và kiểm tra lại các annotation `@ApplicationModule` cùng `@NamedInterface`.

Phân biệt package path với module identifier, named interface name và display name trước khi sửa các khai báo dạng chuỗi. Nếu chỉ muốn sắp xếp lại namespace Java, có thể giữ module identifier bằng `@ApplicationModule(id = "...")`. Nếu identifier hoặc tên giao diện thay đổi, cập nhật dependency ở tất cả module sử dụng. Cuối cùng, dùng `ApplicationModules.verify()` và tạo lại tài liệu module để xác nhận metadata sau refactor phản ánh đúng cấu trúc mới.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Java Language Specification — Package Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
