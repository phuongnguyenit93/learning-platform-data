# Đặt annotation trên package-info.java

Trong Spring Modulith, metadata của application module thường được khai báo ngay trên package bằng các annotation như `@ApplicationModule` và `@NamedInterface`. Java cho phép gắn annotation vào package thông qua file `package-info.java`. Cách này đặt thông tin kiến trúc cạnh package mà nó mô tả, giúp developer đọc được module type, dependency policy và API package ngay trong source tree.

Trong bài học này, ứng dụng bán hàng có hai module `orders` và `catalog`. Bạn sẽ đặt `@ApplicationModule` ở package gốc của `orders`, đặt `@NamedInterface` ở package API của `catalog`, sau đó giới hạn `orders` chỉ được phụ thuộc named interface đã công khai.

## 1. package-info.java là gì?

`package-info.java` là file Java đặc biệt dùng để khai báo annotation và documentation cho một package. File phải chứa package declaration tương ứng; package annotation được viết trước dòng `package`.

Ví dụ tối giản:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.orders;
```

File này phải nằm tại đường dẫn khớp với package trong source set:

```text
src/main/java/com/acme/shop/orders/package-info.java
```

Khi compiler xử lý source, package metadata được lưu trong `package-info.class`. Spring Modulith có thể đọc metadata này để xác định cấu hình module. Tên package trong file phải khớp chính xác với thư mục và package của các class thuộc module.

Một số quy tắc cần nhớ:

- Annotation package phải đứng trước package declaration.
- Một file `package-info.java` chỉ khai báo một package.
- File phải nằm trong source set được build, thông thường là `src/main/java`.
- Không đặt annotation package trên một class thông thường; annotation package và class annotation là hai vị trí khác nhau.
- Dùng tên đầy đủ của annotation trong package declaration. Java đặt import declaration sau package declaration, nên không thể dùng một import nằm trước `package` để rút gọn tên annotation package.

## 2. Phân biệt package gốc ứng dụng và package gốc module

Giả sử ứng dụng có cấu trúc:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
└── catalog
    ├── ProductCatalog.java
    └── api
        └── ProductView.java
```

`ShopApplication` nằm trong package `com.acme.shop`. Theo detection strategy mặc định `direct-subpackages`, các package con trực tiếp `orders` và `catalog` được nhận diện là application module.

`com.acme.shop.orders` là package gốc của module `orders`; `com.acme.shop.catalog` là package gốc của module `catalog`. Các package `orders.internal` và `catalog.api` là package con bên trong module tương ứng. Chúng không tự trở thành application module chỉ vì có package riêng.

Vị trí của annotation quyết định metadata được gắn vào package nào:

| File | Package được mô tả | Mục đích |
|---|---|---|
| `com/acme/shop/orders/package-info.java` | `com.acme.shop.orders` | Metadata của application module `orders` |
| `com/acme/shop/catalog/package-info.java` | `com.acme.shop.catalog` | Metadata của application module `catalog`, nếu cần khai báo |
| `com/acme/shop/catalog/api/package-info.java` | `com.acme.shop.catalog.api` | Metadata của named interface `catalog-api` |
| `com/acme/shop/orders/internal/package-info.java` | `com.acme.shop.orders.internal` | Metadata riêng của package nội bộ, chỉ cần khi có mục đích cụ thể |

Không đặt `@ApplicationModule` ở `catalog/api/package-info.java` nếu ý định là công khai một API package của module `catalog`. Vị trí đó cần `@NamedInterface`.

## 3. Đặt @ApplicationModule trên package gốc

`@ApplicationModule` khai báo metadata cho application module. Một ví dụ:

```java
// src/main/java/com/acme/shop/orders/package-info.java

@org.springframework.modulith.ApplicationModule(
        displayName = "Order Management"
)
package com.acme.shop.orders;
```

Ở đây, `displayName` cung cấp tên hiển thị dễ đọc cho module trong tài liệu và báo cáo. Package identifier mặc định vẫn được suy ra từ package name, trong ví dụ là `orders`.

Có thể khai báo module type tường minh:

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.orders;
```

`CLOSED` là loại module mặc định. Module khác chỉ được truy cập package gốc và các named interface đã công khai. Các package con còn lại là internal đối với module khác.

Nếu muốn module mở các package con cho module khác truy cập, có thể dùng `OPEN`:

```java
@org.springframework.modulith.ApplicationModule(
        type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.orders;
```

`OPEN` mở rộng phạm vi package được expose theo quy tắc của Spring Modulith. Chỉ dùng khi module thực sự muốn công khai các package con; không dùng nó để né một lỗi dependency đang cần được thiết kế lại.

## 4. Khai báo allowedDependencies trong package-info.java

Module có thể giới hạn các module hoặc named interface mà nó được phép phụ thuộc. Ví dụ `orders` chỉ sử dụng API của `catalog`:

```java
// src/main/java/com/acme/shop/orders/package-info.java

@org.springframework.modulith.ApplicationModule(
        displayName = "Order Management",
        allowedDependencies = "catalog :: catalog-api"
)
package com.acme.shop.orders;
```

`allowedDependencies` là một mảng chuỗi; Java cho phép viết gọn khi chỉ có một phần tử. Selector `catalog :: catalog-api` gồm:

- `catalog`: identifier của application module đích.
- `::`: dấu phân cách giữa module và named interface.
- `catalog-api`: tên named interface được công khai bởi module đích.

Nếu module cần nhiều dependency, khai báo nhiều phần tử:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
                "catalog :: catalog-api",
                "customers :: customer-api"
        }
)
package com.acme.shop.orders;
```

Allowlist giới hạn dependency mà module được phép tạo ra. Nó không tự tạo dependency và cũng không thay thế việc công khai API của module đích. Nếu source code của `orders` tham chiếu package nội bộ của `catalog`, chỉ thêm `catalog` vào allowlist không làm package nội bộ trở thành API hợp lệ.

## 5. Đặt @NamedInterface trên package API

`@NamedInterface` đánh dấu một package con là API được công khai với tên xác định. Giả sử `catalog` muốn công khai package `api`:

```java
// src/main/java/com/acme/shop/catalog/api/package-info.java

@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog.api;
```

Sau đó đặt các type thuộc hợp đồng công khai trong package đó:

```java
package com.acme.shop.catalog.api;

import java.util.Optional;

public interface ProductCatalog {

    Optional<ProductView> findBySku(String sku);
}
```

```java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public record ProductView(
        String sku,
        String displayName,
        BigDecimal price) {
}
```

Vì hai type nằm trong `catalog.api`, chúng thuộc named interface `catalog-api`. Module tiêu thụ có thể tham chiếu chúng nếu dependency policy cho phép.

Named interface nên chứa hợp đồng ổn định: facade, interface, DTO hoặc event type mà module khác cần biết. Tránh đưa implementation, repository hoặc entity persistence vào API package chỉ vì các type đó đang có modifier `public`.

## 6. Giữ package nội bộ không có NamedInterface

Module `catalog` có thể tổ chức implementation như sau:

```text
com.acme.shop.catalog
├── api
│   ├── package-info.java       ← @NamedInterface("catalog-api")
│   ├── ProductCatalog.java
│   └── ProductView.java
└── internal
    ├── ProductCatalogService.java
    └── persistence
        ├── ProductRepository.java
        └── ProductEntity.java
```

Không cần gắn annotation đặc biệt để tuyên bố `internal` là internal. Với module `CLOSED`, package con không được expose bằng named interface sẽ không phải API của module. Những type trong đó vẫn có thể được dùng giữa các package bên trong module nếu Java visibility cho phép.

Ví dụ implementation có thể nằm trong package `internal`:

```java
package com.acme.shop.catalog.internal;

import java.util.Optional;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductView;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService implements ProductCatalog {

    @Override
    public Optional<ProductView> findBySku(String sku) {
        // Truy vấn persistence nội bộ và chuyển thành DTO công khai.
        return Optional.empty();
    }
}
```

Spring vẫn có thể component-scan package internal và tạo bean. Việc package không được expose theo Spring Modulith chỉ giới hạn dependency giữa application module; nó không ngăn Spring quản lý bean nội bộ.

## 7. Khi nào cần package-info.java cho module và named interface?

Không phải package nào cũng cần file `package-info.java`. Chỉ tạo file khi muốn khai báo metadata package hoặc documentation cho package đó.

| Nhu cầu | Vị trí | Annotation |
|---|---|---|
| Đặt tên hiển thị, module type hoặc allowlist | Package gốc module, ví dụ `orders` | `@ApplicationModule` |
| Công khai API package con | Package API, ví dụ `catalog.api` | `@NamedInterface` |
| Giữ package implementation nội bộ | Package con như `catalog.internal` | Thường không cần annotation |
| Chỉ ghi Javadoc cho package | Package cần mô tả | Javadoc trong `package-info.java` |

Nếu dùng `direct-subpackages`, Spring Modulith có thể phát hiện module mà không cần `@ApplicationModule`; annotation được thêm khi cần metadata tường minh. Nếu dùng detection strategy `explicitly-annotated`, package module phải được đánh dấu bằng `@ApplicationModule` hoặc marker module được hỗ trợ như jMolecules `@Module`.

Đừng nhầm `@NamedInterface` với marker module. Named interface công khai một phần API của module đã được nhận diện; nó không tự tạo application module mới.

## 8. Kiểm tra cấu trúc package-info.java

Một file hợp lệ cần có package declaration chính xác. Ví dụ file sau nằm trong thư mục `catalog/api` nhưng lại khai báo package `com.acme.shop.catalog`:

```java
@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog;
```

Đây là metadata gắn vào package gốc `catalog`, không phải `catalog.api`. Kết quả là named interface có thể không được nhận diện tại package mà developer mong muốn. Sửa package declaration thành:

```java
@org.springframework.modulith.NamedInterface("catalog-api")
package com.acme.shop.catalog.api;
```

Các lỗi thường gặp khác:

- File tên `package-info.java` bị viết sai như `package-info.java.txt` do công cụ soạn thảo ẩn extension.
- File được đặt trong `src/test/java` trong khi metadata cần có trong production artifact.
- Package declaration khác với package của class hoặc thư mục chứa file.
- Có nhiều file `package-info.java` được tạo ở những package khác nhau vì nhầm module root với API subpackage.
- Annotation được đặt trên class `OrderManagement` thay vì package `com.acme.shop.orders`.
- Module identifier trong `allowedDependencies` không khớp tên module được phát hiện.
- Tên trong `@NamedInterface` không khớp selector trong `allowedDependencies`.

## 9. Kiểm chứng annotation bằng ApplicationModules

Sau khi khai báo package metadata, tạo module model và xác minh:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @org.junit.jupiter.api.Test
    void verifiesModulePackageMetadata() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu `orders` chỉ import type từ `catalog.api`, dependency được giới hạn bởi `catalog :: catalog-api` và không có cycle, verification sẽ thành công.

Để xem module model được phát hiện:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Nếu cần kiểm tra dependency trực tiếp của một module:

```java
var orders = modules.getModuleByName("orders").orElseThrow();

orders.getDirectDependencies(modules).forEach(dependency ->
        System.out.println(
                dependency.getTargetModule().getDisplayName()
                        + " | " + dependency.getDependencyType()
                        + " | " + dependency.getTargetType().getName()));
```

Nếu verification báo truy cập type không được expose, hãy xem package của target type và kiểm tra package-info tương ứng. Nếu báo dependency không được phép, so sánh module identifier và named interface name trong `allowedDependencies` với metadata của module đích.

## 10. Thử nghiệm một lỗi có chủ đích

Sau khi architecture test chạy thành công, thêm tạm một dependency từ `orders` tới implementation nội bộ của `catalog`:

```java
package com.acme.shop.orders;

import com.acme.shop.catalog.internal.ProductCatalogService;

class OrderDebugProbe {

    private final ProductCatalogService catalog;

    OrderDebugProbe(ProductCatalogService catalog) {
        this.catalog = catalog;
    }
}
```

Vì `ProductCatalogService` được khai báo `public`, Java có thể biên dịch tham chiếu này. Tuy nhiên, package `catalog.internal` không thuộc named interface `catalog-api`, nên Spring Modulith phải phát hiện vi phạm module boundary khi chạy `verify()`.

Sau khi quan sát `Violations`, xóa class thử nghiệm và chạy lại architecture test. Không thêm `catalog.internal` vào named interface chỉ để làm test xanh. Nếu module khác thật sự cần một capability, hãy thiết kế một hợp đồng công khai có tên và phạm vi rõ ràng.

## 11. Quy trình đặt annotation trong một module mới

Thực hiện theo trình tự:

1. **Tạo package gốc:** đặt module dưới root package chứa lớp Spring Boot application.
2. **Quyết định module type:** dùng `CLOSED` nếu muốn chỉ công khai base package và named interfaces; chỉ chọn `OPEN` khi có chủ đích.
3. **Tạo package-info.java ở module root:** khai báo `@ApplicationModule` khi cần metadata tường minh hoặc dùng `explicitly-annotated`.
4. **Xác định hợp đồng liên module:** liệt kê các type mà module khác thực sự cần sử dụng.
5. **Tạo API package:** đặt các type hợp đồng trong package con riêng.
6. **Đánh dấu named interface:** thêm `@NamedInterface` vào `package-info.java` của API package.
7. **Đặt implementation vào internal:** không đánh dấu package implementation là named interface.
8. **Khai báo dependency policy:** thêm selector `module :: interface` vào `allowedDependencies` của module tiêu thụ.
9. **Chạy architecture test:** gọi `ApplicationModules.verify()` và đọc toàn bộ `Violations` nếu có.
10. **Review source tree:** bảo đảm vị trí file và package declaration khớp nhau.

## 12. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Module không có metadata dù đã tạo `package-info.java` | File đặt sai source set hoặc sai package declaration | Kiểm tra đường dẫn và dòng `package` |
| Strategy `explicitly-annotated` không tìm thấy module | Thiếu `@ApplicationModule` trên package gốc | Đặt annotation trong `module-root/package-info.java` |
| Named interface không xuất hiện | `@NamedInterface` nằm sai package hoặc file không được compile | Kiểm tra `api/package-info.java` và package declaration |
| `allowedDependencies` không nhận named interface | Selector dùng sai module id hoặc tên interface | So khớp module name và giá trị `@NamedInterface` |
| Module khác vẫn truy cập internal bị báo lỗi | Type đích nằm ngoài base package và named interfaces | Chuyển caller sang API hoặc thiết kế named interface phù hợp |
| Spring không tạo bean trong internal package | Component scan hoặc bean condition không phù hợp | Kiểm tra Spring scanning riêng; không mở module để sửa bean discovery |
| Java compile thành công nhưng Modulith verify thất bại | Java visibility rộng hơn module visibility | Giữ package internal và sửa dependency của module tiêu thụ |

## 13. Checklist hoàn thành

- [ ] `package-info.java` nằm trong source set đúng và tên file chính xác.
- [ ] Package declaration khớp với đường dẫn và package của class.
- [ ] `@ApplicationModule` nằm ở package gốc của module khi cần metadata.
- [ ] Module type `CLOSED` hoặc `OPEN` được chọn có chủ đích.
- [ ] `@NamedInterface` nằm ở package con chứa API công khai.
- [ ] Tên named interface khớp với selector trong `allowedDependencies`.
- [ ] Package internal không bị đánh dấu thành named interface ngoài ý muốn.
- [ ] Module tiêu thụ chỉ tham chiếu type từ API được phép.
- [ ] Đã phân biệt module discovery với Spring component scanning.
- [ ] `ApplicationModules.of(...).verify()` chạy thành công.
- [ ] Đã thử một dependency nội bộ để xác nhận architecture test phát hiện vi phạm.
- [ ] Đã xóa code thử nghiệm và xác nhận verification trở lại thành công.

`package-info.java` là nơi tự nhiên để đặt metadata kiến trúc ở cấp package. Đặt `@ApplicationModule` tại package gốc giúp mô tả module; đặt `@NamedInterface` tại package API giúp công khai hợp đồng có chọn lọc. Khi package declaration, annotation và `allowedDependencies` khớp nhau, ranh giới module trở nên dễ đọc và có thể được Spring Modulith xác minh tự động.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Application Modules and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [NamedInterface annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Java Language Specification – Package Declarations and Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
