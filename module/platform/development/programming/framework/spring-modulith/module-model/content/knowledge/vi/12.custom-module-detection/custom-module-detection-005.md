# Đăng ký strategy trong test sources

Khi quy tắc nhận diện application module chỉ phục vụ kiểm tra kiến trúc và tạo tài liệu, ta có thể đặt cả **custom detection strategy** lẫn cấu hình đăng ký của nó trong test sources. Cách tổ chức này giúp Spring Modulith sử dụng quy tắc riêng khi chạy các bài kiểm tra, trong khi ứng dụng production vẫn giữ cấu hình và classpath của nó.

Spring Modulith cho phép triển khai `ApplicationModuleDetectionStrategy` để tự chọn package nào là base package của module. Strategy được đăng ký bằng thuộc tính `spring.modulith.detection-strategy`, với giá trị là tên đầy đủ của lớp triển khai. Trong một cấu hình chỉ dành cho test, lớp đặt ở `src/test/java` và thuộc tính đặt ở `src/test/resources/application.properties`.

## 1. Vì sao đăng ký trong test sources?

`ApplicationModules` thường được dùng trong các bài kiểm tra kiến trúc để phát hiện module, kiểm tra dependency và tạo tài liệu. Nếu quy tắc tùy chỉnh chỉ phục vụ các công việc đó, ta không cần đưa implementation strategy vào artifact production.

Ví dụ, cấu trúc mã nguồn có thể tổ chức như sau:

```text
shop/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/example/shop/
│   │           ├── ShopApplication.java
│   │           ├── modules/
│   │           │   ├── catalog/
│   │           │   ├── orders/
│   │           │   └── inventory/
│   │           └── shared/
│   └── test/
│       ├── java/
│       │   └── com/example/testarchitecture/
│       │       ├── TestModuleDetectionStrategy.java
│       │       └── ModuleStructureTests.java
│       └── resources/
│           └── application.properties
└── build.gradle
```

Trong ví dụ này, các module nghiệp vụ được đặt dưới `com.example.shop.modules`, còn `shared` nằm ngoài nhánh đó. Strategy tùy chỉnh sẽ chỉ chọn các package con trực tiếp của `modules`. Cả lớp strategy và thuộc tính đăng ký chỉ xuất hiện trên test classpath.

Khi test chạy, Spring Modulith có thể nạp strategy để dựng mô hình phục vụ `ApplicationModules.verify()`. Khi đóng gói và chạy ứng dụng production, các lớp trong `src/test/java` và tài nguyên trong `src/test/resources` không được đưa vào artifact production theo cấu hình build chuẩn.

## 2. Hiểu hợp đồng của ApplicationModuleDetectionStrategy

`ApplicationModuleDetectionStrategy` nằm trong package `org.springframework.modulith.core`. Interface này yêu cầu triển khai một phương thức:

```java
Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage);
```

Spring Modulith truyền vào package gốc của ứng dụng — package chứa lớp Spring Boot application — và strategy trả về một `Stream<JavaPackage>` gồm các package sẽ được xem là base package của application module.

Hai kiểu dữ liệu quan trọng:

- `JavaPackage` đại diện cho một package trong mô hình phân tích của Spring Modulith.
- `Stream<JavaPackage>` là danh sách các package mà strategy chọn làm module base package.

`JavaPackage.getDirectSubPackages()` trả về các package con trực tiếp; `getLocalName()` trả về đoạn tên cuối cùng của package. Ta có thể kết hợp chúng để áp dụng quy ước riêng cho package tree.

## 3. Viết strategy trong src/test/java

Giả sử dự án muốn nhận diện các module nghiệp vụ nằm dưới package `modules`:

```text
com.example.shop
├── ShopApplication.java
├── modules
│   ├── catalog
│   ├── orders
│   └── inventory
└── shared
```

Tạo lớp `TestModuleDetectionStrategy.java` trong `src/test/java/com/example/testarchitecture`:

```java
package com.example.testarchitecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class TestModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(candidate -> candidate.getLocalName().equals("modules"))
                .flatMap(candidate -> candidate.getDirectSubPackages().stream());
    }
}
```

Phương thức thực hiện ba thao tác:

1. Lấy các package con trực tiếp của application root package.
2. Chỉ giữ package có tên cục bộ là `modules`.
3. Trả về các package con trực tiếp bên trong `modules`, tức `catalog`, `orders` và `inventory`.

Strategy không trả về `shared`, vì package đó nằm trực tiếp dưới application root nhưng không thuộc nhánh `modules`. Nó cũng không trả về package `modules` làm module, vì các module nghiệp vụ thực sự nằm sâu hơn một cấp.

Đây chỉ là một quy tắc minh họa. Trong dự án thực tế, có thể chọn package theo hậu tố, tiền tố, annotation riêng hoặc một cấu trúc package khác. Điều quan trọng là strategy phải trả về đúng các package đại diện cho ranh giới nghiệp vụ.

## 4. Đăng ký strategy trong application.properties của test

Tạo hoặc cập nhật file `src/test/resources/application.properties`:

```properties
spring.modulith.detection-strategy=com.example.testarchitecture.TestModuleDetectionStrategy
```

Giá trị của thuộc tính là fully qualified class name của strategy. Khi tạo mô hình module trong test, Spring Modulith dùng lớp này thay cho chiến lược phát hiện mặc định.

Hãy bảo đảm:

- Tên package trong property khớp chính xác với khai báo `package` của lớp strategy.
- Lớp strategy có mặt trên test classpath và có thể được khởi tạo.
- File `application.properties` nằm trong `src/test/resources`, không nằm trong `src/main/resources`, nếu mục tiêu là chỉ áp dụng cho test.

Với Maven và Gradle theo cấu trúc chuẩn, `src/test/resources` được đưa vào test runtime classpath. Không cần tạo thêm file đăng ký `META-INF/spring.factories` cho `ApplicationModuleDetectionStrategy` theo cách cấu hình hiện hành bằng property này.

## 5. Dùng strategy trong bài kiểm tra kiến trúc

Sau khi đăng ký, bài test có thể tạo mô hình từ lớp Spring Boot application và gọi `verify()`:

```java
package com.example.testarchitecture;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesTheCustomModuleArrangement() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);

        Set<String> moduleNames = StreamSupport.stream(modules.spliterator(), false)
                .map(ApplicationModule::getName)
                .collect(Collectors.toSet());

        assertEquals(Set.of("catalog", "orders", "inventory"), moduleNames);
        modules.verify();
    }
}
```

Khi chạy test, Spring Modulith tạo mô hình dựa trên strategy đã đăng ký. Test vừa in các module để tiện quan sát, vừa so sánh tập tên module với danh sách mong đợi để phát hiện trường hợp strategy không chọn đúng package. Sau đó, `verify()` kiểm tra các quy tắc kiến trúc trên mô hình đó, chẳng hạn dependency giữa module, chu trình phụ thuộc và truy cập package nội bộ.

Lưu ý: `ApplicationModules.of(...)` tạo mô hình kiến trúc; nó không cần khởi động toàn bộ Spring `ApplicationContext`. Vì vậy, bài kiểm tra kiến trúc thông thường có thể là JUnit test thuần, miễn là các lớp cần phân tích và cấu hình test có trên classpath.

## 6. Dependency cần có trong test classpath

Custom strategy triển khai interface thuộc `spring-modulith-core`. Do đó, test compile classpath cần nhìn thấy artifact này. Nếu dependency đã được cung cấp bởi bộ starter test đang dùng, không cần khai báo trùng. Nếu chưa có, có thể thêm dependency chỉ dành cho test.

Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.modulith:spring-modulith-core")
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-core</artifactId>
    <scope>test</scope>
</dependency>
```

Hãy để Spring Boot dependency management hoặc Spring Modulith BOM quản lý phiên bản tương thích thay vì tự chọn một phiên bản không đồng bộ với phần còn lại của dự án.

## 7. Phân biệt strategy test-only và strategy dùng lúc runtime

Đăng ký trong test sources phù hợp khi custom detection chỉ phục vụ verification và documentation. Nếu ứng dụng dùng các thành phần Spring Modulith ở runtime, ví dụ `ApplicationModuleInitializer`, hoặc các tính năng production như actuator và observability dựa trên module arrangement, cấu hình test-only sẽ không đủ.

| Nhu cầu | Vị trí strategy | Vị trí đăng ký | Dependency core |
|---|---|---|---|
| Chỉ kiểm tra kiến trúc và tạo tài liệu trong test | `src/test/java` | `src/test/resources/application.properties` | Có trên test compile/runtime classpath |
| Dùng module arrangement bởi thành phần runtime | `src/main/java` | `src/main/resources/application.properties` | Compile-time dependency, ví dụ Gradle `implementation` |

Khi cần runtime support, chuyển cả implementation strategy và cấu hình đăng ký sang production sources. Đồng thời khai báo `spring-modulith-core` là compile-time dependency để mã production có thể nạp và sử dụng strategy.

Gradle cho trường hợp runtime:

```kotlin
dependencies {
    implementation("org.springframework.modulith:spring-modulith-core")
}
```

Không để một tính năng runtime phụ thuộc vào strategy chỉ tồn tại trong test classpath. Khi chạy từ artifact production, các class và tài nguyên test không có mặt nên strategy sẽ không được nạp.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Chỉ đặt class strategy trong `src/test/java` là đủ | Cần đăng ký fully qualified class name qua `spring.modulith.detection-strategy` trong test configuration |
| Đặt property trong `src/main/resources` dù chỉ muốn dùng cho test | Cấu hình sẽ đi vào production artifact; dùng `src/test/resources` cho test-only |
| Dùng `spring.factories` để đăng ký strategy này | Cấu hình hiện hành dùng property `spring.modulith.detection-strategy`; `ApplicationModuleSourceFactory` là SPI khác có cơ chế `spring.factories` riêng |
| Strategy trả về package bất kỳ để Spring tự hiểu ý định | Mỗi phần tử trong stream chính là một module base package; phải chọn đúng ranh giới |
| Strategy test-only tự động có hiệu lực khi chạy ứng dụng production | Test classes và test resources không được đóng gói vào artifact production |
| Dùng strategy test-only cho runtime initializer hoặc actuator | Runtime support cần customization trong production sources và `spring-modulith-core` ở compile-time |

## 9. Quy trình áp dụng

Khi custom module detection chỉ phục vụ kiểm thử, hãy làm theo trình tự:

1. Xác định package tree và quy tắc chọn module base package.
2. Viết implementation `ApplicationModuleDetectionStrategy` trong `src/test/java`.
3. Đăng ký fully qualified class name trong `src/test/resources/application.properties` bằng `spring.modulith.detection-strategy`.
4. Tạo `ApplicationModules.of(ShopApplication.class)` trong bài test và quan sát các module được phát hiện.
5. Gọi `verify()` để kiểm tra dependency và ranh giới module.
6. Nếu sau này cần dùng module arrangement ở runtime, chuyển strategy và cấu hình sang production sources, đồng thời thêm compile-time dependency phù hợp.

Với cách tổ chức này, nhóm có thể thử nghiệm quy tắc package riêng và bảo vệ kiến trúc trong CI mà không đưa logic phát hiện chỉ phục vụ test vào production artifact. Khi quy tắc đã ổn định hoặc có nhu cầu runtime, nhóm có thể chuyển customization sang production sources một cách có chủ đích.

Tài liệu tham khảo: [Spring Modulith – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.customizing-detection), [ApplicationModuleDetectionStrategy Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html), [JavaPackage Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html).
