# Quét classpath và suy ra cấu trúc package

Spring Modulith có thể đọc cấu trúc mã nguồn của một ứng dụng Spring Boot để xây dựng mô hình các application module. API trung tâm cho công việc này là `ApplicationModules`. Khi cung cấp lớp ứng dụng hoặc package gốc, Spring Modulith phân tích các lớp và package nằm bên dưới điểm bắt đầu, sau đó suy ra module nào tồn tại, package nào thuộc module và phần nào là API hay nội bộ.

Trong `SPRING_MODULITH_MODULE_MODEL`, việc hiểu cách quét classpath và suy ra cấu trúc package là nền tảng để đọc ranh giới nghiệp vụ, xác định API công khai và kiểm tra các phụ thuộc giữa module. Bài học này tập trung vào cách tạo mô hình bằng `ApplicationModules`, quy ước phát hiện module mặc định và các lựa chọn khi cấu trúc package không theo quy ước đó.

## 1. `ApplicationModules` làm nhiệm vụ gì?

`ApplicationModules` thuộc artifact `spring-modulith-core`. Lớp này tạo một mô hình trong bộ nhớ về cách ứng dụng được chia thành các module. Mô hình được suy ra từ cấu trúc package của codebase cùng metadata và các tùy chọn cấu hình có liên quan.

Điểm bắt đầu thường là lớp ứng dụng Spring Boot có `@SpringBootApplication`:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleModelInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
    }
}
```

`ApplicationModules.of(ShopApplication.class)` lấy package chứa `ShopApplication` làm package gốc để phân tích. Từ đó, Spring Modulith áp dụng chiến lược phát hiện module để xác định những package nào là package gốc của application module.

Điều cần nhớ là `ApplicationModules` xây dựng mô hình kiến trúc từ các lớp trên classpath. Nó không khởi chạy ứng dụng Spring, không tạo `ApplicationContext` và không thay thế cơ chế component scan của Spring Boot. Việc mô hình hóa module và việc đăng ký bean là hai công việc khác nhau.

## 2. Chọn package gốc để bắt đầu phân tích

Package gốc của ứng dụng thường là package chứa lớp có `@SpringBootApplication`. Ví dụ:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Trong ví dụ, package gốc là `com.example.shop`. Theo quy ước phát hiện mặc định, các package con trực tiếp của `com.example.shop` được xem là các application module.

```text
com.example.shop
├── ShopApplication.java
├── inventory
├── order
└── payment
```

Ba module được nhận diện là `inventory`, `order` và `payment`. Tên logic mặc định của mỗi module được suy ra từ package tương đối với package gốc.

Nếu không muốn truyền lớp ứng dụng, API cũng có overload nhận tên package:

```java
ApplicationModules modules = ApplicationModules.of("com.example.shop");
```

Khi dùng overload này, package được truyền là điểm bắt đầu phân tích. Nếu ứng dụng có cấu hình metadata trên lớp ứng dụng như `@Modulithic`, dùng lớp ứng dụng thường phù hợp hơn vì `ApplicationModules.of(ShopApplication.class)` có thể đọc cấu hình gắn với lớp đó.

## 3. Quy tắc phát hiện module mặc định

Mặc định, Spring Modulith xem mỗi package con trực tiếp của package chính là một module. Những package nằm sâu hơn tiếp tục thuộc module tương ứng, trừ khi chúng được khai báo thành nested application module theo cấu hình phù hợp.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       ├── InventoryManagementImpl.java
│       └── InventoryRepository.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── PlaceOrderService.java
└── payment
    └── PaymentManagement.java
```

Spring Modulith suy ra ba module cấp cao nhất:

- `com.example.shop.inventory`
- `com.example.shop.order`
- `com.example.shop.payment`

Các package `inventory.internal` và `order.internal` không tự trở thành module cấp cao nhất. Chúng là package con thuộc module cha. Theo quy ước đóng gói mặc định, package gốc của module cung cấp API; các package con là phần nội bộ, trừ khi được công bố bằng named interface hoặc cấu hình khác.

### Module đơn giản và module có package con

Một module đơn giản có thể chỉ có package gốc:

```text
com.example.shop.inventory
├── InventoryManagement.java
└── StockItem.java
```

Trong trường hợp không có package con, các kiểu `public` trong package đó tạo nên API của module. Java package scope cũng có thể được dùng để giữ một số kiểu ở mức package-private.

Khi module có package con:

```text
com.example.shop.inventory
├── InventoryManagement.java
├── StockItem.java
└── internal
    ├── InventoryManagementImpl.java
    └── InventoryRepository.java
```

Package gốc vẫn là API mặc định. Package `internal` và các package con khác được xem là nội bộ. Một lớp bên trong package con đôi khi phải khai báo `public` để các lớp khác trong cùng module sử dụng; modifier `public` không tự làm cho lớp đó trở thành API liên module.

## 4. Tạo và quan sát mô hình module

Sau khi tạo `ApplicationModules`, bạn có thể duyệt các module để xem cấu trúc được phân tích:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleModelInspection {

    void printModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }
}
```

Kết quả hiển thị thường bao gồm:

- Tên logic của module.
- Package gốc (base package) của module.
- Các Spring bean được nhận diện bên trong module.
- Thông tin về kiểu nào nằm trong API được công bố và kiểu nào thuộc phần nội bộ.

Ví dụ đầu ra rút gọn có thể trông như sau:

```text
## com.example.shop.inventory ##
> Logical name: inventory
> Base package: com.example.shop.inventory
> Spring beans:
  + ….InventoryManagement
  o ….internal.InventoryManagementImpl

## com.example.shop.order ##
> Logical name: order
> Base package: com.example.shop.order
> Spring beans:
  + ….OrderManagement
  o ….internal.PlaceOrderService
```

Ký hiệu hiển thị trong báo cáo giúp nhận ra các thành phần được công bố và các thành phần nội bộ. Đây là cách nhanh để kiểm tra xem package arrangement có phản ánh đúng ý định thiết kế hay không.

Bạn cũng có thể lấy một module theo tên hoặc xác định module chứa một kiểu cụ thể:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

var inventory = modules.getModuleByName("inventory");
var owner = modules.getModuleByType(InventoryManagement.class);
```

Các phương thức trả về `Optional`, vì vậy trong mã thực tế cần xử lý trường hợp không tìm thấy module hoặc kiểu tương ứng.

## 5. Cấu trúc package quyết định ranh giới như thế nào?

Hãy xem hai cách tổ chức sau.

### Tổ chức theo nghiệp vụ

```text
com.example.shop
├── inventory
│   ├── InventoryManagement.java
│   └── internal
├── order
│   ├── OrderManagement.java
│   └── internal
└── payment
    ├── PaymentManagement.java
    └── internal
```

Cách tổ chức này tạo ra các module nghiệp vụ rõ ràng. Mỗi module có API và phần triển khai riêng. Khi `order` cần kiểm tra tồn kho, nó sử dụng API được công bố của `inventory`.

### Tổ chức theo loại kỹ thuật

```text
com.example.shop
├── controller
├── service
├── repository
└── entity
```

Theo quy ước mặc định, các package con trực tiếp này có thể bị nhận diện thành các module riêng. Logic của một nghiệp vụ như đặt hàng lại bị phân tán qua nhiều module kỹ thuật. Kết quả phân tích khi đó không thể hiện ranh giới nghiệp vụ mà nhóm phát triển mong muốn.

Vì vậy, hãy ưu tiên đặt package cấp cao theo khả năng nghiệp vụ, sau đó tổ chức `web`, `application`, `domain`, `persistence` hoặc `internal` bên trong từng module khi cần.

## 6. Tùy chỉnh chiến lược phát hiện module

Quy ước direct sub-packages phù hợp với phần lớn ứng dụng có package gốc rõ ràng. Nếu cách tổ chức của ứng dụng khác, Spring Modulith cho phép thay đổi module detection strategy.

### Chỉ phát hiện package được đánh dấu

Bạn có thể cấu hình:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Với chiến lược này, Spring Modulith chỉ xem package được đánh dấu rõ ràng bằng `@ApplicationModule` hoặc annotation `@Module` của jMolecules là module base package.

Ví dụ, khai báo trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

Các package không được đánh dấu sẽ không tự trở thành module chỉ vì chúng là package con trực tiếp. Cách này hữu ích khi ứng dụng có nhiều package kỹ thuật cấp cao và muốn chỉ định module một cách tường minh.

### Tùy chỉnh bằng `ApplicationModuleDetectionStrategy`

Nếu hai chiến lược có sẵn không phù hợp, có thể triển khai `ApplicationModuleDetectionStrategy` để chọn các package được xem là module base package:

```java
package com.example.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

class ShopModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(pkg -> !pkg.getName().endsWith(".support"));
    }
}
```

Đây là ví dụ minh họa cách lọc các package con; tiêu chí thực tế cần dựa trên quy ước của ứng dụng. Đăng ký implementation bằng thuộc tính `spring.modulith.detection-strategy` với tên lớp đầy đủ:

```properties
spring.modulith.detection-strategy=com.example.architecture.ShopModuleDetectionStrategy
```

Chiến lược tùy chỉnh cần được đặt trong test classpath nếu chỉ phục vụ kiểm thử cấu trúc và tài liệu. Nếu các thành phần runtime của Spring Modulith cũng cần sử dụng cùng chiến lược, hãy bảo đảm cấu hình và dependency tương ứng có mặt ở runtime.

## 7. Thêm package gốc để phát hiện module

Trong một số ứng dụng, module nằm ở nhiều package gốc khác nhau. `@Modulithic` trên lớp ứng dụng cho phép khai báo thêm root package để Spring Modulith chạy module detection tại các vị trí đó:

```java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.example.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Ở đây, `com.example.shop` vẫn là package gốc của lớp ứng dụng. Spring Modulith cũng áp dụng quá trình phát hiện module cho package gốc bổ sung `com.example.shared`. Các package con phù hợp dưới mỗi root được xử lý theo detection strategy đang dùng.

`additionalPackages` không có nghĩa mọi lớp trong package đó tự động trở thành module. Nó bổ sung một điểm bắt đầu để áp dụng quy tắc phát hiện module. Tương tự, thuộc tính này không thay thế component scan của Spring Boot.

## 8. Loại trừ package khỏi quá trình phân tích

Đôi khi codebase có package sinh tự động, package tích hợp hoặc các kiểu kỹ thuật không nên tham gia vào mô hình module. `ApplicationModules.of` có overload nhận predicate để bỏ qua các lớp hoặc package phù hợp.

Ví dụ, loại trừ package `com.example.shop.generated` và các package con của nó:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage("com.example.shop.generated..")
);
```

Predicate được truyền vào là điều kiện nhận diện các kiểu cần bỏ qua. Cú pháp `..` trong package matcher có thể dùng để khớp package cùng các package con. Hãy loại trừ có chủ đích; bỏ qua package nghiệp vụ quan trọng có thể khiến mô hình thiếu module hoặc bỏ sót dependency cần kiểm tra.

## 9. Nested module và Named Interface

Package con thông thường được xem là phần nội bộ của module cha. Từ Spring Modulith 1.3, có thể khai báo một nested application module bằng cách đánh dấu package con đó bằng `@ApplicationModule`.

Ví dụ:

```text
com.example.shop
└── inventory
    ├── InventoryManagement.java
    ├── internal
    └── replenishment
        ├── package-info.java  // @ApplicationModule
        └── ReplenishmentApi.java
```

Khi `com.example.shop.inventory.replenishment` được đánh dấu, Spring Modulith có thể mô hình hóa nó như một nested module bên trong `inventory`. Đây là cách chia nhỏ một module lớn khi bên trong nó đã có các ranh giới nghiệp vụ riêng cần quản lý.

Nếu chỉ muốn công bố một package con mà không tạo nested module, hãy dùng `@NamedInterface` trên package đó:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Named interface mở rộng bề mặt API của module. Package vẫn thuộc module `inventory`, nhưng các module khác được phép phụ thuộc vào nhóm kiểu đã công bố theo tên `spi`.

## 10. Kiểm tra mô hình sau khi quét

Sau khi tạo mô hình, hãy in cấu trúc và chạy kiểm tra kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModulesTests {

    @Test
    void inspectsAndVerifiesModuleArrangement() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

`modules.forEach(System.out::println)` giúp quan sát mô hình mà quá trình phân tích tạo ra. `verify()` kiểm tra các quy tắc kiến trúc như phụ thuộc vòng, truy cập package nội bộ và các dependency không được cho phép nếu module có khai báo whitelist.

Nếu kết quả không đúng ý định, hãy kiểm tra theo thứ tự:

1. Lớp ứng dụng có nằm ở package gốc mong muốn không?
2. Các module có phải package con trực tiếp theo chiến lược mặc định không?
3. Có package kỹ thuật nào đang bị nhận nhầm thành module không?
4. Có package nghiệp vụ nào nằm ngoài root package hoặc bị loại trừ không?
5. `spring.modulith.detection-strategy`, `@Modulithic(additionalPackages = ...)` hoặc annotation `@ApplicationModule` có đang thay đổi kết quả phát hiện không?
6. Package con cần là internal package, named interface hay nested module?

Không nên sửa package chỉ để làm cho báo cáo nhìn đẹp. Hãy xác định trước ranh giới nghiệp vụ mong muốn rồi điều chỉnh cấu trúc hoặc detection strategy để mô hình phản ánh đúng ranh giới đó.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `ApplicationModules` khởi chạy Spring context để tìm bean | Nó phân tích codebase và tạo mô hình module; component scan và context startup là cơ chế riêng. |
| Mọi package con đều là module | Theo mặc định chỉ package con trực tiếp của root package là module; package sâu hơn thuộc module cha trừ khi được khai báo nested module. |
| Package `service`, `repository` luôn là cấu trúc phù hợp | Nếu chúng nằm trực tiếp dưới root package, chúng có thể bị nhận diện thành module riêng; nên đặt theo module nghiệp vụ. |
| Một lớp `public` trong package con mặc nhiên là API module | Package con là nội bộ theo mặc định; cần named interface hoặc cấu hình phù hợp để công bố. |
| `additionalPackages` mở rộng component scan | Thuộc tính này bổ sung root package cho module detection, không đăng ký Spring bean. |
| `verify()` chỉ in cấu trúc | `verify()` thực thi các kiểm tra kiến trúc và ném lỗi nếu phát hiện vi phạm. |

## 12. Checklist sử dụng `ApplicationModules`

- [ ] Xác định lớp ứng dụng hoặc package gốc làm điểm bắt đầu.
- [ ] Tạo mô hình bằng `ApplicationModules.of(...)`.
- [ ] Kiểm tra package con trực tiếp được nhận diện thành module.
- [ ] Xác nhận package con sâu hơn thuộc đúng module cha hoặc nested module.
- [ ] In mô hình bằng `modules.forEach(System.out::println)` để xem logical name, base package và Spring beans.
- [ ] Chỉ dùng `explicitly-annotated` hoặc custom detection strategy khi cấu trúc cần điều đó.
- [ ] Dùng `@Modulithic(additionalPackages = ...)` khi cần thêm root package.
- [ ] Loại trừ package bằng predicate một cách có chủ đích.
- [ ] Phân biệt nested module với named interface.
- [ ] Chạy `modules.verify()` để kiểm tra ranh giới và dependency.

## 13. Kết luận

`ApplicationModules` tạo mô hình module trong bộ nhớ từ codebase, bắt đầu bằng lớp ứng dụng hoặc package được chỉ định. Theo quy ước mặc định, mỗi package con trực tiếp của package gốc là một application module; các package sâu hơn thuộc module cha và được xem là nội bộ, trừ khi được công bố hoặc khai báo nested module theo cách tường minh.

Khi hiểu đúng điểm bắt đầu quét, quy tắc suy ra package và các tùy chọn detection strategy, nhóm phát triển có thể kiểm tra cấu trúc module trước khi áp dụng các quy tắc phụ thuộc. Kết hợp việc quan sát mô hình với `ApplicationModules.verify()` giúp phát hiện sớm package arrangement không phản ánh đúng ranh giới nghiệp vụ.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — `ApplicationModuleDetectionStrategy` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
