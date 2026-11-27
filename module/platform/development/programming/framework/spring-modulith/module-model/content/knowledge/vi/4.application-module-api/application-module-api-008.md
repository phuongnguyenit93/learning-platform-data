# Giữ tên module ổn định khi refactor package

Trong Spring Modulith, cấu trúc package vừa tổ chức mã nguồn vừa tham gia xác định application module. Theo cách phát hiện mặc định, tên logic của module thường được suy ra từ tên package tương đối với package gốc ứng dụng. Vì vậy, đổi tên hoặc di chuyển package gốc của một module có thể làm thay đổi tên module mà Spring Modulith nhận diện.

Điều này ảnh hưởng tới các nơi tham chiếu tên module, chẳng hạn `allowedDependencies`, named interface dependency, cấu hình shared modules, kiểm thử kiến trúc và các đoạn mã tìm module theo tên. Khi cần tái cấu trúc package nhưng vẫn muốn giữ định danh logic của module, Spring Modulith cung cấp thuộc tính `id` trong `@ApplicationModule` để đặt tên module một cách tường minh.

Trong `SPRING_MODULITH_MODULE_MODEL`, giữ định danh module ổn định giúp bảo toàn ranh giới nghiệp vụ và giảm số thay đổi dây chuyền khi sắp xếp lại package. Bài học này phân biệt tên package, module identifier và display name, sau đó hướng dẫn cách refactor có kiểm soát.

## 1. Vì sao refactor package có thể đổi tên module?

Giả sử package gốc của ứng dụng là `com.example.shop`. Theo quy ước mặc định, package `com.example.shop.inventory` được nhận diện là module có tên logic `inventory`:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── InventoryManagementImpl.java
└── order
    └── internal
        └── PlaceOrderService.java
```

Trong cấu trúc này, `inventory` là phần tên package nằm dưới package gốc. Nếu đổi package gốc module thành `com.example.shop.stock`, tên logic mặc định có thể chuyển thành `stock`:

```text
com.example.shop
├── ShopApplication.java
├── stock
│   ├── InventoryManagement.java
│   └── internal
│       └── InventoryManagementImpl.java
└── order
    └── internal
        └── PlaceOrderService.java
```

Việc thay đổi này có thể tác động đến các khai báo như:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Nếu module sau refactor được nhận diện với tên `stock`, dependency khai báo bằng `inventory` sẽ không còn trỏ tới tên module mới theo cách mặc định. Các tra cứu như `getModuleByName("inventory")` cũng cần được xem xét nếu định danh đã đổi.

Điều cần giữ ổn định là **logical module identifier** khi tên nghiệp vụ của module vẫn là `inventory`, dù package vật lý được đổi từ `inventory` thành `stock` để phản ánh cách tổ chức mã nguồn mới.

## 2. Phân biệt package name, module id và display name

Ba khái niệm này có vai trò khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Package name | Đường dẫn package Java chứa module và các lớp của nó | `com.example.shop.stock` |
| Module id | Định danh logic mà Spring Modulith dùng để nhận diện module và tham chiếu dependency | `inventory` |
| Display name | Tên dễ đọc dùng trong tài liệu hoặc phần hiển thị | `Inventory Management` |

`displayName` chỉ phục vụ hiển thị và tài liệu. Đặt `displayName = "Inventory"` không giữ định danh logic khi package đổi tên. Muốn giữ module identifier ổn định, cần dùng thuộc tính `id`.

## 3. Đặt module id tường minh bằng `@ApplicationModule`

Đặt annotation trên `package-info.java` của package gốc module. Sau khi đổi package thành `com.example.shop.stock`, khai báo `id` giữ tên logic là `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Tệp `package-info.java` phải nằm trong đúng package mới:

```text
src/main/java/com/example/shop/stock/package-info.java
```

Spring Modulith sẽ nhận diện module tại package mới và sử dụng identifier `inventory` theo metadata được khai báo. Nhờ vậy, những module khác có thể tiếp tục tham chiếu module này bằng tên logic `inventory`.

Thuộc tính `id` không được chứa chuỗi `::`, vì Spring Modulith dùng dấu phân cách này trong cú pháp tham chiếu named interface, ví dụ `inventory::spi`. Hãy chọn một id duy nhất, có ý nghĩa nghiệp vụ và đủ ổn định để tồn tại qua nhiều lần tổ chức lại package.

### Giữ nguyên metadata đã có

Nếu `package-info.java` cũ đã khai báo các quy tắc phụ thuộc hoặc kiểu module, hãy chuyển các metadata cần thiết sang package mới và kết hợp chúng trong cùng annotation:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management",
    allowedDependencies = { "catalog", "pricing" }
)
package com.example.shop.stock;
```

Ví dụ này minh họa việc giữ identifier đồng thời duy trì danh sách dependency được phép. Hãy giữ lại đúng các thuộc tính mà module hiện tại thực sự sử dụng; không thêm `allowedDependencies` nếu dự án chưa có chính sách whitelist hoặc không cần giới hạn đó.

## 4. Tác động đến module phụ thuộc

Khi module `inventory` đổi package thành `stock` nhưng vẫn khai báo `id = "inventory"`, các module tiêu thụ tiếp tục dùng logical id `inventory` trong cấu hình dependency.

Ví dụ, module `order` vẫn cho phép phụ thuộc vào module `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Nếu module chỉ công bố một named interface tên `spi`, dependency có thể được giới hạn như sau:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Tên module trong cú pháp `module::named-interface` là logical id. Do đó, giữ `id = "inventory"` giúp những khai báo tham chiếu `inventory::spi` tiếp tục giữ nguyên sau khi package gốc chuyển sang `com.example.shop.stock`.

Các cấu hình khác cũng cần được rà soát nếu chúng tham chiếu tên module, ví dụ `sharedModules` trong cấu hình `@Modulithic`, các bài kiểm thử chọn module theo tên và mã tạo báo cáo kiến trúc. Dùng một hằng số hoặc một nơi tập trung để quản lý tên logic trong mã ứng dụng có thể giúp giảm lỗi do chuỗi tên bị lặp lại.

## 5. Module id ổn định không giữ nguyên Java package

Đây là điểm quan trọng khi lập kế hoạch refactor: `id` giữ tên logic của module, nhưng không giữ tên package Java hoặc các tên lớp.

Ví dụ, trước refactor một module khác có thể import API như sau:

```java
import com.example.shop.inventory.InventoryManagement;
```

Sau khi lớp được chuyển sang package mới, import phải đổi theo vị trí thực tế:

```java
import com.example.shop.stock.InventoryManagement;
```

Module id `inventory` không làm cho package cũ `com.example.shop.inventory` tiếp tục tồn tại. Các tham chiếu Java, cấu hình quét component, vị trí resource, cấu hình serialization hoặc tên lớp đầy đủ được lưu trong cấu hình bên ngoài vẫn cần được cập nhật theo phạm vi refactor.

Tương tự, nếu event class, DTO hoặc named interface được chuyển package, các bên sử dụng chúng cũng phải cập nhật import. Logical id ổn định giúp giữ tên module trong mô hình kiến trúc; nó không tự động tạo lớp tương thích hoặc alias cho package cũ.

## 6. Đảm bảo module vẫn được Spring Modulith phát hiện

Đặt `id` không thay đổi quy tắc phát hiện module. Theo mặc định, Spring Modulith tìm module trong các package con trực tiếp của package chứa lớp ứng dụng Spring Boot. Vì vậy, sau khi refactor, cần xác nhận package mới vẫn nằm trong phạm vi phát hiện phù hợp.

Ví dụ, với package gốc ứng dụng `com.example.shop`, chuyển từ `com.example.shop.inventory` sang `com.example.shop.stock` vẫn giữ module ở cấp package con trực tiếp. Nhưng nếu chuyển sang một package sâu hơn như `com.example.shop.features.stock`, cần xem xét cách phát hiện module. Từ Spring Modulith 1.3, có thể khai báo các nested application module một cách tường minh bằng `@ApplicationModule` trên package tương ứng; dự án cũng có thể dùng detection strategy chỉ nhận package được đánh dấu hoặc cơ chế phát hiện tùy chỉnh.

Đừng xem `id` là cấu hình di chuyển package. Nó chỉ cung cấp logical identifier cho module đã được phát hiện. Nếu module không còn được phát hiện do thay đổi cấu trúc package, chỉ đặt `id` sẽ không khắc phục được vấn đề đó.

## 7. Quy trình refactor package mà giữ module id

Một quy trình an toàn có thể thực hiện theo các bước sau:

1. **Ghi nhận định danh hiện tại.** Xác định package gốc, module name hiện tại, các named interface và các module đang phụ thuộc vào nó.
2. **Chọn id ổn định.** Nếu tên nghiệp vụ vẫn giữ nguyên, dùng tên đó làm logical id, ví dụ `inventory`. Tránh gắn id với tên package tạm thời hoặc tên đội nhóm dễ thay đổi.
3. **Di chuyển package và metadata.** Chuyển các lớp sang package mới, đồng thời chuyển `package-info.java` và giữ các thuộc tính cần thiết như `id`, `allowedDependencies`, `displayName` hoặc `type`.
4. **Cập nhật tham chiếu Java.** Sửa import, package declaration, component scan, resource path và các cấu hình có dùng tên đầy đủ của lớp hoặc package.
5. **Rà soát dependency theo logical id.** Kiểm tra `allowedDependencies`, named interface dependency và `sharedModules`. Giữ tên cũ nếu id đã được giữ; nếu chủ đích đổi id thì cập nhật tất cả bên tham chiếu.
6. **Kiểm tra module discovery.** Xác nhận module mới vẫn được Spring Modulith nhận diện đúng vị trí và đúng ranh giới.
7. **Chạy kiểm thử kiến trúc và ứng dụng.** Xác minh mô hình module, các dependency và luồng nghiệp vụ liên quan.

## 8. Kiểm tra module id sau refactor

Bạn có thể dùng `ApplicationModules` để xây dựng mô hình và tìm module bằng logical id:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentityTests {

    @Test
    void verifiesInventoryIdentifier() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule inventory = modules.getModuleByName("inventory")
                .orElseThrow(() -> new IllegalStateException("inventory module not found"));

        System.out.println("Module identifier: " + inventory.getIdentifier());
        System.out.println("Module package: " + inventory.getBasePackage());
    }
}
```

Sau refactor, kết quả mong đợi là module được tìm thấy bằng id `inventory`, trong khi base package phản ánh vị trí mới `com.example.shop.stock`. Hai thông tin này minh họa sự tách biệt giữa định danh logic và package vật lý.

Bạn cũng nên có kiểm thử kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm thử này giúp phát hiện module không được phát hiện đúng, phụ thuộc vào package nội bộ hoặc dependency không phù hợp với metadata. Ngoài ra, hãy chạy các kiểm thử nghiệp vụ để xác nhận việc đổi package không làm hỏng wiring, component scanning hoặc serialization.

## 9. Tương thích phiên bản và những nhầm lẫn thường gặp

Thuộc tính `id` có trong API `@ApplicationModule` từ Spring Modulith 1.3.0. API 1.2.10 chưa liệt kê thuộc tính này. Nếu dự án đang dùng phiên bản cũ hơn, hãy kiểm tra phiên bản dependency thực tế trước khi dùng ví dụ `id = "inventory"`; có thể cần nâng cấp Spring Modulith hoặc xem việc đổi package như một lần đổi module name và cập nhật các tham chiếu liên quan.

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `displayName` giữ module name ổn định | `displayName` chỉ phục vụ hiển thị; dùng `id` để đặt logical identifier. |
| Đặt `id` sẽ giữ nguyên Java package | `id` không thay đổi package declaration hoặc đường dẫn import. |
| Đặt `id` khiến module tự động được phát hiện ở bất kỳ vị trí nào | Module vẫn phải được phát hiện theo detection strategy và package arrangement đang cấu hình. |
| `allowedDependencies` phải đổi theo tên package mới | Dependency tham chiếu logical module id; nếu id được giữ nguyên thì tên module trong dependency có thể giữ nguyên. |
| Có thể dùng dấu `::` trong module id | Dấu `::` dành cho cú pháp tham chiếu named interface và không được phép xuất hiện trong id. |
| Chỉ cần sửa `package-info.java` là hoàn tất refactor | Cần cập nhật import, component scanning, resource, cấu hình và kiểm thử liên quan tới package cũ. |

## 10. Checklist giữ tên module ổn định

- [ ] Xác định package gốc ứng dụng và module base package hiện tại.
- [ ] Xác định logical module id đang được các module khác tham chiếu.
- [ ] Dùng `@ApplicationModule(id = "...")` nếu phiên bản Spring Modulith hỗ trợ và cần giữ id qua refactor.
- [ ] Chuyển `package-info.java` sang package mới và giữ các metadata cần thiết.
- [ ] Kiểm tra `allowedDependencies`, named interface dependencies và `sharedModules`.
- [ ] Cập nhật các import và cấu hình dùng package hoặc tên lớp đầy đủ.
- [ ] Xác nhận module vẫn được phát hiện theo detection strategy.
- [ ] Kiểm tra module bằng `getModuleByName(...)`, `getIdentifier()` và `getBasePackage()`.
- [ ] Chạy `ApplicationModules.verify()` cùng các kiểm thử nghiệp vụ liên quan.

## 11. Kết luận

Tên module mặc định của Spring Modulith gắn với cấu trúc package. Khi đổi package gốc, tên module suy ra có thể thay đổi và ảnh hưởng đến các cấu hình hoặc mã tham chiếu module. Với phiên bản hỗ trợ, `@ApplicationModule(id = "inventory")` cho phép giữ logical identifier ổn định dù package vật lý được chuyển sang vị trí mới.

Hãy phân biệt module id với Java package và display name: id dùng cho định danh kiến trúc, package dùng để tổ chức lớp và discovery, còn display name phục vụ tài liệu. Khi refactor, giữ metadata đúng vị trí, cập nhật tham chiếu Java, xác nhận module discovery và chạy kiểm thử kiến trúc để đảm bảo ranh giới module vẫn nhất quán.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 1.3.0 — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/1.3.0/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith 1.2.10 — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/1.2.10/api/org/springframework/modulith/ApplicationModule.html)
