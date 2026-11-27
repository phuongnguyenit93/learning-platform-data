# Đối chiếu annotation với model thực tế

`@ApplicationModule` là nơi khai báo metadata cho một application module, còn `ApplicationModules` và `ApplicationModule` là mô hình mà Spring Modulith thực sự xây dựng sau khi phân tích package, module detection strategy, annotation và các dependency trong code. Khi review kiến trúc, chỉ đọc `package-info.java` chưa đủ để biết ứng dụng đang được Spring Modulith hiểu như thế nào. Cần tạo module model, đọc lại các giá trị đã được diễn giải và so sánh chúng với ý định thiết kế.

Việc đối chiếu này giúp phát hiện các tình huống như module có identifier khác dự kiến, display name không được nạp, package bị nhận diện thành module riêng, Named Interface thiếu type, module bị mở ngoài ý muốn hoặc allowlist không khớp dependency thực tế.

## 1. Annotation là đầu vào, module model là kết quả được diễn giải

`@ApplicationModule` có thể được đặt trên package hoặc một type nằm trong package gốc của module. Với Java, metadata thường nằm trong `package-info.java`. Với Kotlin, có thể đặt annotation trên metadata class ở package gốc, thường kết hợp `@PackageInfo`.

Ví dụ metadata của module `orders`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Order Management",
    allowedDependencies = "inventory",
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.orders;
```

Annotation khai báo bốn ý định:

- `id`: logical identifier của module.
- `displayName`: tên thân thiện để hiển thị trong tài liệu và báo cáo.
- `allowedDependencies`: các module hoặc Named Interface mà module được phép phụ thuộc.
- `type`: module đóng (`CLOSED`) hay mở (`OPEN`).

Spring Modulith không chỉ sao chép annotation thành một object. Framework phải phát hiện package nào là module, đọc metadata tương ứng, xác định các Named Interface, phân tích type reference và tạo dependency graph. Kết quả là module model có thể dùng để kiểm tra, lập tài liệu và hỗ trợ runtime.

Do đó, cần phân biệt:

| Nguồn khai báo | Model thực tế |
| --- | --- |
| Annotation và package structure trong source | `ApplicationModules` chứa tập module được phát hiện |
| `id` trong annotation | `ApplicationModule.getIdentifier()` |
| `displayName` trong annotation | `ApplicationModule.getDisplayName()` |
| `type = OPEN/CLOSED` | `ApplicationModule.isOpen()` |
| `allowedDependencies` trong annotation | `ApplicationModule.getAllowedDependencies(modules)` đã được phân giải thành target module/interface |
| `@NamedInterface` trên package/type | `ApplicationModule.getNamedInterfaces()` và `isExposed(type)` |
| Type reference và event listener trong code | `getDirectDependencies()` hoặc `getAllDependencies()` |

## 2. Phân biệt `@ApplicationModule` annotation với `ApplicationModule` model

Hai type có tên giống nhau nhưng thuộc hai package khác nhau:

| Type | Package | Vai trò |
| --- | --- | --- |
| `@ApplicationModule` | `org.springframework.modulith` | Annotation cấu hình module trong source code |
| `ApplicationModule` | `org.springframework.modulith.core` | Object mô tả module sau khi Spring Modulith phân tích ứng dụng |

Trong ví dụ sau, import đúng cả hai khi cần:

```java
import org.springframework.modulith.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
```

Trong `package-info.java`, annotation thường được viết với tên đầy đủ để tránh nhầm lẫn. Trong code kiểm tra model, dùng class `org.springframework.modulith.core.ApplicationModule`.

Annotation có target `PACKAGE` và `TYPE`. Điều này cho phép Java dùng `package-info.java`, trong khi các ngôn ngữ không hỗ trợ package annotation có thể dùng metadata type ở package gốc. Việc đặt annotation trên một class bất kỳ ở package con không có nghĩa class đó tự tạo module mới; vị trí và module detection strategy vẫn quyết định package nào là module base package.

Với Kotlin, có thể đặt metadata trên class trong package gốc và dùng `@PackageInfo`:

```kotlin
package com.acme.shop.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@PackageInfo
@ApplicationModule(
    id = "orders",
    displayName = "Order Management",
    allowedDependencies = ["inventory"]
)
class ModuleMetadata
```

Trong cả Java và Kotlin, mục tiêu là để Spring Modulith đọc metadata của đúng module root. Nếu metadata type nằm ở package con, model có thể không áp dụng annotation cho module mà nhóm đang kiểm tra.

## 3. Tạo module model từ lớp ứng dụng

`ApplicationModules.of(ShopApplication.class)` là điểm bắt đầu để Spring Modulith phân tích ứng dụng:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModules;

class ModuleModelInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.stream().forEach(System.out::println);
    }
}
```

`ApplicationModules` triển khai `Iterable<ApplicationModule>` và cung cấp `stream()` để duyệt tất cả module được phát hiện. Có thể dùng `getModuleByName()` để tìm module theo logical name, `getModuleByType()` để tìm module chứa một class hoặc `getModuleForPackage()` để tìm module sở hữu package.

```java
ApplicationModule orders = modules.getModuleByName("orders")
        .orElseThrow(() -> new IllegalStateException("orders module not found"));

ApplicationModule owner = modules.getModuleByType(OrderLookup.class)
        .orElseThrow();

ApplicationModule packageOwner = modules.getModuleForPackage(
        "com.acme.shop.orders.spi"
).orElseThrow();
```

Ba truy vấn này trả lời ba câu hỏi khác nhau:

- Module có logical identifier `orders` có tồn tại không?
- Type `OrderLookup` thuộc module nào?
- Package `com.acme.shop.orders.spi` được module nào sở hữu?

Nếu một truy vấn không tìm thấy kết quả, hãy kiểm tra module detection strategy và root package trước khi kết luận annotation bị bỏ qua.

## 4. Đối chiếu base package, identifier và display name

Giả sử package module là `com.acme.shop.orders` và annotation khai báo `id = "orders"`, `displayName = "Order Management"`.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleMetadataTests {

    @Test
    void reflectsDeclaredModuleMetadata() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
                .orElseThrow();

        assertThat(orders.getBasePackage().getName())
                .isEqualTo("com.acme.shop.orders");
        assertThat(orders.getIdentifier().toString())
                .isEqualTo("orders");
        assertThat(orders.getDisplayName())
                .isEqualTo("Order Management");
    }
}
```

Các API có ý nghĩa riêng:

- `getBasePackage()` trả về package gốc của module.
- `getIdentifier()` trả về `ApplicationModuleIdentifier`, tức logical identifier.
- `getDisplayName()` trả về tên thân thiện phục vụ hiển thị.

Đừng dùng display name thay cho identifier khi tìm module hoặc khai báo `allowedDependencies`. Display name có thể có dấu cách hoặc được đổi vì mục đích tài liệu; identifier phải ổn định để dùng trong module model và dependency expression.

Nếu không khai báo `id`, identifier thường được suy ra từ local name của module package, trừ khi ứng dụng cấu hình dùng fully-qualified module names. Vì vậy, hãy đối chiếu `getIdentifier()` thay vì tự suy luận từ package.

## 5. Đối chiếu loại module `OPEN` và `CLOSED`

Mặc định, application module là `CLOSED`. Module đóng công bố API và giữ các type trong package con làm nội bộ. Module `OPEN` không bảo vệ package nội bộ theo cùng cách; các type trong sub-package được xem là thuộc unnamed interface trừ khi được gán tường minh vào Named Interface.

Ví dụ khai báo module mở:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.legacy;
```

Đối chiếu với model:

```java
ApplicationModule legacy = modules.getModuleByName("legacy")
        .orElseThrow();

assertThat(legacy.isOpen()).isTrue();
```

Với module đóng:

```java
assertThat(orders.isOpen()).isFalse();
```

Model công khai `isOpen()` để xác nhận module có đang mở hay không. Nếu một module đáng lẽ phải đóng nhưng model trả về `true`, hãy kiểm tra annotation `type`, metadata type trong Kotlin hoặc nguồn metadata được dùng để tạo module.

Đừng kết luận module là `OPEN` chỉ vì một vài type nội bộ được công bố bằng Named Interface. Named Interface công bố một vùng API chọn lọc; `OPEN` nới lỏng ranh giới nội bộ của cả module.

## 6. Đối chiếu API công khai và internal types

Một module có package gốc là API mặc định. Các package con có thể được công bố bằng Named Interface. Model cung cấp `getNamedInterfaces()`, `isExposed(Class<?>)` và `getInternalTypes()` để xem ranh giới đã được diễn giải.

Giả sử module `orders` có cấu trúc:

```text
orders
├── package-info.java
├── OrderManagement.java
├── spi
│   ├── package-info.java
│   └── OrderLookup.java
└── internal
    └── OrderRepository.java
```

Package `orders.spi` được công bố:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
```

Đối chiếu trong test:

```java
import static org.assertj.core.api.Assertions.assertThat;

var spi = orders.getNamedInterfaces().getByName("spi");

assertThat(spi).isPresent();
assertThat(orders.isExposed(OrderLookup.class)).isTrue();
assertThat(orders.isExposed(OrderManagement.class)).isTrue();
assertThat(orders.isExposed(OrderRepository.class)).isFalse();
```

`getNamedInterfaces()` trả về tập interface mà module công bố, bao gồm unnamed interface của package gốc và các Named Interface khai báo tường minh. `getByName("spi")` tìm interface theo tên. `isExposed(type)` trả lời type có nằm trong một interface mà module công bố hay không.

`getInternalTypes()` cung cấp các type được xem là nội bộ:

```java
orders.getInternalTypes().stream()
        .map(com.tngtech.archunit.core.domain.JavaClass::getName)
        .forEach(System.out::println);
```

Khi review, không chỉ kiểm tra Named Interface có tồn tại. Hãy kiểm tra đúng các type cần công bố đã nằm trong interface đó và repository/implementation không bị lộ ngoài ý muốn.

## 7. Đối chiếu `allowedDependencies` đã khai báo

`allowedDependencies` trong annotation là danh sách quyền được phép của module nguồn. Trong module model, `getAllowedDependencies(modules)` phân giải các biểu thức đó thành các target module và Named Interface tương ứng.

Ví dụ module `billing` khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders :: spi",
        "inventory"
    }
)
package com.acme.shop.billing;
```

Có thể đọc lại allowlist đã được phân giải:

```java
import java.util.Set;
import java.util.stream.Collectors;

Set<String> allowed = billing.getAllowedDependencies(modules).stream()
        .map(dependency -> {
            String moduleName = dependency.getTargetModule()
                    .getIdentifier().toString();

            var namedInterface = dependency.getTargetNamedInterface();

            return namedInterface == null
                    ? moduleName
                    : moduleName + " :: " + namedInterface.getName();
        })
        .collect(Collectors.toSet());
```

Kết quả mong đợi tương đương:

```text
orders :: spi
inventory
```

Các method cần hiểu:

- `getTargetModule()` trả về module đích được cho phép.
- `getTargetNamedInterface()` trả về Named Interface được cho phép, hoặc `null` nếu dependency cho phép unnamed/base API của module đích.
- `getAllowedDependencies(modules)` bao gồm dependency khai báo tường minh và các module được đánh dấu shared ở cấp ứng dụng.

Hãy phân biệt ba trường hợp cấu hình:

| Annotation | Ý nghĩa trong module model |
| --- | --- |
| Bỏ qua `allowedDependencies` | Không áp dụng allowlist tường minh; module không bị giới hạn vào một danh sách module cụ thể |
| `allowedDependencies = {}` | Không cho phép dependency tường minh tới module khác; shared modules ở cấp ứng dụng vẫn được tính là dependency được phép |
| `allowedDependencies = { "orders :: spi" }` | Chỉ cho phép dependency tới Named Interface `spi` của module `orders` cùng các shared modules được khai báo |

Do đó, không diễn giải danh sách allowed dependency rỗng như thể annotation đã khai báo một allowlist rỗng. Giá trị mặc định của annotation biểu thị chế độ không giới hạn; mảng rỗng là một chính sách giới hạn rõ ràng.

Đây là danh sách quyền được phép, không phải danh sách dependency mà code hiện tại đang sử dụng. Muốn xem code thực sự tham chiếu module nào, cần đọc direct dependencies.

## 8. Đối chiếu dependency thực tế được phát hiện từ code

Giả sử `billing` inject `OrderLookup` từ `orders.spi` và `InventoryManagement` từ module `inventory`. Những type reference đó tạo dependency thực tế từ `billing` tới hai module đích.

Lấy dependency trực tiếp:

```java
import org.springframework.modulith.core.ApplicationModuleDependency;

billing.getDirectDependencies(modules).stream()
        .forEach(dependency -> System.out.printf(
                "%s -> %s (%s)%n",
                dependency.getSourceType().getName(),
                dependency.getTargetType().getName(),
                dependency.getDependencyType()
        ));
```

`ApplicationModuleDependency` cung cấp:

- `getSourceType()`: type ở module nguồn tạo ra dependency.
- `getTargetType()`: type ở module đích được tham chiếu.
- `getTargetModule()`: module sở hữu type đích.
- `getDependencyType()`: loại dependency được phát hiện, chẳng hạn `USES_COMPONENT`, `EVENT_LISTENER`, `ENTITY` hoặc `DEFAULT`.

Để xem cả dependency bắc cầu:

```java
var allDependencies = billing.getAllDependencies(modules);
```

Hãy bắt đầu bằng dependency trực tiếp khi đối chiếu allowlist. Dependency bắc cầu giúp hiểu phạm vi ảnh hưởng, nhưng không tự cấp quyền cho module nguồn gọi API của module trung gian.

## 9. Phân biệt quyền được phép và dependency đang tồn tại

Đây là một trong những điểm quan trọng nhất khi review module model:

| Khái niệm | API | Câu hỏi |
| --- | --- | --- |
| Allowed dependency | `getAllowedDependencies(modules)` | Module được phép phụ thuộc vào đâu? |
| Actual direct dependency | `getDirectDependencies(modules)` | Code hiện tại đang phụ thuộc trực tiếp vào đâu? |
| Actual transitive dependency | `getAllDependencies(modules)` | Code có thể tiếp cận module nào qua các dependency trung gian? |
| Public API | `getNamedInterfaces()` và `isExposed(type)` | Module đang công bố những type nào? |
| Internal types | `getInternalTypes()` | Type nào vẫn nằm trong vùng nội bộ? |

Một allowlist rộng có thể hợp lệ nhưng không phản ánh nhu cầu thực tế. Ví dụ `billing` được phép dùng `orders :: **`, nhưng code chỉ dùng `orders :: spi`. Đây là cơ hội thu hẹp quyền để module contract rõ hơn.

Ngược lại, nếu code thực tế phụ thuộc `customer` nhưng allowlist không cho phép, model sẽ ghi nhận actual dependency và verification có thể báo violation. Đừng sửa bằng cách thêm module vào allowlist ngay lập tức; trước tiên hãy xác nhận dependency đó có đúng với thiết kế hay không.

## 10. Đối chiếu module detection với annotation

Annotation chỉ có thể ảnh hưởng tới module model nếu package chứa metadata được đưa vào quá trình discovery. Module detection strategy quyết định package nào được xem là module base package.

Ví dụ, default strategy nhận diện direct sub-package của package ứng dụng. Nếu dùng `explicitly-annotated`, module cần được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` theo quy tắc của strategy.

Có thể kiểm tra tập module được phát hiện:

```java
Set<String> moduleIdentifiers = modules.stream()
        .map(module -> module.getIdentifier().toString())
        .collect(Collectors.toSet());

assertThat(moduleIdentifiers).containsExactlyInAnyOrder(
        "orders",
        "inventory",
        "billing"
);
```

Nếu một module bị thiếu, kiểm tra:

- Package có nằm trong root package được quét không?
- Detection strategy có yêu cầu annotation nhưng package chưa được đánh dấu không?
- `@ApplicationModule` có đặt ở package root hay một type đúng vị trí không?
- Có custom strategy hoặc source factory thay đổi module arrangement không?
- Identifier thực tế có khác tên package mặc định không?

`ApplicationModules.getRootPackages()` cũng cho biết các root package đang được dùng để tạo module arrangement:

```java
modules.getRootPackages().forEach(System.out::println);
```

## 11. Đối chiếu nested module và package owner

Nếu ứng dụng có nested application module, package cha có thể chứa module con được phát hiện riêng. Không nên mặc định mọi package con đều là internal package của module cha.

Có thể truy vấn module sở hữu một package:

```java
ApplicationModule owner = modules.getModuleForPackage(
        "com.acme.shop.orders.internal"
).orElseThrow();
```

Nếu package đó được nhận diện thành nested module, `owner` có thể là module con thay vì module `orders`. Có thể kiểm tra quan hệ cha/con:

```java
boolean hasParent = modules.hasParent(owner);

var nestedModules = modules.getNestedModules(orders);
```

Điều này hữu ích khi module model không giống cấu trúc package mà reviewer tưởng tượng. Hãy xác nhận package owner trước khi đánh giá Named Interface hoặc internal access.

## 12. Dùng `verify()` để kiểm tra model có nhất quán về kiến trúc không

Sau khi đối chiếu metadata, chạy verification:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleModel() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc của module model, bao gồm dependency cycle, truy cập package nội bộ và dependency ngoài allowlist nếu module có khai báo giới hạn. Nó không tự biết tập module nào là kỳ vọng nghiệp vụ của nhóm. Vì vậy, nên kết hợp `verify()` với assertion về module identifier, base package, Named Interface và metadata quan trọng.

Nếu muốn lấy violations thay vì để method ném exception ngay, có thể dùng:

```java
var violations = modules.detectViolations();

if (violations.hasViolations()) {
    System.out.println(violations);
}
```

`detectViolations()` thực thi verification và trả về `Violations`. Dùng cách này khi muốn thu thập diagnostic; test vẫn nên fail khi còn violation chưa được xử lý.

## 13. Xây dựng một test đối chiếu metadata có ý nghĩa

Một bài test tốt không cần assert mọi chi tiết của implementation. Hãy chọn các metadata quyết định contract của module:

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleMetadataTests {

    @Test
    void comparesDeclaredMetadataWithTheActualModel() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
                .orElseThrow();

        assertThat(orders.getBasePackage().getName())
                .isEqualTo("com.acme.shop.orders");
        assertThat(orders.getIdentifier().toString())
                .isEqualTo("orders");
        assertThat(orders.getDisplayName())
                .isEqualTo("Order Management");
        assertThat(orders.isOpen()).isFalse();
        assertThat(orders.isExposed(OrderLookup.class)).isTrue();
        assertThat(orders.isExposed(OrderRepository.class)).isFalse();

        Set<String> namedInterfaces = orders.getNamedInterfaces().stream()
                .filter(namedInterface -> namedInterface.isNamed())
                .map(namedInterface -> namedInterface.getName())
                .collect(Collectors.toSet());

        assertThat(namedInterfaces).contains("spi");

        modules.verify();
    }
}
```

Test này bảo vệ các quyết định kiến trúc quan trọng:

- Module có đúng base package và identifier không?
- Display name có được nạp đúng không?
- Module có đang đóng không?
- Contract `OrderLookup` có được công bố không?
- Repository có còn nội bộ không?
- Named Interface `spi` có xuất hiện trong model không?
- Toàn bộ dependency có vượt quy tắc kiến trúc không?

Nếu package được đổi tên hoặc module identifier thay đổi có chủ đích, cập nhật assertion cùng với thay đổi kiến trúc. Assertion giúp reviewer nhìn thấy thay đổi contract thay vì để model âm thầm thay đổi.

## 14. Những dấu hiệu annotation và model đang không khớp

| Dấu hiệu | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `getModuleByName()` không tìm thấy module | Module không được discovery hoặc identifier khác dự kiến | Kiểm tra root packages, detection strategy và `getIdentifier()` của các module |
| Identifier khác tên package | `id` tường minh hoặc fully-qualified module names | Đọc `getIdentifier()`; không suy ra từ package name |
| Display name khác dự kiến | Metadata không được đặt ở package/type mà module model đọc hoặc giá trị hiển thị được suy ra từ identifier | Kiểm tra `package-info.java`, metadata type ở root package và `getIdentifier()` |
| Module được xem là `OPEN` ngoài ý muốn | `type = OPEN` trong annotation hoặc metadata khác | Kiểm tra `isOpen()` và annotation nguồn |
| Named Interface không xuất hiện | Package/type annotation sai vị trí, package không thuộc module hoặc custom discovery thay đổi | Kiểm tra `getNamedInterfaces()` và `isExposed(type)` |
| Allowed dependency thiếu target | Identifier trong annotation sai hoặc target module/interface chưa được phát hiện | Đọc `getAllowedDependencies(modules)` và module model của target |
| Allowed dependency có nhưng actual dependency không dùng | Allowlist rộng hơn nhu cầu hiện tại | So sánh allowed dependencies với direct dependencies và cân nhắc thu hẹp |
| Actual dependency không có trong allowlist | Code có reference ngoài quyền hoặc metadata chưa cập nhật | Xem source/target type, dependency type và quyết định có nên cho phép |
| `verify()` pass nhưng thiếu một module kỳ vọng | Module bị bỏ khỏi detection strategy | Assert tập identifier mong đợi, không chỉ gọi `verify()` |
| Package được gán cho module khác dự kiến | Nested module hoặc root package khác đang chi phối ownership | Dùng `getModuleForPackage()` và kiểm tra nested modules |

## 15. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Annotation là module model | Annotation là metadata đầu vào; `ApplicationModules` xây dựng model từ discovery, metadata và code |
| `id` và `displayName` có thể dùng thay nhau | `id` là logical identifier; display name chỉ phục vụ hiển thị |
| Có `@ApplicationModule` ở đâu cũng tạo module ở đó | Package phải được nhận diện theo detection strategy; annotation cần đặt ở đúng module root/metadata type |
| `allowedDependencies` là dependency thực tế | Nó là danh sách dependency được phép; actual edges được đọc bằng `getDirectDependencies()` |
| Có Named Interface nghĩa là mọi type trong module đều được expose | Chỉ type thuộc interface được công bố mới là API; internal types vẫn có thể bị ẩn |
| `getAllowedDependencies()` chỉ trả annotation thô | API trả các dependency đã được phân giải thành target module/interface và có thể bao gồm shared modules |
| `verify()` pass chứng minh module list đúng ý định | Cần assertion về expected modules và metadata để phát hiện module bị bỏ sót |
| `OPEN` tương đương với Named Interface rộng | `OPEN` nới lỏng ranh giới nội bộ của module; Named Interface công bố một phần API có chọn lọc |

## 16. Ghi nhớ

`@ApplicationModule` khai báo metadata như `id`, `displayName`, `allowedDependencies` và `type`. `ApplicationModules.of(…)` diễn giải package structure, detection strategy, metadata và code để tạo module model. Vì vậy, khi review annotation, hãy đọc lại kết quả qua `ApplicationModule` thay vì chỉ kiểm tra source declaration.

Dùng `getIdentifier()`, `getDisplayName()`, `getBasePackage()` và `isOpen()` để đối chiếu danh tính và loại module. Dùng `getNamedInterfaces()`, `isExposed()` và `getInternalTypes()` để xác nhận API boundary. Dùng `getAllowedDependencies(modules)` để đọc quyền được phép, rồi so sánh với `getDirectDependencies(modules)` và `getAllDependencies(modules)` để hiểu code thực tế đang phụ thuộc vào đâu.

Cuối cùng, kết hợp assertion về module identifiers và metadata với `ApplicationModules.verify()`. Model thực tế mới là căn cứ để đánh giá module arrangement; annotation chỉ thể hiện ý định cấu hình ban đầu.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Application Modules and Explicit Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `@ApplicationModule` annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModule.AllowedDependencies`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.AllowedDependencies.html)
- [Spring Modulith API — `ApplicationModuleDependency`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html)
- [Spring Modulith API — `NamedInterfaces` and `NamedInterface`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterfaces.html)
