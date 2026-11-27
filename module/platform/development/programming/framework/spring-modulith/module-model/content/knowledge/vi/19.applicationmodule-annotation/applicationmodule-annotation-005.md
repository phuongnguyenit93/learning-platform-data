# additionalPackages làm root package bổ sung

Thông thường, Spring Modulith phát hiện application module trong các package con trực tiếp của package chứa lớp Spring Boot application. Với ứng dụng có code được tổ chức ở nhiều namespace, một package gốc duy nhất có thể không bao phủ hết các module cần kiểm tra. `@Modulithic(additionalPackages = ...)` cho phép khai báo thêm những root package để Spring Modulith chạy quá trình phát hiện module.

Điểm quan trọng là `additionalPackages` khai báo **package gốc bổ sung để tìm module**. Theo chiến lược mặc định, các package con trực tiếp của mỗi root mới là application module. Package gốc được thêm vào không tự động trở thành một module.

## 1. Khi nào cần additionalPackages?

Giả sử ứng dụng bán hàng có lớp chính trong `com.acme.shop`, nhưng một số module được đặt trong namespace khác vì lý do tổ chức code hoặc chia sẻ thư viện nội bộ:

```text
com.acme.shop
├── ShopApplication.java
├── orders
└── catalog

com.acme.shared
├── identity
└── pricing

com.acme.fulfillment
└── shipping
```

Nếu chỉ dùng package của `ShopApplication`, Spring Modulith sẽ tìm các module trong `com.acme.shop` theo chiến lược phát hiện đang cấu hình. Các package `identity`, `pricing` và `shipping` nằm ngoài root đó nên không được đưa vào mô hình chỉ nhờ vị trí package của lớp ứng dụng.

Khi thêm `com.acme.shared` và `com.acme.fulfillment`, ta yêu cầu Spring Modulith phát hiện module trong các root này nữa:

```text
Root package mặc định: com.acme.shop
  ├── orders       → module orders
  └── catalog      → module catalog

Root bổ sung: com.acme.shared
  ├── identity     → module identity
  └── pricing      → module pricing

Root bổ sung: com.acme.fulfillment
  └── shipping     → module shipping
```

Như vậy, một `ApplicationModules` model có thể bao gồm module được phát hiện từ nhiều root package.

## 2. Khai báo additionalPackages trên lớp ứng dụng

Đặt `@Modulithic` trên lớp Spring Boot application và truyền các package bổ sung dưới dạng tên package đầy đủ:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@SpringBootApplication
@Modulithic(
        additionalPackages = {
                "com.acme.shared",
                "com.acme.fulfillment"
        }
)
public class ShopApplication {
}
```

`additionalPackages` có kiểu `String[]`, vì vậy có thể khai báo một hoặc nhiều root package. Nếu không cần root bổ sung, giá trị mặc định là mảng rỗng và Spring Modulith chỉ dùng package của lớp mang annotation làm root.

Các chuỗi trong cấu hình phải là tên package thực tế, viết đầy đủ và đúng chính tả. Chúng là điểm bắt đầu cho quá trình phát hiện module, không phải tên module và cũng không phải danh sách từng module con.

## 3. Hiểu đúng ranh giới giữa root package và module

Với chiến lược phát hiện mặc định, Spring Modulith coi các package con trực tiếp của mỗi root package là module. Ví dụ:

```text
com.acme.shared                 ← root package bổ sung
├── identity                    ← application module
│   ├── IdentityService.java
│   └── internal
└── pricing                     ← application module
    ├── Price.java
    └── internal
```

Trong ví dụ này, `com.acme.shared` là root package để quét; `com.acme.shared.identity` và `com.acme.shared.pricing` là các module. Nếu chỉ thêm `com.acme.shared.identity` vào `additionalPackages`, chiến lược mặc định sẽ tìm các module con trực tiếp bên dưới `identity`. Nó không tự coi `identity` là một module chỉ vì package đó xuất hiện trong danh sách root.

Nếu package cần được xem là module không có cấu trúc root/con như quy ước mặc định, hãy xem xét chiến lược phát hiện explicit hoặc `ApplicationModuleDetectionStrategy` phù hợp. `additionalPackages` mở rộng các root đầu vào cho quá trình phát hiện; nó không thay đổi quy tắc nhận diện module của strategy đang dùng.

## 4. Phân biệt phát hiện module với Spring component scanning

`additionalPackages` điều chỉnh mô hình module của Spring Modulith. Nó không tự mở rộng phạm vi component scan của Spring Boot.

Theo mặc định, `@SpringBootApplication` quét component từ package của lớp ứng dụng và các package con. Nếu module bổ sung nằm ngoài namespace đó và chứa `@Component`, `@Service` hoặc `@Configuration` cần được tạo thành bean, hãy cấu hình component scan riêng:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@SpringBootApplication(scanBasePackages = {
        "com.acme.shop",
        "com.acme.shared",
        "com.acme.fulfillment"
})
@Modulithic(additionalPackages = {
        "com.acme.shared",
        "com.acme.fulfillment"
})
public class ShopApplication {
}
```

Hai thuộc tính giải quyết hai việc khác nhau:

| Cấu hình | Tác dụng |
|---|---|
| `@Modulithic(additionalPackages = ...)` | Bổ sung root package cho việc phát hiện và kiểm tra application module |
| `@SpringBootApplication(scanBasePackages = ...)` | Bổ sung package để Spring component scan tìm bean |

Tương tự, entity scan và repository scan của persistence có thể cần cấu hình riêng tùy cách ứng dụng tổ chức JPA. Đừng giả định rằng thêm root vào mô hình Modulith đồng nghĩa mọi cơ chế quét của Spring đều tự nhận package đó.

## 5. Tránh xung đột tên module giữa các root

Khi có nhiều root package, hai root có thể chứa module con cùng tên:

```text
com.acme.shop
└── catalog

com.acme.partner
└── catalog
```

Nếu dùng tên module cục bộ mặc định, cả hai module đều có thể mang tên `catalog`. Khi cần phân biệt chúng trong dependency declaration, cấu hình `useFullyQualifiedModuleNames = true` trên `@Modulithic`:

```java
@SpringBootApplication
@Modulithic(
        additionalPackages = "com.acme.partner",
        useFullyQualifiedModuleNames = true
)
public class ShopApplication {
}
```

Khi đó, tên mặc định của module được biểu diễn bằng package đầy đủ, chẳng hạn `com.acme.shop.catalog` và `com.acme.partner.catalog`. Cách này đặc biệt hữu ích khi `additionalPackages` đưa các namespace độc lập vào cùng một Modulith và có khả năng trùng tên module cục bộ.

Nếu module đã khai báo identifier tường minh bằng `@ApplicationModule(id = "...")`, hãy dùng identifier đó trong cấu hình tham chiếu module. `useFullyQualifiedModuleNames` điều chỉnh tên mặc định được suy ra từ package.

## 6. Kiểm tra các module được phát hiện

Sau khi cấu hình root bổ sung, tạo mô hình từ lớp ứng dụng như bình thường:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(module -> System.out.printf(
        "module=%s, basePackage=%s%n",
        module.getDisplayName(),
        module.getBasePackage().getName()));
```

Kết quả minh họa:

```text
module=orders, basePackage=com.acme.shop.orders
module=catalog, basePackage=com.acme.shop.catalog
module=identity, basePackage=com.acme.shared.identity
module=pricing, basePackage=com.acme.shared.pricing
module=shipping, basePackage=com.acme.fulfillment.shipping
```

Tên hiển thị và thứ tự thực tế phụ thuộc metadata của ứng dụng; điều cần kiểm tra là các base package mong đợi có mặt trong mô hình. Có thể đưa kiểm tra kiến trúc vào test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesModulesFromAllConfiguredRoots() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc trên mô hình module đã được phát hiện, bao gồm chu trình phụ thuộc, truy cập API và `allowedDependencies`. Nếu một root bị bỏ sót hoặc module con không được nhận diện, hãy kiểm tra tên package trong `additionalPackages` và chiến lược phát hiện đang hoạt động.

## 7. additionalPackages khác sharedModules

Hai thuộc tính này cùng nằm trên `@Modulithic` nhưng có mục đích khác nhau:

| Thuộc tính | Mục đích |
|---|---|
| `additionalPackages` | Bổ sung root package để phát hiện application module |
| `sharedModules` | Đánh dấu các module đã được phát hiện là shared module; chúng luôn được đưa vào module integration test bootstrap |

`additionalPackages` ảnh hưởng đến việc module nào xuất hiện trong mô hình. `sharedModules` lựa chọn module theo tên để có mặt trong bootstrap của module integration test. Đánh dấu một module là shared không thay thế việc phát hiện module và cũng không biến package tùy ý thành root mới.

Ví dụ kết hợp hai thuộc tính:

```java
@SpringBootApplication
@Modulithic(
        additionalPackages = "com.acme.shared",
        sharedModules = { "identity" }
)
public class ShopApplication {
}
```

Trong cấu hình này, `com.acme.shared` là root bổ sung để phát hiện các module con; module có tên `identity` được đánh dấu shared cho module integration test bootstrap. Tên trong `sharedModules` phải khớp tên module mà ứng dụng đang sử dụng, bao gồm quy tắc tên đầy đủ nếu đã bật `useFullyQualifiedModuleNames`.

## 8. Những lỗi thường gặp

- **Thêm tên module con thay vì root package:** `additionalPackages` cần package chứa các module con cần phát hiện.
- **Nghĩ root bổ sung tự nó là module:** theo strategy mặc định, các package con trực tiếp mới là module.
- **Bỏ qua namespace của lớp ứng dụng:** package của lớp mang `@Modulithic` vẫn là root mặc định; `additionalPackages` chỉ bổ sung root khác.
- **Nhầm Modulith discovery với component scan:** bean nằm ngoài component scan có thể không được tạo dù module đã xuất hiện trong mô hình.
- **Quên cấu hình JPA scan:** entity và repository nằm ngoài package mặc định có thể cần cấu hình persistence riêng.
- **Để trùng tên module cục bộ:** dùng `useFullyQualifiedModuleNames` hoặc identifier tường minh khi nhiều root có module con trùng tên.
- **Dùng `sharedModules` để thay `additionalPackages`:** shared module phải được phát hiện trước; `sharedModules` không khai báo root package.
- **Khai báo root package sai chính tả hoặc không tồn tại:** mô hình có thể thiếu module mong đợi; hãy xác nhận base package sau khi tạo `ApplicationModules`.

## 9. Checklist cấu hình nhiều root package

- [ ] Package của lớp Spring Boot application đã được xác định là root mặc định.
- [ ] Mỗi package namespace bổ sung đã được khai báo trong `additionalPackages`.
- [ ] Đã xác nhận các module nằm ở đúng vị trí mà detection strategy mong đợi bên dưới từng root.
- [ ] Đã kiểm tra xung đột tên module giữa các root.
- [ ] Đã bật `useFullyQualifiedModuleNames` hoặc đặt identifier riêng nếu cần phân biệt tên.
- [ ] Đã cấu hình component scan cho bean nằm ngoài phạm vi mặc định.
- [ ] Đã xem xét entity scan và repository scan nếu có persistence ngoài root mặc định.
- [ ] Đã chạy `ApplicationModules.of(...).verify()` để kiểm tra cấu trúc và quy tắc phụ thuộc.

`additionalPackages` giúp Spring Modulith mô hình hóa một ứng dụng có module nằm trong nhiều namespace. Khi phân biệt rõ root package, module con, component scan và shared module, ta có thể mở rộng phạm vi kiểm tra kiến trúc mà vẫn giữ được ý nghĩa chính xác của từng cấu hình.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Modulithic annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [AnnotationModulithMetadata API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/AnnotationModulithMetadata.html)
- [Spring Boot – Using the @SpringBootApplication Annotation](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
