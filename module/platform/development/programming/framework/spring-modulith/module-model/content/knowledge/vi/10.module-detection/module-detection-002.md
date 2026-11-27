# Direct sub-packages và điều kiện được coi là module

Spring Modulith suy ra application module từ cấu trúc package của ứng dụng. Với chiến lược phát hiện mặc định, mỗi **package con trực tiếp** của package gốc ứng dụng được xem là một application module. Các package nằm sâu hơn tiếp tục thuộc module gần nhất ở cấp trên, vì vậy `order.internal` mặc định là phần bên trong module `order`, không phải một module độc lập.

Quy tắc này làm cho cấu trúc package trở thành một phần của thiết kế kiến trúc. Chỉ cần đặt một package ở cấp trực tiếp dưới package gốc, Spring Modulith có thể xem nó là module, dù tên package đó là `order`, `service`, `repository` hay `common`. Công cụ không tự hiểu ý nghĩa nghiệp vụ từ tên; nó áp dụng chiến lược phát hiện module lên các package mà nó tìm thấy trên classpath.

Trong `SPRING_MODULITH_MODULE_MODEL`, cần nắm rõ package gốc, cấp package và điều kiện để package được nhận diện thành module trước khi thiết kế API công khai, Named Interface và quy tắc phụ thuộc.

## 1. Package gốc và package con trực tiếp

Package gốc (root package) là điểm xuất phát để Spring Modulith tìm các module. Thông thường, đó là package chứa lớp khởi chạy có `@SpringBootApplication` hoặc lớp ứng dụng được truyền vào `ApplicationModules.of(...)`.

Ví dụ, lớp ứng dụng nằm trong package `com.example.shop`:

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

Với package gốc này, các package con trực tiếp là:

```text
com.example.shop
├── inventory
├── order
├── payment
└── customer
```

Tên đầy đủ của chúng lần lượt là `com.example.shop.inventory`, `com.example.shop.order`, `com.example.shop.payment` và `com.example.shop.customer`. Theo chiến lược mặc định, mỗi package này là một application module.

Package con trực tiếp là package chỉ thêm đúng một cấp tên so với package gốc. Ví dụ, `com.example.shop.order` là package con trực tiếp của `com.example.shop`, còn `com.example.shop.order.internal` là package con của `com.example.shop.order`.

## 2. Quy tắc phát hiện mặc định

Spring Modulith mặc định sử dụng chiến lược `direct-sub-packages`. Có thể hiểu quy tắc này qua ba bước:

1. Xác định package gốc của ứng dụng.
2. Tìm các package con trực tiếp của package gốc trong phạm vi classpath được phân tích.
3. Xem mỗi package tìm được là package gốc của một application module.

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

Các module được phát hiện là:

| Module | Package gốc module | Package con thuộc module |
|---|---|---|
| `inventory` | `com.example.shop.inventory` | `com.example.shop.inventory.internal` |
| `order` | `com.example.shop.order` | `com.example.shop.order.internal` |
| `payment` | `com.example.shop.payment` | Không có trong ví dụ |

`inventory.internal` và `order.internal` không trở thành module cấp cao nhất theo chiến lược mặc định, vì chúng nằm sâu hơn một cấp so với package gốc ứng dụng. Chúng thuộc module `inventory` và `order` tương ứng.

## 3. Điều kiện để một package được coi là module

Với chiến lược `direct-sub-packages`, một package được nhận diện là module khi thỏa mãn các điều kiện chính sau:

**Nó nằm đúng cấp package.** Package phải là package con trực tiếp của root package đang được phân tích. Package ở cấp sâu hơn không tự động trở thành module cấp cao nhất.

**Nó hiện diện trong phạm vi phân tích.** Spring Modulith cần nhìn thấy package qua các kiểu Java hoặc metadata package đã biên dịch trên classpath. Một thư mục rỗng trong source tree, không có kiểu hay metadata được biên dịch, không đủ để tạo ra một package mà bộ phân tích có thể phát hiện.

**Chiến lược phát hiện hiện tại chọn package đó.** Nếu dự án chuyển sang `explicitly-annotated` hoặc dùng `ApplicationModuleDetectionStrategy` tùy chỉnh, điều kiện chọn module sẽ theo chiến lược mới thay vì chỉ dựa vào vị trí trực tiếp.

**Package thuộc root đang được xét.** Một package nằm ngoài root package sẽ không tự xuất hiện trong mô hình chỉ vì nó cùng nằm trong repository hoặc cùng được Java compiler biên dịch. Có thể cần thêm root package hoặc điều chỉnh cách tổ chức và discovery.

Với chiến lược mặc định, không cần đánh dấu từng package con trực tiếp bằng `@ApplicationModule` chỉ để Spring Modulith nhận diện nó là module. Annotation này hữu ích khi cần khai báo metadata hoặc khi dùng chiến lược yêu cầu module được đánh dấu tường minh.

## 4. Cấp package quyết định ranh giới module

Hãy so sánh các package sau khi root là `com.example.shop`:

| Package | Quan hệ với root | Vai trò mặc định |
|---|---|---|
| `com.example.shop.inventory` | Con trực tiếp | Module `inventory` |
| `com.example.shop.order` | Con trực tiếp | Module `order` |
| `com.example.shop.order.internal` | Cháu của root | Package nội bộ thuộc `order` |
| `com.example.shop.order.persistence.jpa` | Hậu duệ sâu hơn | Package bên trong `order` |
| `com.example.shared` | Nằm ngoài root | Không được phát hiện từ root `com.example.shop` |

Một module có thể tổ chức nhiều package con theo trách nhiệm kỹ thuật:

```text
com.example.shop.order
├── OrderManagement.java
├── application
│   └── PlaceOrderService.java
├── domain
│   ├── Order.java
│   └── OrderLine.java
├── persistence
│   └── OrderRepository.java
└── web
    └── OrderController.java
```

Tất cả package `application`, `domain`, `persistence` và `web` vẫn thuộc module `order` theo quy tắc mặc định. Chúng không tự trở thành module riêng chỉ vì có tên package.

## 5. Tên package không quyết định ý nghĩa nghiệp vụ

Spring Modulith dựa vào vị trí package để phát hiện module. Nó không suy luận rằng `order` là nghiệp vụ đơn hàng hay `service` chỉ là một lớp kỹ thuật.

Ví dụ, nếu tổ chức code như sau:

```text
com.example.shop
├── controller
├── service
├── repository
└── entity
```

Theo chiến lược mặc định, bốn package con trực tiếp có thể được nhận diện thành bốn module: `controller`, `service`, `repository` và `entity`. Điều này thường không phản ánh ranh giới nghiệp vụ mong muốn, vì các thành phần của cùng một nghiệp vụ bị tách ra nhiều module kỹ thuật.

Với modular monolith, thường nên tổ chức package cấp cao theo khả năng nghiệp vụ:

```text
com.example.shop
├── customer
│   ├── CustomerManagement.java
│   ├── application
│   └── persistence
├── inventory
│   ├── InventoryManagement.java
│   ├── application
│   └── persistence
└── order
    ├── OrderManagement.java
    ├── application
    └── persistence
```

Khi đó, mỗi module có thể sở hữu logic, dữ liệu và các thành phần kỹ thuật phục vụ đúng nghiệp vụ của mình.

## 6. Có cần `@ApplicationModule` để trở thành module không?

Không phải lúc nào cũng cần. Với chiến lược mặc định `direct-sub-packages`, một package con trực tiếp được phát hiện theo vị trí package. Bạn có thể thêm `@ApplicationModule` trong `package-info.java` để khai báo metadata như tên hiển thị, kiểu module hoặc giới hạn dependency:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Ở ví dụ này, package `com.example.shop.inventory` vốn đã là module theo quy tắc mặc định. Annotation bổ sung metadata cho module.

Nếu chọn chiến lược `explicitly-annotated`, package cần được đánh dấu tường minh bằng `@ApplicationModule` hoặc annotation module tương thích được Spring Modulith hỗ trợ:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Khi đó, package chỉ được chọn làm module nếu có metadata đánh dấu phù hợp. Cùng một package có thể được phát hiện trong chiến lược mặc định nhưng không được chọn trong chiến lược explicit nếu thiếu annotation.

## 7. Khi package con trực tiếp không phải module mong muốn

Vì quy tắc mặc định chọn package con trực tiếp, các package kỹ thuật hoặc package hỗ trợ nằm ở cấp này cũng có thể bị nhận diện thành module. Có một số cách xử lý:

**Tổ chức lại package.** Nếu `common`, `support` hoặc `configuration` chỉ phục vụ một module, hãy cân nhắc đặt nó bên trong module sở hữu trách nhiệm đó.

**Dùng chiến lược explicit.** Đánh dấu những package thực sự là module bằng `@ApplicationModule`, sau đó cấu hình `spring.modulith.detection-strategy=explicitly-annotated`.

**Dùng chiến lược tùy chỉnh.** Triển khai `ApplicationModuleDetectionStrategy` nếu quy tắc chọn module của ứng dụng không khớp với hai chiến lược có sẵn.

Ví dụ, chiến lược tùy chỉnh chỉ chọn một số package con trực tiếp theo tên nghiệp vụ:

```java
package com.example.architecture;

import java.util.Set;
import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

class BusinessModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULES = Set.of(
            "com.example.shop.customer",
            "com.example.shop.inventory",
            "com.example.shop.order",
            "com.example.shop.payment");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(pkg -> MODULES.contains(pkg.getName()));
    }
}
```

Đăng ký chiến lược bằng tên lớp đầy đủ:

```properties
spring.modulith.detection-strategy=com.example.architecture.BusinessModuleDetectionStrategy
```

Ví dụ này giả định các module nghiệp vụ đều là package con trực tiếp của root. Khi cấu trúc package thay đổi, danh sách và chiến lược cũng cần được cập nhật tương ứng.

## 8. Module nằm ngoài package gốc

Giả sử ứng dụng có package gốc `com.example.shop`, nhưng module dùng chung nằm tại `com.example.shared.customer`. Module này không phải hậu duệ của `com.example.shop`, nên không được phát hiện từ root đó theo quy tắc mặc định.

Có thể bổ sung package gốc bằng `@Modulithic` trên lớp ứng dụng:

```java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.example.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Spring Modulith áp dụng chiến lược phát hiện module cho package gốc ứng dụng và các package gốc bổ sung. Các package con của `com.example.shared` có thể được xem là module theo detection strategy hiện hành.

`additionalPackages` chỉ bổ sung root để phát hiện module. Nó không tự biến toàn bộ package được chỉ định thành một module và cũng không thay thế component scan của Spring Boot.

## 9. Kiểm tra các module được phát hiện

Sau khi xác định root package, có thể tạo mô hình và in các module:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionReport {

    void printModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }
}
```

Bạn cũng có thể kiểm tra một module cụ thể bằng logical name:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

var inventory = modules.getModuleByName("inventory")
        .orElseThrow(() -> new IllegalStateException("inventory module not found"));

System.out.println(inventory.getIdentifier());
System.out.println(inventory.getBasePackage());
```

Nếu một package con trực tiếp không xuất hiện, hãy kiểm tra package có nằm trong root được chọn hay không, package có hiện diện trên classpath và detection strategy có lọc nó ra hay không. Nếu một package con sâu hơn xuất hiện như module ngoài dự kiến, hãy xem lại cấu hình nested module hoặc root package bổ sung.

## 10. Kiểm chứng quy tắc module bằng `verify()`

Phát hiện được module mới chỉ là bước đầu. Sau khi mô hình hóa, hãy kiểm tra các ranh giới và dependency:

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

`verify()` kiểm tra các quy tắc kiến trúc mà Spring Modulith hỗ trợ, chẳng hạn truy cập package nội bộ, phụ thuộc vòng và các dependency không được cho phép khi module khai báo whitelist. Kiểm tra này giúp bảo đảm cấu trúc module không chỉ được phát hiện mà còn tuân thủ ranh giới đã thiết kế.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Mọi package nằm dưới root đều là module | Mặc định chỉ package con trực tiếp là module; package sâu hơn thuộc module cha. |
| Chỉ package có tên nghiệp vụ mới được phát hiện | Detection dựa vào vị trí package và chiến lược, không hiểu ngữ nghĩa tên package. |
| Phải có `@ApplicationModule` thì package con trực tiếp mới thành module | Không cần với chiến lược mặc định; annotation dùng để khai báo metadata hoặc phục vụ explicit detection. |
| Thư mục rỗng trong source tree chắc chắn là module | Package cần hiện diện trong phạm vi phân tích trên classpath; thư mục rỗng không có kiểu hay metadata được biên dịch không đủ để phát hiện. |
| `order.internal` tự động là module riêng | Nó là package con thuộc module `order` theo quy tắc mặc định. |
| `additionalPackages` thay đổi component scan | Nó bổ sung root package cho module detection, không đăng ký Spring bean. |
| `verify()` quyết định package nào là module | Detection strategy quyết định module được phát hiện; `verify()` kiểm tra các quy tắc trên mô hình đã tạo. |

## 12. Checklist xác định package có phải module không

- [ ] Xác định đúng root package của ứng dụng.
- [ ] Kiểm tra package đang xét có phải package con trực tiếp của root không.
- [ ] Xác nhận package hiện diện trong classpath được phân tích.
- [ ] Kiểm tra `spring.modulith.detection-strategy` có đang dùng chiến lược mặc định, explicit hay custom không.
- [ ] Kiểm tra package có bị loại khỏi chiến lược tùy chỉnh không.
- [ ] Phân biệt package con trực tiếp với package lồng sâu hơn.
- [ ] Đánh giá tên package cấp cao có phản ánh một trách nhiệm nghiệp vụ không.
- [ ] Dùng `@Modulithic(additionalPackages = ...)` nếu cần thêm root package.
- [ ] In `ApplicationModules` để xác nhận kết quả thực tế.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra ranh giới và dependency.

## 13. Kết luận

Với chiến lược phát hiện mặc định, Spring Modulith xem mỗi package con trực tiếp của root package là một application module nếu package đó hiện diện trong phạm vi classpath được phân tích. Package sâu hơn thuộc module cha; tên package không quyết định ý nghĩa nghiệp vụ và annotation `@ApplicationModule` không bắt buộc chỉ để nhận diện package con trực tiếp trong chiến lược mặc định.

Khi thiết kế modular monolith, hãy chọn root package rõ ràng, đặt module theo trách nhiệm nghiệp vụ và giữ các package kỹ thuật bên trong module tương ứng. Nếu cấu trúc không phù hợp với quy tắc direct sub-packages, có thể dùng explicit detection, custom detection strategy hoặc bổ sung root package. Cuối cùng, quan sát mô hình và chạy `ApplicationModules.verify()` để xác nhận package arrangement phản ánh đúng ranh giới mong muốn.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModuleDetectionStrategy` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
