# Module annotation trong `package-info.java`

Trong Java, `package-info.java` là nơi khai báo tài liệu và annotation ở cấp package. Spring Modulith tận dụng cơ chế này để gắn metadata kiến trúc trực tiếp với package gốc của application module. Khi đặt `@ApplicationModule` trong `package-info.java`, nhóm phát triển có thể đánh dấu package là module và khai báo các thông tin như tên hiển thị, kiểu module hoặc những module mà nó được phép phụ thuộc.

Với detection strategy `explicitly-annotated`, annotation này còn đóng vai trò xác định package nào được chọn làm application module. Nhờ đó, ý định kiến trúc nằm ngay cạnh cấu trúc mã nguồn và có thể được kiểm tra bằng `ApplicationModules`.

Trong `SPRING_MODULITH_MODULE_MODEL`, hiểu đúng cách dùng `package-info.java` giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong ứng dụng Spring Boot.

## 1. `package-info.java` là gì?

Java cho phép khai báo annotation và tài liệu ở cấp package. Theo quy ước của Java, các khai báo này được đặt trong một file tên chính xác là `package-info.java`, nằm trong thư mục tương ứng với package.

Ví dụ, package `com.example.shop.inventory` có file:

```text
src/main/java/com/example/shop/inventory/package-info.java
```

Nội dung file có thể chứa Javadoc mô tả package, annotation package-level và câu lệnh `package`:

```java
/**
 * Quản lý tồn kho và cung cấp các hợp đồng truy vấn số lượng khả dụng.
 */
package com.example.shop.inventory;
```

`package-info.java` không phải lớp Java thông thường. Nó là compilation unit dành cho package metadata. Khi được biên dịch, compiler tạo metadata package trong output của package, cho phép công cụ và framework đọc annotation ở cấp package.

Mỗi package chỉ nên có một `package-info.java`. Tên package trong file phải khớp chính xác với package được thể hiện bởi đường dẫn thư mục.

## 2. Đánh dấu application module bằng `@ApplicationModule`

Spring Modulith cung cấp annotation `@ApplicationModule` để mô tả một application module. Với Java, đặt annotation ngay trước khai báo package trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

File nằm tại:

```text
src/main/java/com/example/shop/inventory/package-info.java
```

Với detection strategy `explicitly-annotated`, package `com.example.shop.inventory` được chọn làm package gốc của module `inventory`. Tên logic mặc định được suy ra từ tên package tương đối với package gốc ứng dụng, trừ khi module có identifier tường minh theo phiên bản Spring Modulith hỗ trợ.

Đặt annotation ở đúng package rất quan trọng. Nếu muốn đánh dấu `inventory`, file phải khai báo `package com.example.shop.inventory;`. Đặt annotation trên package gốc `com.example.shop` hoặc trên một lớp nằm trong package khác không có nghĩa là đã đánh dấu module `inventory`.

## 3. Khai báo metadata module trong `package-info.java`

`@ApplicationModule` có thể khai báo thêm metadata để mô tả ý định thiết kế. Ví dụ, module tồn kho hiển thị tên dễ đọc và chỉ cho phép phụ thuộc vào `catalog` cùng `pricing`:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management",
    allowedDependencies = { "catalog", "pricing" }
)
package com.example.shop.inventory;
```

Các thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| `displayName` | Tên dễ đọc dùng trong tài liệu hoặc báo cáo module |
| `allowedDependencies` | Danh sách module hoặc named interface mà module hiện tại được phép phụ thuộc |
| `type` | Kiểu encapsulation của module, chẳng hạn `CLOSED` hoặc `OPEN` |
| `id` | Định danh logic tường minh, có trong các phiên bản Spring Modulith hỗ trợ thuộc tính này |

Nếu không cần metadata bổ sung, annotation không có thuộc tính vẫn đủ để đánh dấu package. Không nên khai báo whitelist dependency chỉ để làm ví dụ phức tạp hơn; hãy thêm thuộc tính khi nó phản ánh quy tắc kiến trúc thực tế.

### Chọn kiểu module

Module mặc định là closed. Nếu muốn thể hiện rõ lựa chọn đó trong metadata:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.example.shop.inventory;
```

Nếu module cần mở toàn bộ package theo một quyết định kiến trúc có chủ đích, có thể dùng `ApplicationModule.Type.OPEN`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.legacy;
```

Open module làm các package thuộc module trở thành bề mặt được expose theo quy tắc Spring Modulith. Nó không thay đổi Java visibility và không tự đăng ký Spring bean. Chỉ dùng khi phạm vi công bố rộng là chủ đích; nếu chỉ cần chia sẻ một package con, hãy cân nhắc `@NamedInterface`.

## 4. `package-info.java` tham gia module detection như thế nào?

Spring Modulith có các detection strategy để xác định package nào là module. Hai chiến lược thường được dùng là:

- `direct-sub-packages`: chọn các package con trực tiếp của package gốc ứng dụng. Với chiến lược này, package có thể được nhận diện thành module ngay cả khi không có `@ApplicationModule`.
- `explicitly-annotated`: chỉ chọn package được đánh dấu bằng `@ApplicationModule` hoặc annotation module được hỗ trợ như jMolecules `@Module`.

Để bật chiến lược explicit, cấu hình:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Ví dụ cây package:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java       // @ApplicationModule
│   └── internal
├── order
│   ├── package-info.java       // @ApplicationModule
│   └── internal
├── payment
│   └── package-info.java       // @ApplicationModule
├── common                     // không đánh dấu
└── configuration              // không đánh dấu
```

Với `explicitly-annotated`, các package `inventory`, `order` và `payment` được nhận diện thành module. `common` và `configuration` không tự trở thành module độc lập vì không có annotation module phù hợp.

Với `direct-sub-packages`, các package con trực tiếp như `common` và `configuration` cũng có thể được nhận diện thành module. Do đó, lựa chọn detection strategy quyết định vai trò của `package-info.java` trong quá trình phát hiện.

## 5. Phân biệt annotation module với annotation trên lớp

Một lỗi dễ gặp là đặt annotation ở sai vị trí hoặc nhầm annotation package-level với stereotype dùng để đăng ký bean.

Đánh dấu package trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.example.shop.order;
```

Đây là metadata kiến trúc của package `order`.

Trong khi đó, `@Service` trên một lớp:

```java
package com.example.shop.order.internal;

import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {
}
```

đánh dấu lớp là Spring bean candidate. Hai annotation có mục đích khác nhau:

| Annotation | Đặt ở đâu? | Tác dụng |
|---|---|---|
| `@ApplicationModule` | Package gốc module, thường trong `package-info.java` | Đánh dấu module và khai báo metadata kiến trúc |
| `@NamedInterface` | Package con cần expose, thường trong `package-info.java` | Công bố package như một nhóm API có tên |
| `@Service` | Trên lớp | Đánh dấu lớp là Spring service bean candidate |
| `@Repository` | Trên lớp hoặc interface repository | Đánh dấu thành phần truy cập dữ liệu cho Spring |

`@ApplicationModule` không thay thế component scan, không tạo bean và không thay đổi cách Spring inject dependency.

## 6. Kết hợp module annotation với Named Interface

Một module có thể khai báo metadata tại package gốc và công bố một hoặc nhiều package con bằng named interface. Mỗi package có file `package-info.java` riêng.

Metadata module `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Named interface `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Named interface `reporting`:

```java
@org.springframework.modulith.NamedInterface("reporting")
package com.example.shop.inventory.reporting;
```

Hai named interface vẫn thuộc module `inventory`; chúng không trở thành module riêng. Module khác có thể khai báo dependency tới một nhóm API cụ thể, ví dụ `inventory::spi`.

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Trong ví dụ này, `order` chỉ cho phép phụ thuộc vào named interface `spi` của `inventory` theo whitelist đã khai báo.

## 7. Package con không cần đánh dấu nếu chỉ là nội bộ

Không cần tạo `@ApplicationModule` cho mọi package con. Với cấu trúc:

```text
com.example.shop.inventory
├── package-info.java           // @ApplicationModule
├── InventoryManagement.java
├── application
│   └── RecalculateStockService.java
├── domain
│   └── StockItem.java
└── internal
    └── InventoryRepository.java
```

Chỉ package gốc `com.example.shop.inventory` được đánh dấu là module. Các package `application`, `domain` và `internal` thuộc module đó nếu không được khai báo riêng thành nested module theo khả năng của phiên bản Spring Modulith.

Nếu đánh dấu một package con bằng `@ApplicationModule`, bạn đang thể hiện ý định tạo một ranh giới module lồng nhau, chứ không đơn thuần tổ chức thêm thư mục. Chỉ làm vậy khi package con có trách nhiệm nghiệp vụ và quy tắc phụ thuộc đủ độc lập.

## 8. Quy tắc viết `package-info.java` đúng

Hãy tuân theo các điểm sau để annotation được compiler và Spring Modulith nhận diện:

1. **Đúng tên file:** dùng chính xác `package-info.java`, không dùng `PackageInfo.java` hoặc `package-info.txt`.
2. **Đúng thư mục:** đặt file trong source directory tương ứng với package, ví dụ `src/main/java/com/example/shop/inventory/`.
3. **Đúng package declaration:** tên package trong file phải trùng với package mục tiêu.
4. **Đặt annotation trước package declaration:** package annotation xuất hiện trước dòng `package ...;`.
5. **Giữ một file cho mỗi package:** không tạo nhiều file `package-info.java` cho cùng package trong cùng source set.
6. **Đảm bảo được biên dịch:** file phải nằm trong source set và output được đưa vào classpath mà Spring Modulith phân tích.
7. **Không đánh dấu quá rộng:** chỉ đánh dấu package thực sự là module hoặc package thực sự cần expose.

Ví dụ file hoàn chỉnh có Javadoc và annotation:

```java
/**
 * Quản lý tồn kho, số lượng khả dụng và các hợp đồng tích hợp liên quan.
 */
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management",
    allowedDependencies = "catalog"
)
package com.example.shop.inventory;
```

## 9. Kiểm tra annotation và module đã được nhận diện

Sau khi biên dịch ứng dụng hoặc test source set phù hợp, có thể tạo mô hình module bằng `ApplicationModules`:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Để tìm module theo logical name:

```java
var inventory = modules.getModuleByName("inventory")
        .orElseThrow(() -> new IllegalStateException("inventory module not found"));

System.out.println(inventory.getIdentifier());
System.out.println(inventory.getBasePackage());
```

Nếu module không được nhận diện, hãy kiểm tra file `package-info.java` có đúng package, có được biên dịch và có nằm trên classpath được phân tích không. Nếu đang dùng `explicitly-annotated`, hãy kiểm tra annotation có đúng là `@ApplicationModule` hoặc `@Module` của jMolecules không.

## 10. Kiểm chứng ranh giới bằng `ApplicationModules.verify()`

Sau khi module được nhận diện, hãy kiểm tra các quy tắc phụ thuộc và encapsulation:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleMetadataAndDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra mô hình module đã được tạo, bao gồm các dependency và vi phạm ranh giới mà Spring Modulith hỗ trợ phát hiện. Nếu module khai báo `allowedDependencies`, các tham chiếu thực tế phải phù hợp với whitelist. Nếu module đóng, truy cập package con chưa được expose có thể bị phát hiện là vi phạm.

Việc kiểm tra này không thay thế kiểm thử khởi động Spring context. `ApplicationModules` kiểm tra mô hình kiến trúc; kiểm thử context xác nhận component scan, bean registration và dependency injection hoạt động đúng.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `package-info.java` là một lớp Java cần khởi tạo | Đây là compilation unit dùng cho package documentation và package annotation. |
| Phải đặt `@ApplicationModule` trên lớp `ShopApplication` | Annotation cần gắn với package gốc của module, thường qua `package-info.java`. |
| Mọi package con đều cần `package-info.java` | Chỉ tạo file khi cần metadata package, module annotation hoặc named interface. |
| `@ApplicationModule` tự đăng ký bean | Annotation mô tả module; Spring bean vẫn cần stereotype hoặc `@Bean`. |
| `@NamedInterface` tạo module mới | Nó công bố một package con như nhóm API của module sở hữu. |
| Đặt `@ApplicationModule` trong package con chỉ là thêm metadata | Nó có thể tạo nested module nếu phiên bản và detection model hỗ trợ; hãy đánh dấu có chủ đích. |
| Có file `package-info.java` trong source tree là đủ | File cần được compiler xử lý và metadata phải hiện diện trên classpath được phân tích. |

## 12. Checklist tạo module annotation

- [ ] Xác định package gốc cần được nhận diện thành application module.
- [ ] Tạo `package-info.java` trong đúng thư mục package.
- [ ] Viết package declaration trùng với đường dẫn package.
- [ ] Đặt `@ApplicationModule` trước package declaration.
- [ ] Khai báo `displayName`, `allowedDependencies` hoặc `type` khi có nhu cầu thực tế.
- [ ] Nếu dùng `explicitly-annotated`, bảo đảm detection strategy đã được cấu hình.
- [ ] Chỉ đánh dấu package con khi thật sự muốn tạo nested module.
- [ ] Dùng `@NamedInterface` riêng cho package con cần expose như API.
- [ ] Xác nhận `package-info.java` được biên dịch và nằm trên classpath.
- [ ] Quan sát mô hình bằng `ApplicationModules.of(...).forEach(...)`.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra ranh giới và dependency.

## 13. Kết luận

`package-info.java` là vị trí tự nhiên để khai báo metadata ở cấp package trong Java. Spring Modulith dùng `@ApplicationModule` tại đây để đánh dấu package gốc application module và khai báo các quy tắc như tên hiển thị, kiểu module hoặc dependency được phép. Khi dùng detection strategy `explicitly-annotated`, annotation này còn quyết định package nào được chọn làm module.

Hãy đặt file đúng thư mục, dùng package declaration chính xác, bảo đảm file được biên dịch và chỉ đánh dấu những package có ý nghĩa kiến trúc. Phân biệt `@ApplicationModule` với `@NamedInterface` và stereotype Spring để giữ rõ ranh giới giữa module, API package và bean registration. Cuối cùng, dùng `ApplicationModules` để quan sát mô hình và `verify()` để kiểm tra các quy tắc đã khai báo.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `@NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
- [Java Language Specification — Package Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.4)
