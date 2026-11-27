# Giữ identifier ổn định khi đổi display name

Tên hiển thị của một module có thể thay đổi theo ngôn ngữ, thuật ngữ nghiệp vụ hoặc cách nhóm muốn trình bày tài liệu. Logical identifier lại đóng vai trò nhận diện module trong module model và trong các cấu hình tham chiếu đến module đó. Hai giá trị này có mục đích khác nhau, vì vậy không nên dùng tên hiển thị làm định danh kỹ thuật.

Spring Modulith cho phép khai báo riêng hai giá trị bằng `@ApplicationModule`: `id` là logical identifier của module, còn `displayName` là tên dễ đọc dùng cho hiển thị và tài liệu. Khi thay đổi `displayName`, hãy giữ nguyên `id`. Nếu package module được đổi tên trong một lần tái cấu trúc, một `id` tường minh cũng giúp giữ logical identity ổn định.

Sau bài học, bạn có thể:

- Phân biệt package name, logical module identifier và display name.
- Khai báo `id` và `displayName` bằng `@ApplicationModule`.
- Đổi tên hiển thị mà không làm thay đổi định danh module.
- Giữ identifier khi di chuyển hoặc đổi tên package module.
- Cập nhật dependency reference và test theo logical identifier.
- Kiểm tra identifier và display name bằng `ApplicationModules`.
- Lập kế hoạch thay đổi tên an toàn cho một ứng dụng đã có nhiều module consumer.

## 1. Ba khái niệm tên cần phân biệt

Một module có ít nhất ba giá trị dễ bị nhầm lẫn:

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| Package name | `com.acme.shop.orders` | Tổ chức mã nguồn Java/Kotlin và xác định base package |
| Logical identifier | `order-management` | Nhận diện module trong Spring Modulith và các tham chiếu module |
| Display name | `Quản lý đơn hàng` | Hiển thị trong tài liệu, sơ đồ hoặc giao diện quan sát |

Package name là địa chỉ kỹ thuật của code. Logical identifier là tên ổn định mà module model sử dụng. Display name là nhãn thân thiện với người đọc.

Ví dụ, module có thể được khai báo như sau:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        displayName = "Quản lý đơn hàng"
)
package com.acme.shop.orders;
~~~

Trong khai báo trên:

- Package của module là `com.acme.shop.orders`.
- Logical identifier là `order-management`.
- Display name là `Quản lý đơn hàng`.

Ba giá trị có thể giống nhau về nội dung, nhưng chúng không có cùng vai trò. Khi dự án cần đổi cách gọi nghiệp vụ, chỉ display name cần thay đổi. Khi nhóm tái cấu trúc package, package name có thể thay đổi. Nếu khai báo `id` tường minh, logical identifier chỉ thay đổi khi nhóm chủ động quyết định đổi danh tính module; nếu để mặc định, identifier có thể thay đổi theo package.

## 2. Vì sao identifier cần ổn định?

Logical identifier thường được dùng ở những nơi khác ngoài package khai báo module:

- `allowedDependencies` tham chiếu module mà consumer được phép sử dụng.
- `getModuleByName(...)` tra cứu module trong `ApplicationModules`.
- Cấu hình `sharedModules` có thể liệt kê module cần được bootstrap cùng module đang kiểm thử.
- Architecture test có thể khẳng định module với identifier cụ thể tồn tại.
- Tài liệu kiến trúc hoặc quy trình nội bộ có thể dùng identifier để liên kết đến một capability.

Nếu identifier thay đổi chỉ vì nhóm muốn đổi cách hiển thị, các tham chiếu đó có thể không còn khớp. Một thay đổi mang tính trình bày khi đó trở thành thay đổi cấu hình và kiến trúc.

Ví dụ, các consumer đang tham chiếu `orders`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::api"
)
package com.acme.shop.billing;
~~~

Nếu nhóm chỉ muốn hiển thị tên mới là “Quản lý đơn hàng”, không cần đổi dependency reference. Hãy giữ identifier `orders` và thay `displayName`.

## 3. Identifier mặc định được hình thành như thế nào?

Nếu không khai báo `id`, Spring Modulith tạo logical identifier từ package module được phát hiện. Với cách đặt package thông thường, tên module là phần package nằm dưới root package của ứng dụng.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
├── orders
└── inventory
~~~

Khi root package là `com.acme.shop`, module `orders` thường có identifier mặc định là `orders`.

Nếu ứng dụng bật `useFullyQualifiedModuleNames = true`, tên mặc định sử dụng package đầy đủ thay vì tên cục bộ dưới root. Cấu hình này hữu ích khi ứng dụng có nhiều root package chứa các module trùng tên cục bộ.

Ví dụ:

~~~java
@org.springframework.modulith.Modulithic(
        useFullyQualifiedModuleNames = true
)
@org.springframework.boot.autoconfigure.SpringBootApplication
public class ShopApplication {
}
~~~

Khi đó identifier mặc định của module có thể là `com.acme.shop.orders`.

Identifier mặc định thuận tiện khi package structure đã ổn định. Tuy nhiên, nếu package được đổi tên, identifier suy ra từ package cũng có thể đổi theo. Đặt `id` tường minh khi module cần một logical identity ổn định qua các lần đổi tên package hoặc thay đổi root package.

## 4. Khai báo `id` và `displayName` bằng `@ApplicationModule`

`@ApplicationModule` có thể được đặt trên `package-info.java` của module. Đây là cách phổ biến để khai báo metadata cho package gốc.

Tạo file `src/main/java/com/acme/shop/orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        displayName = "Quản lý đơn hàng"
)
package com.acme.shop.orders;
~~~

`id` là logical identifier. Theo API của Spring Modulith, giá trị này không được chứa dấu phân cách `::`, vì dấu đó được dùng khi tham chiếu named interface theo dạng `module::interface`.

`displayName` là tên thân thiện với người đọc. API mô tả đây là tên dùng cho mục đích hiển thị và tài liệu. Bạn có thể dùng tiếng Việt, tiếng Anh hoặc thuật ngữ nghiệp vụ mà nhóm thống nhất.

Một quy ước thực tế:

- Dùng identifier ngắn, ổn định và dễ gõ, ví dụ `orders`, `order-management`, `catalog`.
- Dùng display name mô tả trách nhiệm, ví dụ `Quản lý đơn hàng`.
- Giữ identifier duy nhất trong phạm vi application module model.
- Không nhúng phiên bản, tên nhóm hoặc tên người phụ trách vào identifier.
- Tránh dùng display name trong dependency rule hoặc code tra cứu module.

Quy ước chữ thường và dấu gạch ngang là lựa chọn thiết kế của nhóm, không phải yêu cầu bắt buộc duy nhất của annotation. Điều bắt buộc được API nêu rõ là `id` không chứa `::`.

## 5. Đổi display name mà giữ nguyên identifier

Giả sử module ban đầu được khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        displayName = "Orders"
)
package com.acme.shop.orders;
~~~

Sau khi thống nhất thuật ngữ tiếng Việt, nhóm muốn hiển thị “Quản lý đơn hàng”. Chỉ thay `displayName`:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        displayName = "Quản lý đơn hàng"
)
package com.acme.shop.orders;
~~~

Logical identifier vẫn là `order-management`. Vì vậy, các dependency reference sau vẫn dùng cùng giá trị:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order-management::api"
)
package com.acme.shop.billing;
~~~

Thay đổi này không yêu cầu sửa package, named interface hoặc `allowedDependencies`. Những phần đó chỉ cần thay đổi nếu hợp đồng hoặc cấu trúc code thực sự thay đổi.

## 6. Phân biệt đổi display name với đổi package

Đổi display name và đổi package là hai loại thay đổi khác nhau:

| Thay đổi | Package name | Logical identifier | Display name |
|---|---|---|---|
| Chỉ đổi cách trình bày | Giữ nguyên | Giữ nguyên | Thay đổi |
| Đổi package, không khai báo `id` | Thay đổi | Có thể thay đổi theo package | Có thể vẫn giữ |
| Đổi package, có `id` tường minh | Thay đổi | Giữ nguyên nếu giữ `id` | Có thể giữ hoặc đổi |
| Chủ động đổi logical identity | Có thể giữ hoặc đổi | Thay đổi | Độc lập |

Ví dụ nhóm muốn đổi package `com.acme.shop.orders` thành `com.acme.shop.ordering`. Nếu module chưa có `id` tường minh, identifier mặc định có thể đổi từ `orders` sang `ordering`. Khi đó các consumer đang dùng `orders::api` phải được cập nhật.

Nếu module đã có `id = "order-management"`, nhóm có thể di chuyển package mà vẫn giữ logical identifier đó:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        displayName = "Quản lý đơn hàng"
)
package com.acme.shop.ordering;
~~~

Identifier vẫn là `order-management`, trong khi package mới là `com.acme.shop.ordering`.

Lưu ý: `id` chỉ ổn định logical identity của module. Nó không đổi tên Java package, không sửa import, không di chuyển file và không thay thế các bước refactor cần thiết của Spring component scanning, persistence scanning hoặc test.

## 7. Dùng identifier trong `allowedDependencies`

Khi module provider có named interface, dependency reference kết hợp logical identifier và tên named interface bằng `::`.

Ví dụ module orders công khai API:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.ordering.api;
~~~

Module billing chỉ được phép sử dụng API đó:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order-management::api"
)
package com.acme.shop.billing;
~~~

Ở đây:

- `order-management` là logical identifier của provider.
- `api` là tên named interface được provider công khai.
- `::` phân tách module identifier và named interface.

Nếu đổi `displayName` từ “Orders” thành “Quản lý đơn hàng”, dependency reference vẫn là `order-management::api`.

Nếu đổi identifier thành `sales-orders`, dependency reference cần chuyển sang `sales-orders::api`. Đây là thay đổi hợp đồng định danh và cần cập nhật các consumer liên quan.

## 8. Tra cứu identifier và display name trong module model

`ApplicationModules` cung cấp `getModuleByName(String)` để tra cứu module theo logical name. Đối tượng `ApplicationModule` cung cấp hai accessor riêng:

- `getIdentifier()` trả về logical identifier.
- `getDisplayName()` trả về tên dùng cho hiển thị.

Ví dụ:

~~~java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentityInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("order-management")
                .orElseThrow();

        System.out.println("Identifier: " + orders.getIdentifier());
        System.out.println("Display name: " + orders.getDisplayName());
        System.out.println("Base package: " + orders.getBasePackage());
    }
}
~~~

Kết quả có thể thể hiện:

~~~text
Identifier: order-management
Display name: Quản lý đơn hàng
Base package: com.acme.shop.ordering
~~~

Ba dòng cho thấy logical identity, tên hiển thị và vị trí package được quản lý riêng. Đây là cách kiểm tra hữu ích sau khi đổi display name hoặc di chuyển package.

## 9. Viết architecture test bảo vệ identifier

Nếu identifier được các module khác tham chiếu, hãy kiểm tra sự tồn tại của identifier đó trong architecture test.

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleIdentityTests {

    @Test
    void keepsOrderManagementIdentifierStable() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules
                .getModuleByName("order-management")
                .orElseThrow();

        assertThat(orders.getIdentifier().toString())
                .isEqualTo("order-management");
        assertThat(orders.getDisplayName()).isEqualTo("Quản lý đơn hàng");
        assertThat(orders.getBasePackage().getName())
                .isEqualTo("com.acme.shop.ordering");
    }
}
~~~

Test này bảo vệ ba quyết định:

- Consumer tiếp tục nhận diện module qua `order-management`.
- Display name của module là `Quản lý đơn hàng`.
- Package hiện tại của module là `com.acme.shop.ordering`.

Nếu display name thay đổi vì lý do biên tập, nhóm chỉ cần cập nhật assertion display name nếu muốn khóa nội dung đó. Nếu yêu cầu kiến trúc là identifier phải ổn định, giữ assertion cho identifier ngay cả khi display name thay đổi.

Khi muốn kiểm tra toàn bộ dependency rule, có thể bổ sung `modules.verify()` trong architecture test. Test identifier và test dependency graph bảo vệ hai khía cạnh khác nhau của module model.

## 10. Identifier và `useFullyQualifiedModuleNames`

`@Modulithic(useFullyQualifiedModuleNames = true)` yêu cầu Spring Modulith dùng package đầy đủ làm tên mặc định của module thay vì tên cục bộ dưới root package. Điều này hữu ích khi nhiều root package có các module trùng tên.

Ví dụ:

~~~java
@org.springframework.modulith.Modulithic(
        additionalPackages = "com.acme.shared",
        useFullyQualifiedModuleNames = true
)
@org.springframework.boot.autoconfigure.SpringBootApplication
public class ShopApplication {
}
~~~

Nếu không có `id` tường minh, module trong `com.acme.shop.orders` có thể được nhận diện bằng tên đầy đủ `com.acme.shop.orders`. Một module cùng tên cục bộ trong root `com.acme.shared` có thể được phân biệt bằng package đầy đủ của nó.

Nếu một module có `id` tường minh, hãy dùng identifier đã khai báo để tham chiếu module. Đừng tự suy luận identifier từ display name hoặc từ một phần package. Kiểm tra kết quả thực tế bằng `ApplicationModules` sau khi thay đổi metadata hoặc root package.

Khi bật fully qualified names, hãy rà soát:

- Các giá trị trong `allowedDependencies`.
- Các giá trị module trong `sharedModules`.
- Các lời gọi `getModuleByName(...)`.
- Architecture test và script nội bộ đang tra cứu module theo tên.

Giữ một quy ước identifier thống nhất trong toàn ứng dụng sẽ giúp dependency metadata dễ đọc hơn.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đổi display name nhưng test lookup thất bại | Test dùng display name làm tham số `getModuleByName` | Tra cứu bằng logical identifier |
| `allowedDependencies` không tìm thấy module | Dependency string dùng display name thay cho identifier | Dùng `id` hoặc identifier mặc định thực tế |
| Package rename làm dependency rule thất bại | Identifier mặc định được suy ra từ package đã đổi | Khai báo `id` tường minh hoặc cập nhật toàn bộ reference |
| Named interface reference không hợp lệ | Dùng sai module identifier hoặc sai tên interface | Kiểm tra `id`, `@NamedInterface` và cú pháp `module::interface` |
| Annotation id bị từ chối | Giá trị chứa `::` | Chọn identifier không chứa dấu phân cách này |
| Hai module khó phân biệt | Identifier cục bộ bị trùng giữa các root | Bật fully qualified module names hoặc chọn `id` tường minh khác nhau |
| Tài liệu vẫn hiển thị tên cũ | Display name được khai báo ở metadata khác hoặc tài liệu chưa được tạo lại | Kiểm tra annotation module và tạo lại tài liệu theo quy trình dự án |
| Module không còn được phát hiện sau package move | Package mới không còn khớp root hoặc detection strategy | Kiểm tra package root, detection strategy và module model |

## 12. Quy trình đổi tên an toàn

Khi nhóm muốn đổi tên hiển thị hoặc package, hãy làm theo thứ tự:

1. Xác định identifier hiện tại bằng `ApplicationModules` hoặc module metadata.
2. Ghi nhận các consumer đang tham chiếu identifier đó trong `allowedDependencies`, `sharedModules` và architecture test.
3. Nếu module chưa có `id` tường minh và cần giữ identity qua package rename, thêm `id` trước khi di chuyển package.
4. Thay đổi `displayName` theo thuật ngữ nghiệp vụ mới, giữ nguyên `id`.
5. Nếu cần đổi package, thực hiện refactor package và cập nhật Java/Kotlin imports cùng các cấu hình liên quan.
6. Tạo lại module model và xác nhận `getModuleByName(id)` vẫn tìm thấy module.
7. Kiểm tra `getDisplayName()` và base package phản ánh giá trị mong muốn.
8. Chạy architecture test và xác minh `allowedDependencies` vẫn trỏ đúng provider.
9. Cập nhật tài liệu hiển thị và sơ đồ được sinh từ module model.
10. Chỉ đổi `id` khi có quyết định chủ động về logical identity; khi đó cập nhật tất cả consumer reference trong cùng thay đổi.

Không cần đổi identifier chỉ để đồng bộ cách viết hoa, ngôn ngữ hoặc thuật ngữ trong tài liệu. Logical identifier nên có vòng đời dài hơn display name.

## 13. Bài tập thực hành

Bạn có module ban đầu:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "customer",
        displayName = "Customer"
)
package com.acme.shop.customer;
~~~

Một module CRM sử dụng named interface `customer::api`. Nhóm muốn đổi display name sang “Hồ sơ khách hàng” và sau đó chuyển package từ `com.acme.shop.customer` sang `com.acme.shop.customers`.

Hãy thực hiện:

1. Viết lại `package-info.java` với display name mới nhưng giữ `id = "customer"`.
2. Chuyển package module sang `com.acme.shop.customers`.
3. Giữ nguyên tên named interface `api`.
4. Kiểm tra `allowedDependencies = "customer::api"` ở module CRM.
5. Dùng `ApplicationModules.getModuleByName("customer")` để tra cứu.
6. Xác nhận `getDisplayName()` trả về “Hồ sơ khách hàng”.
7. Xác nhận base package mới là `com.acme.shop.customers`.
8. Chạy `ApplicationModules.verify()` để kiểm tra dependency graph.

Kết quả mong đợi:

| Thuộc tính | Giá trị sau thay đổi |
|---|---|
| Package | `com.acme.shop.customers` |
| Identifier | `customer` |
| Display name | `Hồ sơ khách hàng` |
| Named interface | `api` |
| Dependency reference | `customer::api` |

Giải thích vì sao CRM không cần thay dependency reference khi package và display name đã đổi nhưng logical identifier được giữ nguyên.

## 14. Checklist review identifier

- [ ] Package name được xem là vị trí code, không phải display name.
- [ ] Module có logical identifier rõ ràng khi cần ổn định qua package refactor.
- [ ] Display name mô tả đúng trách nhiệm và ngôn ngữ nghiệp vụ.
- [ ] `id` không chứa `::`.
- [ ] Identifier được dùng nhất quán trong `allowedDependencies`.
- [ ] `sharedModules` và các lookup sử dụng logical identifier.
- [ ] Named interface reference có dạng `module-id::interface-name`.
- [ ] Test kiểm tra module tồn tại bằng `getModuleByName(id)`.
- [ ] Package rename đã cập nhật import và cấu hình Java/Spring liên quan.
- [ ] Module model sau thay đổi vẫn được phát hiện đúng.
- [ ] `ApplicationModules.verify()` không báo vi phạm mới.
- [ ] Tài liệu hiển thị dùng display name mới.

## 15. Ghi nhớ

Package name, logical identifier và display name là ba giá trị khác nhau. Package name tổ chức mã nguồn; identifier nhận diện module trong module model và các dependency reference; display name giúp người đọc hiểu module trong tài liệu và giao diện hiển thị. Dùng `@ApplicationModule(id = "...", displayName = "...")` để tách hai tên ở cấp module. Khi đổi display name, giữ nguyên id. Khi đổi package, một id tường minh giúp giữ logical identity, nhưng vẫn phải cập nhật imports và cấu hình liên quan đến package. Dùng `ApplicationModules.getModuleByName(id)`, `getIdentifier()` và `getDisplayName()` để xác minh kết quả.

## Tài liệu tham khảo

- [Spring Modulith API – `@ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API – `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API – `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API – `Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
