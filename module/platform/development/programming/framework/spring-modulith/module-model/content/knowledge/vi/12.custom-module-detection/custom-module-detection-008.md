# Kiểm thử strategy với package tree đại diện

Một `ApplicationModuleDetectionStrategy` chỉ hữu ích khi nó nhận diện đúng các package đại diện cho module trong cấu trúc ứng dụng thực tế. Vì vậy, bài kiểm thử cần kiểm tra cả package được chọn, package bị loại và những package lồng bên trong module. Chỉ xác nhận kết quả không rỗng sẽ không phát hiện được trường hợp strategy vô tình biến `shared`, `configuration` hoặc `internal` thành module độc lập.

Spring Modulith gọi `getModuleBasePackages(JavaPackage rootPackage)` với package gốc của ứng dụng. Strategy trả về một `Stream<JavaPackage>` chứa các package gốc cần được xem là application module. Có thể kiểm tra thuật toán bằng một package tree nhỏ được tạo từ các fixture trong source test, sau đó kiểm tra thêm kết quả qua `ApplicationModules` để xác nhận cách Spring Modulith sử dụng strategy.

## 1. Xác định package tree cần kiểm thử

Giả sử ứng dụng bán hàng có package gốc `com.acme.shop`. Các module nghiệp vụ nằm ở những package con trực tiếp và được đánh dấu bằng annotation riêng `@DomainModule`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── package-info.java       // @DomainModule
│   ├── Order.java
│   ├── api
│   │   └── OrderApi.java
│   └── internal
│       └── OrderRepository.java
├── catalog
│   ├── package-info.java       // @DomainModule
│   ├── Product.java
│   └── api
│       └── CatalogApi.java
├── shared
│   └── Money.java
├── bootstrap
│   └── WebConfiguration.java
└── architecture
    └── DomainModulesDetectionStrategyTests.java
```

Trong cấu trúc này, `orders` và `catalog` là module. Các package `api` và `internal` nằm bên trong module tương ứng. `shared`, `bootstrap` và `architecture` là package hỗ trợ, không phải module nghiệp vụ.

| Package | Kết quả mong đợi | Lý do |
|---|---|---|
| `com.acme.shop.orders` | Được chọn | Có annotation `@DomainModule` |
| `com.acme.shop.catalog` | Được chọn | Có annotation `@DomainModule` |
| `com.acme.shop.shared` | Bị loại | Không có annotation |
| `com.acme.shop.bootstrap` | Bị loại | Không có annotation |
| `com.acme.shop.orders.internal` | Không được chọn riêng | Đây là package lồng trong module `orders` |

Quy ước của ví dụ là chỉ xét package con trực tiếp của package gốc. Quy ước này giúp các package nội bộ như `orders.internal` không bị tách thành module ngoài ý muốn. Nếu kiến trúc cho phép module lồng nhau, cần thiết kế và kiểm thử quy tắc duyệt cây riêng.

## 2. Đánh dấu package module trong fixture

Tạo annotation dùng riêng cho quy ước phát hiện module:

```java
package com.acme.shop.architecture;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
public @interface DomainModule {
}
```

Đặt annotation trên `package-info.java` của từng package module:

```java
@com.acme.shop.architecture.DomainModule
package com.acme.shop.orders;
```

```java
@com.acme.shop.architecture.DomainModule
package com.acme.shop.catalog;
```

Không đặt annotation trên `shared`, `bootstrap` hoặc các package con như `orders.internal`. Khi biên dịch, annotation package được lưu trong `package-info.class`; package tree mà Spring Modulith phân tích có thể đọc metadata này.

## 3. Cài đặt strategy theo quy ước

`JavaPackage` trong API của Spring Modulith là kiểu đại diện cho một package cùng cấu trúc package liên quan. Dùng `getDirectSubPackages()` để chỉ lấy các package con trực tiếp, rồi kiểm tra annotation trên từng package:

```java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class DomainModulesDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(candidate -> candidate
                        .getAnnotation(DomainModule.class)
                        .isPresent());
    }
}
```

Strategy trả về package object do Spring Modulith cung cấp, không trả về tên package dạng `String`. Kết quả cũng luôn là một stream hợp lệ. Nếu không có package con nào mang annotation, stream sẽ rỗng.

Để thay đổi quy ước, có thể lọc theo tên package, marker class hoặc metadata khác. Mỗi quy tắc cần được thể hiện rõ trong fixture. Ví dụ, nếu chọn package theo tên `domain`, hãy thêm cả package hợp lệ và package có tên gần giống nhưng không hợp lệ để phát hiện lỗi lọc chuỗi.

## 4. Kiểm thử trực tiếp trên package tree

Với Spring Modulith từ phiên bản 1.4, `ApplicationModules.getRootPackages()` cung cấp package gốc đã được phân tích. Có thể lấy package tree này rồi gọi strategy trực tiếp để kiểm tra thuật toán mà không cần tự tạo đối tượng `JavaPackage`:

```java
package com.acme.shop.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.JavaPackage;
import com.acme.shop.ShopApplication;

class DomainModulesDetectionStrategyTests {

    private final DomainModulesDetectionStrategy strategy =
            new DomainModulesDetectionStrategy();

    @Test
    void detectsOnlyDirectPackagesMarkedAsModules() {
        JavaPackage rootPackage = ApplicationModules
                .of(ShopApplication.class)
                .getRootPackages()
                .get(0);

        List<String> detectedPackages = strategy
                .getModuleBasePackages(rootPackage)
                .map(JavaPackage::getName)
                .sorted()
                .collect(Collectors.toList());

        assertThat(detectedPackages).containsExactly(
                "com.acme.shop.catalog",
                "com.acme.shop.orders");
    }
}
```

Đặt lớp `ShopApplication` thực tế ở package gốc `com.acme.shop` trong ứng dụng. Nếu ví dụ kiểm thử được đặt trong một project riêng, thay lớp này bằng lớp ứng dụng thật hoặc một lớp fixture nằm đúng package gốc. Các fixture `package-info.java` và lớp trong những package con phải được biên dịch và nằm trên test classpath.

Phép kiểm tra dùng danh sách tên package đã sắp xếp để kết quả ổn định. Không phụ thuộc vào thứ tự duyệt của collection package, vì thứ tự đó không phải quy tắc phát hiện module.

### Kiểm tra trường hợp không có module

Tạo thêm một package gốc fixture, ví dụ `com.acme.empty`, chỉ có các package con không được đánh dấu:

```text
com.acme.empty
├── EmptyApplication.java
├── shared
│   └── Clock.java
└── configuration
    └── Settings.java
```

Với fixture này, gọi strategy trên package gốc và thu kết quả thành danh sách. Assertion cần xác nhận danh sách rỗng. Trường hợp này bảo vệ quy tắc rằng strategy không tự suy diễn mọi package con thành module khi không có marker.

## 5. Kiểm tra kết quả qua ApplicationModules

Kiểm thử trực tiếp xác nhận thuật toán lọc package. Cần thêm một kiểm thử tích hợp để chắc chắn strategy đã được đăng ký đúng và Spring Modulith thực sự tạo module từ những package mong đợi:

```java
@Test
void applicationModulesUsesTheConfiguredDetectionStrategy() {
    ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

    List<String> detectedPackages = modules.stream()
            .map(module -> module.getBasePackage().getName())
            .sorted()
            .collect(Collectors.toList());

    assertThat(detectedPackages).containsExactly(
            "com.acme.shop.catalog",
            "com.acme.shop.orders");
}
```

Kiểm thử này yêu cầu strategy được đăng ký trong test runtime. Với các phiên bản Spring Modulith hiện hành, có thể cấu hình tên lớp qua thuộc tính `spring.modulith.detection-strategy`:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.DomainModulesDetectionStrategy
```

Đặt thuộc tính trong nguồn cấu hình mà phiên bản Spring Modulith của project sử dụng. Với những phiên bản cũ hơn, tài liệu 1.1 hướng dẫn đăng ký implementation trong `META-INF/spring.factories` bằng key `org.springframework.modulith.core.ApplicationModuleDetectionStrategy`. Hãy đối chiếu đúng phiên bản được quản lý bởi dependency management của ứng dụng.

Sau khi xác nhận module được tạo đúng, có thể gọi `modules.verify()` trong một kiểm thử kiến trúc riêng để kiểm tra các quy tắc phụ thuộc giữa module. Kiểm tra phát hiện package và kiểm tra phụ thuộc trả lời hai câu hỏi khác nhau: strategy xác định ranh giới module, còn `verify()` kiểm tra code có tuân thủ các ranh giới đó hay không.

## 6. Những trường hợp cần đưa vào bộ kiểm thử

| Trường hợp | Điều cần xác nhận |
|---|---|
| Hai package module có marker | Cả hai xuất hiện đúng một lần trong kết quả |
| Package hỗ trợ không có marker | Không xuất hiện trong kết quả |
| Package con `api` hoặc `internal` | Không trở thành module riêng |
| Package gốc không có package con được đánh dấu | Strategy trả về stream rỗng |
| Thêm một package module mới có marker | Package mới được phát hiện mà không phải sửa danh sách tên trong strategy |
| Thêm package mới không có marker | Kết quả không thay đổi |
| Package-info không được đưa vào quá trình phân tích | Bài kiểm thử phải phát hiện metadata marker không còn được đọc |

Một số lỗi thường gặp cần chú ý:

- Dùng toàn bộ package con trong cây thay vì package con trực tiếp, khiến `api` hoặc `internal` bị nhận diện thành module.
- Chỉ kiểm tra số lượng module, nên một package sai vẫn có thể thay thế package đúng mà bài kiểm thử không phát hiện.
- Dựa vào thứ tự của `Set` hoặc collection khi so sánh kết quả.
- Đặt annotation trên package nhưng cấu hình bước import loại bỏ `package-info.class`, làm marker biến mất khỏi package tree.
- Chỉ gọi trực tiếp strategy mà không kiểm tra cấu hình đăng ký; thuật toán đúng vẫn có thể không được Spring Modulith sử dụng khi chạy kiểm thử kiến trúc.

Khi package tree đại diện bao phủ các trường hợp hợp lệ, trường hợp bị loại và package lồng nhau, bộ kiểm thử sẽ bảo vệ được quy ước phát hiện module trước những thay đổi cấu trúc package về sau.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [JavaPackage API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
