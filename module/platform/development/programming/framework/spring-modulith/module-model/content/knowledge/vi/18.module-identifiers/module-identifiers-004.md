# Identifier trong allowedDependencies

Khi khai báo `@ApplicationModule(allowedDependencies = ...)`, Spring Modulith cần biết chính xác module nào được phép trở thành đích của một phụ thuộc. Chuỗi trong `allowedDependencies` tham chiếu đến **module identifier** (định danh logic của module), không phải tên hiển thị dành cho tài liệu hay tên tùy ý của một package con.

Spring Modulith cho phép đặt identifier rõ ràng bằng thuộc tính `id` của `@ApplicationModule`. Identifier này được dùng trong các khai báo phụ thuộc và các cấu hình tham chiếu module. Hiểu cách đặt và phân giải identifier giúp tránh lỗi do đổi tên package, nhầm `displayName` hoặc viết sai tên named interface.

## 1. Phân biệt identifier, package và displayName

Một application module có một package gốc, một định danh logic và có thể có một tên hiển thị. Ba khái niệm này phục vụ các mục đích khác nhau:

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Base package | `com.acme.shop.catalog` | Xác định phạm vi package thuộc module |
| Module identifier | `product-catalog` | Định danh module trong cấu hình như `allowedDependencies` |
| Display name | `Product Catalog` | Tên dễ đọc dùng trong tài liệu và hiển thị |

Nếu không khai báo `id`, Spring Modulith suy ra định danh module từ cấu trúc package. Theo mặc định, tên module là tên package con trực tiếp (local module name). Nếu ứng dụng bật `useFullyQualifiedModuleNames`, tên mặc định sẽ dùng package đầy đủ. Khi khai báo `id` tường minh, hãy dùng identifier đó trong các tham chiếu module.

`displayName` chỉ phục vụ hiển thị. Đổi `displayName` không phải là cách đổi module identifier và không nên dùng giá trị này trong `allowedDependencies`.

## 2. Đặt identifier bằng @ApplicationModule

Giả sử module `catalog` có package gốc `com.acme.shop.catalog`. Đặt metadata trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        id = "product-catalog",
        displayName = "Product Catalog"
)
package com.acme.shop.catalog;
```

Trong đó:

- `id = "product-catalog"` là định danh logic mà module khác dùng khi tham chiếu.
- `displayName = "Product Catalog"` là tên hiển thị cho tài liệu hoặc sơ đồ.
- Package gốc vẫn là `com.acme.shop.catalog`; identifier không thay đổi package Java.

`@ApplicationModule` có thể được đặt trên package hoặc một type nằm trong package gốc của module. Cách dùng `package-info.java` giúp metadata nằm ngay cạnh khai báo package và dễ nhận biết khi đọc cấu trúc module.

Thuộc tính `id` không được chứa dấu phân cách `::`. Spring Modulith dùng dấu này để phân tách module identifier và tên named interface trong một dependency selector. Hãy chọn identifier không rỗng, ổn định và duy nhất trong phạm vi các module của ứng dụng.

## 3. Dùng identifier trong allowedDependencies

Giả sử module `orders` cần sử dụng API của module `catalog`. Khi `catalog` đã khai báo `id = "product-catalog"`, module `orders` tham chiếu bằng identifier đó:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "product-catalog"
)
package com.acme.shop.orders;
```

Khai báo này cho phép `orders` phụ thuộc vào API không tên (base package API) của module `product-catalog`. Tên package `catalog` không còn là giá trị tham chiếu cần dùng khi module đã có identifier tường minh `product-catalog`.

Nếu module cần phụ thuộc vào một named interface cụ thể, nối identifier và tên named interface bằng `::`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "product-catalog::catalog-api"
)
package com.acme.shop.orders;
```

Module cung cấp API khai báo named interface tương ứng, ví dụ:

```java
@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog.api;
```

Khi đó, `orders` được phép tham chiếu các type thuộc named interface `catalog-api` của module có identifier `product-catalog`. Chuỗi `catalog-api` là tên được khai báo trong `@NamedInterface`, không mặc nhiên là tên package `api`.

## 4. Cấu trúc selector của allowedDependencies

Một entry trong `allowedDependencies` có thể chỉ định module hoặc một named interface cụ thể:

```text
<module-identifier>
<module-identifier>::<named-interface-name>
```

Các dạng selector thường dùng:

| Selector | Phạm vi được phép |
|---|---|
| `product-catalog` | API không tên ở package gốc của module |
| `product-catalog::catalog-api` | Named interface `catalog-api` |
| `product-catalog::*` | Tất cả named interface được khai báo của module, không bao gồm API không tên ở package gốc |
| `product-catalog::**` | API không tên ở package gốc và tất cả named interface được khai báo của module |

Có thể khai báo nhiều entry khi module cần nhiều hợp đồng:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
                "product-catalog::catalog-api",
                "customer-management::customer-api"
        }
)
package com.acme.shop.orders;
```

Mỗi entry phải tham chiếu đúng identifier của module đích và, nếu có `::`, đúng tên named interface đã công khai. `*` và `**` có ý nghĩa khác nhau: `*` chỉ bao phủ named interfaces; `**` bao phủ cả package gốc và tất cả named interfaces.

## 5. Identifier mặc định và tên module đầy đủ

Theo mặc định, Spring Modulith dùng tên module cục bộ được suy ra từ package. Ví dụ:

```text
com.acme.shop
├── orders
├── catalog
└── customers
```

Các identifier mặc định tương ứng thường là `orders`, `catalog` và `customers`. Nếu nhiều root package được đưa vào cùng một Modulith và có thể trùng tên module cục bộ, có thể yêu cầu sử dụng tên package đầy đủ bằng `@Modulithic`:

```java
@org.springframework.boot.autoconfigure.SpringBootApplication
@org.springframework.modulith.Modulithic(
        useFullyQualifiedModuleNames = true
)
public class ShopApplication {
}
```

Khi bật tùy chọn này, tên mặc định được dùng trong các tham chiếu module sẽ là package đầy đủ, chẳng hạn `com.acme.shop.catalog`. Tùy chọn này hữu ích khi ứng dụng có nhiều root package và các module con có thể trùng tên cục bộ.

Không nên trộn lẫn tên cục bộ và tên đầy đủ trong cùng một allowlist nếu chưa xác định rõ chế độ đặt tên của ứng dụng. Nếu một module có `id` tường minh, hãy dùng identifier đã khai báo đó nhất quán trong `allowedDependencies` và các cấu hình tham chiếu module liên quan.

## 6. Kiểm tra identifier mà mô hình module đã nhận diện

Có thể xem identifier của từng module bằng API `ApplicationModule.getIdentifier()`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(module -> System.out.printf(
        "package=%s, id=%s, displayName=%s%n",
        module.getBasePackage().getName(),
        module.getIdentifier(),
        module.getDisplayName()));
```

`getIdentifier()` trả về `ApplicationModuleIdentifier`, một value object đại diện cho identifier logic. `toString()` cho phép hiển thị giá trị định danh. API này hữu ích khi cần xác nhận Spring Modulith đã đọc đúng metadata của module.

Sau khi kiểm tra identifier, chạy kiểm thử kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesAllowedModuleIdentifiers() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quan hệ phụ thuộc thực tế có tuân thủ `allowedDependencies` hay không. Nếu identifier trong allowlist không trỏ tới module tồn tại, hoặc named interface được chỉ định không tồn tại, việc phân giải dependency sẽ thất bại và cần sửa metadata hoặc selector.

## 7. Những lỗi thường gặp

| Khai báo sai | Vì sao sai | Cách sửa |
|---|---|---|
| `allowedDependencies = "Product Catalog"` | Dùng `displayName` thay cho identifier | Dùng `product-catalog` |
| `allowedDependencies = "catalog"` trong khi module đặt `id = "product-catalog"` | Tham chiếu tên cũ hoặc tên package suy ra | Dùng `product-catalog` |
| `allowedDependencies = "product-catalog::api"` khi named interface tên `catalog-api` | Tên interface không khớp metadata | Dùng `product-catalog::catalog-api` |
| `id = "product-catalog::catalog-api"` | Đưa dấu phân cách selector vào module identifier | Chỉ đặt `id = "product-catalog"` |
| Dùng package đầy đủ khi ứng dụng đang dùng tên cục bộ | Không khớp chế độ định danh mặc định | Dùng tên local hoặc bật `useFullyQualifiedModuleNames` nhất quán |
| Đổi `id` nhưng không cập nhật allowlist | Các module tiêu thụ vẫn tham chiếu identifier cũ | Cập nhật mọi tham chiếu và chạy lại verification |
| Dùng `*` khi muốn bao gồm cả API package gốc | `*` chỉ chọn named interfaces | Dùng `**` nếu cần cả base package API |

Một lưu ý khác: `allowedDependencies` có ba trạng thái cần phân biệt. Bỏ thuộc tính để giữ hành vi mặc định không giới hạn allowlist; khai báo mảng rỗng để không cho phép phụ thuộc vào module khác; khai báo một hoặc nhiều entry để chỉ cho phép các module/interface được liệt kê. Các shared module được cấu hình ở cấp ứng dụng vẫn được Spring Modulith xử lý theo quy tắc shared module.

## 8. Quy trình thay đổi module identifier an toàn

Khi cần đổi identifier của một module, hãy xử lý theo trình tự:

1. Xác định package gốc và identifier hiện tại bằng `ApplicationModules`.
2. Đổi `id` trong metadata của module cung cấp.
3. Tìm tất cả `allowedDependencies` đang tham chiếu identifier cũ và cập nhật sang identifier mới.
4. Cập nhật các cấu hình khác có tham chiếu module identifier, chẳng hạn danh sách shared modules nếu có.
5. Chạy `ApplicationModules.of(ShopApplication.class).verify()` để phát hiện selector sai hoặc dependency không được phép.
6. Kiểm tra lại tài liệu kiến trúc và sơ đồ nếu chúng hiển thị identifier hoặc display name.

Identifier là tên kỹ thuật được các module khác tham chiếu. Hãy giữ nó ổn định qua các thay đổi về package hoặc cách trình bày nếu hợp đồng phụ thuộc không cần thay đổi. Khi muốn đổi tên chỉ để dễ đọc, hãy cân nhắc cập nhật `displayName` thay vì đổi `id`.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Explicit Application Module Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [ApplicationModuleIdentifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Modulithic annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
