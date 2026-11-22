# Phạm vi quét của `@ComponentScan` và vị trí package trong Spring Core Container

## 1. Vì sao class có `@Component` nhưng Spring vẫn không tìm thấy bean?

Giả sử một ứng dụng có service sau:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

Một class mang `@Service` (vốn là một dạng chuyên biệt của `@Component`) có **đủ metadata để được phát hiện**, nhưng chưa chắc đã có bean `OrderService` trong Spring IoC Container. Để Spring đăng ký class thành bean theo component scanning, package của class phải nằm trong **phạm vi quét** của một cấu hình đã được kích hoạt, class phải là ứng viên hợp lệ và không bị các filter/condition loại bỏ.

Ví dụ nếu ứng dụng chỉ quét `com.example.billing`, Spring không tự đi sang `com.example.shop.service`. Lỗi thường bộc lộ khi constructor cần `OrderService` mà không có bean tương ứng:

```text
No qualifying bean of type 'com.example.shop.service.OrderService' available
```

Đây là ví dụ về **nội dung thông báo lỗi** có thể gặp; stack trace đầy đủ thay đổi theo điểm tiêm và phiên bản Spring.

Mục tiêu của bài này là nắm chính xác:

1. `@ComponentScan` chọn gói gốc và các gói con ra sao;
2. sự khác biệt giữa package mặc định, `basePackages` và `basePackageClasses`;
3. vị trí đặt configuration class hoặc `@SpringBootApplication` ảnh hưởng việc phát hiện component như thế nào;
4. cách quét có kiểm soát qua nhiều package/module mà không mở phạm vi tùy tiện;
5. cách chẩn đoán bean bị thiếu và tránh các sai lầm về package, classpath, filter và condition.

## 2. `@ComponentScan` thực sự quét gì?

`@ComponentScan` thuộc package `org.springframework.context.annotation`. Khi một class cấu hình được xử lý, annotation này yêu cầu Spring tìm các **component candidates** trong một hoặc nhiều base package. Scanner chủ yếu đọc metadata các file `.class` khả dụng trên classpath (hoặc trong module path với điều kiện thích hợp) và đăng ký **bean definitions** cho các ứng viên hợp lệ.

Theo mặc định, ứng viên là class được chú thích bằng `@Component` hoặc một stereotype có meta-annotation `@Component`, như:

- `@Service` cho lớp nghiệp vụ;
- `@Repository` cho lớp truy cập dữ liệu;
- `@Controller` cho lớp web/controller;
- `@Configuration` cho lớp cấu hình;
- stereotype tự định nghĩa được meta-annotated bằng `@Component`.

Component scan **không** tự tìm mọi Java class trong package rồi tạo tất cả thành bean. Một class bình thường không mang stereotype phù hợp vẫn không trở thành bean chỉ vì classpath chứa nó. Ngoài ra, class ứng viên phải có thể được Spring tạo và không bị bỏ bởi filter hoặc điều kiện cấu hình.

Quy trình khái quát:

```text
Configuration được đăng ký vào ApplicationContext
                     |
                     v
        Đọc metadata @ComponentScan
                     |
                     v
   Chọn một hoặc nhiều base package cụ thể
                     |
                     v
   Duyệt class trong package và các package con
                     |
                     v
  Đánh giá stereotype + include/exclude filters
                     |
                     v
     Đăng ký bean definitions hợp lệ
                     |
                     v
Spring tạo bean, resolve dependency và quản lý vòng đời
```

**Hai giai đoạn khác nhau:** scanner đăng ký *định nghĩa bean*; việc tạo *instance* phụ thuộc vào scope, lazy initialization, dependency và tiến trình refresh của context. `@ComponentScan` không định nghĩa trình tự chạy method nghiệp vụ và không tự khởi động HTTP server.

## 3. Package của class cấu hình là mốc mặc định

Cấu hình sau **không chỉ định** `basePackages`:

```java
package com.example.shop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class ShopConfig {
}
```

Với cấu hình này, Spring mặc định bắt đầu quét tại **package của class khai báo `@ComponentScan`**, tức `com.example.shop`, rồi đi vào các **subpackage** như `com.example.shop.service` và `com.example.shop.persistence`.

Ví dụ cấu trúc Java:

```text
com.example/
├── shop/
│   ├── ShopConfig.java                  <-- có @ComponentScan
│   ├── service/
│   │   └── OrderService.java            <-- được quét
│   └── persistence/
│       └── OrderRepository.java         <-- được quét
├── shared/
│   └── TextConverter.java               <-- KHÔNG được quét
└── billing/
    └── InvoiceService.java              <-- KHÔNG được quét
```

Package `com.example.shared` và `com.example.billing` là **package ngang cấp** với `com.example.shop`. Scanner không tự lên package cha `com.example` để đi sang các nhánh ngang cấp.

| Class/package | So với base package `com.example.shop` | Được xét bởi lượt scan này? |
| --- | --- | --- |
| `com.example.shop.ShopConfig` | Cùng package | Có |
| `com.example.shop.service.OrderService` | Package con | Có |
| `com.example.shop.persistence.OrderRepository` | Package con | Có |
| `com.example.shared.TextConverter` | Nhánh ngang cấp | Không |
| `com.example.billing.InvoiceService` | Nhánh ngang cấp | Không |
| `com.example.BaseHelper` | Package cha | Không |

“Được xét bởi lượt scan” không đồng nghĩa “chắc chắn có bean”: class vẫn phải đáp ứng stereotype, bộ lọc, điều kiện và quy tắc đăng ký. Hơn nữa một bean ngoài vùng scan **vẫn có thể được đăng ký bằng cách khác**, chẳng hạn `@Bean` hoặc `@Import`.

### Package Java khác đường dẫn ngẫu nhiên trên máy

Với source `src/main/java/com/example/shop/service/OrderService.java`, phần quan trọng ở đầu file là:

```java
package com.example.shop.service;
```

Compiler tạo tên đầy đủ `com.example.shop.service.OrderService`. Component scanner dựa vào metadata class và package trên **runtime classpath/module path**, chứ không dò mọi thư mục có file `.java` trong workspace. Quy tắc tổ chức thư mục theo package rất hữu ích, nhưng gốc `src/main/java` là source root của build tool, không phải base package mặc định của `@ComponentScan`.

**Đặt configuration class vào default package** (file Java không khai báo `package`) là cấu trúc cần tránh. Khi không có base package cụ thể, quét từ gốc có thể khiến Spring tìm quá rộng trên classpath, gây hiệu năng kém và cấu hình ngoài ý muốn. Luôn dùng package có tên rõ ràng.

## 4. Chỉ rõ phạm vi bằng `basePackages`

Class cấu hình ở `com.example.app` vẫn có thể yêu cầu quét các package khác:

```java
@Configuration
@ComponentScan(basePackages = {"com.example.shop", "com.example.shared"})
class AppConfig { }
```

Đây là snippet cấu hình minh họa với imports thích hợp. Scanner xét hai package và mọi subpackage. Giá trị `basePackages` là **Java package name**, không phải đường dẫn `src/main/java` hoặc fully qualified tên class. Cú pháp `@ComponentScan("com.example.shop")` dùng thuộc tính `value`, là alias cho `basePackages`; tránh cấu hình hai alias với giá trị mâu thuẫn. Chuỗi package có thể bị bỏ sót khi refactor.

## 5. Chỉ rõ phạm vi bằng `basePackageClasses`

`basePackageClasses` chọn **package chứa một class hoặc interface làm marker** và các package con:

```java
@Configuration
@ComponentScan(basePackageClasses = {ShopPackage.class, SharedPackage.class})
class AppConfig { }
```

Giả định `ShopPackage` ở `com.example.shop` và `SharedPackage` ở `com.example.shared`. Marker không cần `@Component`, vì nó chỉ chọn gốc quét. Đặt marker tại **root feature**; dùng nhầm `OrderService.class` ở `com.example.shop.service` sẽ bỏ qua sibling `com.example.shop.persistence`. Khai báo `basePackages` và `basePackageClasses` cùng lúc sẽ chọn **hợp các vùng** đã liệt kê. Các ví dụ đầy đủ và đánh đổi về refactor được trình bày ngay ở bài chuyên sâu tiếp theo.

## 6. Ví dụ đầy đủ Java 17+: một package được quét, một package bị bỏ sót

Ứng dụng chạy với **Spring Framework 6.2.x** qua `spring-context`, không dùng Spring Boot. Hai `ApplicationContext` được tạo lần lượt:

- `ShopOnlyConfig` quét đúng `demo.shop`. Bean `OrderService` và `OrderRepository` được phát hiện, còn `SharedEncoder` ở `demo.shared` không xuất hiện.
- `ExpandedConfig` sử dụng `basePackageClasses` với hai marker tại `demo.shop` và `demo.shared`. Cả ba bean được phát hiện.

Mã Java trong ví dụ là chương trình thực, tách thành các file và package tương ứng; các đoạn rời ở các mục khác chỉ có tính minh họa.

### 6.1. Cấu trúc thư mục

```text
component-scan-packages/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── demo/
        ├── app/
        │   └── ScanPackagesDemo.java
        ├── shop/
        │   ├── ShopPackage.java
        │   ├── service/
        │   │   └── OrderService.java
        │   └── persistence/
        │       └── OrderRepository.java
        └── shared/
            ├── SharedPackage.java
            └── text/
                └── SharedEncoder.java
```

`settings.gradle`:

```groovy
rootProject.name = 'component-scan-packages'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.ScanPackagesDemo'
}
```

Dự án cần JDK 17+ và bản Gradle tương thích với JDK đang dùng.

### 6.2. Class ứng dụng và hai cấu hình scan

File `src/main/java/demo/app/ScanPackagesDemo.java`:

```java
package demo.app;

import demo.shop.ShopPackage;
import demo.shop.service.OrderService;
import demo.shared.SharedPackage;
import demo.shared.text.SharedEncoder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

public class ScanPackagesDemo {

    public static void main(String[] args) {
        try (var shop =
                new AnnotationConfigApplicationContext(ShopOnlyConfig.class)) {
            System.out.println("shop.orderService = " +
                    shop.containsBean("orderService"));
            System.out.println("shop.sharedEncoder = " +
                    shop.containsBean("sharedEncoder"));
            System.out.println("shop.message = " +
                    shop.getBean(OrderService.class).message());
        }

        try (var expanded =
                new AnnotationConfigApplicationContext(ExpandedConfig.class)) {
            System.out.println("expanded.orderService = " +
                    expanded.containsBean("orderService"));
            System.out.println("expanded.sharedEncoder = " +
                    expanded.containsBean("sharedEncoder"));

            String message =
                    expanded.getBean(OrderService.class).message();
            String decorated =
                    expanded.getBean(SharedEncoder.class).encode(message);
            System.out.println("expanded.message = " + decorated);
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "demo.shop")
class ShopOnlyConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = {
        ShopPackage.class,
        SharedPackage.class
})
class ExpandedConfig {
}
```

Chỉ có `ScanPackagesDemo` là top-level `public` trong file; `ShopOnlyConfig` và `ExpandedConfig` là package-private class hợp lệ trong cùng package `demo.app`. Việc đăng ký trực tiếp class cấu hình vào `AnnotationConfigApplicationContext` khiến Spring xử lý `@ComponentScan` của chúng, dù bản thân package `demo.app` không phải vùng scan của hai lượt quét.

### 6.3. Marker tại package root

File `src/main/java/demo/shop/ShopPackage.java`:

```java
package demo.shop;

public final class ShopPackage {
    private ShopPackage() {
    }
}
```

File `src/main/java/demo/shared/SharedPackage.java`:

```java
package demo.shared;

public final class SharedPackage {
    private SharedPackage() {
    }
}
```

Hai class này **không có `@Component`**. Chúng chỉ đánh dấu package root cho `basePackageClasses`; Spring không tạo bean `ShopPackage` hoặc `SharedPackage` từ scanning mặc định.

### 6.4. Các class trong `demo.shop`

File `src/main/java/demo/shop/persistence/OrderRepository.java`:

```java
package demo.shop.persistence;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public String load() {
        return "ok";
    }
}
```

File `src/main/java/demo/shop/service/OrderService.java`:

```java
package demo.shop.service;

import demo.shop.persistence.OrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String message() {
        return "order:" + repository.load();
    }
}
```

Hai component này ở **hai subpackage ngang cấp** (`demo.shop.service` và `demo.shop.persistence`). Quét từ root `demo.shop` sẽ lấy cả hai. Constructor duy nhất của `OrderService` không cần `@Autowired`; Spring chọn `OrderRepository` theo kiểu để inject.

### 6.5. Component ở nhánh `demo.shared`

File `src/main/java/demo/shared/text/SharedEncoder.java`:

```java
package demo.shared.text;

import org.springframework.stereotype.Component;

@Component
public class SharedEncoder {
    public String encode(String value) {
        return "[" + value + "]";
    }
}
```

Bean này nằm **ngoài** `demo.shop` nên không có trong `ShopOnlyConfig`. Nó chỉ xuất hiện trong context `ExpandedConfig` vì cấu hình này bổ sung root `demo.shared`.

### 6.6. Chạy và kiểm tra stdout

Tại thư mục chứa `build.gradle`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell. Các dòng do `System.out.println` in ra là:

```text
shop.orderService = true
shop.sharedEncoder = false
shop.message = order:ok
expanded.orderService = true
expanded.sharedEncoder = true
expanded.message = [order:ok]
```

**Giải thích chính xác đầu ra:**

1. `shop.orderService = true`: package root `demo.shop` chứa `demo.shop.service` nên `OrderService` được phát hiện.
2. `shop.sharedEncoder = false`: `demo.shared.text` là nhánh ngang cấp, không thuộc `demo.shop`.
3. `shop.message = order:ok`: `OrderService` nhận `OrderRepository` qua constructor; cả hai nằm dưới root được quét.
4. `expanded.orderService = true`: marker `ShopPackage.class` đặt root ở `demo.shop`.
5. `expanded.sharedEncoder = true`: marker `SharedPackage.class` bổ sung root `demo.shared`.
6. `expanded.message = [order:ok]`: lấy trực tiếp hai bean từ context và gọi phương thức Java; không có HTTP hay web controller.

Hai context độc lập có bean registry riêng. Một bean được đăng ký trong `expanded` không thể tự làm bean tương ứng xuất hiện trong `shop`.

## 7. Đặt `@SpringBootApplication` ở package nào?

Trong Spring Boot, `@SpringBootApplication` bao gồm chức năng của `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Khi không đặt thuộc tính scan tùy chỉnh, component scanning dùng **package chứa class `@SpringBootApplication`** làm root và tìm trong các subpackage.

Cấu trúc nên dùng cho dự án thông thường:

```text
com.acme.shop/
├── ShopApplication.java              <-- @SpringBootApplication
├── api/
│   └── OrderController.java          <-- @RestController
├── service/
│   └── OrderService.java             <-- @Service
└── persistence/
    └── OrderRepositoryImpl.java      <-- @Repository
```

`ShopApplication` đặt ở `com.acme.shop` giúp tìm các component trong ba nhánh con mà không cần khai báo tên từng nhánh. Nếu chuyển `ShopApplication` xuống `com.acme.shop.api`, scanner mặc định sẽ chủ yếu tìm `com.acme.shop.api` và các nhánh dưới đó; service/repository ở sibling packages có nguy cơ không được phát hiện.

Mã minh họa class Boot:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Đoạn này cần dependency Spring Boot thích hợp và là **minh họa riêng**, không phải phần mã chạy của dự án Spring Context ở mục 6.

### Chỉnh package scan trong Boot

Khi component thuộc nhiều root package, có thể chọn rõ:

```java
@SpringBootApplication(scanBasePackages = {
        "com.acme.shop",
        "com.acme.shared"
})
public class ShopApplication {
}
```

Hoặc type-safe:

```java
@SpringBootApplication(scanBasePackageClasses = {
        ShopMarker.class,
        SharedMarker.class
})
public class ShopApplication {
}
```

Hai đoạn Boot là **biến thể minh họa độc lập**, cần class marker/package tương ứng. Trong Spring Boot, `scanBasePackages` và `scanBasePackageClasses` là alias tới cơ chế **`@ComponentScan`**.

**Giới hạn quan trọng:** các thuộc tính `scanBasePackages` của `@SpringBootApplication` điều chỉnh **component scanning**, không tự điều chỉnh phạm vi quét **JPA entity** hay **Spring Data repository interface**. Những cơ chế này có quy tắc cấu hình khác nhau; khi cần, dùng `@EntityScan` và `@EnableJpaRepositories` (hoặc cơ chế tương ứng với Spring Data module). Mở rộng component scan không bảo đảm entity/repository proxy ở package ngoài root Boot sẽ tự được nhận diện.

## 8. Nhiều module và thư viện Java: điều kiện classpath

Một ứng dụng nhiều Gradle module có thể tổ chức:

```text
shop-app
  └── package com.acme.shop
common-library
  └── package com.acme.common
```

Giả sử `common-library` xuất bản một `@Component` trong `com.acme.common`. Để ứng dụng nhận bean qua component scan, **đồng thời** cần:

1. Artifact/module chứa class phải có trên runtime classpath (hoặc được nhìn thấy từ module system tương ứng).
2. Base package scan phải bao phủ `com.acme.common`.
3. Class phải là component candidate hợp lệ và không bị filter/condition loại trừ.
4. Các dependency cần để tạo bean phải thỏa mãn.

Ví dụ trong `build.gradle` của `shop-app`:

```groovy
dependencies {
    implementation project(':common-library')
}
```

Đây là **minh họa cho một multi-project Gradle build** đã khai báo `:common-library`; dòng trên không tự đủ tạo một dự án độc lập. Nó chỉ giải quyết sự hiện diện của module thư viện trên classpath; scanner vẫn phải quét đúng package hoặc thư viện phải cung cấp cơ chế đăng ký riêng.

**Không đặt base package chỉ theo tên Gradle module.** Spring quét Java package trên classpath, không trực tiếp hiểu tên project Gradle. Một module Gradle có thể chứa nhiều package, hoặc nhiều module cùng sử dụng một package prefix.

### Java Module System (JPMS)

Nếu ứng dụng chạy theo Java module path với `module-info.java`, việc Spring tìm metadata, gọi constructor hoặc inject bằng reflection có thể cần cấu hình `exports`/`opens` phù hợp. Lỗi truy cập reflection do JPMS không đồng nghĩa package không được scan. Hãy phân biệt “không tìm thấy bean definition” với “tìm thấy bean nhưng không thể tạo instance hoặc truy cập thành viên”.

## 9. Quét có kiểm soát bằng bộ lọc

`includeFilters` và `excludeFilters` chỉ chọn/loại candidates **bên trong base package**. Ví dụ loại một implementation khỏi lượt scan:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyOrderService.class))
class AppConfig { }
```

Đây là snippet cần import `FilterType` và định nghĩa `LegacyOrderService`. Exclude filter không ngăn class được đăng ký qua `@Bean` hoặc scanner khác. Với `useDefaultFilters=false`, stereotype mặc định không được chọn trừ khi có include filter thích hợp; filter cũng không mở rộng vùng package scan.

## 10. `@ComponentScan` kết hợp với `@Import` và `@Bean`

`@Import` đưa class/configuration được hỗ trợ vào quá trình đăng ký, còn `@Bean` đăng ký definition từ factory method. Chúng có thể đưa bean vào context ngay cả khi class nằm ngoài root của component scan:

```java
@Configuration(proxyBeanMethods = false)
class UtilityConfig {
    @Bean
    JsonHelper jsonHelper() { return new JsonHelper(); }
}
```

`JsonHelper` là kiểu giả định trong snippet. Đừng mở scan cả thư viện chỉ để tạo một bean cần dùng; nhưng cũng phải bảo đảm configuration chứa `@Bean` thực sự đã được đăng ký/import. Dependency JAR có trên runtime classpath và annotation được scan là hai điều kiện riêng.

## 11. Các lỗi về phạm vi quét và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `@Service` có trên class nhưng thiếu bean | Class ở package ngoài root scan | So sánh `package` của class với `@ComponentScan`/package class Boot |
| Quét `com.acme.shop.service` nhưng không thấy repository | Repository ở `com.acme.shop.persistence` là sibling | Dùng marker ở `com.acme.shop` hoặc bổ sung root persistence |
| `@ComponentScan` để trống quét nhầm nơi | Class cấu hình nằm trong package hẹp | Đặt cấu hình tại root phù hợp hoặc chỉ rõ `basePackageClasses` |
| `@SpringBootApplication` đặt sâu trong package web | Default scan chỉ phủ nhánh web | Đưa class Boot lên root package hoặc mở scan rõ ràng |
| Mở `scanBasePackages` mà JPA repository vẫn không có | Component scan khác Spring Data repository scanning | Kiểm tra `@EnableJpaRepositories`/auto-config packages của Spring Data |
| `@Entity` không được quản lý | Entity scanning khác component scanning | Kiểm tra `@EntityScan`/cấu hình JPA |
| Module thư viện có class nhưng bean vẫn không thấy | Thiếu dependency runtime hoặc thiếu package root scan | Kiểm tra dependency graph/runtime classpath và package |
| Class ngoài scan vẫn thành bean | Có `@Import`, `@Bean`, auto-configuration hoặc registration khác | Kiểm tra mọi nguồn bean definition thay vì kết luận scan sai |
| `@ComponentScan` có root đúng nhưng class biến mất | Bị `excludeFilters`, `@Profile`/`@Conditional` hoặc không là candidate | Kiểm tra metadata/filter/condition |
| Dùng `useDefaultFilters=false` rồi `@Service` không còn | Đã tắt stereotype filter mặc định | Thêm include filter đúng hoặc bỏ cấu hình tắt |
| Có bean definition nhưng tạo bean lỗi | Constructor dependency thiếu, circular dependency, lỗi factory, JPMS reflection | Phân biệt registration với instantiation, đọc exception chain |
| Hai bean cùng tên sau khi mở rộng scan | Các class khác package trùng tên mặc định/explicit name | Chọn tên có chủ đích hoặc giới hạn vùng quét |
| Quét quá rộng gây bean lạ/xung đột | Base package là root chung quá lớn | Thu hẹp package roots, dùng marker/filters/explicit registration |
| Gõ `basePackages="...OrderService"` | Truyền tên class thay vì package | Đổi thành package hoặc dùng `basePackageClasses` |
| Đặt component ở thư mục source nhưng không xuất hiện runtime | Class chưa compile hoặc chưa nằm trên runtime classpath | Kiểm tra build output, source set và dependencies |

### Quy trình debug theo bằng chứng

**Bước 1 — Xác định loại lỗi.** Nếu `getBeanNamesForType(OrderService.class)` rỗng, kiểm tra đăng ký/candidate. Nếu tên có mặt nhưng tạo bean thất bại, điều tra constructor, factory, scope, post-processor hoặc module accessibility. Nếu nhiều tên xuất hiện, xử lý ambiguity bằng thiết kế injection/qualifier thích hợp.

**Bước 2 — So sánh các package thật.** Mở khai báo `package` của class component và package của configuration/Boot main. Vẽ sơ đồ root → subpackage. Đừng chỉ dựa vào vị trí file hiển thị trong IDE.

**Bước 3 — Đọc cấu hình scan đã kích hoạt.** Xác định `@ComponentScan` nằm trên class thực sự đã đăng ký/import hay chưa. Nếu có nhiều configuration class, kiểm tra từng lượt scan, không suy ra tất cả theo một annotation.

**Bước 4 — Kiểm tra điều kiện.** Xem `@Profile`, `@Conditional` và exclude/include filters; với Boot, điều kiện auto-config và profile active cũng cần được xét nếu bean phụ thuộc chúng.

**Bước 5 — Dùng context để kiểm tra thay vì đoán.** Ví dụ, trong context thử nghiệm:

```java
String[] names = context.getBeanNamesForType(OrderService.class);
System.out.println(java.util.Arrays.toString(names));
```

Đây là **đoạn minh họa** khi có sẵn biến `context` và class `OrderService`. Nó giúp xác định các bean đã đăng ký/nhìn thấy theo kiểu mà container có thể resolve. Với Spring Boot, báo cáo condition evaluation hoặc `/actuator/beans` (khi Actuator được thêm và endpoint được bật/phân quyền) có thể hỗ trợ, nhưng không phải điều kiện tiên quyết để debug Spring Core Container.

## 12. Những sai lầm về cấu trúc package cần tránh

### Sai lầm A: mọi class ở chung source root thì cùng được scan

`src/main/java` là một thư mục nguồn của build; `com.example.shop` và `org.example.shared` vẫn là hai Java package khác nhau. Chúng chỉ được Spring phát hiện trong **các root scan đã cấu hình**, không do cùng nằm dưới `src/main/java`.

### Sai lầm B: `basePackageClasses` quét “theo kiểu” của class

`basePackageClasses = OrderService.class` **không yêu cầu Spring chỉ tạo bean có kiểu `OrderService`**. Nó yêu cầu quét package chứa `OrderService`. Muốn chọn cụ thể một bean theo class, có thể đăng ký rõ với `@Import` hoặc `@Bean` khi phù hợp.

### Sai lầm C: quét package cha càng rộng càng tốt

Mở `@ComponentScan("com")` có thể đi qua nhiều dependency hoặc package ứng dụng không liên quan. Kết quả có thể là startup chậm, nhiều bean definition ngoài ý muốn, xung đột tên hoặc duplicate dependency. Chọn **package roots hẹp nhưng đủ bao phủ** là thiết kế tốt hơn.

### Sai lầm D: mở rộng scan nghĩa là đã cấu hình đủ mọi framework

JPA entity scanning, Spring Data repository scanning, MVC mapping, transaction management và security configuration có những cơ chế riêng. Một class `@RestController` được scan thành bean chưa có nghĩa URL mapping chạy nếu web context chưa cấu hình. Mở rộng component scan cũng không tự bật repository proxy hoặc quét entity.

### Sai lầm E: annotation luôn tạo bean tức thì

Component scanning có thể phát hiện class, nhưng instance chỉ được tạo theo lifecycle/scope và dependency resolution. `@Lazy`, prototype scope, điều kiện profile và những bean được tạo qua factory method có thể thay đổi thời điểm có instance. Khi debug, phân biệt **bean definition không có** với **bean có nhưng không tạo được**.

## 13. Bài tập thực hành có đáp án

**Bài 1 — Dời marker xuống package con.** Trong ví dụ mục 6, thay `ShopPackage.class` trong `ExpandedConfig` bằng `OrderService.class`, vẫn giữ `SharedPackage.class`. Dự đoán kết quả.

*Đáp án:* Spring chỉ quét `demo.shop.service` và `demo.shared`. `OrderRepository` ở `demo.shop.persistence` không được quét; tạo `OrderService` sẽ thiếu dependency `OrderRepository` và context refresh thường thất bại với `UnsatisfiedDependencyException`. Không thể chạy đến các dòng output của `expanded` nếu không bổ sung đăng ký repository.

**Bài 2 — Thêm package root.** Đổi `ShopOnlyConfig` thành:

```java
@ComponentScan(basePackages = {"demo.shop", "demo.shared"})
```

*Đáp án:* `shop.sharedEncoder = true` và có thể lấy bean `SharedEncoder` từ context `shop`. Các đoạn code khác không đổi; đây là ví dụ đổi phạm vi quét mà không di chuyển class.

**Bài 3 — Đưa configuration class sang package khác.** Giả sử `ShopOnlyConfig` chuyển từ `demo.app` sang `demo.config` nhưng vẫn giữ `@ComponentScan(basePackages="demo.shop")`. Nó còn quét `OrderService` không?

*Đáp án:* **Có**. Vì thuộc tính `basePackages` ghi rõ root scan, vị trí mới của configuration class không thay đổi root đã khai báo.

**Bài 4 — Xóa `basePackages`.** Giữ `ShopOnlyConfig` ở `demo.app` và đổi annotation thành `@ComponentScan` không tham số. Bean `OrderService` có được đăng ký tự động không?

*Đáp án:* **Không qua lượt scan này**. Scanner mặc định đi từ `demo.app` và các subpackage, trong khi `demo.shop` là sibling. Nếu không có cách đăng ký khác, việc `getBean(OrderService.class)` sẽ thất bại.

**Bài 5 — Chỉ thêm dependency Gradle.** Ứng dụng phụ thuộc module chứa `@Component` ở `com.example.payments` nhưng `@ComponentScan` chỉ quét `com.example.orders`. Dependency mới đủ để Spring tạo bean payment chưa?

*Đáp án:* **Chưa**. Dependency đảm bảo class khả dụng trên classpath; Spring còn cần base package phù hợp hoặc một cơ chế registration độc lập.

**Bài 6 — Entity/repository scanning trong Boot.** Đặt `@SpringBootApplication(scanBasePackages={"com.example.app","com.example.data"})` nhưng một `@Entity` dưới `com.example.data.model` chưa được JPA nhận diện. Có thể kết luận `@ComponentScan` hỏng không?

*Đáp án:* **Không**. `@Entity` không phải Spring component stereotype để tự được quét như `@Service`. Kiểm tra JPA entity scanning và cấu hình `@EntityScan` hoặc auto-configuration package; tương tự repository interface thuộc quy trình Spring Data.

**Bài 7 — Debug lỗi “bean có nhưng không inject được”.** Nếu `getBeanNamesForType(PaymentClient.class)` có hai tên, liệu mở rộng `@ComponentScan` hơn nữa có chắc sửa được lỗi?

*Đáp án:* **Không**. Khi đã có nhiều ứng viên, cần kiểm tra `@Qualifier`, `@Primary` hoặc thiết kế dependencies; mở rộng scan có thể làm ambiguity lớn hơn.

## 14. Checklist thiết kế và ghi nhớ

Trước khi khai báo `@ComponentScan`:

1. Ghi rõ **package root nào được quét** và package con nào chứa các component cần thiết.
2. Dùng `@ComponentScan` không tham số khi configuration class thật sự nằm ở root mong muốn; nếu không, khai báo `basePackages` hoặc ưu tiên `basePackageClasses` với marker đặt đúng root.
3. Giữ Boot main class ở package root phù hợp; chỉ mở rộng scan khi có module/package ngoài ranh giới mặc định.
4. Kiểm tra runtime classpath, stereotype, profile/condition và filters; việc quét đúng package chưa bảo đảm bean tạo được.
5. Phân biệt component scan với `@Bean`/`@Import`, Spring Data repository scanning và JPA entity scanning.
6. Đừng đặt scan root quá cao chỉ để tránh thiết kế package; quét hẹp, có chủ đích sẽ dễ bảo trì và kiểm thử hơn.

Quy tắc cốt lõi: **`@ComponentScan` quét từ một hoặc nhiều base package xuống các package con, không tự sang package cha hoặc nhánh ngang cấp.** Vị trí của class khai báo annotation chỉ quyết định root mặc định khi chưa chỉ rõ package. `basePackageClasses` cho phép dùng marker type-safe; `basePackages` dùng tên package bằng chuỗi. Quét đúng vùng classpath là một điều kiện để đăng ký bean, còn stereotype và các điều kiện khác quyết định class có thật sự được đăng ký hay không.

### Tài liệu Spring chính thức

- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework Javadoc — `@ComponentScan`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework Reference — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Boot Reference — Locating the Main Application Class](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html).
- [Spring Boot Javadoc — `@SpringBootApplication`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html).
