# Kích hoạt explicitly-annotated detection

Spring Modulith mặc định nhận diện application module bằng cách xem các package con trực tiếp của package chứa lớp Spring Boot là module. Quy ước này thuận tiện khi ứng dụng đã có cấu trúc package rõ ràng. Với hệ thống legacy, có thể tồn tại nhiều package tiện ích, adapter hoặc mã dùng chung ở cùng cấp với các module nghiệp vụ. Nếu muốn chủ động chọn package nào là application module, hãy dùng chiến lược explicitly-annotated.

Chiến lược này chỉ nhận diện package được đánh dấu bằng Spring Modulith @ApplicationModule hoặc jMolecules @Module. Bài thực hành này hướng dẫn bật chiến lược, đánh dấu các module nghiệp vụ, kiểm tra mô hình được phát hiện và xử lý các package bị bỏ sót.

## 1. Mục tiêu và kết quả cần đạt

Sau bài thực hành, bạn sẽ có thể:

- Giải thích khác biệt giữa chiến lược mặc định direct-subpackages và explicitly-annotated.
- Bật chiến lược explicitly-annotated bằng property spring.modulith.detection-strategy.
- Đánh dấu package gốc của từng application module bằng @ApplicationModule.
- Xác nhận package chưa được đánh dấu không bị nhận diện nhầm thành module.
- Dùng ApplicationModules để xem mô hình và verify() để kiểm tra ranh giới.
- Nhận biết lỗi thường gặp khi thiếu package-info.java hoặc cấu hình property không đến được JVM chạy test.

## 2. Chuẩn bị cấu trúc ứng dụng

Giả sử ứng dụng Spring Boot có package gốc com.example.shop và các package sau:

~~~text
com.example.shop
├── Application.java
├── orders
│   ├── OrderManagement.java
│   └── internal
│       └── OrderRepository.java
├── inventory
│   ├── StockAvailability.java
│   └── internal
│       └── StockRepository.java
├── shipping
│   └── ShippingService.java
└── shared
    └── DateTimeProvider.java
~~~

Trong ví dụ này, orders, inventory và shipping là các application module. Package shared chứa tiện ích dùng chung và chưa được xác định là một module nghiệp vụ độc lập.

Với chiến lược mặc định direct-subpackages, Spring Modulith có thể xem cả orders, inventory, shipping và shared là các module vì chúng đều là package con trực tiếp của com.example.shop.

Khi chuyển sang explicitly-annotated, chỉ những package được đánh dấu mới trở thành application module. Vì vậy, ta sẽ đánh dấu ba package nghiệp vụ và để shared không được đánh dấu.

## 3. Đánh dấu package gốc của module

Trong Java, cách thông dụng để đặt annotation cho một package là tạo file package-info.java ngay trong package đó.

Tạo file src/main/java/com/example/shop/orders/package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule
package com.example.shop.orders;
~~~

Tạo file src/main/java/com/example/shop/inventory/package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
~~~

Tạo file src/main/java/com/example/shop/shipping/package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule
package com.example.shop.shipping;
~~~

Không tạo annotation @ApplicationModule cho package shared trong bài tập này. Package đó không phải một module nghiệp vụ độc lập nên không được đưa vào danh sách module được phát hiện.

Nếu muốn đặt tên hiển thị cho module trong tài liệu, có thể khai báo thuộc tính displayName:

~~~java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng"
)
package com.example.shop.orders;
~~~

displayName chỉ hỗ trợ tài liệu và khả năng đọc hiểu. Nó không thay thế identifier của module trong allowedDependencies.

## 4. Bật explicitly-annotated detection

Chiến lược được chọn bằng property:

~~~properties
spring.modulith.detection-strategy=explicitly-annotated
~~~

Property này được Spring Modulith dùng khi xây dựng mô hình application module. Với các lệnh test chạy trong JVM riêng, hãy bảo đảm property được truyền vào JVM thực thi test.

Ví dụ cấu hình Maven Surefire trong pom.xml:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.modulith.detection-strategy>
                explicitly-annotated
            </spring.modulith.detection-strategy>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Với Gradle, cấu hình system property cho test task:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty(
        "spring.modulith.detection-strategy",
        "explicitly-annotated"
    )
}
~~~

Nếu cần kích hoạt khi chạy ứng dụng production, truyền property vào JVM khởi chạy ứng dụng:

~~~bash
java -Dspring.modulith.detection-strategy=explicitly-annotated -jar application.jar
~~~

Trong môi trường triển khai, có thể truyền system property qua cấu hình JVM của container hoặc service. Hãy bảo đảm cùng một chiến lược được sử dụng ở những nơi cần xây dựng mô hình module: architecture test, tài liệu được sinh tự động và runtime features.

Không chỉ thêm property vào một file test rồi giả định mọi JVM đều nhận được nó. Nếu build tool fork JVM để chạy test, cần kiểm tra system property đã được chuyển vào test process.

## 5. Kiểm tra danh sách module được phát hiện

Tạo một test để in mô hình module:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void listsExplicitlyAnnotatedModules() {
        var modules = ApplicationModules.of(Application.class);

        System.out.println(modules);
    }
}
~~~

Chạy test với property explicitly-annotated đã cấu hình. Kết quả mong đợi là mô hình có ba module:

- orders
- inventory
- shipping

Package shared không xuất hiện như một application module độc lập vì package này không được đánh dấu.

Để kiểm tra trực tiếp, có thể lấy module theo tên:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionAssertions {

    @Test
    void detectsOnlyAnnotatedPackages() {
        var modules = ApplicationModules.of(Application.class);

        assertThat(modules.getModuleByName("orders")).isPresent();
        assertThat(modules.getModuleByName("inventory")).isPresent();
        assertThat(modules.getModuleByName("shipping")).isPresent();
        assertThat(modules.getModuleByName("shared")).isEmpty();
    }
}
~~~

Đoạn assertion sử dụng AssertJ. Nếu test class chưa có AssertJ trên test classpath, dùng assertion library đã được dự án cấu hình hoặc kiểm tra mô hình bằng output của modules.

Lưu ý: package không được nhận diện thành module không tự động trở thành một module nội bộ khác. Các kiểu trong package không được gán vào application module có thể nằm ngoài đồ thị module mà Spring Modulith kiểm tra. Vì vậy, không nên bỏ annotation ở một module nghiệp vụ chỉ để làm cho architecture test hết báo lỗi.

## 6. Kiểm tra ranh giới sau khi nhận diện

Khi đã xác nhận đúng danh sách module, thêm bài kiểm tra cấu trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Giả sử shipping phụ thuộc vào API của inventory. Đặt hợp đồng trong package gốc hoặc một named interface được công khai. Ví dụ:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.inventory.api;
~~~

Khai báo dependency được phép trên package gốc của shipping:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shop.shipping;
~~~

Nếu package shipping đã có @ApplicationModule để bật detection, hãy gộp các thuộc tính vào cùng một annotation thay vì tạo hai khai báo package-info.java:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shop.shipping;
~~~

Sau đó, chạy lại verify(). Chiến lược explicitly-annotated xác định package nào là module; các quy tắc named interface và allowedDependencies tiếp tục kiểm soát cách module phụ thuộc vào nhau.

## 7. So sánh với chiến lược mặc định

| Tiêu chí | direct-subpackages | explicitly-annotated |
|---|---|---|
| Cách chọn module | Mọi package con trực tiếp của package gốc | Chỉ package được đánh dấu bằng @ApplicationModule hoặc jMolecules @Module |
| Công sức ban đầu | Ít, nếu cấu trúc package đã chuẩn | Cần đánh dấu từng module |
| Package tiện ích cùng cấp | Có thể bị nhận diện thành module | Bị bỏ qua nếu không được đánh dấu |
| Kiểm soát danh sách module | Dựa trên cấu trúc package | Chủ động qua annotation |
| Phù hợp | Ứng dụng có quy ước package module nhất quán | Legacy code hoặc ứng dụng cần chọn module tường minh |

Chiến lược explicitly-annotated đặc biệt hữu ích khi một ứng dụng có nhiều package cùng cấp nhưng không phải package nào cũng đại diện cho một module nghiệp vụ. Đổi lại, nhóm phải duy trì annotation khi tạo module mới.

## 8. Dùng jMolecules @Module khi dự án đã áp dụng jMolecules

Ngoài @ApplicationModule, chiến lược explicitly-annotated cũng nhận diện package được đánh dấu bằng annotation @Module của jMolecules.

Ví dụ package-info.java:

~~~java
@org.jmolecules.ddd.annotation.Module
package com.example.shop.orders;
~~~

Chỉ dùng cách này khi dự án đã có dependency jMolecules phù hợp. Nếu dự án chưa sử dụng jMolecules, Spring Modulith @ApplicationModule là lựa chọn trực tiếp và không cần thêm annotation framework khác.

Không đánh dấu cùng package bằng nhiều annotation module chỉ để thử nghiệm. Hãy chọn một cách khai báo nhất quán cho codebase và bảo đảm các module mới tuân theo quy ước đó.

## 9. Xử lý package lồng nhau

Chiến lược explicitly-annotated cũng hữu ích khi một module lớn có các phần cần được quản lý như nested application module.

Ví dụ:

~~~text
com.example.shop
└── inventory
    ├── package-info.java
    ├── StockManagement.java
    └── replenishment
        ├── package-info.java
        └── ReplenishmentService.java
~~~

Nếu package com.example.shop.inventory.replenishment được đánh dấu @ApplicationModule, Spring Modulith có thể nhận diện nó như nested module của inventory ở các phiên bản hỗ trợ nested application modules.

Chỉ đánh dấu package lồng nhau khi nó có trách nhiệm và ranh giới riêng cần quản lý. Các package internal, persistence, adapter hoặc implementation thông thường nên tiếp tục nằm trong module cha và không cần đánh dấu.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy module orders | Thiếu package-info.java hoặc package chưa có annotation | Đánh dấu package gốc bằng @ApplicationModule |
| Package shared vẫn xuất hiện | Property chưa được áp dụng hoặc test JVM dùng chiến lược mặc định | Kiểm tra system property trong đúng JVM chạy test |
| Không có module nào được phát hiện | Chưa đánh dấu package module nào hoặc sai package gốc | Đánh dấu các package nghiệp vụ và kiểm tra Application.class |
| Module mới không xuất hiện | Quên annotation khi tạo package mới | Thêm package-info.java với @ApplicationModule |
| verify() vẫn báo dependency không hợp lệ | Detection đã đúng nhưng allowedDependencies hoặc named interface chưa đúng | Kiểm tra module identifier, named interface và phía consumer |
| Test và production phát hiện khác nhau | Hai môi trường dùng property hoặc classpath khác nhau | Đồng bộ detection strategy và annotation trong production sources |

Khi chẩn đoán, kiểm tra theo thứ tự: package gốc của Application, system property trong JVM, package-info.java của module, rồi mới xem các dependency và named interface. Cách này giúp phân biệt lỗi phát hiện module với lỗi vi phạm dependency.

## 11. Checklist hoàn thành bài thực hành

- [ ] Xác định đúng package gốc chứa Application.java.
- [ ] Liệt kê các package nghiệp vụ cần trở thành application module.
- [ ] Tạo package-info.java và đánh dấu từng package bằng @ApplicationModule.
- [ ] Để package tiện ích shared không được đánh dấu nếu nó không phải module độc lập.
- [ ] Truyền spring.modulith.detection-strategy=explicitly-annotated vào JVM chạy test.
- [ ] In ApplicationModules và xác nhận danh sách module đúng.
- [ ] Chạy ApplicationModules.of(Application.class).verify().
- [ ] Kiểm tra các named interface và allowedDependencies của consumer.
- [ ] Đồng bộ chiến lược phát hiện với runtime features nếu production sử dụng chúng.
- [ ] Ghi nhận quy ước: mọi module mới phải được đánh dấu tường minh.

## 12. Bài tập mở rộng

1. Tạo một package analytics cùng cấp với orders và inventory nhưng không đánh dấu @ApplicationModule.
2. Chạy test với direct-subpackages và ghi nhận danh sách module.
3. Bật explicitly-annotated, đánh dấu orders, inventory và shipping, rồi chạy lại test.
4. So sánh danh sách module giữa hai chiến lược và giải thích vì sao analytics không xuất hiện trong mô hình mới.
5. Đánh dấu analytics bằng @ApplicationModule và xác nhận module xuất hiện sau khi chạy lại.
6. Tạo một package nested như inventory.replenishment, đánh dấu nó và quan sát mô hình nested module nếu phiên bản Spring Modulith của dự án hỗ trợ.
7. Tạm bỏ annotation khỏi một module nghiệp vụ, xác nhận module biến mất khỏi mô hình, rồi khôi phục annotation.
8. Chạy verify() và giải thích sự khác nhau giữa lỗi module không được phát hiện và lỗi module phụ thuộc sai API.

Kết quả cuối cùng cần chứng minh được rằng danh sách application module được kiểm soát bằng annotation, package tiện ích không bị nhận diện nhầm, và các module nghiệp vụ vẫn được Spring Modulith xác minh theo đúng ranh giới mong muốn.

## Tài liệu tham khảo

- [Customizing Application Module Detection – Spring Modulith Reference](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
