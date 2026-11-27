# ApplicationModule đại diện cho một module cụ thể

Trong Spring Modulith, `ApplicationModule` là đối tượng mô hình đại diện cho một application module cụ thể trong ứng dụng Spring Boot. Nó mô tả một vùng package có trách nhiệm nghiệp vụ, cùng các thông tin cần thiết để hiểu ranh giới và hợp đồng của vùng đó. Khi cần làm việc với mô-đun `orders`, `inventory` hoặc `customers`, ta lấy `ApplicationModule` tương ứng từ mô hình tổng thể `ApplicationModules`.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, việc hiểu `ApplicationModule` giúp ta đọc cấu trúc mô-đun, xác định API công khai, xem package nền và kiểm chứng các phụ thuộc trong một modular monolith. Đối tượng này là mô tả kiến trúc được Spring Modulith khám phá từ package và metadata của ứng dụng; nó không phải một Spring bean hay một service nghiệp vụ được tạo để xử lý request.

## 1. ApplicationModule là gì?

Một ứng dụng Spring Boot có thể được tổ chức thành nhiều mô-đun nghiệp vụ. Ví dụ, một hệ thống bán hàng có thể gồm:

- `orders`: quản lý đơn hàng và các quy tắc liên quan đến vòng đời đơn.
- `inventory`: quản lý tồn kho và thao tác giữ hoặc giải phóng hàng.
- `customers`: quản lý thông tin và chính sách khách hàng.

Với cấu trúc package:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
├── inventory
│   ├── InventoryManagement.java
│   └── internal
└── customers
    ├── CustomerManagement.java
    └── internal
```

Spring Modulith khám phá các package mô-đun bên dưới package ứng dụng. Mỗi mô-đun được biểu diễn trong mô hình bằng một `ApplicationModule`. Đối tượng này cung cấp một điểm truy cập thống nhất để truy vấn thông tin về mô-đun thay vì phải tự phân tích tên package hoặc quét classpath bằng tay.

`ApplicationModule` có thể được hiểu là một mô tả có cấu trúc của ranh giới mô-đun. Tùy cấu hình và phiên bản Spring Modulith, mô hình có thể cung cấp thông tin như tên mô-đun, package nền, named interfaces và các metadata kiến trúc liên quan. Những thông tin này hỗ trợ việc quan sát và kiểm chứng kiến trúc.

## 2. Phân biệt ApplicationModules và ApplicationModule

Hai kiểu này có quan hệ tập hợp và phần tử:

| Kiểu | Ý nghĩa | Cách dùng thường gặp |
|---|---|---|
| `ApplicationModules` | Mô hình tổng thể chứa các application module được khám phá trong ứng dụng | Tạo mô hình, duyệt toàn bộ mô-đun, tìm mô-đun theo tên và kiểm chứng cấu trúc |
| `ApplicationModule` | Mô hình đại diện cho một mô-đun cụ thể | Đọc tên và metadata của mô-đun, xem API công khai và hiểu ranh giới package |

Có thể hình dung `ApplicationModules` như danh mục mô-đun của ứng dụng, còn `ApplicationModule` là một mục cụ thể trong danh mục đó. Khi cần xem cấu trúc toàn hệ thống, làm việc với `ApplicationModules`; khi cần xem riêng một năng lực nghiệp vụ, lấy `ApplicationModule` tương ứng.

Lưu ý có hai kiểu tên gần giống nhau trong Spring Modulith:

| Kiểu | Package | Vai trò |
|---|---|---|
| `@ApplicationModule` | `org.springframework.modulith` | Annotation dùng để khai báo metadata hoặc quy tắc cho package mô-đun |
| `ApplicationModule` | `org.springframework.modulith.core` | Đối tượng mô hình đại diện cho mô-đun đã được khám phá |

Annotation nằm trong source code để khai báo ý định kiến trúc. Đối tượng trong package `core` là kết quả mô hình hóa mà chương trình có thể truy vấn. Không nên nhầm annotation với đối tượng mô hình chỉ vì chúng có tên giống nhau.

## 3. Tạo mô hình và lấy một ApplicationModule

Trước tiên, tạo `ApplicationModules` từ lớp ứng dụng Spring Boot:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
```

Sau đó, tìm mô-đun theo logical name:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders")
    .orElseThrow(() -> new IllegalStateException("Module orders not found"));
```

`getModuleByName()` trả về `Optional<ApplicationModule>`, vì tên được yêu cầu có thể không tồn tại trong mô hình. Dùng `orElseThrow()` khi sự vắng mặt của mô-đun là lỗi cấu hình hoặc lỗi giả định của chương trình. Nếu việc tìm thấy mô-đun là tùy chọn, có thể dùng `ifPresent()` hoặc xử lý `Optional` theo nhu cầu.

Tên truyền vào là logical name của mô-đun theo mô hình Spring Modulith. Với cấu trúc package mặc định, tên này thường tương ứng với tên package con trực tiếp bên dưới package ứng dụng, ví dụ `orders` trong `com.acme.shop.orders`.

## 4. Đọc thông tin nhận diện của mô-đun

Sau khi lấy được `ApplicationModule`, có thể đọc tên và package nền của nó:

```java
System.out.println("Module name: " + orders.getName());
System.out.println("Base package: " + orders.getBasePackage().getName());
```

`getName()` trả về tên mô-đun. `getBasePackage()` cung cấp package nền mà mô-đun đại diện; đối tượng package cung cấp tên đầy đủ qua `getName()`. Hai thông tin này giúp phân biệt logical name dùng trong quy tắc kiến trúc với tên package Java đầy đủ dùng trong source code.

Ví dụ, với `orders`:

| Thuộc tính | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Module name | `orders` | Tên mô-đun trong mô hình |
| Base package | `com.acme.shop.orders` | Package nền trong mã nguồn |
| Root application package | `com.acme.shop` | Package ứng dụng dùng làm điểm khám phá |

Không nên ghép tên package bằng cách tự nối chuỗi nếu có thể đọc trực tiếp từ mô hình. Việc lấy dữ liệu từ `ApplicationModule` giúp báo cáo phản ánh cấu trúc mà Spring Modulith thực sự nhận diện.

## 5. Đọc API công khai của ApplicationModule

Một mô-đun có thể công khai API mặc định ở package gốc và các named interface được khai báo rõ ràng. `ApplicationModule` cung cấp `getNamedInterfaces()` để đọc tập hợp các bề mặt API đó:

```java
import org.springframework.modulith.core.NamedInterface;

orders.getNamedInterfaces().stream()
    .forEach(namedInterface -> {
        System.out.println("Interface: " + namedInterface.getName());

        namedInterface.forEach(type ->
            System.out.println("  - " + type.getName())
        );
    });
```

Tập hợp này bao gồm unnamed interface đại diện cho API mặc định và những named interface được công khai tường minh. Mỗi `NamedInterface` mô tả một bề mặt công khai cùng các kiểu thành viên của nó.

Ví dụ, mô-đun `inventory` có thể công khai `InventoryOperations` trong named interface `api`. Mô-đun `orders` có thể được phép phụ thuộc vào `inventory::api`, trong khi các lớp repository trong package `internal` vẫn là chi tiết triển khai. Việc đọc named interfaces giúp ta hiểu một mô-đun cho phép bên ngoài sử dụng những kiểu nào.

## 6. ApplicationModule và phụ thuộc giữa các mô-đun

Một mô-đun không tồn tại tách biệt khỏi phần còn lại của ứng dụng. Nó có thể sử dụng API công khai của mô-đun khác theo những quy tắc phụ thuộc được mô hình hóa. Ví dụ, `orders` cần gọi thao tác giữ hàng từ `inventory`:

```text
orders  ───────>  inventory::api
```

Trong `orders/package-info.java`, có thể giới hạn phụ thuộc:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory :: api"
)
package com.acme.shop.orders;
```

Ở đây `inventory` là logical name của mô-đun đích và `api` là named interface mà nó công khai. `ApplicationModule` đại diện cho một phía của quan hệ này trong mô hình; `ApplicationModules` cung cấp ngữ cảnh toàn ứng dụng để Spring Modulith kiểm tra các quan hệ giữa những mô-đun.

Khi thiết kế phụ thuộc, hãy giữ chiều phụ thuộc dễ hiểu và tránh để các mô-đun tạo thành chu trình. Một mô-đun nên truy cập hợp đồng công khai của mô-đun khác thay vì gọi trực tiếp các lớp triển khai nội bộ.

## 7. Dùng ApplicationModule trong báo cáo và kiểm thử

Có thể dùng `ApplicationModule` để tạo báo cáo ngắn về các mô-đun được khám phá:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .sorted((left, right) -> left.getName().compareTo(right.getName()))
    .forEach(module -> {
        System.out.println("Module: " + module.getName());
        System.out.println("Package: " + module.getBasePackage().getName());
        System.out.println("Named interfaces:");

        module.getNamedInterfaces().stream()
            .forEach(namedInterface ->
                System.out.println("  - " + namedInterface.getName())
            );
    });
```

Đầu ra này hữu ích khi muốn xem nhanh ranh giới package và các bề mặt API. Nếu cần lưu báo cáo, có thể ánh xạ dữ liệu sang một DTO hoặc cấu trúc đơn giản thay vì để lớp trình bày phụ thuộc trực tiếp vào các đối tượng mô hình của Spring Modulith.

Một bài kiểm thử có thể xác nhận mô-đun nghiệp vụ quan trọng đã được khám phá:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleTests {

    @Test
    void discoversOrdersModule() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
            .orElseThrow();

        assertThat(orders.getName()).isEqualTo("orders");
        assertThat(orders.getBasePackage().getName())
            .isEqualTo("com.acme.shop.orders");
    }
}
```

Kiểm thử trên bảo vệ giả định về sự tồn tại và định danh package của mô-đun. Để kiểm tra cả quy tắc phụ thuộc và các ràng buộc kiến trúc, cần gọi `verify()`:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Việc đọc metadata và việc xác minh kiến trúc là hai nhiệm vụ bổ trợ nhau: metadata giúp quan sát mô hình, còn `verify()` kiểm tra mô hình có vi phạm các quy tắc Spring Modulith áp dụng hay không.

## 8. Phân biệt ApplicationModule với các khái niệm khác

Tên gọi “module” xuất hiện ở nhiều tầng trong hệ sinh thái Java. Cần phân biệt rõ:

| Khái niệm | Phạm vi | Đặc điểm |
|---|---|---|
| `ApplicationModule` của Spring Modulith | Bên trong một ứng dụng Spring Boot | Mô tả ranh giới package và hợp đồng giữa các vùng nghiệp vụ |
| Java Platform Module System (JPMS) | Module Java ở cấp nền tảng | Khai báo module bằng `module-info.java`, kiểm soát `requires` và `exports` |
| Maven/Gradle module | Đơn vị build | Có thể được build và quản lý dependency như một project con |
| Microservice | Đơn vị triển khai và vận hành | Thường có tiến trình, triển khai và giao tiếp qua ranh giới mạng riêng |

`ApplicationModule` không mặc định tạo ra một JAR riêng, một module JPMS, một tiến trình độc lập hay một microservice. Các application module trong modular monolith thường cùng chạy trong một ứng dụng và cùng được triển khai như một đơn vị. Giá trị của chúng nằm ở ranh giới kiến trúc có thể quan sát và kiểm chứng.

## 9. Những nhầm lẫn thường gặp

- **Coi `ApplicationModule` là một Spring bean.** Đây là đối tượng mô hình kiến trúc được dùng để mô tả cấu trúc mô-đun, không phải service nghiệp vụ để inject vào controller.
- **Nhầm `ApplicationModule` với `ApplicationModules`.** Một kiểu đại diện cho mô-đun cụ thể; kiểu còn lại đại diện cho tập hợp mô-đun của ứng dụng.
- **Nhầm annotation với model class.** `org.springframework.modulith.ApplicationModule` là annotation; `org.springframework.modulith.core.ApplicationModule` là kiểu mô hình.
- **Cho rằng một application module là một microservice.** Ranh giới package trong modular monolith không tự tạo ra ranh giới tiến trình hoặc triển khai.
- **Tự suy ra package và API từ tên mô-đun.** Hãy đọc thông tin từ đối tượng mô hình và named interfaces thay vì dựa vào quy ước đặt tên không được kiểm chứng.
- **Cho rằng lấy được ApplicationModule nghĩa là kiến trúc hợp lệ.** Đọc được mô hình chỉ xác nhận mô-đun đã được khám phá; cần `ApplicationModules.verify()` để kiểm tra các quy tắc kiến trúc.

## Kết luận

`ApplicationModule` là đại diện có cấu trúc cho một mô-đun cụ thể trong ứng dụng Spring Boot. Ta lấy nó từ `ApplicationModules`, dùng `getName()` và `getBasePackage()` để hiểu định danh và package nền, rồi đọc `getNamedInterfaces()` để biết các bề mặt API công khai. Khi kết hợp việc đọc metadata với quy tắc `allowedDependencies` và `ApplicationModules.verify()`, nhóm có thể quản lý ranh giới nghiệp vụ và phụ thuộc giữa các package một cách rõ ràng ngay trong modular monolith.
