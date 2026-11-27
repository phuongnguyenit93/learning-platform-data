# Identifier mặc định từ package hoặc tên module

Spring Modulith gán một định danh logic cho mỗi application module để phân biệt module trong mô hình kiến trúc và tham chiếu module đó trong các quy tắc dependency. Theo quy ước mặc định, identifier được suy ra từ tên package gốc của module. Ví dụ, module có base package `com.example.shop.inventory` thường có identifier `inventory`.

Identifier logic khác với tên package đầy đủ và tên hiển thị. Package đầy đủ là namespace Java dùng trong câu lệnh `package` và `import`; identifier là tên ngắn dùng để nhận diện module; `displayName` là nhãn dễ đọc dành cho tài liệu hoặc báo cáo. Từ Spring Modulith 1.3.0, có thể khai báo identifier tường minh bằng thuộc tính `id` của `@ApplicationModule`, nhờ đó giữ tên module ổn định khi package được đổi tên.

Trong `SPRING_MODULITH_MODULE_MODEL`, identifier giúp xác định module, khai báo `allowedDependencies` và giữ các tham chiếu kiến trúc dễ hiểu qua những lần refactor. Bài học này giải thích quy tắc mặc định, cách đặt `id` và cách quản lý thay đổi package mà không làm thay đổi danh tính logic của module.

## 1. Ba tên cần phân biệt

Giả sử module tồn kho được đặt tại package `com.example.shop.inventory`:

| Khái niệm | Giá trị ví dụ | Mục đích |
|---|---|---|
| Base package | `com.example.shop.inventory` | Namespace Java chứa các lớp của module |
| Module identifier | `inventory` | Định danh logic của application module |
| Display name | `Inventory Management` | Tên dễ đọc trong tài liệu hoặc báo cáo |

Ba giá trị có thể liên quan nhưng không thay thế cho nhau. Java compiler sử dụng package đầy đủ để phân giải kiểu. Spring Modulith sử dụng identifier để nhận diện module và tham chiếu module trong metadata. Display name phục vụ người đọc.

Ví dụ một module có thể được khai báo như sau:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Vì không đặt `id`, identifier được suy ra theo quy ước từ package gốc của module: `inventory`. `displayName` là `Inventory Management`, còn base package vẫn là `com.example.shop.inventory`.

## 2. Identifier mặc định được suy ra từ package

Với cấu trúc module theo package, Spring Modulith thường lấy tên package gốc module làm logical name mặc định. Ví dụ:

```text
com.example.shop
├── inventory
├── order
├── payment
└── customer
```

Các identifier mặc định tương ứng là:

| Base package | Identifier mặc định |
|---|---|
| `com.example.shop.inventory` | `inventory` |
| `com.example.shop.order` | `order` |
| `com.example.shop.payment` | `payment` |
| `com.example.shop.customer` | `customer` |

Identifier này là tên ngắn mà các module khác dùng khi khai báo dependency. Ví dụ, `order` có thể cho phép phụ thuộc vào module `inventory` bằng `allowedDependencies = "inventory"`.

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Khai báo này tham chiếu identifier của module cung cấp, không phải tên lớp triển khai và cũng không phải tên đầy đủ `com.example.shop.inventory`.

## 3. Đặt identifier tường minh bằng `id`

Khi muốn tên module không phụ thuộc vào tên package, có thể khai báo `id` trong `@ApplicationModule` tại `package-info.java` của module:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Trong ví dụ này:

- Base package là `com.example.shop.stock`.
- Identifier tường minh là `inventory`.
- Display name là `Inventory Management`.

Module vẫn nằm trong package `stock`, nhưng danh tính logic của nó là `inventory`. Module tiêu thụ tiếp tục tham chiếu identifier `inventory` trong `allowedDependencies`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Đặt `id` hữu ích khi tên package phản ánh cách tổ chức kỹ thuật hoặc cần được thay đổi, trong khi tên module đã trở thành một phần của hợp đồng kiến trúc mà nhiều module khác tham chiếu.

## 4. Vì sao identifier ổn định quan trọng khi refactor package?

Nếu không khai báo `id`, identifier mặc định gắn với tên package module. Giả sử ban đầu module có package:

```text
com.example.shop.inventory
```

Identifier mặc định là `inventory`. Sau khi nhóm phát triển đổi package thành:

```text
com.example.shop.stock
```

identifier mặc định có thể đổi thành `stock`. Các metadata tham chiếu identifier cũ, ví dụ `allowedDependencies = "inventory"`, cần được xem xét và cập nhật theo tên mới.

Nếu muốn giữ danh tính logic `inventory`, khai báo `id` tường minh trước hoặc trong quá trình refactor:

```java
@org.springframework.modulith.ApplicationModule(id = "inventory")
package com.example.shop.stock;
```

Khi package được chuyển từ `inventory` sang `stock`, identifier vẫn là `inventory`. Các consumer đang phụ thuộc vào identifier này không phải đổi chuỗi dependency chỉ vì package provider được tổ chức lại.

Lưu ý: giữ identifier không có nghĩa là toàn bộ refactor tự động không cần cập nhật. Các câu lệnh `import`, package declaration, cấu hình component scan, vị trí resource và những tham chiếu Java tới kiểu đã chuyển package vẫn cần được cập nhật theo namespace mới.

## 5. So sánh identifier mặc định và identifier tường minh

| Tiêu chí | Identifier mặc định | Identifier tường minh |
|---|---|---|
| Nguồn giá trị | Suy ra từ tên package gốc module | Thuộc tính `id` của `@ApplicationModule` |
| Ví dụ | Package `com.example.shop.inventory` → `inventory` | Package `com.example.shop.stock` với `id = "inventory"` |
| Phụ thuộc vào package name | Có | Không phụ thuộc trực tiếp vào tên package sau khi đã đặt `id` |
| Khi đổi package | Identifier mặc định có thể đổi theo | Identifier giữ nguyên nếu `id` không đổi |
| Khi phù hợp | Package name đã ổn định và phản ánh đúng module | Module cần danh tính ổn định qua refactor hoặc tên package không nên là hợp đồng |

Không cần đặt `id` cho mọi module. Nếu package đã mang tên nghiệp vụ ổn định và không có lý do tách biệt danh tính logic, identifier mặc định đơn giản và dễ hiểu.

## 6. Identifier được dùng trong `allowedDependencies`

`allowedDependencies` tham chiếu module thông qua identifier. Ví dụ, module `order` phụ thuộc module `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Nếu `inventory` sử dụng identifier mặc định từ package `com.example.shop.inventory`, chuỗi `inventory` khớp identifier đó.

Nếu provider đổi package thành `com.example.shop.stock` nhưng khai báo `id = "inventory"`, consumer vẫn tham chiếu `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory"
)
package com.example.shop.stock;
```

Consumer không cần thay đổi `allowedDependencies` chỉ vì base package provider đã đổi.

### Dependency tới Named Interface

Identifier module cũng là phần đầu của cú pháp dependency tới named interface. Giả sử module `inventory` công bố package `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.stock.spi;
```

Consumer khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Phần `inventory` là module identifier; phần `spi` là tên named interface. Tên package đầy đủ `com.example.shop.stock.spi` không được dùng thay cho chuỗi `inventory::spi` trong metadata dependency.

## 7. `displayName` không phải identifier

`displayName` phục vụ việc trình bày tên module cho con người. Nó không thay thế `id` và không phải chuỗi cần dùng trong `allowedDependencies`.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Stock and Availability Management"
)
package com.example.shop.stock;
```

Trong cấu hình này:

- Identifier là `inventory`.
- Display name là `Stock and Availability Management`.
- Base package là `com.example.shop.stock`.

Consumer vẫn khai báo `allowedDependencies = "inventory"`. Nếu nhóm chỉnh `displayName` thành `Inventory`, identifier không vì thế mà thay đổi.

Hãy chọn display name để người đọc hiểu trách nhiệm module. Hãy chọn identifier ngắn, ổn định và phù hợp cho metadata kiến trúc. Tránh dùng display name có dấu cách làm giá trị dependency.

## 8. Chọn identifier tốt

Identifier là tên logic được tham chiếu ở nhiều nơi, vì vậy nên tuân theo một quy ước nhất quán:

- **Ngắn và có nghĩa nghiệp vụ:** `inventory`, `order`, `customer`, `pricing`.
- **Ổn định:** tránh gắn identifier với tên nhóm, tên cá nhân, tên sprint hoặc chi tiết triển khai tạm thời.
- **Duy nhất trong mô hình ứng dụng:** tránh hai module có cùng identifier gây mơ hồ khi tham chiếu.
- **Nhất quán về cách viết:** dùng một kiểu chữ và quy ước đặt tên thống nhất trong toàn ứng dụng.
- **Không lạm dụng display name:** identifier nên là token dễ dùng trong `allowedDependencies`; display name dành cho câu chữ dễ đọc.

Ví dụ, nếu package là `com.example.shop.inventory.persistence`, đó thường là package con thuộc module `inventory`, không nên đặt identifier module là `persistence` chỉ vì package này chứa repository. Chỉ tạo module riêng khi có ranh giới trách nhiệm và dependency thực sự độc lập.

## 9. Lưu ý tương thích phiên bản

Thuộc tính `id` của `@ApplicationModule` được hỗ trợ từ Spring Modulith 1.3.0. Các phiên bản 1.2.x như 1.2.10 chưa có thuộc tính này trong annotation. Nếu mã nguồn dùng:

```java
@org.springframework.modulith.ApplicationModule(id = "inventory")
package com.example.shop.stock;
```

nhưng dự án đang dùng phiên bản chưa hỗ trợ `id`, compiler sẽ báo không tìm thấy thuộc tính annotation tương ứng.

Trước khi dùng identifier tường minh, hãy kiểm tra phiên bản Spring Modulith do BOM hoặc dependency management của dự án quản lý. Không nên nâng riêng một module Spring Modulith mà bỏ qua sự đồng bộ phiên bản giữa các artifact trong cùng bộ thư viện.

Nếu dự án đang dùng phiên bản cũ, có thể tiếp tục dùng identifier mặc định từ package và lên kế hoạch cập nhật phiên bản trước khi áp dụng `id` tường minh.

## 10. Kiểm tra identifier trong mô hình module

Sau khi khai báo package và metadata, tạo mô hình bằng `ApplicationModules`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Đầu ra mô hình giúp kiểm tra module được phát hiện, package gốc và thông tin nhận diện tương ứng. Khi module có `id` tường minh, hãy xác nhận identifier thể hiện đúng tên logic mong muốn.

Có thể đưa kiểm tra cấu trúc vào test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc như dependency được cho phép, truy cập package nội bộ và dependency cycle. Nếu đổi identifier, kiểm tra này giúp phát hiện các tham chiếu dependency chưa được cập nhật.

## 11. Quy trình refactor package mà giữ identifier ổn định

Giả sử module `inventory` cần chuyển từ package `com.example.shop.inventory` sang `com.example.shop.stock`, nhưng các module consumer vẫn nên tham chiếu tên `inventory`.

1. **Xác định identifier hiện tại.** Kiểm tra module đang dùng identifier mặc định hay `id` tường minh.
2. **Chọn tên logic cần giữ.** Xác nhận `inventory` vẫn là tên phù hợp với trách nhiệm module.
3. **Khai báo `id` tường minh.** Đặt `@ApplicationModule(id = "inventory")` trong `package-info.java` của package mới.
4. **Di chuyển package và cập nhật import.** Refactor các lớp sang `com.example.shop.stock`; cập nhật tham chiếu Java và cấu hình liên quan.
5. **Giữ dependency metadata.** Các consumer tiếp tục dùng `inventory` hoặc `inventory::spi` nếu đó là identifier đã giữ.
6. **Kiểm tra named interfaces.** Bảo đảm package metadata và tên named interface vẫn đúng sau khi di chuyển.
7. **Chạy kiểm tra kiến trúc.** Dùng `ApplicationModules.verify()` để xác nhận module và dependency được nhận diện đúng.
8. **Kiểm thử runtime.** Xác nhận component scan, bean registration và các luồng nghiệp vụ vẫn hoạt động sau refactor.

Identifier ổn định giảm số thay đổi trong metadata kiến trúc, nhưng không thay thế việc cập nhật namespace Java và kiểm thử ứng dụng.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Identifier là tên package đầy đủ | Identifier là tên logic của module; base package là namespace Java. |
| Identifier luôn là `displayName` | `displayName` chỉ phục vụ trình bày; dependency tham chiếu identifier. |
| Đổi package không ảnh hưởng identifier mặc định | Identifier mặc định suy ra từ package có thể đổi khi package module đổi tên. |
| Đặt `id` sẽ giữ nguyên package Java | `id` giữ danh tính logic; package declaration và import vẫn thay đổi khi refactor. |
| `allowedDependencies` dùng base package đầy đủ | Nó tham chiếu module identifier, ví dụ `inventory` hoặc `inventory::spi`. |
| Đổi `displayName` cần sửa dependency | Thay đổi display name không thay đổi identifier. |
| Mọi module đều cần `id` tường minh | Chỉ cần khi muốn tách danh tính logic khỏi tên package hoặc cần giữ ID ổn định qua refactor. |
| Thuộc tính `id` có ở mọi phiên bản Spring Modulith | `id` được hỗ trợ từ Spring Modulith 1.3.0; cần kiểm tra phiên bản trước khi dùng. |

## 13. Checklist quản lý module identifier

- [ ] Xác định base package và identifier mặc định của module.
- [ ] Phân biệt identifier với tên package đầy đủ và `displayName`.
- [ ] Dùng identifier trong `allowedDependencies` và named-interface dependency.
- [ ] Chọn `id` tường minh nếu module cần giữ danh tính logic qua refactor package.
- [ ] Bảo đảm identifier duy nhất và theo quy ước đặt tên thống nhất.
- [ ] Kiểm tra phiên bản Spring Modulith hỗ trợ thuộc tính `id`.
- [ ] Cập nhật package declaration, import và cấu hình liên quan khi di chuyển package.
- [ ] Giữ dependency metadata nếu identifier không đổi.
- [ ] Quan sát mô hình bằng `ApplicationModules`.
- [ ] Chạy `ApplicationModules.verify()` và kiểm thử Spring context sau refactor.

## 14. Kết luận

Theo quy ước mặc định, Spring Modulith suy ra module identifier từ tên package gốc của application module. Identifier là tên logic ngắn được dùng để nhận diện module và tham chiếu trong `allowedDependencies`; nó khác với base package Java và `displayName`.

Khi cần giữ danh tính module ổn định qua refactor package, có thể khai báo `@ApplicationModule(id = "...")` từ Spring Modulith 1.3.0. Ví dụ, module chuyển từ package `inventory` sang `stock` vẫn có thể giữ identifier `inventory`, nhờ đó các consumer tiếp tục tham chiếu cùng một tên logic. Hãy dùng identifier có ý nghĩa và ổn định, kiểm tra phiên bản thư viện, cập nhật namespace Java sau refactor và chạy `ApplicationModules.verify()` để xác nhận dependency metadata vẫn hợp lệ.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith 1.3 — Release notes](https://github.com/spring-projects/spring-modulith/releases/tag/1.3.0)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
