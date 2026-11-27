# Custom detection trong production sources

## Vì sao custom detection phải nằm trong production sources?

Spring Modulith xây dựng mô hình application module từ package gốc của lớp Spring Boot application. Theo mặc định, các package con trực tiếp được xem là module. Khi cấu trúc dự án không theo quy ước đó, bạn có thể cung cấp một ApplicationModuleDetectionStrategy để chọn các package làm module base package theo quy tắc riêng.

Một chiến lược tùy chỉnh có thể đủ dùng trong kiểm thử kiến trúc và sinh tài liệu. Khi ứng dụng sử dụng các tính năng Spring Modulith tại runtime, chẳng hạn ApplicationModuleInitializer, runtime verification, actuator hoặc observability, chiến lược phát hiện module cũng phải có mặt trong mã nguồn production.

Lý do nằm ở phạm vi biên dịch và classpath:

- src/test/java và src/test/resources chỉ có trong môi trường test.
- Ứng dụng được đóng gói và chạy từ production artifact không mang theo các lớp và cấu hình chỉ dành cho test.
- Nếu chiến lược hoặc cấu hình đăng ký chỉ tồn tại trong test sources, runtime có thể không tìm thấy lớp tùy chỉnh hoặc tạo ra một mô hình module khác với mô hình mà test đã xác minh.

Vì vậy, khi runtime cần sử dụng cùng quy tắc phát hiện module, hãy đặt lớp chiến lược trong src/main/java và cấu hình đăng ký trong src/main/resources.

## Khi nào cần custom detection?

Mặc định, Spring Modulith coi các package con trực tiếp của package chứa lớp Spring Boot application là application module. Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
├── catalog
└── configuration
~~~

Trong cấu trúc này, các package con trực tiếp có thể được phát hiện như các module. Nếu nhóm muốn chỉ chọn orders, inventory và catalog, đồng thời để configuration nằm ngoài danh sách module nghiệp vụ, có thể dùng chiến lược tùy chỉnh.

Trước khi viết chiến lược riêng, hãy xem xét các lựa chọn có sẵn:

- direct-subpackages: dùng quy tắc mặc định, chọn package con trực tiếp.
- explicitly-annotated: chỉ chọn package được đánh dấu bằng @ApplicationModule hoặc annotation @Module của jMolecules.
- Tên lớp tùy chỉnh: dùng khi quy tắc phát hiện phụ thuộc vào naming convention hoặc logic riêng của dự án.

Nếu explicitly-annotated đã diễn đạt đúng cấu trúc, không cần tạo thêm một lớp chiến lược. Custom detection phù hợp khi quy tắc của dự án không thể biểu đạt gọn bằng các lựa chọn có sẵn.

## ApplicationModuleDetectionStrategy hoạt động thế nào?

ApplicationModuleDetectionStrategy là một SPI để tùy chỉnh việc chọn module base package. Spring Modulith gọi phương thức getModuleBasePackages với package gốc của ứng dụng. Phương thức trả về một Stream<JavaPackage> chứa những package cần được coi là module.

Luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Package của ShopApplication"] --> B["ApplicationModuleDetectionStrategy"]
    B --> C["Chọn package theo quy ước"]
    C --> D["orders"]
    C --> E["inventory"]
    C --> F["catalog"]
    D --> G["ApplicationModules"]
    E --> G
    F --> G
    G --> H["Verification và runtime features"]
~~~

Chiến lược chỉ quyết định package nào là module base package. Các quy tắc về API công khai, named interface, phụ thuộc được phép và phần triển khai nội bộ vẫn được mô hình hóa theo metadata module và cấu trúc package.

## Ví dụ chiến lược tùy chỉnh

Giả sử package gốc là com.acme.shop. Nhóm quy ước ba module nghiệp vụ là orders, inventory và catalog. Các package khác như configuration hoặc shared không được chọn làm module nghiệp vụ độc lập.

Tạo lớp chiến lược trong production source set:

~~~java
package com.acme.shop.architecture;

import java.util.Set;
import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class DomainModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULE_NAMES =
        Set.of("orders", "inventory", "catalog");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(
            JavaPackage rootPackage) {

        String prefix = rootPackage.getName() + ".";

        return rootPackage.getDirectSubPackages().stream()
            .filter(candidate -> {
                String packageName = candidate.getName();

                if (!packageName.startsWith(prefix)) {
                    return false;
                }

                String relativeName = packageName.substring(prefix.length());
                return MODULE_NAMES.contains(relativeName);
            });
    }
}
~~~

Phương thức nhận package gốc, duyệt các package con trực tiếp và chỉ trả về package có tên nằm trong tập MODULE_NAMES. Tập tên được khai báo rõ giúp quy tắc dễ đọc và dễ review.

Với cấu trúc ví dụ, kết quả là ba module:

- com.acme.shop.orders
- com.acme.shop.inventory
- com.acme.shop.catalog

Khi thêm module billing, nhóm cần cập nhật quy ước phát hiện để billing được đưa vào mô hình. Nếu muốn module mới tự động được phát hiện, có thể thay tập tên cố định bằng một quy ước đặt tên nhất quán, chẳng hạn một tiền tố package dành riêng cho module nghiệp vụ.

Đây là ví dụ cho cấu trúc có module nằm ở package con trực tiếp. Nếu module nằm sâu hơn trong cây package, hãy chọn API duyệt package con phù hợp của phiên bản Spring Modulith đang sử dụng và viết quy tắc kiểm tra độ sâu một cách tường minh. Tránh trả về đồng thời cả package cha và package con nếu dự án không chủ đích sử dụng nested application modules.

## Đăng ký chiến lược trong production configuration

Đặt cấu hình trong src/main/resources/application.properties:

~~~properties
spring.modulith.detection-strategy=com.acme.shop.architecture.DomainModuleDetectionStrategy
~~~

Giá trị của thuộc tính là tên đầy đủ của lớp triển khai ApplicationModuleDetectionStrategy. Lớp cần nằm trong production classpath để Spring Modulith có thể khởi tạo chiến lược khi ứng dụng chạy.

Cấu trúc file nên có dạng:

~~~text
src
├── main
│   ├── java
│   │   └── com/acme/shop
│   │       ├── ShopApplication.java
│   │       └── architecture
│   │           └── DomainModuleDetectionStrategy.java
│   └── resources
│       └── application.properties
└── test
    └── java
        └── com/acme/shop
            └── ModularityTests.java
~~~

Nếu dự án có application profile riêng, hãy bảo đảm cấu hình detection strategy được nạp trong các profile chạy production. Tránh chỉ đặt thuộc tính trong application-test.properties hoặc src/test/resources nếu runtime cũng cần sử dụng nó.

## Khai báo dependency cho runtime support

Nếu chỉ sử dụng ApplicationModules để kiểm tra kiến trúc trong test hoặc tạo tài liệu, dependency cần thiết có thể chỉ nằm trong test scope.

Khi dùng các thành phần runtime của Spring Modulith, cần khai báo spring-modulith-core ở compile-time vì lớp chiến lược production triển khai API này. Đồng thời, thêm spring-modulith-runtime để kích hoạt runtime auto-configuration.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.modulith:spring-modulith-core")
    runtimeOnly("org.springframework.modulith:spring-modulith-runtime")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-core</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Hãy để Spring Modulith BOM quản lý phiên bản các artifact nếu dự án đã sử dụng BOM. Giữ các artifact cùng một dòng phiên bản tương thích.

spring-modulith-runtime đăng ký các thành phần runtime như ApplicationModulesRuntime, SpringBootApplicationRuntime và RuntimeApplicationModuleVerifier. Runtime verifier chỉ kiểm tra cấu trúc module khi thuộc tính bật verification được cấu hình thành true.

Ví dụ bật kiểm chứng khi ứng dụng khởi động:

~~~properties
spring.modulith.runtime.verification-enabled=true
~~~

Khi phát hiện vi phạm kiến trúc, runtime verifier có thể làm quá trình khởi động thất bại. Đây là cách đưa quy tắc module vào vòng đời chạy ứng dụng, giúp phát hiện cấu trúc không hợp lệ ngay khi triển khai hoặc khởi động.

Nếu chỉ cần ApplicationModuleInitializer hoặc các tính năng runtime khác mà không muốn kiểm chứng tự động khi startup, không bật thuộc tính verification-enabled. Hai lựa chọn này có mục đích riêng.

## Kiểm tra mô hình module trong test

Sau khi đưa chiến lược và cấu hình vào production sources, test kiến trúc có thể sử dụng cùng quy tắc với ứng dụng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesProductionModuleArrangement() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test nên chạy với cấu hình application phù hợp để phát hiện cùng chiến lược đã đăng ký trong production. Khi cần kiểm tra danh sách module, có thể in mô hình ra log hoặc console trong quá trình phát triển:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
~~~

Đối chiếu kết quả với quy ước package của dự án. Xác nhận các module nghiệp vụ dự kiến đã được phát hiện, package hạ tầng không bị đưa vào ngoài ý muốn và các nested module được mô hình hóa đúng.

Test kiểm chứng cấu trúc nên tiếp tục chạy trong CI. Runtime verification là lớp kiểm tra bổ sung khi ứng dụng khởi động; nó không thay thế việc chạy test kiến trúc trong pipeline phát triển.

## Phân biệt test-only customization và production customization

| Nhu cầu | Vị trí chiến lược và đăng ký | Lý do |
|---|---|---|
| Chỉ kiểm chứng kiến trúc trong test | src/test/java và src/test/resources có thể đủ | Chỉ test cần quy tắc tùy chỉnh |
| Chỉ sinh tài liệu trong test | Test sources có thể đủ | Documenter chạy trong quy trình test/tạo tài liệu |
| Runtime verification | src/main/java và src/main/resources | Runtime cần nạp cùng chiến lược |
| ApplicationModuleInitializer | src/main/java và src/main/resources nếu dùng custom detection | Thứ tự initializer dựa trên mô hình module tại runtime |
| Actuator hoặc observability dựa trên module | Production sources | Các tính năng production cần thấy đúng module arrangement |

Không nên sao chép hai bản chiến lược gần giống nhau vào test và production. Hai bản có thể dần khác nhau và làm test xác minh một mô hình trong khi ứng dụng chạy với mô hình khác. Hãy đặt một chiến lược dùng chung trong production sources nếu cả hai môi trường đều cần nó.

## Những lỗi thường gặp

**Chỉ đặt lớp chiến lược trong src/test/java.** Test chạy thành công nhưng production artifact không chứa lớp đó. Khi runtime cố nạp tên lớp trong cấu hình, ứng dụng có thể không khởi tạo được chiến lược hoặc sử dụng quy tắc mặc định khác.

**Chỉ đặt thuộc tính trong src/test/resources.** Test có thể đọc được cấu hình, nhưng runtime không có thuộc tính đăng ký. Hãy đặt cấu hình ở application.properties production khi runtime cần nó.

**Quên spring-modulith-core ở compile-time.** Lớp chiến lược trong src/main/java không thể biên dịch nếu interface và JavaPackage không có trên compile classpath.

**Cho rằng spring-modulith-runtime tự bật verification.** Artifact này cung cấp runtime auto-configuration, nhưng kiểm chứng khi startup được điều khiển bằng spring.modulith.runtime.verification-enabled. Giá trị mặc định là false.

**Chọn package quá rộng.** Nếu strategy trả về cả package dùng chung, cấu hình hoặc package kỹ thuật, mô hình module có thể không còn phản ánh ranh giới nghiệp vụ. Hãy viết quy tắc rõ ràng và kiểm tra danh sách module kết quả.

**Để test và production dùng hai chiến lược khác nhau.** Kết quả kiểm thử khi đó không còn đại diện chính xác cho mô hình được sử dụng lúc chạy. Hãy chia sẻ cùng lớp chiến lược và cấu hình nếu cả hai môi trường cần custom detection.

**Nhầm custom module detection với custom named interface detection.** getModuleBasePackages chọn package nào trở thành module. Nếu mục tiêu là tự động chọn package API bên trong từng module, hãy xem xét override detectNamedInterfaces thay vì thay đổi danh sách module base package.

## Quy trình triển khai

Khi chuyển custom detection sang production, thực hiện theo trình tự:

1. Xác định quy ước package và danh sách module mà ứng dụng thực sự cần.
2. Kiểm tra xem direct-subpackages hoặc explicitly-annotated đã đủ đáp ứng hay chưa.
3. Nếu cần logic riêng, triển khai ApplicationModuleDetectionStrategy trong src/main/java.
4. Đăng ký tên lớp qua spring.modulith.detection-strategy trong src/main/resources/application.properties.
5. Khai báo spring-modulith-core ở compile-time và spring-modulith-runtime ở runtime nếu sử dụng runtime support.
6. Chạy test ApplicationModules.verify() với cấu hình production strategy.
7. Nếu muốn xác minh ngay khi ứng dụng khởi động, bật spring.modulith.runtime.verification-enabled.
8. Kiểm tra log hoặc kết quả mô hình để bảo đảm danh sách module đúng với thiết kế.

## Bài tập vận dụng

Một ứng dụng có package gốc com.acme.fulfillment. Các module nghiệp vụ nằm ở orders, stock và delivery. Package configuration và shared chỉ chứa cấu hình và thành phần dùng chung. Nhóm đã viết CustomModuleDetectionStrategy trong src/test/java nên test kiến trúc chạy đúng. Tuy nhiên, ứng dụng cũng dùng ApplicationModuleInitializer và muốn bật runtime verification.

Hãy xử lý tình huống:

1. Chuyển lớp chiến lược vào src/main/java/com/acme/fulfillment/architecture.
2. Cấu hình spring.modulith.detection-strategy trong src/main/resources/application.properties.
3. Bổ sung spring-modulith-core ở compile-time và spring-modulith-runtime ở runtime.
4. Giữ test ApplicationModules.verify() để kiểm tra mô hình được phát hiện.
5. Bật spring.modulith.runtime.verification-enabled nếu muốn ứng dụng xác minh cấu trúc khi startup.
6. Xác nhận orders, stock và delivery được phát hiện; configuration và shared được xử lý theo chủ đích thiết kế.

Kết quả mong đợi: test và runtime sử dụng cùng một chiến lược phát hiện module. Runtime components có thể đọc mô hình module thống nhất, và startup verification được thực thi khi nhóm bật cấu hình tương ứng.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích vì sao runtime features cần custom detection trong production sources, triển khai ApplicationModuleDetectionStrategy, đăng ký chiến lược trong application.properties production, khai báo dependency đúng scope và phân biệt kiểm chứng kiến trúc trong test với kiểm chứng tự động khi ứng dụng khởi động.

Tài liệu tham khảo:

- [Spring Modulith — Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
