# Đổi module identifier và tác động tới cấu hình

Trong Spring Modulith, mỗi application module có một logical identifier để các mô-đun khác tham chiếu trong quy tắc phụ thuộc và để framework nhận diện mô-đun trong mô hình. Identifier này có thể được suy ra từ cách tổ chức package hoặc được khai báo tường minh bằng thuộc tính `id` của `@ApplicationModule`. Khi đổi identifier, package Java có thể vẫn giữ nguyên, nhưng những cấu hình và đoạn code đang tham chiếu tới tên cũ cần được rà soát.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, identifier là một phần của hợp đồng kiến trúc: `allowedDependencies` dùng nó để chỉ định mô-đun đích; các API truy vấn mô hình và kiểm thử module cũng có thể nhận tên logic đó. Hiểu rõ sự khác nhau giữa identifier, package nền và display name giúp nhóm đổi tên mô-đun có kiểm soát, tránh làm hỏng quy tắc phụ thuộc hoặc cấu hình kiểm thử.

## 1. Phân biệt identifier, package và display name

Ba giá trị này có mục đích khác nhau:

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| Base package | `com.acme.shop.inventory` | Vị trí package Java mà application module đại diện |
| Module identifier | `inventory` hoặc `stock` | Định danh logic được dùng để tham chiếu mô-đun |
| Display name | `Inventory Management` | Tên dễ đọc dùng cho tài liệu và hiển thị |

Ví dụ, package `com.acme.shop.inventory` có thể khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    id = "stock",
    displayName = "Inventory Management"
)
package com.acme.shop.inventory;
```

Trong trường hợp này, package nền vẫn là `com.acme.shop.inventory`, identifier logic là `stock`, còn display name là `Inventory Management`. `displayName` phục vụ con người đọc báo cáo; nó không thay thế identifier và không phải giá trị để ghi vào `allowedDependencies`.

Nếu không khai báo `id`, Spring Modulith sử dụng tên module được suy ra từ cách phát hiện package. Theo cấu hình mặc định, tên đó thường là tên package con trực tiếp, chẳng hạn `inventory`. Nếu ứng dụng bật `@Modulithic(useFullyQualifiedModuleNames = true)`, tên mặc định được dùng là tên package đầy đủ. Vì vậy, khi dự án sử dụng chế độ tên đầy đủ, hãy kiểm tra identifier thực tế trước khi thay đổi cấu hình phụ thuộc.

## 2. Khai báo identifier tường minh bằng @ApplicationModule

Thuộc tính `id` cho phép tách định danh logic khỏi tên package. Điều này hữu ích khi package được đổi để phản ánh cấu trúc code mới, trong khi các mô-đun phụ thuộc vẫn nên tham chiếu cùng một tên logic.

Ví dụ, `inventory` có identifier `stock`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "stock"
)
package com.acme.shop.inventory;
```

`id` là chuỗi không được chứa dấu phân cách `::`, vì Spring Modulith dùng `::` để phân biệt tên mô-đun với tên named interface trong biểu thức dependency. Hãy chọn identifier ngắn, rõ nghĩa và duy nhất trong phạm vi ứng dụng.

Identifier không tự tạo ra application module và cũng không di chuyển package. Mô-đun vẫn được phát hiện từ cấu trúc package hoặc chiến lược phát hiện đã cấu hình. `id` chỉ tùy chỉnh tên logic mà mô hình gắn với mô-đun đã được phát hiện.

## 3. allowedDependencies phải dùng identifier của mô-đun đích

Giả sử `orders` cần phụ thuộc vào named interface `api` của mô-đun `inventory`. Trước khi đổi identifier, cấu hình có thể là:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Sau khi `inventory` khai báo `id = "stock"`, dependency phải tham chiếu identifier mới:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "stock::api"
)
package com.acme.shop.orders;
```

Phần trước `::` là identifier của mô-đun đích; phần sau `::` là tên named interface mà mô-đun đích công khai. Nếu chỉ đổi `id` mà giữ nguyên `allowedDependencies = "inventory::api"`, Spring Modulith không còn tìm thấy mô-đun đích theo tên cũ và việc xác minh cấu trúc có thể thất bại.

Nếu mô-đun chỉ cho phép phụ thuộc vào package gốc của mô-đun đích, cấu hình có thể chỉ chứa identifier, ví dụ `allowedDependencies = "stock"`. Nếu dùng named interface, hãy giữ đúng tên interface sau dấu `::`; đổi identifier không tự đổi tên named interface.

Lưu ý `allowedDependencies` được khai báo trong mô-đun đang tạo dependency. Khi đổi identifier của mô-đun `inventory`, cần tìm tất cả mô-đun consumer có cấu hình tham chiếu tới `inventory`, rồi chuyển chúng sang `stock`.

## 4. Đọc identifier từ ApplicationModule

Khi viết code kiểm tra hoặc tạo báo cáo, hãy đọc identifier từ mô hình thay vì tự suy ra từ tên package:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule stock = modules.getModuleByName("stock")
    .orElseThrow(() -> new IllegalStateException("Module stock not found"));

System.out.println("Identifier: " + stock.getIdentifier());
System.out.println("Base package: " + stock.getBasePackage().getName());
System.out.println("Display name: " + stock.getDisplayName());
```

Từ Spring Modulith 1.3, `ApplicationModule.getIdentifier()` là API dùng để đọc logical identifier. `getName()` đã deprecated từ phiên bản này và nên được thay bằng `getIdentifier()`. `getBasePackage()` vẫn cho biết package Java mà mô-đun đại diện; `getDisplayName()` trả về tên hiển thị.

`ApplicationModules.getModuleByName(...)` nhận tên logic để tìm mô-đun. Khi identifier đã được tùy chỉnh, hãy truyền identifier mới, ví dụ `stock`, thay vì tiếp tục dùng tên package cũ `inventory`.

## 5. Những cấu hình và tham chiếu cần rà soát khi đổi ID

Đổi identifier có thể ảnh hưởng nhiều điểm ngoài file `package-info.java` của mô-đun sở hữu:

| Vị trí | Giá trị cần rà soát | Ví dụ trước → sau |
|---|---|---|
| `@ApplicationModule(allowedDependencies = ...)` | Identifier của mô-đun đích | `inventory::api` → `stock::api` |
| `ApplicationModules.getModuleByName(...)` | Tên dùng để tìm module | `"inventory"` → `"stock"` |
| `@ApplicationModuleTest(module = ...)` | Module được bootstrap khi test nằm ngoài package module | `module = "inventory"` → `module = "stock"` |
| `@ApplicationModuleTest(extraIncludes = ...)` | Các module được thêm vào test slice | `"inventory"` → `"stock"` |
| `@Modulithic(sharedModules = ...)` hoặc `@Modulith.sharedModules` | Tên các module được xem là shared | cập nhật nếu module đổi ID |
| Bộ lọc hoặc tích hợp runtime theo module | `ApplicationModuleIdentifier` | kiểm tra cấu hình và logic sử dụng identifier |

Không phải dự án nào cũng sử dụng tất cả các vị trí trên. Hãy tìm trong source code, test và cấu hình của chính ứng dụng những chuỗi tên module đang được tham chiếu. Đặc biệt chú ý các cấu hình test đặt ngoài package module, vì chúng phải chỉ định tên logic bằng thuộc tính `module`.

## 6. Phân biệt đổi identifier và đổi package

Hai thay đổi này có thể xảy ra độc lập:

**Chỉ đổi identifier:** package `com.acme.shop.inventory` giữ nguyên nhưng `id` đổi từ `inventory` sang `stock`. Các import Java không cần đổi chỉ vì identifier thay đổi. Tuy nhiên, các tham chiếu dùng tên logic như `allowedDependencies`, `getModuleByName`, `sharedModules` và cấu hình test cần được cập nhật.

**Chỉ đổi package:** package `com.acme.shop.inventory` được chuyển thành `com.acme.shop.stock`. Nếu không có `id` tường minh, tên logic mặc định thường thay đổi theo tên package mới, do đó các cấu hình tham chiếu cũng cần cập nhật. Nếu mô-đun đã khai báo `id = "inventory"`, identifier có thể được giữ ổn định trong khi package nền thay đổi.

Ngay cả khi giữ identifier ổn định, đổi package vẫn có thể yêu cầu sửa import Java, `package-info.java`, vị trí named interface, component scanning và các cấu hình dựa trên package. `id` chỉ tách tên logic khỏi package; nó không làm cho refactor package trở nên tự động.

Ví dụ giữ identifier ổn định qua một lần đổi package:

```java
// Trước: com.acme.shop.inventory/package-info.java
@org.springframework.modulith.ApplicationModule(id = "stock")
package com.acme.shop.inventory;
```

```java
// Sau: com.acme.shop.warehouse/package-info.java
@org.springframework.modulith.ApplicationModule(id = "stock")
package com.acme.shop.warehouse;
```

Các mô-đun consumer vẫn tham chiếu `stock::api`. Tuy nhiên, code Java sử dụng các kiểu trong package đã di chuyển vẫn phải cập nhật import tương ứng.

## 7. Tác động tới shared modules và tên đầy đủ

`@Modulithic` hoặc `@Modulith` trên lớp ứng dụng có thể khai báo `sharedModules` và `useFullyQualifiedModuleNames`:

```java
@org.springframework.modulith.Modulithic(
    sharedModules = "stock",
    useFullyQualifiedModuleNames = false
)
@org.springframework.boot.autoconfigure.SpringBootApplication
public class ShopApplication {}
```

`sharedModules` liệt kê tên logic của các mô-đun được xem là dùng chung và luôn được đưa vào một số bootstrap của module test. Nếu identifier của một shared module đổi, hãy cập nhật giá trị tương ứng.

`useFullyQualifiedModuleNames` quyết định tên mặc định được suy ra từ package là tên cục bộ hay tên package đầy đủ. Đây là thiết lập ở cấp ứng dụng, không phải thuộc tính đổi `displayName`. Nếu dự án bật chế độ tên đầy đủ hoặc có `additionalPackages`, hãy kiểm tra các identifier được mô hình tạo ra trước và sau khi thay đổi; tránh trộn lẫn tên package đầy đủ với logical ID tường minh trong cùng một cấu hình.

## 8. Tác động tới metadata runtime và công cụ quan sát

Spring Modulith có thể xuất metadata mô-đun vào `META-INF/spring-modulith/application-modules.json`. Metadata này chứa các `ApplicationModuleIdentifier` và được runtime support sử dụng để nhận diện cấu trúc mô-đun. Một số tích hợp module-aware, chẳng hạn bộ lọc migration Flyway hoặc observability, cũng làm việc với `ApplicationModuleIdentifier`.

Vì vậy, sau khi đổi ID:

- Build lại ứng dụng để metadata xuất ra phản ánh identifier mới.
- Kiểm tra các bộ lọc hoặc quy tắc migration theo module nếu dự án dùng Spring Modulith Flyway support.
- Kiểm tra dashboard, truy vấn log/metric/trace hoặc báo cáo nội bộ nếu chúng nhóm dữ liệu theo module identifier.
- Không giả định các file migration, schema hay package Java tự đổi tên theo `id`; các cấu trúc đó có quy tắc và công cụ quản lý riêng.

Đổi identifier không tự di chuyển dữ liệu, không đổi tên bảng, không di chuyển package và không tự cập nhật các chuỗi cấu hình do ứng dụng tự quản lý.

## 9. Quy trình đổi identifier an toàn

Khi cần đổi `inventory` thành `stock`, có thể thực hiện theo trình tự:

1. **Kiểm kê tham chiếu.** Tìm `inventory` trong `allowedDependencies`, `getModuleByName`, `@ApplicationModuleTest`, `extraIncludes`, `sharedModules` và cấu hình riêng của ứng dụng. Phân biệt tên module với tên package, bảng hoặc tên hiển thị.
2. **Chọn định danh mới.** Bảo đảm identifier duy nhất, dễ hiểu và không chứa `::`. Quyết định có cần giữ identifier cũ để tránh thay đổi hợp đồng cấu hình hay không.
3. **Cập nhật khai báo module.** Đặt `id = "stock"` trên package gốc của mô-đun sở hữu.
4. **Cập nhật consumer.** Đổi các dependency tham chiếu mô-đun đích sang `stock`, giữ nguyên tên named interface nếu API không đổi.
5. **Cập nhật test và shared module.** Chỉnh các module name trong test slice và cấu hình bootstrap dùng identifier cũ.
6. **Kiểm tra tích hợp runtime.** Rà soát metadata xuất, Flyway module-aware configuration và observability nếu dự án sử dụng chúng.
7. **Xác minh mô hình.** Dùng `ApplicationModules` để kiểm tra identifier đã được nhận diện đúng và gọi `verify()` để phát hiện dependency không hợp lệ.
8. **Chạy kiểm thử liên quan.** Chạy module integration tests, kiểm thử bootstrap và các kiểm thử migration/observability chịu ảnh hưởng.

Ví dụ kiểm tra identifier và quy tắc kiến trúc:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierTests {

    @Test
    void usesStockAsInventoryModuleIdentifier() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        var module = modules.getModuleByName("stock").orElseThrow();

        assertThat(module.getIdentifier().toString()).isEqualTo("stock");
        assertThat(module.getBasePackage().getName())
            .isEqualTo("com.acme.shop.inventory");
    }

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test đầu xác nhận identifier logic và package nền là hai giá trị riêng. Test thứ hai kiểm tra các quy tắc phụ thuộc được Spring Modulith áp dụng. Nếu package cũng được đổi, hãy cập nhật assertion về base package nhưng có thể giữ assertion identifier nếu `id` vẫn là `stock`.

## 10. Những nhầm lẫn thường gặp

- **“Đổi displayName là đổi module identifier.”** `displayName` chỉ phục vụ hiển thị; `id` mới là logical identifier.
- **“Đổi package luôn phải đổi ID.”** Nếu khai báo `id` tường minh, có thể giữ identifier ổn định khi package được di chuyển.
- **“Đổi `id` tự cập nhật allowedDependencies.”** Các chuỗi tham chiếu trong consumer phải được rà soát và cập nhật.
- **“Identifier được phép chứa `::`.”** `::` là dấu phân cách module và named interface, nên không được dùng bên trong `id`.
- **“Tên trong ApplicationModuleTest là tên package.”** Thuộc tính `module` nhận logical name của mô-đun khi test nằm ngoài package module.
- **“Build thành công nghĩa là tất cả cấu hình đã được cập nhật.”** Những chuỗi tên trong cấu hình riêng, test hoặc hệ thống quan sát có thể không được compiler phát hiện.
- **“Identifier đổi thì package, database và migration cũng đổi.”** `id` chỉ thay định danh logic; các thay đổi package và dữ liệu cần kế hoạch riêng.

## Kết luận

Module identifier là tên logic dùng để tham chiếu một application module. Dùng `@ApplicationModule(id = "...")` khi cần giữ định danh ổn định qua thay đổi package hoặc muốn tên logic rõ nghĩa hơn. Khi đổi ID, cập nhật các `allowedDependencies`, truy vấn mô hình, cấu hình module test, shared modules và tích hợp runtime có dùng identifier. Giữ riêng ba khái niệm `getIdentifier()`, `getBasePackage()` và `getDisplayName()`, rồi chạy `ApplicationModules.verify()` cùng các kiểm thử liên quan để xác nhận cấu hình sau thay đổi.

## Tài liệu tham khảo

- [Spring Modulith — ApplicationModule annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — ApplicationModule model](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — Modulithic annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
