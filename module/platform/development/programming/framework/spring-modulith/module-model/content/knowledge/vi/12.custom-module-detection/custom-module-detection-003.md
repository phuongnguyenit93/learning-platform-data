# Chọn module theo quy ước tên package

Khi cấu trúc package của ứng dụng không khớp với chiến lược phát hiện mặc định, bạn có thể tự chọn application module theo một quy ước tên package thống nhất. Spring Modulith cung cấp `ApplicationModuleDetectionStrategy` để nhận package gốc của ứng dụng và trả về các package được xem là module. Một custom strategy có thể lọc package con trực tiếp theo tiền tố, hậu tố hoặc biểu thức tên đã thống nhất trong nhóm.

Ví dụ, nhóm quy ước mọi module nghiệp vụ có tên package bắt đầu bằng `module_`: `com.acme.shop.module_catalog`, `com.acme.shop.module_order`. Các package tiện ích như `configuration`, `bootstrap` hoặc `support` không khớp quy ước nên không được chọn làm module. Quy tắc được đặt trong một strategy và cấu hình bằng `spring.modulith.detection-strategy`.

Sau bài học, bạn có thể:

- Thiết kế quy ước tên package để phân biệt module nghiệp vụ với package hạ tầng.
- Viết `ApplicationModuleDetectionStrategy` lọc package theo tiền tố, hậu tố hoặc mẫu tên.
- Đăng ký custom strategy bằng tên lớp đầy đủ.
- Kiểm tra danh sách module được phát hiện và xử lý package không khớp quy ước.

## 1. Xác định quy ước tên package trước khi viết strategy

Custom detection chỉ hoạt động tốt khi quy ước tên package rõ ràng, nhất quán và có thể kiểm tra bằng mã. Ví dụ, ứng dụng có root package `com.acme.shop` và tổ chức như sau:

```text
com.acme.shop
├── module_catalog
│   ├── CatalogService.java
│   └── internal
│       └── ProductRepository.java
├── module_order
│   ├── OrderService.java
│   └── internal
│       └── OrderRepository.java
├── module_customer
│   └── CustomerService.java
├── configuration
│   └── WebConfiguration.java
└── bootstrap
    └── StartupConfiguration.java
```

Nhóm thống nhất các quy tắc:

1. Chỉ package con trực tiếp của `com.acme.shop` mới được xét làm module.
2. Tên package module phải bắt đầu bằng `module_`.
3. Phần sau tiền tố chỉ dùng chữ thường, chữ số và dấu gạch dưới; ký tự đầu tiên phải là chữ cái.
4. Package không bắt đầu bằng `module_` là package hỗ trợ, cấu hình hoặc bootstrap và không được chọn làm module.
5. Package con sâu hơn, chẳng hạn `module_catalog.internal`, thuộc module cha; không được quét đệ quy để tạo module mới.

Tên package được chọn cũng là cơ sở để Spring Modulith xác định logical name. Với ví dụ trên, module có tên `module_catalog`, `module_order` và `module_customer`. Khi khai báo phụ thuộc, phải dùng đúng logical name này.

Một quy ước tốt cần tránh trường hợp tên package chỉ tình cờ khớp mẫu. Nếu nhóm đã dùng `module_` cho package tiện ích hoặc mã sinh tự động, hãy chọn tiền tố khác dành riêng cho module nghiệp vụ.

## 2. Viết strategy lọc theo tiền tố và mẫu tên

Tạo lớp triển khai `ApplicationModuleDetectionStrategy`. Phương thức `getModuleBasePackages` nhận `JavaPackage` của root và trả về stream các package được chọn làm module.

```java
package com.acme.shop;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class ShopModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(pkg -> pkg.getLocalName()
                        .matches("module_[a-z][a-z0-9_]*"));
    }
}
```

Điều kiện `matches` kiểm tra toàn bộ tên package con:

- `module_catalog` khớp mẫu.
- `module_order` khớp mẫu.
- `module_customer_v2` khớp mẫu.
- `configuration` không khớp vì thiếu tiền tố.
- `module_Catalog` không khớp vì chứa chữ hoa.
- `module_2catalog` không khớp vì ký tự đầu sau tiền tố là chữ số.

`getDirectSubPackages()` giúp giới hạn việc lựa chọn ở một cấp ngay dưới root package. Điều này rất quan trọng: nếu quét mọi package con theo cách đệ quy, package `internal` hoặc `persistence` bên trong module có thể bị tách nhầm thành module độc lập.

Nếu quy ước chỉ cần kiểm tra tiền tố, có thể viết ngắn hơn:

```java
return rootPackage.getDirectSubPackages().stream()
        .filter(pkg -> pkg.getLocalName().startsWith("module_"));
```

Phiên bản dùng biểu thức tên chặt hơn khi bạn muốn kiểm soát cả phần tên phía sau tiền tố. Chọn mức kiểm tra phù hợp với quy ước thực tế; tránh tạo pattern phức tạp hơn mức cần thiết.

## 3. Lọc theo hậu tố hoặc danh sách tên cho phép

Không nhất thiết phải dùng tiền tố `module_`. Nếu dự án đang có quy ước hậu tố `_module`, strategy có thể lọc như sau:

```java
return rootPackage.getDirectSubPackages().stream()
        .filter(pkg -> pkg.getLocalName().matches("[a-z][a-z0-9_]*_module"));
```

Khi đó, `catalog_module` và `order_module` được chọn. Logical name của module sẽ mang hậu tố này, vì vậy các khai báo phụ thuộc cũng phải dùng tên tương ứng.

Một số dự án có số lượng module nhỏ và danh sách được quản lý tập trung. Có thể dùng allowlist tên package:

```java
import java.util.Set;

private static final Set<String> MODULE_PACKAGES = Set.of(
        "catalog",
        "order",
        "customer"
);

@Override
public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
    return rootPackage.getDirectSubPackages().stream()
            .filter(pkg -> MODULE_PACKAGES.contains(pkg.getLocalName()));
}
```

Với cách này, package mới sẽ không tự trở thành module cho đến khi được thêm vào danh sách. Đây là lựa chọn phù hợp khi muốn review từng module mới, nhưng danh sách cần được cập nhật cùng lúc với thay đổi cấu trúc package.

Đừng kết hợp nhiều quy ước tên không liên quan trong cùng strategy nếu không có lý do rõ ràng. Một quy tắc đơn giản giúp người phát triển dự đoán kết quả và giảm nguy cơ package hạ tầng vô tình trở thành module.

## 4. Đăng ký custom strategy

Đặt lớp strategy trong source set phù hợp, sau đó cấu hình tên lớp đầy đủ. Nếu chiến lược được dùng khi chạy kiểm tra kiến trúc, có thể đặt lớp trong `src/test/java` và property trong `src/test/resources/application.properties`:

```properties
spring.modulith.detection-strategy=com.acme.shop.ShopModuleDetectionStrategy
```

Nếu ứng dụng cần dùng chiến lược đó khi runtime, đặt lớp trong `src/main/java` và property trong `src/main/resources/application.properties`. Lớp strategy phải có mặt trên classpath ở nơi Spring Modulith tạo mô hình.

Với YAML, cấu hình tương đương:

```yaml
spring:
  modulith:
    detection-strategy: com.acme.shop.ShopModuleDetectionStrategy
```

Property nhận tên lớp đầy đủ, gồm package và tên class, không phải tên bean hay tên ngắn của class. Implementation nên có constructor không tham số để framework có thể khởi tạo strategy theo cơ chế cấu hình.

## 5. Kiểm tra kết quả phát hiện

Sau khi đăng ký strategy, hãy tạo mô hình từ lớp ứng dụng Spring Boot chính:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionInspection {

    void inspect() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

Đối chiếu kết quả với quy ước đã chọn:

| Package | Kết quả mong đợi | Lý do |
|---|---|---|
| `com.acme.shop.module_catalog` | Được phát hiện | Package con trực tiếp, khớp tiền tố và mẫu tên |
| `com.acme.shop.module_order` | Được phát hiện | Package con trực tiếp, khớp tiền tố và mẫu tên |
| `com.acme.shop.configuration` | Bị bỏ qua | Không khớp tiền tố `module_` |
| `com.acme.shop.module_catalog.internal` | Không phải module riêng | Đây là package con sâu hơn của module `module_catalog` |

`verify()` kiểm tra các quy tắc kiến trúc trên các module được phát hiện. Nó không tự chứng minh rằng mọi package nghiệp vụ mong muốn đã được chọn. Vì vậy, ngoài `verify()`, hãy quan sát danh sách module và đối chiếu với danh sách module kỳ vọng.

Một bài kiểm tra có thể gọi strategy thông qua mô hình `ApplicationModules`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void detectsModulesUsingPackageConvention() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

Khi số lượng module đã ổn định, nên lưu danh sách module kỳ vọng trong test hoặc một kiểm tra riêng để phát hiện package module bị đổi tên hay vô tình bị loại khỏi pattern.

## 6. Những lỗi dễ gặp khi chọn theo tên package

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Module không xuất hiện | Tên package không khớp tiền tố, hậu tố hoặc regex | Kiểm tra `getLocalName()` và mẫu tên |
| Package `internal` trở thành module | Strategy quét package con đệ quy | Chỉ xét `getDirectSubPackages()` của root |
| Package cấu hình bị nhận diện thành module | Pattern quá rộng | Dùng tiền tố dành riêng hoặc allowlist |
| Module mới bị bỏ sót | Danh sách tên cho phép chưa cập nhật | Cập nhật allowlist cùng thay đổi package và test |
| Dependency khai báo không tìm thấy module | Dùng tên ngắn khác logical name phát sinh từ package | Dùng đúng tên module mà Spring Modulith hiển thị |
| Test nhận diện đúng nhưng runtime nhận diện khác | Strategy hoặc property chỉ có trong test source set | Đặt implementation và cấu hình ở source set tương ứng với nơi sử dụng |

Đặc biệt, tên package là một phần của hợp đồng kiến trúc khi dùng convention-based detection. Đổi `module_catalog` thành `catalog` có thể khiến module biến mất khỏi mô hình, đồng thời làm các chuỗi `allowedDependencies` trỏ đến tên cũ không còn phù hợp. Hãy xem đổi tên package module là một thay đổi kiến trúc và cập nhật các phụ thuộc liên quan trong cùng thay đổi.

## 7. Ghi nhớ

Custom detection theo quy ước tên package giúp nhóm kiểm soát module bằng một quy tắc có thể tự động hóa. Strategy nhận root package và lọc các package con trực tiếp bằng tiền tố, hậu tố, regex hoặc danh sách cho phép. Hãy chọn một quy ước tên dành riêng cho module nghiệp vụ, tránh quét đệ quy package con và kiểm tra danh sách module thực tế sau khi cấu hình. Logical name phát sinh từ tên package được dùng tiếp trong `allowedDependencies`, vì vậy đổi tên package cũng là thay đổi hợp đồng kiến trúc cần được rà soát.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.detection)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [JavaPackage API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
