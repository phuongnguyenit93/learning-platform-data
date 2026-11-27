# Module rỗng và package chỉ chứa technical class

Spring Modulith phát hiện application module chủ yếu dựa trên cấu trúc package của ứng dụng. Với chiến lược mặc định, mỗi package con trực tiếp của package chứa lớp `@SpringBootApplication` được xem là một package mô-đun. Framework không tự hiểu rằng `orders` là năng lực nghiệp vụ còn `config`, `mapper` hay `persistence` chỉ là package kỹ thuật. Vì vậy, một package cấp cao chỉ chứa class cấu hình hoặc helper vẫn có thể bị nhận diện thành một module.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, điều quan trọng là đặt ranh giới package phù hợp với trách nhiệm nghiệp vụ, sau đó dùng `ApplicationModules` để kiểm tra mô hình được phát hiện. Một thư mục rỗng trong IDE không tự trở thành module; Spring Modulith làm việc với cấu trúc package và các kiểu được tìm thấy trên classpath. Ngược lại, chỉ một class kỹ thuật ở package con trực tiếp cũng đủ khiến package đó trở thành ứng viên module theo chiến lược mặc định.

## 1. Quy tắc phát hiện mặc định

Package chứa lớp ứng dụng chính là root package. Ví dụ:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
```

Với cấu trúc trên, Spring Modulith mặc định xem các package con trực tiếp của `com.acme.shop` là application module:

```text
com.acme.shop                         // root package
├── ShopApplication.java
├── orders                            // module
├── inventory                         // module
└── customers                         // module
```

Đây là quy tắc cấu trúc, không phải phân tích ý nghĩa tên package. Nếu package `orders` chứa nghiệp vụ đơn hàng thì nó là một module hợp lý. Nếu package `config` chỉ chứa cấu hình Spring, nó vẫn nằm ở cùng cấp và có thể bị phát hiện như một module khác.

Các package sâu hơn thuộc về module cha theo mặc định:

```text
com.acme.shop
├── ShopApplication.java
└── orders                            // module orders
    ├── OrderManagement.java
    ├── application
    ├── domain
    ├── persistence
    ├── config
    └── internal
```

`orders.persistence`, `orders.config` và `orders.internal` là các package bên trong module `orders`; chúng không tự trở thành module ngang hàng. Từ Spring Modulith 1.3, package con có thể trở thành nested application module nếu được khai báo tường minh bằng `@ApplicationModule`. Nếu không có khai báo nested module, các package con vẫn thuộc module cha.

## 2. Thư mục rỗng khác với package có metadata

Một thư mục `reports/` mới tạo trong IDE nhưng không chứa source type, `package-info.java` hoặc metadata được biên dịch không tạo ra một Java package hữu hình trong mô hình classpath. Spring Modulith không đọc danh sách thư mục trống trên ổ đĩa để tự sinh application module.

Khi package có source hoặc metadata được biên dịch, tình hình khác đi:

- Một class trong `com.acme.shop.reports` làm package trở thành package có type trên classpath. Theo chiến lược mặc định, package con trực tiếp này được xem là một module, kể cả class duy nhất chỉ là helper kỹ thuật.
- `package-info.java` có thể mang annotation và được biên dịch thành `package-info.class`. `@ApplicationModule` khai báo metadata của module; `@NamedInterface` đánh dấu một package là API được công khai của module đã tồn tại, không phải annotation thay thế `@ApplicationModule` trong chiến lược phát hiện `explicitly-annotated`.
- Với chiến lược `explicitly-annotated`, package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` có thể được chọn làm module base package, kể cả khi package không chứa service hay domain class thông thường.

Do đó, cần phân biệt một package không có gì trên classpath với một module có metadata nhưng chưa có nghiệp vụ. Trường hợp thứ nhất không tạo ra module chỉ vì thư mục tồn tại. Trường hợp thứ hai có thể được phát hiện vì package đã được thể hiện bằng class hoặc metadata.

## 3. Package chỉ chứa technical class vẫn có thể thành module

Giả sử ứng dụng có cấu trúc:

```text
com.acme.shop
├── ShopApplication.java
├── orders
│   └── OrderService.java
├── inventory
│   └── InventoryService.java
├── config
│   └── WebConfiguration.java
├── mapper
│   └── OrderMapper.java
└── persistence
    └── JpaConfiguration.java
```

Theo chiến lược mặc định, `config`, `mapper` và `persistence` cũng là các module vì chúng là package con trực tiếp của root package. Spring Modulith không yêu cầu package phải chứa domain service, aggregate hoặc Spring bean mới được nhận diện. Chỉ dựa vào cấu trúc package, những package kỹ thuật này đã là các module ứng viên.

Điều đó có thể dẫn đến mô hình kiến trúc không phản ánh nghiệp vụ:

- Báo cáo module hiển thị `config`, `mapper` và `persistence` như các đơn vị chức năng ngang hàng với `orders` và `inventory`.
- Code nghiệp vụ có thể bị xem là phụ thuộc vào các module kỹ thuật riêng, tạo thêm quan hệ cần quản lý.
- Quy tắc `allowedDependencies` có thể phải khai báo các dependency kỹ thuật vốn chỉ là chi tiết bên trong một năng lực nghiệp vụ.
- Module integration test hoặc tài liệu kiến trúc có thể phản ánh các nhóm package kỹ thuật thay vì các năng lực nghiệp vụ.
- Việc thay đổi một mapper hoặc cấu hình persistence có thể tạo cảm giác như đang thay đổi một module độc lập, dù trách nhiệm thực tế thuộc về `orders` hoặc `inventory`.

Tên package không quyết định trách nhiệm kiến trúc. Vị trí của nó trong cây package mới là yếu tố quan trọng đối với chiến lược phát hiện mặc định.

## 4. Đưa technical class về bên trong module nghiệp vụ

Nếu `OrderMapper` chỉ phục vụ đơn hàng, hãy đặt nó trong module `orders`:

```text
com.acme.shop
├── ShopApplication.java
├── orders                            // module orders
│   ├── OrderManagement.java          // API mặc định
│   ├── application
│   │   └── PlaceOrderService.java
│   ├── persistence
│   │   └── OrderRepository.java
│   ├── mapper
│   │   └── OrderMapper.java
│   └── config
│       └── OrderConfiguration.java
└── inventory                         // module inventory
    ├── InventoryOperations.java
    └── internal
        └── InventoryRepository.java
```

Giờ đây, `orders.persistence`, `orders.mapper` và `orders.config` thuộc module `orders`. Chúng có thể phối hợp nội bộ theo thiết kế của module mà không tạo thêm các module cấp cao.

Quy tắc thực tế:

- Technical class phục vụ riêng một năng lực nghiệp vụ nên nằm trong module sở hữu năng lực đó.
- Repository, entity, mapper, configuration, exception và helper nội bộ nên ở package con phù hợp như `internal`, `persistence`, `mapping` hoặc `config` bên trong module.
- Chỉ tạo module `shared` hoặc `integration` khi nó thực sự có trách nhiệm, hợp đồng và vòng đời độc lập đủ rõ.
- Không gom mọi class kỹ thuật của toàn hệ thống vào một package cấp cao chỉ vì chúng cùng loại kỹ thuật; cách đó thường tách một năng lực nghiệp vụ ra khỏi các thành phần của nó.

## 5. Khi nào một technical module riêng là hợp lý?

Không phải mọi package kỹ thuật đều cần được gộp vào module nghiệp vụ. Một module kỹ thuật riêng có thể hợp lý nếu nó cung cấp một năng lực dùng chung có hợp đồng rõ và được nhiều module tiêu thụ.

Ví dụ, `identity` có thể là một module nghiệp vụ/kỹ thuật độc lập nếu nó sở hữu xác thực, phân quyền và chính sách danh tính. `messaging` có thể là module riêng nếu nó quản lý việc gửi thông báo với API và quy tắc retry riêng. `shared-kernel` có thể tồn tại nếu nhóm xác định rõ những kiểu dùng chung ổn định và giới hạn phạm vi của chúng.

Hãy tự hỏi:

1. Package này có trách nhiệm hoặc năng lực được mô tả độc lập không?
2. Nó có API mà consumer thực sự cần không?
3. Nó có sở hữu quy tắc, dữ liệu hoặc vòng đời thay đổi riêng không?
4. Các consumer có thể phụ thuộc vào hợp đồng ổn định thay vì vào helper triển khai không?
5. Việc giữ nó thành module riêng có làm ranh giới rõ hơn không?

Nếu câu trả lời chủ yếu là “đây là nơi chứa mapper/config/repository”, package đó nhiều khả năng chỉ là một phần triển khai của module nghiệp vụ khác.

## 6. Xem các module Spring Modulith thực sự phát hiện

Không nên suy đoán từ tên folder. Hãy tạo mô hình từ lớp ứng dụng và liệt kê identifier cùng package nền:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .map(module -> module.getIdentifier() + " -> "
        + module.getBasePackage().getName())
    .sorted()
    .forEach(System.out::println);
```

Nếu đầu ra có các mục như:

```text
config -> com.acme.shop.config
inventory -> com.acme.shop.inventory
mapper -> com.acme.shop.mapper
orders -> com.acme.shop.orders
```

thì `config` và `mapper` đã được mô hình hóa thành module. Đây là tín hiệu để xem lại package arrangement: các package đó là năng lực độc lập hay chỉ là technical class của một module khác?

Có thể kiểm tra một package cụ thể đang thuộc module nào:

```java
var owner = modules.getModuleForPackage("com.acme.shop.orders.persistence")
    .orElseThrow();

System.out.println(owner.getIdentifier()); // orders
```

`getModuleForPackage()` hữu ích khi một package sâu cần được xác nhận là package nội bộ của module nào. Sau khi điều chỉnh cấu trúc, gọi `verify()` để kiểm tra lại các dependency:

```java
modules.verify();
```

## 7. Chọn chiến lược phát hiện phù hợp

Spring Modulith cung cấp ba hướng chính để xác định module base package.

### Chiến lược mặc định: direct sub-packages

Đây là lựa chọn mặc định. Mọi package con trực tiếp của package ứng dụng được xem là module base package. Cách này đơn giản và phù hợp khi nhóm tổ chức package cấp cao theo năng lực nghiệp vụ.

Không cần khai báo annotation trên từng module. Vì vậy, nếu dự án có nhiều package kỹ thuật ở cấp cao, hãy cân nhắc di chuyển chúng vào module sở hữu hoặc chọn một chiến lược phát hiện rõ ràng hơn.

### Chỉ phát hiện package được đánh dấu

Nếu muốn tự chọn module, cấu hình:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Sau đó đánh dấu package module bằng `@ApplicationModule` trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.orders;
```

Một package kỹ thuật như `com.acme.shop.config` sẽ không trở thành module chỉ vì nó là package con trực tiếp, miễn là nó không được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module`.

Chiến lược này làm ý định phát hiện tường minh hơn, nhưng nhóm phải duy trì annotation cho từng module. Package có annotation cũng cần được xem xét về trách nhiệm; đánh dấu tất cả package kỹ thuật không làm chúng trở thành module nghiệp vụ tốt.

### Tạo custom ApplicationModuleDetectionStrategy

Khi quy tắc của dự án phức tạp hơn, có thể viết chiến lược riêng. Ví dụ, giữ các package con trực tiếp nhưng bỏ các package kỹ thuật có tên `config`, `mapper` và `persistence`:

```java
package com.acme.shop.architecture;

import java.util.Set;
import java.util.stream.Stream;

import com.tngtech.archunit.core.domain.JavaPackage;
import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> TECHNICAL_PACKAGES =
        Set.of("config", "mapper", "persistence");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage basePackage) {
        return ApplicationModuleDetectionStrategy.directSubPackage()
            .getModuleBasePackages(basePackage)
            .filter(candidate -> !TECHNICAL_PACKAGES.contains(
                candidate.getRelativeName()
            ));
    }
}
```

Đăng ký class trong `application.properties`:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

Đây chỉ là ví dụ theo tên package. Trong dự án thật, có thể dùng allowlist các năng lực nghiệp vụ hoặc kiểm tra metadata thay vì blacklist. Một blacklist có thể bỏ sót package kỹ thuật mới nếu nhóm quên cập nhật; một allowlist có thể yêu cầu cập nhật mỗi khi thêm module. Hãy chọn quy tắc mà nhóm có thể duy trì và kiểm thử.

## 8. Loại trừ package khỏi inspection có phải cách sửa tốt?

`ApplicationModules.of(...)` có overload nhận predicate để loại class hoặc package khỏi việc kiểm tra. Ví dụ tài liệu Spring Modulith:

```java
import com.tngtech.archunit.core.domain.JavaClass;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(
    ShopApplication.class,
    JavaClass.Predicates.resideInAPackage("com.acme.shop.db..")
);
```

Package matcher `com.acme.shop.db..` khớp package `db` và các package con. Cơ chế này phù hợp khi có code nằm ngoài phạm vi kiến trúc mà nhóm muốn kiểm tra, chẳng hạn adapter hoặc code được quản lý như thư viện riêng.

Không nên dùng exclusion để che một package nghiệp vụ hoặc technical dependency nội bộ của ứng dụng. Khi loại class khỏi inspection, nhóm cũng mất khả năng phát hiện một số dependency phát sinh từ những class đó. Nếu package chỉ đặt sai cấp, di chuyển nó vào module sở hữu hoặc điều chỉnh detection strategy thường diễn đạt ý định kiến trúc tốt hơn.

## 9. Checklist xử lý module rỗng hoặc module kỹ thuật

Khi `ApplicationModules` hiển thị một module không có nội dung nghiệp vụ rõ ràng, hãy kiểm tra theo thứ tự:

1. Xác định package nền và vị trí của nó so với root package ứng dụng.
2. Liệt kê các type trong package đó và phân loại domain, application, infrastructure, configuration hoặc helper.
3. Nếu package chỉ chứa technical class phục vụ một năng lực, di chuyển chúng vào package con của module nghiệp vụ sở hữu.
4. Nếu module kỹ thuật có trách nhiệm và API độc lập, giữ nó thành module và công khai hợp đồng có chủ đích.
5. Nếu cần kiểm soát module bằng annotation, cân nhắc `explicitly-annotated`.
6. Nếu có quy ước phát hiện riêng, triển khai `ApplicationModuleDetectionStrategy` và kiểm thử chiến lược đó.
7. Liệt kê lại `ApplicationModules` để xác nhận mô hình mới phản ánh đúng ranh giới mong muốn.
8. Chạy `ApplicationModules.verify()` để kiểm tra dependency sau khi tổ chức lại package.

## 10. Những nhầm lẫn thường gặp

- **“Chỉ package có service nghiệp vụ mới được phát hiện.”** Chiến lược mặc định dựa vào package con trực tiếp, không phân loại class theo ý nghĩa nghiệp vụ.
- **“Folder rỗng trong IDE tự tạo module.”** Folder không có type hoặc package metadata trên classpath không đủ để tạo module trong mô hình.
- **“Package chỉ có `@Configuration` không phải module.”** Nếu nó là package con trực tiếp, nó vẫn có thể được phát hiện theo mặc định.
- **“Mọi package con đều là module.”** Chỉ package con trực tiếp của root package là module theo chiến lược mặc định; package sâu hơn thuộc module cha, trừ khi được khai báo là nested module.
- **“Đổi tên `config` thành `infrastructure` sẽ giải quyết.”** Nếu vẫn ở cấp trực tiếp dưới root package, package mới vẫn có thể được phát hiện thành module.
- **“Dùng explicitly-annotated là đủ để có ranh giới tốt.”** Annotation quyết định package nào là module; nhóm vẫn phải chọn module dựa trên trách nhiệm và hợp đồng phù hợp.
- **“Loại trừ package luôn an toàn.”** Exclusion làm giảm phạm vi code được kiểm tra và có thể che giấu dependency cần quản lý.

## Kết luận

Một module rỗng về nghiệp vụ hoặc package chỉ chứa technical class thường là dấu hiệu cần xem lại cách tổ chức package. Theo mặc định, Spring Modulith nhận diện package con trực tiếp của root package thành module mà không đánh giá chúng có chứa năng lực nghiệp vụ hay không. Hãy đặt technical class bên trong module sở hữu chúng, chỉ giữ module kỹ thuật riêng khi nó có trách nhiệm và API độc lập, hoặc dùng `explicitly-annotated`/custom `ApplicationModuleDetectionStrategy` khi cấu trúc dự án cần quy tắc phát hiện khác. Luôn kiểm tra mô hình thực tế bằng `ApplicationModules` trước khi dựa vào nó để xác minh kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Simple and Advanced Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [ArchUnit — JavaPackage API](https://www.javadoc.io/doc/com.tngtech.archunit/archunit/latest/com/tngtech/archunit/core/domain/JavaPackage.html)
