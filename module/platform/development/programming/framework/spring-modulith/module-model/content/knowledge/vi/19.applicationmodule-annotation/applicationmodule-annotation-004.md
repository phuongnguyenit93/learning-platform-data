# systemName ở cấp ứng dụng

Một ứng dụng Spring Boot có thể chứa nhiều application module như `inventory`, `order` và `payment`. Khi Spring Modulith tạo tài liệu mô tả các module, người đọc cần biết những module đó thuộc về hệ thống nào. Thuộc tính `systemName` của `@Modulithic` cung cấp tên logic của toàn ứng dụng để sử dụng trong tài liệu được sinh ra.

`systemName` được khai báo ở cấp lớp ứng dụng Spring Boot, không phải trên `package-info.java` của từng module. Nó mô tả danh tính của ứng dụng trong tài liệu kiến trúc; nó không đổi tên package, tên application module hoặc tên tiến trình đang chạy.

## 1. Vì sao cần tên hệ thống ở cấp ứng dụng?

Spring Modulith xây dựng mô hình từ cấu trúc package và các khai báo module. Ví dụ, một ứng dụng bán hàng có thể gồm:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
├── order
├── payment
└── shipping
~~~

Các module này cùng thuộc một ứng dụng. Khi tài liệu kiến trúc được tạo, một tên hệ thống dễ hiểu giúp người đọc nhận ra phạm vi tài liệu, nhất là khi tổ chức có nhiều ứng dụng hoặc nhiều modular monolith.

Tên package ứng dụng như `com.acme.shop` hữu ích cho Java và cho việc nhận diện package gốc. Tuy nhiên, package không phải lúc nào cũng là tên thân thiện mà nhóm muốn hiển thị trong tài liệu. `systemName` cho phép cung cấp tên logic riêng, ví dụ `Shop Platform`.

Thuộc tính này có ý nghĩa mô tả. Nó không thay thế cấu hình vận hành hoặc định danh kỹ thuật mà các thành phần khác của hệ thống sử dụng.

## 2. Khai báo `systemName` bằng `@Modulithic`

Đặt `@Modulithic` trên lớp ứng dụng chính, cùng với `@SpringBootApplication`:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(systemName = "Shop Platform")
@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này:

- `ShopApplication` là lớp ứng dụng gốc mà Spring Modulith dùng để xây dựng mô hình.
- `@Modulithic` khai báo các tùy chỉnh ở cấp toàn ứng dụng.
- `systemName = "Shop Platform"` cung cấp tên logic dùng trong tài liệu được sinh ra.
- `@SpringBootApplication` tiếp tục đảm nhiệm cấu hình và khởi chạy ứng dụng Spring Boot.

`@Modulithic` có thể được sử dụng cùng `@SpringBootApplication`; hai annotation có trách nhiệm khác nhau. Một annotation mô tả cách Spring Modulith tổ chức ứng dụng, annotation còn lại cấu hình ứng dụng Spring Boot.

Nếu không khai báo `systemName`, giá trị mặc định của thuộc tính là chuỗi rỗng. Vì vậy, nếu tài liệu cần một tên hệ thống rõ ràng, hãy khai báo một giá trị có ý nghĩa ngay trên lớp ứng dụng.

## 3. `systemName` thuộc về toàn ứng dụng

Giả sử `ShopApplication` là điểm bắt đầu của ứng dụng có bốn module:

~~~text
Shop Platform
│
├── inventory
├── order
├── payment
└── shipping
~~~

`systemName` được đặt một lần ở lớp ứng dụng. Các module vẫn giữ tên và package riêng:

| Thành phần | Ví dụ | Phạm vi |
| --- | --- | --- |
| System name | `Shop Platform` | Toàn ứng dụng |
| Application module | `inventory` | Một module trong ứng dụng |
| Base package | `com.acme.shop.inventory` | Package gốc của module |
| Module display name | Tên hiển thị riêng của module nếu được cấu hình | Một module |

Không cần lặp lại cùng một `systemName` trên từng module. `@ApplicationModule` dùng để mô tả một application module, trong khi `@Modulithic` cấu hình mô hình Modulith ở cấp ứng dụng.

Ví dụ, khai báo module vẫn có thể nằm trong `package-info.java` của package `inventory`:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory"
)
package com.acme.shop.inventory;
~~~

Tên hệ thống là `Shop Platform`; tên hiển thị của module là `Inventory`. Hai giá trị trả lời hai câu hỏi khác nhau: tài liệu đang nói về ứng dụng nào và phần chức năng cụ thể nào đang được mô tả.

## 4. `systemName` dùng cho tài liệu được sinh ra

Spring Modulith hỗ trợ tạo tài liệu từ mô hình application module. Có thể khởi tạo mô hình bằng `ApplicationModules` và dùng `Documenter` để tạo module canvas:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentation {

    void generate() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        new Documenter(modules).writeModuleCanvases();
    }
}
~~~

`ApplicationModules.of(ShopApplication.class)` đọc cấu hình Modulith trên lớp ứng dụng và xây dựng mô hình module. Tên hệ thống được khai báo bằng `systemName` là thông tin logic để tài liệu được sinh ra có thể nhận diện ứng dụng.

API `ApplicationModules` cũng cung cấp `getSystemName()` để đọc tên hệ thống nếu đã khai báo:

~~~java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.getSystemName().ifPresent(name ->
        System.out.println("System: " + name)
);
~~~

Giá trị trả về là `Optional<String>` vì `systemName` có thể chưa được khai báo. Có thể dùng cách đọc này trong công cụ nội bộ hoặc bước tạo tài liệu tùy chỉnh khi cần biết tên hệ thống từ mô hình Modulith.

`systemName` là metadata mô tả. Nó không tự tạo module, không thay đổi dependency graph và không thay thế bước kiểm chứng kiến trúc bằng `ApplicationModules.verify()`.

## 5. Phân biệt `systemName` với các tên cấu hình khác

Một ứng dụng Spring Boot có thể có nhiều giá trị tên. Chúng có mục đích và nơi cấu hình khác nhau:

| Giá trị | Ví dụ | Mục đích |
| --- | --- | --- |
| `@Modulithic(systemName = ...)` | `Shop Platform` | Tên logic của ứng dụng trong tài liệu Spring Modulith |
| `spring.application.name` | `shop-service` | Tên ứng dụng trong hệ sinh thái cấu hình và tích hợp Spring |
| Package gốc | `com.acme.shop` | Phạm vi package để phát hiện module mặc định |
| Module name | `inventory` | Định danh một application module trong mô hình |
| `@ApplicationModule(displayName = ...)` | `Inventory` | Tên hiển thị của một module |
| Artifact hoặc project name | `shop-app` | Định danh build artifact hoặc project |

Các giá trị có thể giống nhau nếu nhóm muốn, nhưng chúng không tự động đồng nghĩa và không tự đồng bộ với nhau. Thay đổi `systemName` không đổi `spring.application.name`, artifact name hoặc tên package.

Ví dụ, cấu hình sau vẫn có thể dùng tên kỹ thuật cho môi trường vận hành và tên thân thiện cho tài liệu:

~~~yaml
spring:
  application:
    name: shop-service
~~~

~~~java
@Modulithic(systemName = "Shop Platform")
@SpringBootApplication
public class ShopApplication {
    // ...
}
~~~

Khi đó, `shop-service` tiếp tục là tên ứng dụng trong cấu hình Spring, còn `Shop Platform` là tên logic Spring Modulith dùng cho tài liệu.

## 6. Chọn một `systemName` có ý nghĩa

Vì tên này phục vụ việc đọc tài liệu, hãy chọn tên mà kiến trúc sư, lập trình viên và người vận hành đều nhận ra.

Một số nguyên tắc hữu ích:

- Dùng tên sản phẩm hoặc hệ thống mà tổ chức đang sử dụng nhất quán.
- Tránh dùng tên package dài nếu nó khó đọc với người không viết Java.
- Tránh đưa phiên bản triển khai như `v2.7.4` vào tên hệ thống nếu phiên bản không phải một phần của danh tính hệ thống.
- Giữ tên ổn định giữa các môi trường nếu các môi trường là những lần triển khai của cùng một hệ thống.
- Nếu hai ứng dụng độc lập có tài liệu riêng, mỗi ứng dụng nên có tên logic riêng để tránh nhầm lẫn.

Ví dụ:

| Tên | Nhận xét |
| --- | --- |
| `Shop Platform` | Dễ đọc, phù hợp tài liệu sản phẩm |
| `Customer Portal` | Phù hợp nếu ứng dụng đại diện cho cổng khách hàng |
| `com.acme.shop` | Chính xác về package nhưng ít thân thiện hơn trong tài liệu |
| `shop-prod-01` | Mang chi tiết môi trường, thường không phù hợp làm tên logic ổn định |

Tên cụ thể phụ thuộc cách tổ chức gọi hệ thống. Điều quan trọng là dùng một tên thống nhất và không nhầm nó với module name.

## 7. Các tùy chỉnh cấp ứng dụng khác trong `@Modulithic`

`systemName` là một trong các tùy chỉnh mà `@Modulithic` cung cấp. Những thuộc tính khác có mục đích riêng:

| Thuộc tính | Mục đích |
| --- | --- |
| `systemName` | Tên logic của ứng dụng dùng trong tài liệu |
| `sharedModules` | Khai báo module được xem là shared và luôn được đưa vào bootstrap của kiểm thử tích hợp module |
| `additionalPackages` | Bổ sung các package gốc để Spring Modulith phát hiện application module |
| `useFullyQualifiedModuleNames` | Chọn dùng tên module đầy đủ theo package thay cho tên module cục bộ mặc định |

Ví dụ, nếu ứng dụng có các module dùng chung cần luôn được đưa vào bootstrap của module integration tests, có thể khai báo:

~~~java
@Modulithic(
    systemName = "Shop Platform",
    sharedModules = { "shared", "configuration" }
)
@SpringBootApplication
public class ShopApplication {
    // ...
}
~~~

Trong ví dụ, `systemName` vẫn chỉ là tên hệ thống cho tài liệu. `sharedModules` điều khiển một khía cạnh khác của việc chạy kiểm thử module. Không nên thêm tên module vào `sharedModules` chỉ vì muốn nó xuất hiện trong tài liệu.

Nếu ứng dụng có module nằm dưới nhiều package gốc, `additionalPackages` có thể bổ sung các package gốc đó để phát hiện module:

~~~java
@Modulithic(
    systemName = "Shop Platform",
    additionalPackages = {
        "com.acme.shop",
        "com.acme.fulfillment"
    }
)
@SpringBootApplication
public class ShopApplication {
    // ...
}
~~~

Trong trường hợp này, `systemName` vẫn mô tả ứng dụng Modulith tổng thể. Các package bổ sung ảnh hưởng đến phạm vi phát hiện module, không tạo ra một `systemName` riêng cho từng package gốc.

## 8. Kiểm tra cấu hình `systemName`

Có thể kiểm tra cấu hình theo hai lớp:

**Kiểm tra metadata trong mô hình Modulith**

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithConfigurationTests {

    @Test
    void exposesConfiguredSystemName() {
        var modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getSystemName())
                .contains("Shop Platform");
    }
}
~~~

Kiểm tra này xác nhận mô hình được tạo từ lớp ứng dụng có chứa system name mong đợi. Nếu tên không được khai báo, `getSystemName()` trả về `Optional.empty()`.

**Kiểm tra cấu trúc module**

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc kiến trúc của module, chẳng hạn dependency và ranh giới package. Nó không thay thế assertion về nội dung `systemName`; hai kiểm tra có mục đích khác nhau.

## 9. Những nhầm lẫn thường gặp

**Đặt `systemName` trên `@ApplicationModule`.** `systemName` là tùy chỉnh cấp ứng dụng của `@Modulithic`. `@ApplicationModule` mô tả một module riêng lẻ.

**Đặt annotation trên `package-info.java`.** `@Modulithic` được đặt trên lớp ứng dụng Spring Boot. `package-info.java` là nơi thường dùng để khai báo metadata của từng application module bằng `@ApplicationModule`.

**Cho rằng `systemName` đổi tên module.** Tên module vẫn được xác định từ cấu trúc và metadata module. `systemName` mô tả toàn ứng dụng trong tài liệu.

**Cho rằng `systemName` đổi `spring.application.name`.** Hai thuộc tính có mục đích riêng. Thay đổi tên hệ thống cho tài liệu không tự thay đổi cấu hình Spring Boot.

**Cho rằng `systemName` ảnh hưởng đến phát hiện module hoặc dependency.** Nó là thông tin mô tả được dùng trong tài liệu; việc phát hiện module và kiểm tra dependency được điều khiển bởi cấu trúc package cùng các tùy chỉnh tương ứng.

**Cho rằng khai báo `systemName` thay thế kiểm thử kiến trúc.** Tên hệ thống không xác nhận module được phân chia đúng. Vẫn cần dùng `ApplicationModules.verify()` để kiểm tra ranh giới và dependency.

## 10. Checklist khai báo `systemName`

- [ ] Xác định tên logic mà nhóm muốn hiển thị trong tài liệu kiến trúc.
- [ ] Đặt `@Modulithic` trên lớp ứng dụng Spring Boot.
- [ ] Khai báo `systemName` ở cấp ứng dụng, không đặt trên package module.
- [ ] Giữ tên module và tên hiển thị của module ở phạm vi cấu hình module.
- [ ] Phân biệt `systemName` với `spring.application.name`, package name và artifact name.
- [ ] Giữ tên ổn định giữa các môi trường nếu chúng thuộc cùng một hệ thống.
- [ ] Tạo Application Module Canvas để kiểm tra tài liệu được sinh ra.
- [ ] Có thể kiểm tra metadata bằng `ApplicationModules.getSystemName()`.
- [ ] Tiếp tục kiểm tra cấu trúc bằng `ApplicationModules.verify()`.

## 11. Kết luận

`systemName` là tên logic của toàn ứng dụng mà Spring Modulith dùng trong tài liệu được sinh ra. Hãy khai báo nó bằng `@Modulithic(systemName = "...")` trên lớp ứng dụng Spring Boot. Giá trị này giúp tài liệu nhận diện hệ thống, trong khi tên package, tên module, `spring.application.name` và tên artifact tiếp tục giữ vai trò riêng.

Khi cần xác minh tên đã được đưa vào mô hình, dùng `ApplicationModules.getSystemName()`. Khi cần kiểm tra ranh giới và dependency của các module, dùng `ApplicationModules.verify()`. Hai bước này giúp phân biệt metadata mô tả ứng dụng với các quy tắc kiến trúc cần được kiểm chứng.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `Modulithic` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — `Modulith` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulith.html)
