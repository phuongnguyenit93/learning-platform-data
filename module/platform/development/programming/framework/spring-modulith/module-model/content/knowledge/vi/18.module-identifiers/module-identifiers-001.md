# ApplicationModuleIdentifier biểu diễn tên logic

Trong Spring Modulith, `ApplicationModuleIdentifier` là value object biểu diễn định danh logic của một application module. Nó cho biết module được gọi bằng tên nào trong mô hình kiến trúc, trong khi package nền cho biết module nằm ở đâu trong mã nguồn và display name cung cấp tên dễ đọc cho tài liệu. Ba khái niệm này có liên quan nhưng không thay thế cho nhau.

Khi cần ghi log, tra cứu module, khai báo dependency hoặc đối chiếu module trong test, nên dùng identifier được trả về từ `ApplicationModule.getIdentifier()`. Từ Spring Modulith 1.3, `getName()` đã deprecated và được thay bằng `getIdentifier()`. Identifier cũng là phần tên module được dùng trong các biểu thức dependency như `inventory::api`.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, hiểu đúng `ApplicationModuleIdentifier` giúp nhóm quản lý ranh giới nghiệp vụ, API công khai và phụ thuộc giữa package trong một ứng dụng Spring Boot. Nó là định danh của module trong mô hình Spring Modulith, không phải tên class Java, tên database, tên Maven artifact hay tên hiển thị trên giao diện.

## 1. Ba giá trị cần phân biệt

Một application module có ít nhất ba thông tin dễ bị nhầm lẫn:

| Khái niệm | Kiểu dữ liệu | Ví dụ | Mục đích |
|---|---|---|---|
| Base package | `JavaPackage` | `com.acme.shop.inventory` | Xác định vùng package Java mà module sở hữu |
| Logical identifier | `ApplicationModuleIdentifier` | `inventory` hoặc `stock` | Định danh module trong mô hình và các tham chiếu kiến trúc |
| Display name | `String` | `Inventory Management` | Tên con người đọc trong tài liệu hoặc sơ đồ |

Ví dụ module có package `com.acme.shop.inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "stock",
    displayName = "Inventory Management"
)
package com.acme.shop.inventory;
```

Khi Spring Modulith tạo model, các giá trị tương ứng là:

```text
Base package:       com.acme.shop.inventory
Logical identifier: stock
Display name:       Inventory Management
```

`ApplicationModuleIdentifier` đại diện cho `stock`. Nó không lưu toàn bộ package name và cũng không phải `displayName`. Vì vậy, nếu package được di chuyển hoặc display name được đổi, identifier có thể vẫn giữ nguyên khi nhóm đã khai báo `id` tường minh.

## 2. Identifier được tạo ra như thế nào?

Spring Modulith cần một tên logic cho mỗi module được phát hiện. Nếu không khai báo `id`, identifier thường được suy ra từ tên package module tương ứng với application root. Ví dụ, với root package `com.acme.shop`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
└── customers
```

Các identifier mặc định thường là `orders`, `inventory` và `customers`.

Nếu ứng dụng bật `useFullyQualifiedModuleNames`, tên mặc định có thể sử dụng tên package đầy đủ, chẳng hạn `com.acme.shop.inventory`. Cấu hình này ảnh hưởng cách suy ra tên mặc định; nó không thay đổi package Java.

Khi cần tên logic ổn định hoặc muốn tách tên module khỏi tên package, khai báo `id` trên `@ApplicationModule`:

```java
@org.springframework.modulith.ApplicationModule(id = "stock")
package com.acme.shop.inventory;
```

Sau đó, module vẫn có base package `com.acme.shop.inventory`, nhưng logical identifier là `stock`. Đây là cách giữ các tham chiếu kiến trúc ổn định khi nhóm đổi tên package hoặc muốn dùng một tên module ngắn, có ý nghĩa nghiệp vụ hơn.

## 3. ApplicationModuleIdentifier là một value object

Kiểu `ApplicationModuleIdentifier` nằm trong package `org.springframework.modulith.core`. Nó đại diện cho định danh của một `ApplicationModule` và cung cấp các thao tác giá trị:

- `of(String)` tạo identifier từ một chuỗi.
- `toString()` trả về dạng chuỗi của identifier.
- `equals()` và `hashCode()` cho phép so sánh và dùng identifier làm key trong collection.
- `compareTo()` cho phép sắp xếp identifier.

Ví dụ:

```java
import org.springframework.modulith.core.ApplicationModuleIdentifier;

ApplicationModuleIdentifier ordersId =
    ApplicationModuleIdentifier.of("orders");

ApplicationModuleIdentifier anotherOrdersId =
    ApplicationModuleIdentifier.of("orders");

System.out.println(ordersId); // orders
System.out.println(ordersId.equals(anotherOrdersId)); // true
```

`ApplicationModuleIdentifier.of(...)` không chấp nhận giá trị `null`, chuỗi rỗng hoặc chuỗi chứa `::`. Dấu `::` được Spring Modulith dùng làm dấu phân cách giữa module identifier và tên named interface, vì vậy không được đặt dấu này bên trong identifier.

`ApplicationModuleIdentifier` không cung cấp một getter kiểu `getValue()` trong API hiện hành. Khi cần biểu diễn thành chuỗi, dùng `toString()`. Khi cần so sánh hai identifier, ưu tiên `equals()` thay vì tự so sánh chuỗi ở nhiều nơi.

## 4. Đọc identifier từ ApplicationModule

Tạo mô hình module từ lớp ứng dụng và lấy module theo logical name:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule inventory = modules.getModuleByName("stock")
    .orElseThrow(() -> new IllegalStateException("Module stock not found"));

System.out.println(inventory.getIdentifier());
System.out.println(inventory.getBasePackage().getName());
System.out.println(inventory.getDisplayName());
```

Đầu ra minh họa:

```text
stock
com.acme.shop.inventory
Inventory Management
```

`getIdentifier()` trả về `ApplicationModuleIdentifier`; `getBasePackage()` trả về package nền; `getDisplayName()` trả về tên dùng cho hiển thị. Khi cần log hoặc serialize identifier trong một báo cáo nội bộ, chuyển nó sang chuỗi bằng `toString()`.

Không nên tiếp tục dùng `getName()` trong code mới. API này đã deprecated từ Spring Modulith 1.3 để chuyển sang `getIdentifier()`, giúp thể hiện rõ kiểu dữ liệu và ý nghĩa của giá trị được trả về.

## 5. Tra cứu module và so sánh identifier

`ApplicationModules.getModuleByName(String)` nhận tên logic dưới dạng `String` và trả về `Optional<ApplicationModule>`. Khi đang có một `ApplicationModuleIdentifier`, có thể dùng `toString()` để tra cứu:

```java
ApplicationModuleIdentifier identifier =
    ApplicationModuleIdentifier.of("stock");

ApplicationModule module = modules.getModuleByName(identifier.toString())
    .orElseThrow(() -> new IllegalArgumentException(
        "Unknown module: " + identifier
    ));
```

Vì `getModuleByName()` nhận chuỗi, cần truyền đúng logical identifier hiện hành. Nếu module đã khai báo `id = "stock"`, truyền `"inventory"` chỉ vì đó là tên package có thể không tìm thấy module.

Để xác định một type thuộc module nào, dùng `getModuleByType(...)`; để xác định package thuộc module nào, dùng `getModuleForPackage(...)`. Đây là các truy vấn theo vị trí của type/package, khác với `getModuleByName(...)` vốn tra cứu theo identifier.

## 6. Identifier trong allowedDependencies và Named Interface

Logical identifier là phần đầu của biểu thức dependency có qualified named interface. Giả sử module `inventory` có identifier `stock` và công khai named interface `api`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Module `orders` có thể giới hạn dependency tới named interface đó:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "stock::api"
)
package com.acme.shop.orders;
```

Biểu thức `stock::api` có hai thành phần:

- `stock`: logical identifier của module cung cấp API.
- `api`: tên named interface được module đó công khai.

Nếu đổi identifier từ `inventory` thành `stock`, các `allowedDependencies` đang tham chiếu `inventory::api` phải được rà soát và cập nhật thành `stock::api`. Tên named interface `api` không tự đổi theo identifier.

Đây là một lý do quan trọng để phân biệt identifier với package. Java import vẫn dùng package `com.acme.shop.inventory.api`, trong khi quy tắc kiến trúc dùng `stock::api`.

## 7. Identifier trong shared modules và module tests

Một số cấu hình Spring Modulith cũng dùng tên logic để tham chiếu module. Ví dụ, `sharedModules` trên metadata ứng dụng khai báo các module được xem là shared và luôn được đưa vào một số module test bootstrap. Các giá trị này phải khớp với identifier mà mô hình nhận diện.

Tương tự, `@ApplicationModuleTest(module = "...")` có thể chỉ định module được bootstrap khi test nằm ngoài package của module. Khi identifier được tùy chỉnh, dùng tên logic mới trong thuộc tính này.

Ví dụ, nếu module tồn kho có identifier `stock`:

```java
@org.springframework.modulith.test.ApplicationModuleTest(module = "stock")
class InventoryIntegrationTests {
    // Kiểm thử module inventory.
}
```

Không phải mọi bài test đều cần chỉ định `module`; khi test nằm trong package module, Spring Modulith có thể xác định module theo vị trí package. Nhưng với cấu hình tham chiếu tên logic, hãy tránh dùng tên package cũ sau khi identifier đã được đổi.

## 8. Dùng identifier trong báo cáo và collection

Vì `ApplicationModuleIdentifier` hỗ trợ equality, hash code và natural ordering, có thể dùng nó để nhóm hoặc sắp xếp module trong báo cáo:

```java
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

// Key là ApplicationModuleIdentifier, value là module tương ứng.
Map<ApplicationModuleIdentifier, ApplicationModule> modulesById =
    modules.stream().collect(Collectors.toMap(
        ApplicationModule::getIdentifier,
        module -> module
    ));

// Hai identifier được tạo từ cùng một chuỗi có thể so sánh bằng nhau.
ApplicationModule stock = modulesById.get(
    ApplicationModuleIdentifier.of("stock")
);
```

Hai lần tạo `ApplicationModuleIdentifier.of("stock")` tạo các giá trị bằng nhau theo `equals()`, nên identifier mới có thể tra cứu phần tử được lưu với identifier trước đó trong `Map`.

Có thể sắp xếp danh sách module theo identifier:

```java
modules.stream()
    .sorted((left, right) ->
        left.getIdentifier().compareTo(right.getIdentifier()))
    .forEach(module -> System.out.println(
        module.getIdentifier() + " -> " + module.getBasePackage().getName()
    ));
```

Khi hiển thị, nên trình bày cả identifier và base package nếu người đọc cần phân biệt tên logic với vị trí mã nguồn. Nếu chỉ hiển thị display name, hai module có tên hiển thị giống nhau có thể khó phân biệt trong báo cáo kỹ thuật.

## 9. Đổi identifier có tác động gì?

Đổi `id` không tự đổi package Java. Tuy nhiên, mọi cấu hình hoặc code tham chiếu logical identifier cũ cần được kiểm tra.

Giả sử module chuyển từ identifier `inventory` sang `stock`:

| Vị trí | Trước | Sau |
|---|---|---|
| `@ApplicationModule(id = ...)` | `inventory` | `stock` |
| `getModuleByName(...)` | `"inventory"` | `"stock"` |
| `allowedDependencies` | `inventory::api` | `stock::api` |
| `sharedModules` | `inventory` | `stock` |
| `@ApplicationModuleTest(module = ...)` | `inventory` | `stock` |
| Base package | `com.acme.shop.inventory` | Không đổi nếu chỉ đổi ID |
| Java import | `com.acme.shop.inventory.api.*` | Không đổi nếu chỉ đổi ID |

Hãy tìm các tham chiếu identifier trong source, test và cấu hình ứng dụng. Nếu identifier được dùng trong metadata runtime, observability hoặc tích hợp module-aware, cần kiểm tra cách những thành phần đó tiêu thụ tên module. Đổi ID không tự di chuyển dữ liệu, đổi tên bảng, đổi Maven artifact hoặc sửa chuỗi cấu hình do ứng dụng tự quản lý.

## 10. Những nhầm lẫn thường gặp

- **“ApplicationModuleIdentifier là package name.”** Không đúng. Package nền và logical identifier là hai thuộc tính riêng; identifier có thể được tùy chỉnh bằng `@ApplicationModule(id = "...")`.
- **“Identifier là display name.”** `displayName` dành cho hiển thị; identifier dùng để tham chiếu module trong mô hình và cấu hình kiến trúc.
- **“ApplicationModule.getName() vẫn là API nên dùng.”** Phương thức này deprecated từ 1.3; code mới nên dùng `getIdentifier()`.
- **“ApplicationModuleIdentifier có getValue().”** API hiện hành cung cấp `of(String)`, `toString()`, `equals()`, `hashCode()` và `compareTo()`; không có getter `getValue()`.
- **“Identifier có thể chứa `::`.”** Không được, vì `::` phân cách module với named interface trong dependency expression.
- **“Đổi package tự động cập nhật mọi dependency.”** Nếu identifier mặc định suy ra từ package, tên logic có thể đổi theo; các chuỗi tham chiếu vẫn phải được rà soát. Nếu ID được khai báo tường minh, có thể giữ nó ổn định khi di chuyển package.
- **“Dùng `getModuleByName()` với base package.”** Phương thức này tra cứu tên logic. Muốn tìm module từ package, dùng `getModuleForPackage()`.
- **“Identifier là ID bền vững của database.”** Đây là định danh trong mô hình Spring Modulith; không mặc định xem nó là khóa dữ liệu hoặc mã định danh công khai cho hệ thống bên ngoài.

## 11. Quy trình sử dụng identifier an toàn

Khi thiết kế hoặc thay đổi module identifier, hãy thực hiện:

1. **Xác định base package.** Kiểm tra package nền mà Spring Modulith phát hiện cho module.
2. **Chọn logical identifier.** Dùng tên ngắn, rõ nghĩa, duy nhất trong ứng dụng và không chứa `::`.
3. **Khai báo ID tường minh nếu cần.** Đặt `id` trong `@ApplicationModule` khi muốn tách tên logic khỏi package.
4. **Đọc identifier từ model.** Dùng `ApplicationModule.getIdentifier()` thay vì tự nối chuỗi từ package hoặc gọi API deprecated `getName()`.
5. **Cập nhật tham chiếu.** Rà soát `allowedDependencies`, `getModuleByName`, `sharedModules`, module test và tích hợp có sử dụng tên logic.
6. **Kiểm tra qualified dependency.** Bảo đảm phần trước `::` là identifier mới và phần sau là named interface đúng.
7. **Viết test.** So sánh với `ApplicationModuleIdentifier.of(...)`, kiểm tra module lookup và chạy `ApplicationModules.verify()`.
8. **Cập nhật báo cáo.** Hiển thị identifier cùng base package hoặc display name để người đọc hiểu đúng từng giá trị.

Ví dụ kiểm thử:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierTests {

    @Test
    void exposesTheExpectedLogicalIdentifier() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        var stock = modules.getModuleByName("stock").orElseThrow();

        assertThat(stock.getIdentifier())
            .isEqualTo(ApplicationModuleIdentifier.of("stock"));
        assertThat(stock.getBasePackage().getName())
            .isEqualTo("com.acme.shop.inventory");
    }

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Test đầu chứng minh logical identifier `stock` có thể khác base package `com.acme.shop.inventory`. Test thứ hai kiểm tra dependency và ranh giới kiến trúc theo mô hình đã phát hiện.

## Kết luận

`ApplicationModuleIdentifier` là value object biểu diễn tên logic của một application module. Lấy nó từ `ApplicationModule.getIdentifier()`, tạo giá trị từ chuỗi bằng `ApplicationModuleIdentifier.of(...)`, so sánh bằng `equals()` và chuyển sang chuỗi bằng `toString()` khi cần. Hãy giữ riêng logical identifier, base package và display name; dùng identifier trong tra cứu module, `allowedDependencies`, shared modules và module test. Khi đổi ID, rà soát mọi tham chiếu tên logic rồi chạy kiểm thử và `ApplicationModules.verify()` để bảo đảm mô hình kiến trúc vẫn nhất quán.

## Tài liệu tham khảo

- [Spring Modulith — ApplicationModuleIdentifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html)
- [Spring Modulith — ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — @ApplicationModule annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
