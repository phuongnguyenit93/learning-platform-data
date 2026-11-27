# Chọn detection strategy dễ hiểu và tái lập

Spring Modulith xây dựng application module model bằng cách phân tích package của ứng dụng và áp dụng một module detection strategy. Strategy quyết định package nào trở thành application module base package. Nếu lựa chọn strategy quá rộng, các package kỹ thuật như `config`, `common` hoặc `infrastructure` có thể bị nhận diện thành module ngoài ý muốn. Nếu strategy quá đặc thù, module mới có thể bị bỏ sót hoặc test và runtime phát hiện ra hai module arrangement khác nhau.

Một detection strategy tốt cần dễ giải thích, ổn định khi cấu trúc package thay đổi có chủ đích và tái lập giữa local, CI và runtime. Hãy bắt đầu bằng convention đơn giản nhất phù hợp với codebase; chỉ tăng mức tùy chỉnh khi có một yêu cầu kiến trúc cụ thể mà convention hiện tại không thể diễn đạt.

## 1. Detection strategy quyết định điều gì?

`ApplicationModules.of(ShopApplication.class)` tạo một mô hình trong bộ nhớ về các application module được phát hiện từ codebase. Module model được dùng cho verification, tài liệu kiến trúc, module integration tests và các runtime features.

Detection strategy xác định các package nào là module base package. Ví dụ:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
├── inventory
│   └── InventoryManagement.java
├── shipping
│   └── ShippingService.java
└── configuration
    └── WebConfiguration.java
```

Với strategy mặc định, các package con trực tiếp `order`, `inventory`, `shipping` và `configuration` đều có thể được nhận diện là application module. Nếu `configuration` chỉ là package cấu hình kỹ thuật và không phải capability nghiệp vụ, kết quả đó có thể không đúng ý định của nhóm.

Detection strategy trả lời câu hỏi “package nào là module?”. Nó không quyết định module được phép truy cập package nào, không đặt `allowedDependencies`, không công bố Named Interface và không tự biến một module thành `OPEN`. Các quy tắc đó được mô tả bằng module metadata và các cơ chế riêng.

## 2. Ba lựa chọn chính

Spring Modulith cung cấp hai chiến lược dựng sẵn và một extension point để tự định nghĩa:

| Strategy | Cách nhận diện | Phù hợp khi |
| --- | --- | --- |
| Mặc định `directSubPackage()` | Mỗi package con trực tiếp của package ứng dụng là một module | Cấu trúc package đã tổ chức theo capability ở cùng một cấp |
| `explicitly-annotated` | Chỉ package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` là module | Codebase có nhiều package kỹ thuật hoặc module nằm ở vị trí chọn lọc |
| Custom `ApplicationModuleDetectionStrategy` | Code của dự án chọn module base package theo quy tắc riêng | Cấu trúc package không thể mô tả rõ bằng hai strategy dựng sẵn |

Không có strategy nào luôn tốt nhất cho mọi ứng dụng. Tiêu chí lựa chọn là sự tương ứng giữa convention package và ranh giới module mà nhóm muốn duy trì.

## 3. Dùng strategy mặc định khi package đã phản ánh capability

Mặc định, Spring Modulith coi mỗi direct sub-package của package chứa lớp `@SpringBootApplication` là một application module.

Ví dụ:

```text
com.acme.shop                       package chứa ShopApplication
├── ShopApplication.java
├── order                            module order
├── inventory                        module inventory
├── shipping                         module shipping
└── customer                         module customer
```

Không cần thêm annotation hoặc property để bật cách phát hiện này. Có thể viết tường minh trong code khi cần tham chiếu strategy:

```java
ApplicationModuleDetectionStrategy strategy =
        ApplicationModuleDetectionStrategy.directSubPackage();
```

Trong phần lớn ứng dụng, cứ để mặc định là cách dễ hiểu nhất. Mỗi package cấp một tương ứng một capability, module mới được tạo bằng cách thêm package cùng cấp, và module model không phụ thuộc vào một danh sách tên hard-code.

### Khi nào default strategy không phù hợp?

Không nên dùng mặc định nếu package root chứa cả module nghiệp vụ lẫn các package kỹ thuật không phải module:

```text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
├── shipping
├── config
├── bootstrap
└── shared-kernel
```

Với cấu trúc này, `config`, `bootstrap` hoặc `shared-kernel` cũng có thể bị xem là module. Nếu các package đó chỉ là phần hỗ trợ của ứng dụng, nhóm cần thay đổi cách phát hiện hoặc tổ chức lại package.

## 4. Dùng `explicitly-annotated` khi cần chọn module có chủ đích

Nếu chỉ một số package là module, có thể cấu hình strategy `explicitly-annotated`. Strategy này chỉ xem package được đánh dấu bằng Spring Modulith `@ApplicationModule` hoặc jMolecules `@Module` là module base package.

Trong `application.properties`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Đánh dấu package module bằng `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.order;
```

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
```

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.shipping;
```

Package `config`, `bootstrap` hoặc `shared-kernel` không được nhận diện thành module chỉ vì chúng là package con trực tiếp. Chúng chỉ trở thành module nếu được đánh dấu theo strategy đang dùng.

### Ưu điểm và chi phí

Strategy này làm ranh giới module hiện rõ trong source code và phù hợp với hệ thống có nhiều package không phải capability. Đổi lại, mỗi module mới cần có annotation hoặc marker tương ứng. Nếu quên đánh dấu, package đó có thể bị bỏ khỏi module model mà không nhất thiết gây lỗi compile.

Vì vậy, cần có test xác nhận tập module mong đợi. Không nên chỉ dựa vào việc các package có annotation mà kết luận toàn bộ module đã được phát hiện.

## 5. Custom strategy chỉ khi hai lựa chọn dựng sẵn không đủ

Nếu module được tổ chức theo một convention riêng, có thể triển khai `ApplicationModuleDetectionStrategy`. Interface này có phương thức chính:

```java
Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage);
```

Spring Modulith truyền package root của ứng dụng vào method. Implementation trả về stream các package sẽ được xem là module base package.

Ví dụ, legacy codebase đặt các module bên dưới `com.acme.shop.modules`, trong khi root package ứng dụng là `com.acme.shop`. Nhóm muốn chọn các package có dạng `modules.<capability>`:

```text
com.acme.shop
├── ShopApplication.java
├── modules
│   ├── order
│   ├── inventory
│   └── shipping
├── config
└── bootstrap
```

Có thể dùng `getSubPackagesMatching()` để chọn đúng package có hai segment tương đối `modules.<name>`:

```java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class CapabilityModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getSubPackagesMatching(
                (candidate, trailingName) -> trailingName.matches("modules\\.[^.]+")
        );
    }
}
```

`trailingName` là tên package tương đối so với root package. Pattern `modules\\.[^.]+` trong Java string chọn `modules.order`, `modules.inventory` hoặc `modules.shipping`, nhưng không chọn `modules.order.internal`.

Đăng ký class bằng property:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.CapabilityModuleDetectionStrategy
```

Custom strategy nên ngắn, deterministic và có thể giải thích bằng một quy tắc package cụ thể. Tránh logic dựa trên filesystem hiện tại, thứ tự duyệt không ổn định, biến môi trường không được quản lý hoặc trạng thái thay đổi theo thời điểm chạy.

## 6. Chọn strategy theo hình dạng package thực tế

Một số mẫu package phổ biến và lựa chọn phù hợp:

| Hình dạng package | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| `root.order`, `root.inventory`, `root.shipping` | Default direct sub-package | Capability nằm ở cùng cấp và không có package kỹ thuật cùng cấp cần loại trừ |
| `root.order`, `root.inventory`, `root.config`, `root.bootstrap` | Explicitly annotated | Chỉ package module được đánh dấu; package hỗ trợ không tự trở thành module |
| `root.modules.order`, `root.modules.inventory` | Custom strategy hoặc đổi package về direct sub-package | Module được lồng dưới một namespace chung |
| Nhiều root package độc lập | `@Modulithic(additionalPackages = …)` hoặc `ApplicationModuleSourceFactory` | Cần yêu cầu detection ở nhiều package root |
| Một số module legacy nằm ở package rời rạc | Explicitly annotated hoặc `ApplicationModuleSourceFactory` | Ranh giới được mô tả rõ thay vì dựa vào quy tắc tên phức tạp |

Trước khi viết custom strategy, hãy cân nhắc liệu package có thể được tổ chức lại để dùng default hay không. Một thay đổi cấu trúc đơn giản thường dễ hiểu và dễ tái lập hơn một thuật toán discovery tùy chỉnh.

## 7. Xác định thêm root package bằng `@Modulithic`

Nếu ứng dụng có module nằm ngoài package root của lớp Spring Boot application, `@Modulithic` có thể khai báo `additionalPackages`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.acme.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Spring Modulith sẽ kích hoạt module detection cho package bổ sung đó. `additionalPackages` giải quyết việc cung cấp thêm root package; detection strategy vẫn quyết định các module bên dưới mỗi root được nhận diện như thế nào.

Không dùng `additionalPackages` để biến một package đơn lẻ thành module tùy ý mà không hiểu root arrangement. Nếu chỉ cần thêm một module cụ thể từ package ngoài, cân nhắc `ApplicationModuleSourceFactory`.

## 8. Dùng `ApplicationModuleSourceFactory` cho module đến từ package khác

Khi ứng dụng nhận module từ các package root khác nhau hoặc từ một module source được đóng góp bên ngoài, Spring Modulith cung cấp `ApplicationModuleSourceFactory`. Factory có thể trả về root package cần quét, detection strategy áp dụng cho root đó và danh sách module base package được tạo tường minh.

Một implementation có thể đăng ký qua `META-INF/spring.factories`:

```properties
org.springframework.modulith.core.ApplicationModuleSourceFactory=com.acme.shop.architecture.ShopModuleSourceFactory
```

Factory phù hợp khi một hệ thống có nhiều bounded package root hoặc cần đóng góp module từ một phần code riêng. Đây là cơ chế nâng cao; không nên dùng nó nếu tất cả module đã nằm gọn bên dưới một package ứng dụng và default strategy đủ dùng.

## 9. Named Interface detection là một phần tùy chỉnh riêng

`ApplicationModuleDetectionStrategy` còn có method mặc định `detectNamedInterfaces(JavaPackage, ApplicationModuleInformation)`. Method này cho phép custom cách phát hiện Named Interface bên trong một module.

Ví dụ, nếu dự án thống nhất mọi package tên `api` bên dưới module là Named Interface, có thể override method này bằng `NamedInterfaces.Builder`:

Đặt method này trong cùng implementation của `ApplicationModuleDetectionStrategy` và import các kiểu sau:

```java
import org.springframework.modulith.core.ApplicationModuleInformation;
import org.springframework.modulith.core.JavaPackage;
import org.springframework.modulith.core.NamedInterfaces;
```

```java
@Override
public NamedInterfaces detectNamedInterfaces(
        JavaPackage basePackage,
        ApplicationModuleInformation information) {

    return NamedInterfaces.builder(basePackage)
            .recursive()
            .matching("api")
            .build();
}
```

Đoạn code trên chọn các package tên `api` theo phạm vi recursive của module. Builder còn hỗ trợ include hoặc exclude package theo predicate. Unnamed interface của package gốc luôn được giữ lại vì đó là API mặc định cần thiết của module.

Chỉ override `detectNamedInterfaces()` khi dự án có convention rõ ràng và muốn áp dụng nhất quán. Nếu team đã dùng `@NamedInterface` trong `package-info.java`, discovery mặc định thường dễ đọc hơn vì contract nằm ngay tại package được công bố.

## 10. Đăng ký strategy và giữ cấu hình nhất quán

Có thể cấu hình built-in explicitly annotated bằng:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Custom strategy được đăng ký bằng fully-qualified class name:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.CapabilityModuleDetectionStrategy
```

Nếu không khai báo property, Spring Modulith dùng default direct-sub-package strategy. Hãy đặt property trong cấu hình có thể được cả test và runtime nhìn thấy nếu cả hai cần cùng module arrangement.

Với custom strategy chỉ phục vụ verification và documentation trong test, có thể đặt implementation và registration trong test sources. Nếu ứng dụng sử dụng runtime components như `ApplicationModuleInitializer`, Actuator hoặc observability support, strategy cần sẵn có ở production sources/runtime classpath; Spring Modulith cũng yêu cầu `spring-modulith-core` là compile-time dependency trong trường hợp này.

Không để một bản custom strategy chỉ tồn tại trong `src/test/java` nếu runtime cần dùng nó. Khi đó architecture test có thể phát hiện module theo một quy tắc, nhưng runtime features không có cùng strategy.

## 11. Kiểm tra module arrangement có tái lập không

Sau khi chọn strategy, tạo một test xác nhận đúng tập module dự kiến:

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void detectsExpectedApplicationModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        Set<String> identifiers = modules.stream()
                .map(module -> module.getIdentifier().toString())
                .collect(Collectors.toSet());

        assertThat(identifiers).containsExactlyInAnyOrder(
                "order",
                "inventory",
                "shipping"
        );

        modules.verify();
    }
}
```

Assertion về tập identifier giúp phát hiện hai tình huống mà `verify()` một mình có thể không trả lời theo ý định của nhóm: module bị bỏ sót khỏi detection và package kỹ thuật vô tình trở thành module. Sau khi xác nhận tập module, `verify()` kiểm tra các dependency và package boundary.

Nếu module có `id` tường minh hoặc bật fully-qualified module names, assertion phải dùng identifier thực tế tương ứng. Không hard-code local package name khi module model đã được cấu hình một identifier khác.

## 12. Giữ detection nhất quán giữa local, CI và runtime

Một module arrangement có thể thay đổi nếu strategy, root package hoặc classpath khác nhau giữa các môi trường. Để kết quả tái lập:

1. Đặt detection strategy trong source/configuration được quản lý bằng version control.
2. Dùng cùng Spring Modulith version qua BOM cho test và runtime.
3. Đảm bảo custom strategy có mặt ở mọi classpath cần sử dụng.
4. Không chọn module theo trạng thái filesystem hoặc môi trường chạy không được khai báo.
5. Kiểm tra tập module mong đợi bằng test.
6. Nếu dùng runtime verification, chạy cùng strategy và module metadata trong production artifact.
7. Khi thay package hoặc thêm module, cập nhật expected module set trong architecture test.

Nếu có nhiều application root package, kiểm tra cả danh sách root package. Đừng chỉ assert một nhóm module con rồi bỏ qua một root khác chưa được đưa vào model.

## 13. Các dấu hiệu strategy đang quá phức tạp

Hãy xem lại lựa chọn nếu:

- Một developer mới không thể đoán module nào được nhận diện chỉ bằng cách nhìn package và annotation.
- Thêm package mới đôi khi tạo module, đôi khi không, tùy theo tên file hoặc môi trường.
- Custom strategy có nhiều ngoại lệ cho từng package mà không có quy tắc chung.
- Test phải mock hoặc sửa environment để module model có thể được tạo.
- Test và runtime có hai implementation detection strategy khác nhau.
- Nhóm không có test xác nhận tập module mong đợi.

Trong các trường hợp này, hãy đơn giản hóa package layout, chuyển sang explicitly annotated hoặc thu hẹp custom strategy thành một quy tắc tên package duy nhất.

## 14. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Default strategy quét mọi package con ở mọi độ sâu thành module | Nó coi các direct sub-package của application root là module base package |
| `explicitly-annotated` nhận diện mọi package có annotation Spring bất kỳ | Nó tìm package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` |
| `spring.modulith.detection-strategy` đặt API của module | Property chọn module base package; Named Interface và API boundary là cơ chế khác |
| Custom strategy chỉ cần override `getModuleBasePackages()` trong mọi trường hợp | Có thể override thêm `detectNamedInterfaces()` nếu cần tùy chỉnh Named Interface discovery |
| `additionalPackages` thay thế detection strategy | Nó thêm root package; strategy vẫn quyết định module bên dưới root |
| `ApplicationModuleSourceFactory` cần cho mọi ứng dụng nhiều module | Cơ chế này dành cho module từ các root/package source khác; một root thông thường không cần nó |
| Architecture test pass nghĩa runtime chắc chắn dùng cùng module model | Chỉ đúng khi strategy, metadata và classpath cần thiết nhất quán giữa test và runtime |
| `verify()` đảm bảo mọi module dự kiến đều được phát hiện | Cần assertion về expected module set để phát hiện module bị bỏ sót hoặc package bị nhận nhầm |

## 15. Ghi nhớ

Spring Modulith mặc định nhận diện các direct sub-package của package chứa `@SpringBootApplication` thành application module. Đây là lựa chọn dễ hiểu nhất khi mỗi capability nằm trong một package cùng cấp. Nếu chỉ một số package được xem là module, dùng `spring.modulith.detection-strategy=explicitly-annotated` và đánh dấu module bằng `@ApplicationModule` hoặc jMolecules `@Module`.

Chỉ viết custom `ApplicationModuleDetectionStrategy` khi cấu trúc package không thể diễn đạt bằng hai lựa chọn trên. Giữ `getModuleBasePackages()` deterministic, đăng ký strategy bằng property và đặt code ở đúng source set mà test/runtime cần. Dùng `@Modulithic(additionalPackages = …)` hoặc `ApplicationModuleSourceFactory` khi cần thêm root package hoặc module từ package source khác.

Cuối cùng, kiểm tra module model bằng assertion về expected module identifiers rồi chạy `ApplicationModules.verify()`. Một strategy dễ hiểu và tái lập là strategy mà developer có thể dự đoán module từ package/metadata, CI và runtime tạo cùng một arrangement, và mọi thay đổi module đều được phát hiện qua test.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith API — `JavaPackage`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
- [Spring Modulith API — `NamedInterfaces`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterfaces.html)
- [Spring Modulith API — `ApplicationModuleSourceFactory`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleSourceFactory.html)
