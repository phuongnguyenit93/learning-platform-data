# Detection dựa trên package của lớp Spring Boot chính

Spring Modulith dùng package của lớp ứng dụng Spring Boot làm điểm bắt đầu để phát hiện application module. Với chiến lược mặc định, mỗi package con trực tiếp của package này được nhận diện là một module. Vì vậy, vị trí package trong mã nguồn của lớp `@SpringBootApplication` quyết định phạm vi mà Spring Modulith xem xét khi xây dựng mô hình module.

Ví dụ, nếu `ShopApplication` thuộc package `com.acme.shop`, các package `com.acme.shop.catalog`, `com.acme.shop.order` và `com.acme.shop.customer` sẽ được nhận diện thành các module. Nếu đặt lớp ứng dụng trong `com.acme.shop.bootstrap`, Spring Modulith lấy `com.acme.shop.bootstrap` làm root; các package `com.acme.shop.catalog` và `com.acme.shop.order` khi đó không còn là package con trực tiếp của root này.

Sau bài học, bạn có thể:

- Xác định root package từ lớp ứng dụng Spring Boot.
- Dự đoán các module được phát hiện từ vị trí package của lớp ứng dụng.
- Nhận biết lỗi đặt lớp ứng dụng quá sâu trong cây package.
- Phân biệt package dùng để phát hiện module với phạm vi component scan của Spring Boot.
- Bổ sung root package bằng `@Modulithic` và kiểm tra mô hình bằng `ApplicationModules`.

## 1. Package của lớp ứng dụng là root package

Một ứng dụng Spring Boot thường có lớp chính được đánh dấu `@SpringBootApplication`:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Trong ví dụ này, package của `ShopApplication` là `com.acme.shop`. Spring Modulith sử dụng package đó làm root package khi tạo mô hình từ lớp ứng dụng. Với detection strategy mặc định `directSubPackage`, các package con trực tiếp là những module được phát hiện.

```text
com.acme.shop                         <- root package
├── ShopApplication.java
├── catalog                           <- module: catalog
│   ├── CatalogService.java
│   └── internal
│       └── ProductRepository.java
├── order                             <- module: order
│   ├── OrderService.java
│   └── internal
│       └── OrderRepository.java
└── customer                          <- module: customer
    └── CustomerService.java
```

Kết quả phát hiện là ba module `catalog`, `order` và `customer`. Tên module được xác định từ package module, nên package `com.acme.shop.order` có logical name là `order`.

Các package sâu hơn như `com.acme.shop.order.internal` thuộc module `order`. Chúng không tự trở thành module ngang hàng. Đây là lý do cấu trúc package nên phản ánh ranh giới nghiệp vụ ở cấp trực tiếp dưới root package.

## 2. Điều gì xảy ra nếu lớp ứng dụng nằm quá sâu?

Giả sử dự án có cấu trúc:

```text
com.acme.shop
├── catalog
├── order
└── bootstrap
    └── ShopApplication.java
```

Lớp `ShopApplication` khai báo:

```java
package com.acme.shop.bootstrap;

@SpringBootApplication
public class ShopApplication {
    // main(...)
}
```

Root package mà Spring Modulith lấy từ lớp ứng dụng lúc này là `com.acme.shop.bootstrap`. Theo chiến lược `directSubPackage`, Spring Modulith tìm các package con trực tiếp bên dưới root đó. `catalog` và `order` là package ngang hàng với `bootstrap`, nên không được phát hiện như module con của root `com.acme.shop.bootstrap`.

Để ứng dụng có mô hình dễ dự đoán, hãy đặt lớp ứng dụng ở package chung phía trên các module:

```text
com.acme.shop
├── ShopApplication.java              <- đặt lớp ứng dụng tại đây
├── bootstrap
│   └── StartupConfiguration.java
├── catalog
├── order
└── customer
```

Nếu có lý do kiến trúc khiến lớp ứng dụng phải nằm trong package riêng, hãy chủ động cấu hình root package bổ sung thay vì giả định Spring Modulith sẽ tự suy ra package cha.

## 3. Tên package Java quyết định cấu trúc, không phải tên thư mục hiển thị

Java xác định package bằng khai báo `package` trong mã nguồn. Trong dự án thông thường, đường dẫn thư mục phản ánh tên package, nhưng điều Spring Modulith phân tích là package của các kiểu được biên dịch.

Ví dụ:

```java
package com.acme.shop.order;

public class OrderService {
}
```

Kiểu này thuộc `com.acme.shop.order`, bất kể tên file là `OrderService.java` và được lưu trong source set nào. Để việc phát hiện module rõ ràng, hãy duy trì sự nhất quán giữa khai báo package và cấu trúc thư mục nguồn.

Đừng đặt lớp `@SpringBootApplication` trong package mặc định hoặc một package quá rộng như `com`. Root quá rộng có thể khiến nhiều namespace không liên quan bị đưa vào phạm vi phân tích; root quá sâu có thể bỏ sót các module nghiệp vụ là package ngang hàng. Hãy chọn package gốc thể hiện ranh giới của đúng một ứng dụng.

## 4. Root package của Modulith và component scan là hai khái niệm riêng

`@SpringBootApplication` cũng kích hoạt component scan của Spring Boot. Theo mặc định, Spring Boot quét package của lớp ứng dụng và các package con để tìm bean. Thuộc tính `scanBasePackages` có thể thay đổi phạm vi component scan.

Ví dụ:

```java
@SpringBootApplication(scanBasePackages = {
        "com.acme.shop",
        "com.acme.shared"
})
public class ShopApplication {
}
```

Khai báo trên điều chỉnh nơi Spring Boot tìm component. Nó không nên được xem là cách khai báo root package bổ sung cho mô hình Spring Modulith. Spring Modulith có cấu hình riêng cho việc đó qua `@Modulithic(additionalPackages = ...)`.

Phân biệt trách nhiệm:

| Cấu hình | Mục đích |
|---|---|
| Package của `ShopApplication` | Root package mặc định để Spring Modulith phát hiện module |
| `@SpringBootApplication(scanBasePackages = ...)` | Các package Spring Boot quét để tìm component |
| `@Modulithic(additionalPackages = ...)` | Các root package bổ sung được đưa vào mô hình Spring Modulith |
| `spring.modulith.detection-strategy` | Cách chọn module base package bên trong các root package |

Việc bean được Spring component scan tìm thấy không tự động chứng minh package đó đã được nhận diện là một application module. Hãy kiểm tra mô hình Modulith riêng biệt.

## 5. Bổ sung root package bằng `@Modulithic`

Khi ứng dụng cần phân tích thêm một namespace độc lập, bạn có thể dùng `@Modulithic` trên lớp ứng dụng:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.acme.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Trong cấu hình này, `com.acme.shop` vẫn là root lấy từ package của lớp ứng dụng; `com.acme.shared` được bổ sung như một root package khác cho việc phân tích Modulith. Các package con của từng root được xử lý theo detection strategy đang sử dụng.

Bạn có thể chỉ định nhiều package bổ sung:

```java
@Modulithic(additionalPackages = {
        "com.acme.shared",
        "com.acme.integration"
})
@SpringBootApplication
public class ShopApplication {
}
```

Chỉ thêm những root package thực sự thuộc phạm vi kiến trúc cần kiểm tra. Nếu một namespace chỉ chứa thư viện dùng chung và không phải application module, hãy cân nhắc cơ chế shared modules hoặc cách tổ chức phù hợp với mục đích thay vì biến mọi package thành module nghiệp vụ.

## 6. Chọn đúng lớp khi tạo `ApplicationModules`

Trong bài kiểm tra kiến trúc, lớp truyền vào `ApplicationModules.of(...)` xác định ứng dụng mà mô hình được xây dựng từ đó:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Hãy truyền lớp ứng dụng chính của ứng dụng đang kiểm tra. Nếu truyền nhầm một lớp cấu hình nằm sâu trong package `com.acme.shop.bootstrap`, package đó có thể trở thành điểm bắt đầu của mô hình được tạo từ lớp ấy, dẫn đến kết quả phát hiện khác với mô hình dự kiến.

Để quan sát module được phát hiện trước khi xác minh:

```java
var modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
modules.verify();
```

Khi đọc kết quả, đối chiếu logical name và base package của từng module với cây package thực tế. Nếu module bị thiếu, hãy kiểm tra package của lớp ứng dụng, detection strategy và cấu hình `additionalPackages` trước khi chỉnh sửa metadata của từng module.

## 7. Checklist thiết kế package cho lớp ứng dụng

Khi khởi tạo hoặc tái cấu trúc ứng dụng Spring Modulith, hãy kiểm tra:

1. Lớp `@SpringBootApplication` nằm trong package gốc chung của ứng dụng.
2. Mỗi module nghiệp vụ là package con trực tiếp của root theo chiến lược mặc định.
3. Các package sâu hơn được tổ chức bên trong module sở hữu chúng.
4. Không nhầm `scanBasePackages` với root package của Spring Modulith.
5. Root package độc lập bổ sung được khai báo bằng `@Modulithic(additionalPackages = ...)` khi cần.
6. Bài kiểm tra dùng đúng lớp ứng dụng trong `ApplicationModules.of(...)`.
7. `ApplicationModules.verify()` chạy trong bộ kiểm tra kiến trúc của dự án.

## 8. Ghi nhớ

Package của lớp ứng dụng Spring Boot là root package mặc định để Spring Modulith phát hiện module. Với chiến lược `directSubPackage`, các package con trực tiếp của root là application module; package con sâu hơn thuộc module cha. Đặt lớp ứng dụng quá sâu có thể khiến các module nghiệp vụ nằm ngoài phạm vi phát hiện. `scanBasePackages` điều khiển component scan của Spring Boot, còn `@Modulithic(additionalPackages = ...)` bổ sung root package cho mô hình Modulith. Luôn tạo mô hình bằng đúng lớp ứng dụng và xác minh kết quả bằng `ApplicationModules.verify()`.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals – Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules)
- [Spring Modulith Fundamentals – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.detection)
- [Spring Modulith API – `@Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Boot – `@SpringBootApplication` và component scan](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
