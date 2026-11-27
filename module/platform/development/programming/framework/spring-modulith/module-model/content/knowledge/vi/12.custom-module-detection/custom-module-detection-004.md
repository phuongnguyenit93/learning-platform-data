# Chọn module theo annotation riêng

Spring Modulith có sẵn các cách phát hiện application module phổ biến: mặc định chọn package con trực tiếp của package chứa lớp Spring Boot application; chiến lược `explicitly-annotated` chọn package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module`. Nhưng một dự án có thể đã có quy ước riêng, chẳng hạn đánh dấu capability bằng annotation `@BusinessModule`, `@BoundedContext` hoặc `@FeatureArea`.

Trong trường hợp đó, ta có thể tự định nghĩa annotation ở cấp package và triển khai `ApplicationModuleDetectionStrategy` để chọn những package mang annotation ấy. Cách này giúp module model phản ánh quy ước kiến trúc của tổ chức, trong khi Spring Modulith vẫn tiếp tục cung cấp kiểm tra dependency, API boundary và tài liệu hóa module.

## 1. Khi nào cần annotation riêng?

Giả sử ứng dụng bán hàng tổ chức code theo namespace:

```text
com.acme.shop
├── ShopApplication.java
├── business
│   ├── order
│   ├── inventory
│   └── customer
├── integration
│   ├── payment
│   └── shipping
└── support
    └── monitoring
```

Nhóm muốn các package `business.order`, `business.inventory`, `business.customer`, `integration.payment` và `integration.shipping` trở thành application module. Những package `business`, `integration` chỉ là namespace để nhóm code, còn `support.monitoring` không phải capability cần quản lý như module.

Có thể dùng `@ApplicationModule` trên từng package cùng chiến lược `explicitly-annotated`. Tuy nhiên, nếu tổ chức đã có một annotation thống nhất để đánh dấu bounded context hoặc capability, tạo thêm một marker riêng có thể làm kiến trúc nhất quán với các quy ước sẵn có.

Một annotation riêng phù hợp khi:

- Nhiều dự án trong tổ chức đã dùng cùng một marker cho module hoặc bounded context.
- Muốn phân biệt package module với package chỉ dùng để nhóm namespace.
- Muốn annotation mang thêm metadata riêng của tổ chức, ví dụ mã domain hoặc nhóm sở hữu.
- Quy tắc chọn module không thể diễn đạt gọn bằng package con trực tiếp hoặc marker tích hợp sẵn.

Nếu `@ApplicationModule` hoặc `@Module` của jMolecules đã đáp ứng nhu cầu, hãy ưu tiên chiến lược có sẵn. Custom annotation kéo theo một strategy và cấu hình cần được duy trì.

## 2. Định nghĩa annotation đánh dấu package

Trước tiên, tạo annotation riêng. Vì mục tiêu là đánh dấu package, dùng `ElementType.PACKAGE`:

```java
package com.acme.shop.architecture;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface BusinessModule {
}
```

Ba metadata quan trọng:

- `@Target(ElementType.PACKAGE)` giới hạn annotation vào package declaration. Nhờ vậy, không thể vô tình dùng nó trên class hoặc method.
- `@Retention(RetentionPolicy.RUNTIME)` giữ annotation trong metadata của package ở runtime, thuận tiện cho công cụ phân tích và reflection.
- `@Documented` giúp marker xuất hiện trong Javadoc của package.

Annotation này chỉ là marker do ứng dụng định nghĩa. Bản thân nó không làm Spring Modulith nhận package thành module. Việc chọn package sẽ do `ApplicationModuleDetectionStrategy` thực hiện ở bước tiếp theo.

## 3. Gắn marker vào `package-info.java`

Java không có cú pháp gắn annotation trực tiếp vào một thư mục. Package annotation được khai báo trong `package-info.java` của package tương ứng.

Ví dụ, đánh dấu module `order`:

`src/main/java/com/acme/shop/business/order/package-info.java`

```java
@com.acme.shop.architecture.BusinessModule
package com.acme.shop.business.order;
```

Đánh dấu module `inventory`:

`src/main/java/com/acme/shop/business/inventory/package-info.java`

```java
@com.acme.shop.architecture.BusinessModule
package com.acme.shop.business.inventory;
```

Và `customer`:

```java
@com.acme.shop.architecture.BusinessModule
package com.acme.shop.business.customer;
```

Các package `integration.payment` và `integration.shipping` cũng được đánh dấu theo cách tương tự. Không đánh dấu `com.acme.shop.business` hoặc `com.acme.shop.integration` nếu chúng chỉ là namespace và không phải module thực sự.

Một package không có marker vẫn là package Java bình thường. Nó có thể nằm bên trong module cha hoặc ngoài các module mà nhóm muốn quản lý. Vì vậy, marker cần được đặt tại đúng package root của capability.

## 4. Viết `ApplicationModuleDetectionStrategy`

`ApplicationModuleDetectionStrategy` có phương thức `getModuleBasePackages(JavaPackage rootPackage)`. Spring Modulith gọi phương thức này với package gốc được suy ra từ lớp Spring Boot application. Strategy cần trả về một `Stream<JavaPackage>` gồm những package sẽ trở thành root package của application module.

Ta có thể dùng `JavaPackage.getSubPackagesAnnotatedWith(…)` để tìm tất cả package con mang annotation riêng:

```java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getSubPackagesAnnotatedWith(BusinessModule.class);
    }
}
```

Phương thức `getSubPackagesAnnotatedWith(BusinessModule.class)` trả về các package con có khai báo marker `@BusinessModule`. Nó tìm trong các package nằm dưới root package, vì vậy những package lồng nhau cũng có thể được phát hiện nếu chúng được đánh dấu.

Strategy không cần tự duyệt từng class hoặc tự phân tích tên package bằng chuỗi. `JavaPackage` đã cung cấp abstraction cho package tree và API tìm package có annotation.

Hãy bảo đảm strategy luôn trả về một stream hợp lệ. Nếu không tìm thấy package nào, trả về stream rỗng; không trả về `null`:

```java
return Stream.empty();
```

Trong ví dụ chính, `rootPackage.getSubPackagesAnnotatedWith(BusinessModule.class)` tự trả về stream rỗng nếu không có package phù hợp.

## 5. Đăng ký strategy bằng cấu hình Spring Modulith

Khai báo class strategy trong `application.yml`:

```yaml
spring:
  modulith:
    detection-strategy: com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

Hoặc trong `application.properties`:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

Giá trị của property là fully qualified class name của implementation. Spring Modulith sử dụng strategy này khi xây dựng application module model.

Nếu custom strategy chỉ phục vụ kiểm tra kiến trúc hoặc sinh tài liệu trong test, có thể đặt class và cấu hình tương ứng trong test source set/test configuration. Nếu ứng dụng sử dụng các runtime component của Spring Modulith như `ApplicationModuleInitializer`, Actuator hoặc observability dựa trên module model, strategy cần có mặt trên runtime classpath; khi đó cần khai báo `spring-modulith-core` như dependency compile-time theo hướng dẫn của phiên bản đang dùng.

Trong Spring Modulith hiện hành, đăng ký strategy bằng property `spring.modulith.detection-strategy` là cách được tài liệu chính thức hướng dẫn. Các hướng dẫn cũ từng dùng `META-INF/spring.factories`; không nên sao chép cơ chế đăng ký cũ vào dự án mới nếu phiên bản hiện tại đã hỗ trợ property trên.

## 6. Module model sau khi áp dụng marker riêng

Với package tree đã đánh dấu, strategy sẽ chọn các module root sau:

```text
com.acme.shop
├── ShopApplication.java
├── architecture
│   ├── BusinessModule.java
│   └── BusinessModuleDetectionStrategy.java
├── business
│   ├── order                 @BusinessModule
│   ├── inventory             @BusinessModule
│   └── customer              @BusinessModule
├── integration
│   ├── payment               @BusinessModule
│   └── shipping              @BusinessModule
└── support
    └── monitoring            không có marker
```

Module model có năm module: `business.order`, `business.inventory`, `business.customer`, `integration.payment` và `integration.shipping`. Các package `business`, `integration`, `support` không được chọn chỉ vì chúng là package con trực tiếp của application root; strategy custom chỉ trả về package mang marker.

Tên logic của module được Spring Modulith suy ra từ vị trí package trong module arrangement. Marker `@BusinessModule` ở ví dụ trên chỉ quyết định package nào được chọn; nó không tự đặt tên module hoặc tạo `displayName`.

## 7. Kết hợp marker riêng với metadata `@ApplicationModule`

Marker riêng và `@ApplicationModule` có thể phục vụ hai vai trò khác nhau:

- `@BusinessModule` xác định package nào được chọn làm module root.
- `@ApplicationModule` cung cấp metadata Spring Modulith như `displayName`, `allowedDependencies` hoặc `type`.

Ví dụ, package `order` mang cả hai annotation:

```java
@com.acme.shop.architecture.BusinessModule
@org.springframework.modulith.ApplicationModule(
    displayName = "Order management",
    allowedDependencies = {
        "business.inventory",
        "business.customer"
    }
)
package com.acme.shop.business.order;
```

Custom strategy chỉ tìm `@BusinessModule`, nhưng Spring Modulith vẫn có thể đọc metadata `@ApplicationModule` của package được chọn. Như vậy, marker riêng không buộc nhóm phải tự xây dựng lại các thuộc tính kiến trúc đã có sẵn trong framework.

Hãy xác nhận tên module thực tế trong module model trước khi ghi `allowedDependencies`, đặc biệt khi package được đặt sâu dưới các namespace như `business.order`. Không giả định tên logical module luôn giống segment cuối nếu ứng dụng dùng cấu hình naming hoặc nguồn module tùy chỉnh.

## 8. Marker riêng không thay thế Named Interface

`@BusinessModule` chọn package nào là module root. Nó không tự công bố các package con của module thành API và cũng không xác định package nào là Named Interface.

Ví dụ, module `order` vẫn có thể có cấu trúc:

```text
business.order
├── OrderManagement.java       API package mặc định
├── events
│   ├── package-info.java      @NamedInterface("events")
│   └── OrderPlaced.java
└── internal
    └── OrderRepository.java  implementation nội bộ
```

Package `events` vẫn cần `@NamedInterface("events")` nếu module khác được phép sử dụng event ở đó. Package `internal` vẫn là implementation nội bộ. Việc chọn module theo marker riêng không làm thay đổi quy tắc đóng gói mặc định của Spring Modulith.

Tương tự, marker không tự cấu hình Spring component scanning, JPA entity scanning, repository scanning hoặc cấu hình component của ứng dụng. Nó chỉ tham gia phát hiện module trong module model. Nếu package module nằm ngoài phạm vi component scan của Spring Boot, nhóm vẫn phải xử lý cấu hình scan riêng.

## 9. Kiểm tra module được phát hiện

Sau khi đăng ký strategy, tạo module model và in các module để xác nhận:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void printsDetectedModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Kiểm tra output để xác nhận:

- Mọi package mang `@BusinessModule` đều trở thành module root.
- Package không có marker không bị chọn nhầm thành module.
- Nested package được đánh dấu có xuất hiện như nested module theo ý định hay không.
- `@ApplicationModule` metadata như `displayName` và `allowedDependencies` được áp dụng đúng.
- Dependency và package boundary tuân thủ các quy tắc đã khai báo.

`verify()` kiểm tra cấu trúc của module model đã phát hiện. Nó không biết danh sách module mà nhóm dự định có. Vì vậy, nên bổ sung một completeness test so sánh tập module root mong đợi với module thực tế:

```java
package com.acme.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ExpectedModulesTests {

    @Test
    void detectsAllBusinessModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        Set<String> expected = Set.of(
                "com.acme.shop.business.order",
                "com.acme.shop.business.inventory",
                "com.acme.shop.business.customer",
                "com.acme.shop.integration.payment",
                "com.acme.shop.integration.shipping"
        );

        Set<String> actual = modules.stream()
                .map(module -> module.getBasePackage().getName())
                .collect(Collectors.toSet());

        assertEquals(expected, actual);
    }
}
```

Test này phát hiện cả package bị quên marker lẫn package bị đánh dấu thừa. Kết hợp completeness test với `verify()` giúp bảo vệ hai yêu cầu riêng: phát hiện đúng danh sách module và kiểm tra dependency/boundary của các module đó.

## 10. Giới hạn và lựa chọn thay thế

Custom annotation đem lại tính linh hoạt nhưng cũng tạo thêm một quy ước mà nhóm phải duy trì. Trước khi áp dụng rộng, hãy cân nhắc các lựa chọn sau:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Module nằm ở package con trực tiếp của application root | Detection mặc định `direct-sub-packages` |
| Muốn đánh dấu module bằng `@ApplicationModule` hoặc jMolecules `@Module` | `explicitly-annotated` |
| Muốn chọn package bằng annotation riêng của tổ chức | Custom `ApplicationModuleDetectionStrategy` và marker annotation |
| Muốn điều chỉnh cách nhận diện Named Interface theo quy ước riêng | Override `detectNamedInterfaces(…)` trong strategy |
| Muốn đóng góp module từ package root khác hoặc nguồn độc lập | Xem `ApplicationModuleSourceFactory` và `@Modulithic(additionalPackages = …)` |

Nếu marker riêng chỉ khác tên nhưng không mang lại quy tắc hoặc metadata có giá trị, dùng `@ApplicationModule` có sẵn sẽ đơn giản hơn. Custom strategy nên tập trung vào một quy tắc chọn module dễ hiểu, ổn định và có test bảo vệ.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có module nào được phát hiện | Marker chưa được gắn hoặc strategy không tìm đúng annotation | Kiểm tra `package-info.java`, `@Target(PACKAGE)` và class marker được truyền vào `getSubPackagesAnnotatedWith()` |
| Annotation có trong source nhưng không được tìm thấy | `package-info.java` chưa được biên dịch hoặc retention/metadata không phù hợp | Kiểm tra compiled package metadata và dùng retention phù hợp như `RUNTIME` |
| Package namespace bị chọn nhầm | Strategy dùng package con trực tiếp thay vì lọc marker | Trả về đúng stream package được đánh dấu |
| Module bị thiếu trong test nhưng runtime có | Test không nạp property strategy hoặc dùng classpath khác | Đồng bộ `spring.modulith.detection-strategy` và source set |
| `@ApplicationModule` metadata không xuất hiện | Marker custom chỉ chọn package nhưng package metadata chưa được khai báo đúng | Đặt `@ApplicationModule` trong đúng `package-info.java` hoặc metadata type theo quy ước hỗ trợ |
| Consumer không được phép dùng event | Nhầm marker module với Named Interface | Công bố package event bằng `@NamedInterface` và khai báo dependency phù hợp |
| Component không được Spring tạo bean | Nhầm module detection với component scanning | Kiểm tra riêng base package của Spring Boot component scan |

## 12. Ghi nhớ

Để chọn application module theo annotation riêng, hãy tạo marker annotation ở cấp package, gắn marker vào `package-info.java` của từng module và triển khai `ApplicationModuleDetectionStrategy` để trả về các package được đánh dấu. `JavaPackage.getSubPackagesAnnotatedWith()` giúp tìm các package đó mà không cần tự duyệt tên hoặc class.

Đăng ký strategy bằng `spring.modulith.detection-strategy` trỏ đến fully qualified class name. Custom marker chỉ quyết định package nào trở thành module root; `@ApplicationModule` vẫn có thể cung cấp metadata, `@NamedInterface` vẫn công bố API ở package con, còn Spring component scanning vẫn là cơ chế riêng. Cuối cùng, kiểm tra module model và duy trì test so sánh module root mong đợi để bảo đảm không thiếu hoặc thừa module khi quy ước package thay đổi.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith API — `JavaPackage`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
