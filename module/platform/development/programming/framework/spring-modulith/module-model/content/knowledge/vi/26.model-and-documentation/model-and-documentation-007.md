# Kiểm tra tài liệu sau khi đổi package

Đổi tên package của một application module có thể làm thay đổi nhiều hơn các câu lệnh `package` và `import`. Spring Modulith suy ra mô hình module từ cấu trúc package, package metadata và các tham chiếu kiểu Java. Vì vậy, sau khi refactor package, cần kiểm tra lại module nào được phát hiện, module identifier nào đang được dùng, các dependency còn hợp lệ hay không và tài liệu kiến trúc được sinh ra có phản ánh cấu trúc mới không.

Tài liệu được tạo trước khi refactor có thể tiếp tục chứa tên package cũ, tên module cũ hoặc các cạnh dependency không còn đúng. `ApplicationModules.verify()` kiểm tra quy tắc kiến trúc của mô hình hiện tại; `Documenter` tạo lại các tài liệu từ mô hình đó. Hai bước có mục tiêu khác nhau và nên được thực hiện cùng nhau sau khi đổi package.

Trong `SPRING_MODULITH_MODULE_MODEL`, bài học này trình bày quy trình kiểm tra sau package rename: xác nhận module detection, metadata, identifier, dependency, Spring component scan, sinh lại tài liệu và review các thay đổi trước khi chấp nhận refactor.

## 1. Vì sao đổi package ảnh hưởng tới tài liệu module?

Spring Modulith sử dụng package structure để xác định ranh giới application module và phân loại package API hoặc internal. Ví dụ, ứng dụng có root package `com.example.shop`:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java
│   └── internal
├── order
│   └── internal
└── payment
    └── internal
```

Theo cách phát hiện module mặc định, các package con trực tiếp của root package có thể được nhận diện là application module. Module `inventory` có base package `com.example.shop.inventory` và identifier mặc định thường là `inventory`.

Giả sử nhóm đổi package:

```text
com.example.shop.inventory
```

thành:

```text
com.example.shop.stock
```

Thay đổi này có thể ảnh hưởng đến:

- Package declaration và các import trong source code.
- Package gốc mà Spring Modulith dùng để phát hiện module.
- Module identifier mặc định nếu identifier được suy ra từ tên package.
- `allowedDependencies` và named-interface dependency tham chiếu identifier cũ.
- Vị trí và nội dung `package-info.java` chứa `@ApplicationModule` hoặc `@NamedInterface`.
- Component scan nếu package mới nằm ngoài phạm vi scan của ứng dụng.
- Tên package hiển thị trong module model, sơ đồ và module canvas.
- Các tài liệu thủ công hoặc ví dụ code còn ghi package cũ.

Do đó, một lần đổi package chỉ hoàn tất khi source, module model, dependency metadata và tài liệu đều nhất quán.

## 2. Phân biệt các loại tên trước khi refactor

Trước khi đổi package, ghi nhận ba giá trị riêng biệt:

| Khái niệm | Ví dụ trước refactor | Vai trò |
|---|---|---|
| Base package | `com.example.shop.inventory` | Namespace Java của module |
| Module identifier | `inventory` | Tên logic dùng trong mô hình và dependency metadata |
| Display name | `Inventory Management` | Nhãn dành cho người đọc trong tài liệu |

Nếu không có `id` tường minh, identifier mặc định có thể được suy ra từ tên module/package. Vì vậy, đổi package từ `inventory` sang `stock` có thể làm identifier mặc định đổi theo.

Display name là metadata trình bày. Nếu khai báo `displayName = "Inventory Management"`, nhãn này có thể giữ nguyên khi package đổi. Nhưng giữ display name không tự giữ module identifier. Nếu consumer đang tham chiếu identifier `inventory`, hãy quyết định có cần khai báo `id = "inventory"` để giữ danh tính logic hay không.

Ví dụ sau refactor:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Ở đây base package đã đổi thành `com.example.shop.stock`, identifier vẫn là `inventory` và display name vẫn là `Inventory Management`. Thuộc tính `id` cần phiên bản Spring Modulith có hỗ trợ; hãy kiểm tra phiên bản dependency của dự án trước khi dùng.

## 3. Xác nhận root package và module detection

`ApplicationModules` tạo mô hình từ lớp ứng dụng được truyền vào:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Trước và sau package rename, hãy xác nhận `ShopApplication` vẫn nằm ở root package phù hợp và các module vẫn được phát hiện theo chiến lược dự án đang sử dụng.

### Trường hợp chỉ đổi package module con

Nếu `ShopApplication` vẫn ở `com.example.shop` và module được chuyển từ `com.example.shop.inventory` sang `com.example.shop.stock`, module mới vẫn nằm dưới root package. Với chiến lược phát hiện module dựa trên package con trực tiếp, nó vẫn có thể được phát hiện như một module; tên mặc định có thể đổi theo package mới.

### Trường hợp di chuyển module ra ngoài root package

Nếu module được chuyển thành `com.example.stock`, nó không còn là package con của `com.example.shop`. Với cấu hình discovery dựa trên root package cũ, module có thể không còn được phát hiện trong mô hình.

Khi đó cần xem lại thiết kế root package, vị trí lớp `@SpringBootApplication` và detection strategy. Không nên chỉ sửa tài liệu để ghi nhận package mới trong khi module đã biến mất khỏi mô hình.

### Trường hợp dùng explicit module detection

Nếu dự án sử dụng chiến lược `explicitly-annotated`, hãy xác nhận package mới vẫn có metadata `@ApplicationModule` cần thiết để được phát hiện. Việc di chuyển source mà bỏ quên `package-info.java` có thể khiến module không còn xuất hiện như mong đợi.

## 4. Di chuyển `package-info.java` cùng package

Package metadata là một phần của mô hình kiến trúc. Khi đổi package, cần di chuyển và cập nhật mọi file `package-info.java` tương ứng.

Ví dụ trước refactor:

```text
src/main/java/com/example/shop/inventory/package-info.java
src/main/java/com/example/shop/inventory/spi/package-info.java
```

Metadata module:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Metadata named interface:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Sau khi chuyển sang `com.example.shop.stock`, các file metadata phải khai báo package mới:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.stock.spi;
```

Kiểm tra cả package gốc và package con. Nếu `package-info.java` vẫn khai báo tên cũ, metadata có thể không gắn với package mà nhóm định expose.

## 5. Kiểm tra Named Interface sau khi đổi package

Tên named interface và package chứa nó là hai giá trị khác nhau. Ví dụ, package `com.example.shop.inventory.spi` được công bố bằng tên `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Sau khi đổi package thành `com.example.shop.stock.spi`, tên named interface vẫn có thể là `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.stock.spi;
```

Nếu module identifier được giữ là `inventory`, consumer tiếp tục dùng:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Nếu identifier mặc định đổi thành `stock`, consumer cần tham chiếu identifier mới:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "stock::spi"
)
package com.example.shop.order;
```

Khi review, xác nhận ba phần khớp nhau:

1. Provider có `@NamedInterface("spi")` trên package mới.
2. Consumer tham chiếu đúng module identifier.
3. Tên sau dấu `::` khớp chính xác với tên named interface được công bố.

Đừng đổi tên named interface chỉ vì package Java đổi tên nếu hợp đồng logic của nhóm API không thay đổi.

## 6. Kiểm tra `allowedDependencies` và các tham chiếu module

`allowedDependencies` dùng module identifier, không dùng fully qualified package name. Khi package rename làm identifier mặc định thay đổi, các consumer cần được cập nhật.

Ví dụ trước refactor:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "payment::processing" }
)
package com.example.shop.order;
```

Nếu provider đổi identifier từ `inventory` thành `stock`, consumer cần đổi thành:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "stock", "payment::processing" }
)
package com.example.shop.order;
```

Nếu provider khai báo `id = "inventory"` để giữ identifier, consumer tiếp tục dùng `inventory`.

Hãy tìm các tham chiếu không chỉ trong `allowedDependencies`, mà còn trong:

- Các chuỗi `module::interface`.
- Test hoặc helper gọi `getModuleByName(...)`.
- Script, cấu hình hoặc công cụ nội bộ tham chiếu module identifier.
- Tài liệu kiến trúc, sơ đồ và ví dụ code.

Không thay thế hàng loạt chuỗi `inventory` bằng `stock` mà không phân loại. Một số vị trí là package path, một số là module identifier, một số là display name hoặc thuật ngữ nghiệp vụ. Chúng có thể cần giá trị khác nhau sau refactor.

## 7. Kiểm tra Java references và package imports

IDE refactoring hoặc compiler có thể giúp cập nhật các tham chiếu kiểu Java. Sau khi đổi package, kiểm tra:

- `package` declaration của mọi lớp đã chuyển.
- Các câu lệnh `import` trong consumer.
- Fully qualified class name được dùng trực tiếp trong annotation hoặc cấu hình.
- Generic type, method parameter, return type và inheritance.
- Test fixture, test slice và cấu hình test tham chiếu package cũ.
- Resource path hoặc file cấu hình được đặt theo package nếu dự án có sử dụng.

Ví dụ import cũ:

```java
import com.example.shop.inventory.InventoryAvailability;
```

Sau khi chuyển interface sang package mới:

```java
import com.example.shop.stock.InventoryAvailability;
```

Nếu identifier vẫn là `inventory`, import Java vẫn dùng package `stock`, trong khi `allowedDependencies` vẫn dùng identifier `inventory`. Đây là ví dụ điển hình cho việc package name và module identifier không thể thay thế nhau.

## 8. Kiểm tra Spring component scan

Spring Boot thường quét component từ package chứa lớp `@SpringBootApplication` và các package con. Nếu module chỉ được chuyển giữa các package con của root hiện tại, component scan mặc định thường vẫn bao phủ module mới.

Nhưng nếu module được chuyển ra ngoài package root, bean có thể không còn được quét. Khi đó, Spring context có thể thiếu service, repository hoặc listener dù module model của Spring Modulith đã được cấu hình lại.

Ví dụ lớp ứng dụng:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Nếu module vẫn ở `com.example.shop.stock`, nó vẫn là package con của `com.example.shop`. Nếu chuyển sang `com.example.stock`, hãy đánh giá lại component scan và vị trí root application class. Không nên thêm `@ComponentScan` rộng một cách máy móc; hãy chọn root package phản ánh phạm vi ứng dụng.

Sau refactor, dùng context test để xác nhận bean được đăng ký và inject:

```java
@SpringBootTest
class ApplicationContextTests {

    @Test
    void applicationContextStarts() {
        // Spring phải tạo được context với các bean sau refactor.
    }
}
```

`ApplicationModules.verify()` và Spring context test kiểm tra hai khía cạnh khác nhau: một bên là ranh giới module, bên kia là khả năng khởi tạo bean runtime.

## 9. Kiểm tra lại module model trước khi sinh tài liệu

Sau khi cập nhật source và metadata, tạo lại mô hình:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

So sánh kết quả với cấu trúc dự kiến:

| Điều cần kiểm tra | Kết quả mong đợi |
|---|---|
| Module được phát hiện | Module xuất hiện đúng một lần trong mô hình |
| Base package | Hiển thị package mới |
| Logical name/identifier | Giữ nguyên hoặc đổi theo quyết định refactor |
| Display name | Giữ nhãn nghiệp vụ nếu trách nhiệm module không đổi |
| Named Interface | Vẫn có đúng tên và package được công bố |
| Spring beans | Component thuộc module mới được nhận diện |
| Dependencies | Consumer tham chiếu đúng provider và interface |

Nếu module không xuất hiện, kiểm tra root package, detection strategy và metadata trước khi sinh tài liệu. Nếu module xuất hiện với identifier mới ngoài dự kiến, xem lại `id` và các dependency references.

## 10. Chạy `ApplicationModules.verify()` sau package rename

Đưa kiểm tra kiến trúc vào test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructureAfterPackageRefactoring() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra này giúp phát hiện:

- Dependency cycle phát sinh do thay đổi package hoặc reference.
- Consumer truy cập package nội bộ chưa được expose.
- Dependency trực tiếp không nằm trong `allowedDependencies`.
- Named interface hoặc module identifier được tham chiếu không đúng.

`verify()` không đánh giá tiêu đề tài liệu có dễ hiểu hay không và cũng không khởi tạo toàn bộ Spring context. Sau khi verification thành công, vẫn cần kiểm tra component scan và tài liệu sinh ra.

## 11. Sinh lại tài liệu từ module model mới

Tài liệu được sinh trước package rename phản ánh mô hình tại thời điểm cũ. Sau khi xác nhận mô hình mới, dùng `Documenter` để tạo lại các tài liệu cần thiết.

Ví dụ:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

new Documenter(modules)
        .writeModulesAsPlantUml()
        .writeIndividualModulesAsPlantUml()
        .writeModuleCanvases();
```

Các đầu ra có thể gồm sơ đồ module tổng thể, sơ đồ riêng cho từng module và Application Module Canvas. Chúng được tạo từ module model hiện tại, nên package và quan hệ dependency thể hiện trong tài liệu sẽ phản ánh cấu trúc sau refactor.

Chỉ gọi các phương thức sinh tài liệu sau khi module model đã được kiểm tra. Nếu mô hình vẫn thiếu module hoặc có dependency sai, việc sinh tài liệu có thể tạo ra một sơ đồ nhất quán với mô hình sai đó.

## 12. Review tài liệu được sinh và phát hiện nội dung cũ

Sau khi sinh lại tài liệu, review các đầu ra thay vì giả định việc chạy `Documenter` đã làm sạch mọi dấu vết cũ.

Kiểm tra:

- Package cũ còn xuất hiện trong sơ đồ PlantUML hoặc module canvas không?
- Module có xuất hiện hai lần dưới tên cũ và tên mới không?
- Dependency arrow có đúng hướng consumer → provider không?
- Named Interface có tên đúng và nằm dưới đúng module không?
- Các bean được phân loại API/internal có còn đúng sau khi di chuyển package không?
- Display name có còn phản ánh trách nhiệm nghiệp vụ không?
- Các đường dẫn và liên kết trong tài liệu có trỏ tới source/package mới không?

Tài liệu cũ có thể còn tồn tại trong output directory hoặc trong thư mục tài liệu được commit, tùy quy trình dự án. Hãy xác định rõ file nào do `Documenter` tạo, file nào được chỉnh thủ công, rồi cập nhật hoặc loại bỏ bản generated stale theo quy trình quản lý tài liệu của repository. Không xóa thủ công các file chưa xác định nguồn gốc.

## 13. So sánh diff trước và sau refactor

Git diff giúp nhận ra thay đổi tài liệu ngoài dự kiến:

```bash
git diff --stat
git diff -- path/to/generated/module-documentation
```

Khi review diff, phân loại thay đổi:

| Loại thay đổi | Có thể hợp lý sau package rename? | Điều cần xác nhận |
|---|---:|---|
| Base package đổi | Có | Package mới đúng vị trí và module vẫn được phát hiện |
| Module identifier đổi | Có thể | Consumer metadata và công cụ tham chiếu đã cập nhật |
| Display name giữ nguyên | Thường nên giữ nếu trách nhiệm không đổi | Nhãn vẫn đúng ngữ nghĩa nghiệp vụ |
| Dependency edge thay đổi | Có thể | Thay đổi có phản ánh reference thực tế và thiết kế mới không |
| Named Interface biến mất | Cần điều tra | Package metadata có bị bỏ quên hoặc đổi tên không |
| Spring bean biến mất khỏi canvas | Cần điều tra | Component scan, stereotype và module scope có thay đổi không |
| Sơ đồ cũ vẫn còn | Cần điều tra | Output stale chưa được thay thế hoặc dọn theo quy trình chưa? |

Đừng chấp nhận một diff chỉ vì số lượng file thay đổi nhỏ. Một module biến mất khỏi sơ đồ có thể là dấu hiệu root package hoặc detection strategy đã sai.

## 14. Cập nhật tài liệu thủ công và ví dụ code

`Documenter` không thể biết mọi tài liệu thủ công trong repository. Sau package rename, tìm và review các nội dung có thể chứa tên cũ:

- Hướng dẫn onboarding và tài liệu kiến trúc.
- README của module hoặc ví dụ code trong tài liệu nội bộ.
- Diagram được vẽ thủ công.
- Cấu hình, script hoặc test helper tham chiếu package cũ.
- Link tới source code trong wiki hoặc hệ thống tài liệu.
- Mẫu cấu hình component scan và test package.

Khi cập nhật tài liệu, phân biệt package path với module identifier. Ví dụ package mới có thể là `com.example.shop.stock`, trong khi identifier được giữ là `inventory` và display name vẫn là `Inventory Management`. Tài liệu phải dùng đúng giá trị theo từng ngữ cảnh.

## 15. Quy trình kiểm tra đầy đủ sau package rename

Có thể áp dụng quy trình sau cho một lần refactor:

1. **Ghi nhận trạng thái trước refactor.** Lưu base package, identifier, display name, named interfaces và dependency graph.
2. **Đổi package bằng refactoring tool.** Di chuyển source, test và resource liên quan.
3. **Cập nhật package metadata.** Di chuyển `package-info.java`, sửa `@ApplicationModule` và `@NamedInterface` theo package mới.
4. **Quyết định identifier.** Giữ `id` nếu cần ổn định logical identity; nếu dùng tên mặc định, cập nhật consumer references khi identifier đổi.
5. **Giữ hoặc cập nhật display name.** Giữ nhãn nếu trách nhiệm nghiệp vụ không đổi; đổi khi phạm vi module thực sự thay đổi.
6. **Cập nhật dependency metadata.** Kiểm tra `allowedDependencies` và `module::interface` ở consumer.
7. **Kiểm tra module detection.** Xác nhận root package và chiến lược phát hiện vẫn bao phủ module mới.
8. **Kiểm tra component scan.** Xác nhận Spring vẫn tìm thấy component, repository và listener sau khi di chuyển.
9. **Tạo module model mới.** Dùng `ApplicationModules.of(...)` và quan sát module, package, bean, dependency.
10. **Chạy verification.** Gọi `ApplicationModules.verify()` để kiểm tra cycle, encapsulation và whitelist.
11. **Sinh lại tài liệu.** Dùng `Documenter` tạo PlantUML và module canvas từ mô hình mới.
12. **Review generated diff.** Tìm package cũ, module trùng, cạnh sai và file generated stale.
13. **Cập nhật tài liệu thủ công.** Sửa ví dụ, link và hướng dẫn còn chứa package cũ.
14. **Kiểm tra Spring context và nghiệp vụ.** Xác nhận bean wiring và luồng module vẫn hoạt động.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Đổi package chỉ cần sửa import | Cần kiểm tra module detection, package metadata, identifier, dependency, component scan và tài liệu. |
| Module identifier luôn giữ nguyên khi package đổi | Identifier mặc định có thể đổi theo tên module/package; dùng `id` tường minh nếu cần giữ. |
| Giữ `displayName` sẽ giữ module identity | Display name chỉ là nhãn trình bày; identifier cần được quản lý riêng. |
| `@NamedInterface` không cần di chuyển cùng package | `package-info.java` của named interface phải theo package mới và khai báo đúng package. |
| `allowedDependencies` dùng package đầy đủ | Nó dùng module identifier hoặc `module::interface`. |
| `verify()` tự sinh tài liệu mới | `verify()` kiểm tra quy tắc; `Documenter` mới tạo tài liệu. |
| Tài liệu cũ tự biến mất khi sinh tài liệu mới | Cần review output directory và xử lý generated stale theo quy trình dự án. |
| Module xuất hiện trong sơ đồ là đủ | Cần xác nhận base package, identifier, display name, API, bean và dependency đều đúng. |
| `ApplicationModules.verify()` xác nhận component scan | Cần Spring context test để kiểm tra bean được đăng ký và inject lúc chạy. |
| Package nằm ngoài root vẫn tự động được phát hiện | Kết quả phụ thuộc root package và detection strategy đang dùng. |

## 17. Checklist review sau khi đổi package

- [ ] Root application class vẫn xác định đúng phạm vi ứng dụng.
- [ ] Module mới được phát hiện đúng một lần.
- [ ] Base package trong module model là package mới.
- [ ] `package-info.java` của module đã được di chuyển và cập nhật.
- [ ] `@NamedInterface` vẫn gắn với đúng package con.
- [ ] Module identifier được giữ hoặc đổi theo quyết định rõ ràng.
- [ ] `displayName` phản ánh đúng trách nhiệm nghiệp vụ.
- [ ] `allowedDependencies` và named-interface references dùng identifier đúng.
- [ ] Các Java import và test references không còn package cũ ngoài chủ đích.
- [ ] Component scan vẫn tìm thấy các Spring component.
- [ ] `ApplicationModules.verify()` thành công.
- [ ] Spring context test khởi tạo được ứng dụng.
- [ ] PlantUML và module canvas đã được sinh lại từ module model mới.
- [ ] Generated diff không còn package cũ hoặc module trùng ngoài chủ đích.
- [ ] Tài liệu thủ công và ví dụ code đã được cập nhật.

## 18. Kết luận

Sau khi đổi package, cần xác minh lại cả module model và tài liệu kiến trúc. Package rename có thể làm thay đổi module detection, identifier mặc định, package metadata, named interface, dependency references và phạm vi component scan. Display name có thể được giữ ổn định để tài liệu tiếp tục dùng cùng nhãn nghiệp vụ; nếu cần giữ logical identity, hãy quản lý `id` riêng.

Quy trình an toàn là cập nhật source và `package-info.java`, xác nhận module model bằng `ApplicationModules`, chạy `verify()`, kiểm tra Spring context, rồi sinh lại tài liệu bằng `Documenter`. Cuối cùng, review PlantUML, module canvas, diff và tài liệu thủ công để tìm package cũ, module trùng hoặc dependency sai. `verify()` bảo vệ quy tắc kiến trúc; `Documenter` phản ánh mô hình hiện tại; review tài liệu xác nhận người đọc đang nhìn thấy đúng cấu trúc sau refactor.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `Documenter` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
