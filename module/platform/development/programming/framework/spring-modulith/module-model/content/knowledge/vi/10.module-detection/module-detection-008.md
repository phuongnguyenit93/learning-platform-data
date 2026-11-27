# Phát hiện nhầm package thành module

Spring Modulith suy ra Application Module từ cấu trúc package của ứng dụng. Theo chiến lược mặc định, **mọi package con trực tiếp của package chứa class @SpringBootApplication đều được xem là package gốc của một module**. Quy tắc này dễ dùng khi ứng dụng được tổ chức theo nghiệp vụ, nhưng có thể tạo ra module ngoài ý muốn nếu package gốc chứa các thư mục kỹ thuật như **config**, **common**, **web**, **persistence** hoặc **utils**.

Ví dụ, nếu **com.acme.shop.config** chỉ chứa cấu hình Spring dùng chung cho toàn ứng dụng, việc Spring Modulith nhận diện nó thành module **config** có thể làm dependency graph không phản ánh đúng ranh giới nghiệp vụ. Bài học này hướng dẫn cách nhận ra tình huống đó, tổ chức lại package và lựa chọn chiến lược phát hiện module phù hợp.

## 1. Quy tắc phát hiện mặc định

Spring Modulith lấy package của class ứng dụng Spring Boot làm application root package. Class đó thường được đánh dấu bằng **@SpringBootApplication** và chứa phương thức **main(…)**.

Ví dụ:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với application root package là **com.acme.shop**, chiến lược mặc định xem các package con trực tiếp sau đây là module:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
├── customers
├── config
├── common
├── web
└── persistence
~~~

Spring Modulith không tự suy luận rằng **orders**, **inventory**, **customers** là nghiệp vụ còn **config**, **common**, **web**, **persistence** là tầng kỹ thuật. Tất cả đều nằm ở cùng cấp package nên đều có thể được nhận diện là Application Module.

Quy tắc mặc định chỉ xét **package con trực tiếp** của application root. Các package lồng bên trong một module, chẳng hạn **com.acme.shop.orders.internal.persistence**, mặc định thuộc module **orders**; chúng không tự trở thành module riêng.

## 2. Vì sao package kỹ thuật dễ bị nhận diện nhầm?

Lỗi thường xuất hiện khi ứng dụng được tổ chức theo tầng kỹ thuật ở cấp cao nhất:

~~~text
com.acme.shop
├── ShopApplication.java
├── controller
│   ├── OrderController.java
│   └── CustomerController.java
├── service
│   ├── OrderService.java
│   └── CustomerService.java
├── repository
│   ├── OrderRepository.java
│   └── CustomerRepository.java
└── config
    └── PersistenceConfiguration.java
~~~

Theo quy tắc mặc định, **controller**, **service**, **repository** và **config** có thể bị nhận diện thành bốn module riêng. Khi đó, các class cùng một nghiệp vụ như đặt hàng lại nằm rải rác ở nhiều module kỹ thuật.

Hậu quả có thể thấy ở dependency graph:

- **controller** phụ thuộc **service**.
- **service** phụ thuộc **repository**.
- Các nghiệp vụ **orders** và **customers** không còn được thể hiện thành những module có quyền sở hữu rõ ràng.
- Các quy tắc phụ thuộc được kiểm tra theo ranh giới kỹ thuật thay vì ranh giới nghiệp vụ.

Spring Modulith có thể kiểm chứng chính xác đồ thị được suy ra từ package, nhưng không thể tự biết nhóm package đó có đại diện đúng cho năng lực nghiệp vụ của ứng dụng hay không. Vì vậy, việc phát hiện module đúng cần kết hợp quy tắc framework với quyết định thiết kế của đội ngũ.

## 3. Phân biệt module thật và package kỹ thuật

Không phải mọi package tên **common**, **shared** hoặc **config** đều sai. Cần xét trách nhiệm thực tế của package.

| Dấu hiệu | Có thể là Application Module | Thường chỉ là package kỹ thuật |
|---|---|---|
| Trách nhiệm | Sở hữu một năng lực nghiệp vụ hoặc capability rõ ràng | Gom class theo framework hoặc tầng kỹ thuật |
| API | Có hợp đồng mà module khác sử dụng có chủ đích | Chủ yếu chứa helper, cấu hình hoặc adapter dùng chung |
| Nội bộ | Có logic và chi tiết triển khai do module tự quản lý | Không có ranh giới nghiệp vụ độc lập |
| Phụ thuộc | Có thể mô tả bằng các quan hệ giữa module | Phụ thuộc chéo nhiều nghiệp vụ chỉ vì cùng tầng |
| Thay đổi | Có thể thay đổi nghiệp vụ tương đối độc lập | Thay đổi một nghiệp vụ thường kéo theo sửa nhiều package kỹ thuật |

Ví dụ, **shared** có thể là module hợp lệ nếu nó sở hữu một capability dùng chung ổn định, có API rõ ràng và được các module khác tiêu thụ có chủ đích. Nhưng nếu **shared** chỉ là nơi gom mọi class chưa biết đặt ở đâu, nó không tạo ra ranh giới tốt.

Tương tự, **config** có thể là một module có ý nghĩa nếu nó quản lý một năng lực cấu hình độc lập được công bố có chủ đích. Nếu chỉ chứa cấu hình Spring Boot, datasource và bean setup toàn ứng dụng, thường không nên xem nó là module nghiệp vụ.

## 4. Tổ chức package theo module nghiệp vụ

Thay vì đặt package theo tầng kỹ thuật ở cấp application root, hãy đưa các class về module sở hữu nghiệp vụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       ├── OrderService.java
│       ├── OrderController.java
│       ├── persistence
│       │   └── JpaOrderRepository.java
│       └── config
│           └── OrderConfiguration.java
├── customers
│   ├── CustomerDirectory.java
│   └── internal
│       ├── CustomerService.java
│       ├── CustomerController.java
│       └── persistence
│           └── JpaCustomerRepository.java
└── inventory
    ├── InventoryManagement.java
    └── internal
        ├── InventoryService.java
        └── persistence
            └── JpaInventoryRepository.java
~~~

Ở cấu trúc này:

- **orders**, **customers** và **inventory** là các module nghiệp vụ.
- Controller, service triển khai, repository và cấu hình riêng được đặt trong module sở hữu chúng.
- Package **internal** và các subpackage của nó mặc định thuộc module cha, không tự trở thành module riêng.
- Module khác chỉ nên sử dụng API package hoặc Named Interface được module sở hữu công bố.

Nếu có cấu hình thực sự dùng chung cho toàn ứng dụng, có thể đặt class cấu hình tại application root package hoặc một vị trí cấu hình phù hợp với cơ chế khởi động. Tránh tạo package kỹ thuật cấp một chỉ để gom các class từ nhiều nghiệp vụ.

## 5. Kiểm tra những module Spring Modulith thực sự nhận diện

Đừng chỉ nhìn cấu trúc folder trong IDE. Hãy xem mô hình được tạo từ chính class ứng dụng:

~~~java
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionInspection {

    public static void main(String[] args) {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.stream()
            .map(module -> module.getBasePackage().getName())
            .sorted()
            .forEach(System.out::println);
    }
}
~~~

Đoạn mã in ra base package của từng module mà Spring Modulith nhận diện. Nếu kết quả chứa các package như **com.acme.shop.config**, **com.acme.shop.web** hoặc **com.acme.shop.persistence**, hãy kiểm tra xem chúng có thật sự là ranh giới module mong muốn hay chỉ là package kỹ thuật.

Có thể kiểm tra module đang sở hữu một package cụ thể:

~~~java
var owner = modules.getModuleForPackage("com.acme.shop.config");

owner.ifPresent(module ->
    System.out.println(module.getBasePackage().getName())
);
~~~

**getModuleForPackage(…)** giúp trả lời package đang xét thuộc module nào trong mô hình. Đây là cách hữu ích để điều tra một class hoặc package đang bị phân loại ngoài dự kiến.

## 6. Chọn chiến lược explicitly-annotated

Nếu application root chứa nhiều package kỹ thuật và chỉ muốn những package được đánh dấu rõ ràng trở thành module, có thể chuyển sang chiến lược **explicitly-annotated**.

Trong **application.properties**:

~~~properties
spring.modulith.detection-strategy=explicitly-annotated
~~~

Sau đó, đánh dấu package gốc của từng module bằng **@ApplicationModule** trong **package-info.java**:

~~~java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.orders;
~~~

Tương tự cho các module còn lại:

~~~java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.customers;
~~~

~~~java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
~~~

Chiến lược này chỉ xem các package được đánh dấu bằng Spring Modulith **@ApplicationModule** hoặc jMolecules **@Module** là module base package. Các package kỹ thuật không được đánh dấu như **config**, **web** và **persistence** sẽ không tự trở thành module chỉ vì chúng nằm trực tiếp dưới application root.

Điều cần lưu ý là mọi module dự định tham gia mô hình đều phải được đánh dấu. Nếu quên annotation, package đó sẽ không được phát hiện như một module theo chiến lược này.

**@NamedInterface** không thay thế **@ApplicationModule**. Named Interface công bố thêm API bên trong một module đã được nhận diện; nó không đánh dấu package thành module mới.

## 7. Dùng custom ApplicationModuleDetectionStrategy khi cần quy tắc riêng

Nếu danh sách module có thể xác định bằng một quy ước ổn định, nhưng không muốn thêm annotation vào từng package, có thể viết **ApplicationModuleDetectionStrategy**.

Ví dụ, ứng dụng chỉ xem **orders**, **customers** và **inventory** là module:

~~~java
package com.acme.shop.architecture;

import java.util.Set;
import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULE_PACKAGES =
        Set.of("orders", "customers", "inventory");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
            .filter(candidate ->
                MODULE_PACKAGES.contains(candidate.getLocalName()));
    }
}
~~~

Đăng ký strategy trong **application.properties** bằng tên đầy đủ của class:

~~~properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
~~~

Spring Modulith gọi **getModuleBasePackages(…)** với application root package. Strategy trả về các **JavaPackage** được chọn làm base package của module. Trong ví dụ, các package **config**, **web**, **common** hoặc **persistence** bị loại khỏi danh sách vì không nằm trong tập module đã định nghĩa.

Custom strategy hữu ích khi quy tắc phát hiện dựa trên naming convention, cấu trúc nhiều nhóm hoặc metadata riêng. Tuy nhiên, hãy giữ logic phát hiện đơn giản và dễ kiểm tra. Một danh sách module được khai báo tường minh thường dễ bảo trì hơn một thuật toán suy luận phức tạp.

Nếu strategy chỉ được dùng cho kiểm chứng và tạo tài liệu trong test, đặt implementation và cấu hình tương ứng trong test sources. Nếu các thành phần runtime của Spring Modulith cũng cần dùng strategy đó, cần bảo đảm implementation và **spring-modulith-core** có mặt trong runtime classpath theo hướng dẫn chính thức.

## 8. Phân biệt additionalPackages với module detection strategy

**@Modulithic(additionalPackages = …)** cho phép khai báo thêm package gốc để Spring Modulith bắt đầu phát hiện module bên ngoài package của class ứng dụng. Nó giải quyết trường hợp ứng dụng có nhiều package root.

Ví dụ:

~~~java
@org.springframework.modulith.Modulithic(
    additionalPackages = "com.acme.shared"
)
@org.springframework.boot.autoconfigure.SpringBootApplication
public class ShopApplication {
}
~~~

Đây không phải bộ lọc loại trừ package kỹ thuật trong application root. Với mỗi root package được cấu hình, chiến lược phát hiện module vẫn được áp dụng. Nếu vấn đề là **config** hoặc **web** đang bị nhận diện nhầm, hãy điều chỉnh cấu trúc package hoặc detection strategy thay vì dùng **additionalPackages**.

## 9. Kiểm chứng sau khi sửa cách phát hiện module

Sau khi tổ chức lại package hoặc đổi detection strategy, tạo bài test kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.stream()
            .map(module -> module.getBasePackage().getName())
            .forEach(System.out::println);

        modules.verify();
    }
}
~~~

Khi đọc kết quả:

1. Xác nhận danh sách base package đúng với các năng lực nghiệp vụ mong muốn.
2. Kiểm tra các package kỹ thuật không còn xuất hiện như module độc lập ngoài ý muốn.
3. Kiểm tra package lồng bên trong từng module vẫn thuộc module sở hữu.
4. Chạy **verify()** để phát hiện chu trình phụ thuộc, truy cập package nội bộ và dependency ngoài danh sách cho phép.

**verify()** kiểm tra cấu trúc và các quy tắc phụ thuộc của mô hình đã phát hiện. Nó không tự kết luận rằng **common** hoặc **config** là một ranh giới nghiệp vụ hợp lý. Vì vậy, cần xem danh sách module trước khi chỉ dựa vào kết quả PASS/FAIL của verification.

## 10. Các lỗi thường gặp khi sửa module detection

**Chỉ đổi tên package kỹ thuật.** Đổi **service** thành **services** hoặc **common** thành **shared** không giải quyết vấn đề nếu package vẫn nằm trực tiếp dưới application root. Chiến lược mặc định vẫn nhận diện nó là module.

**Đưa mọi package kỹ thuật vào một module common.** Cách này có thể tạo module có trách nhiệm quá rộng và làm các module nghiệp vụ phụ thuộc vào một vùng dùng chung khó kiểm soát. Chỉ tạo shared module khi có capability và hợp đồng rõ ràng.

**Đánh dấu mọi package bằng @ApplicationModule.** Với chiến lược explicitly-annotated, annotation biến package thành module base package. Không đánh dấu **internal**, **persistence** hoặc **config** nếu chúng chỉ là chi tiết triển khai.

**Dùng @NamedInterface để tạo module.** Named Interface chỉ công bố package thuộc module đã tồn tại. Nó không thay thế chiến lược phát hiện module.

**Đặt class @SpringBootApplication quá sâu.** Application root package được suy ra từ package của class ứng dụng. Nếu class này nằm trong **com.acme.shop.bootstrap**, chiến lược mặc định sẽ bắt đầu từ package đó. Hãy đặt class ứng dụng ở root phù hợp hoặc cấu hình thêm root package theo đúng mục đích.

**Bỏ qua module list sau khi đổi strategy.** Một test **verify()** thành công không đảm bảo danh sách module đã đúng ý định. Hãy in hoặc kiểm tra base package của các module như một phần của review.

## 11. Quy trình xử lý package bị nhận diện nhầm

Khi phát hiện một package kỹ thuật xuất hiện như module, hãy làm theo trình tự:

1. Xác định package của class **@SpringBootApplication**; đây là điểm bắt đầu phát hiện module.
2. Liệt kê các module bằng **ApplicationModules.of(ShopApplication.class)**.
3. Đối chiếu base package của từng module với ranh giới nghiệp vụ thực tế.
4. Nếu package chỉ là tầng kỹ thuật, chuyển class về module nghiệp vụ sở hữu nó.
5. Nếu cấu trúc không thể tổ chức lại ngay, cân nhắc **explicitly-annotated** hoặc custom detection strategy.
6. Đánh dấu đúng các module nghiệp vụ nếu dùng chiến lược explicitly-annotated.
7. Kiểm tra lại module list và chạy **ApplicationModules.verify()**.

Khi package được tổ chức theo quyền sở hữu nghiệp vụ, Spring Modulith có thể tạo dependency graph phản ánh đúng các module mà đội ngũ muốn kiểm soát. Điều này giúp các quy tắc kiến trúc, API package và Named Interface có ý nghĩa rõ ràng hơn trong quá trình phát triển modular monolith.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): quy tắc phát hiện module mặc định, explicitly-annotated, custom strategy và additional packages.
- [Javadoc — ApplicationModuleDetectionStrategy](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html): **directSubPackage()**, **explicitlyAnnotated()** và **getModuleBasePackages()**.
- [Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): xem các module được phát hiện qua **stream()** và **getModuleForPackage()**.
- [Javadoc — JavaPackage](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html): truy cập tên package và các package con trực tiếp.
