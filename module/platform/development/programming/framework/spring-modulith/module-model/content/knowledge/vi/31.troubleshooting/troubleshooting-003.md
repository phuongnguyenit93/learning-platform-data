# Module biến mất sau khi đổi detection strategy

Sau khi thay `spring.modulith.detection-strategy`, một số application module có thể biến mất khỏi kết quả `ApplicationModules`, dù các class Java vẫn còn trong source code và Spring Boot vẫn có thể tạo bean từ chúng. Đây thường là dấu hiệu strategy mới đang tìm module theo một quy ước package hoặc annotation khác với cách codebase hiện tại được tổ chức.

Spring Modulith không coi mọi package có class là một module. Strategy nhận diện module base package từ root package của ứng dụng. Khi đổi strategy, tập package được chọn có thể thay đổi; vì vậy cần kiểm tra root package, độ sâu package, annotation và cấu hình strategy trước khi kết luận module đã bị xóa.

## 1. Hiểu strategy mặc định trước khi thay đổi

Root package mặc định là package chứa lớp Spring Boot application, thường là lớp có `@SpringBootApplication`. Với strategy mặc định, mỗi package con trực tiếp của root được xem là một application module.

Ví dụ:

```text
com.acme.shop                 ← package của ShopApplication
├── ShopApplication.java
├── orders                     ← module orders
│   ├── OrderManagement.java
│   └── internal
├── catalog                    ← module catalog
│   └── ProductManagement.java
└── customers                  ← module customers
    └── CustomerManagement.java
```

Mô hình mặc định sẽ nhận diện `orders`, `catalog` và `customers`. Các package con như `orders.internal` không tự động trở thành module cấp cao nhất. Nếu muốn tách một package con thành nested application module, cần đánh dấu package đó bằng `@ApplicationModule` theo quy tắc nested module.

Có thể ghi rõ strategy mặc định trong `application.properties`:

```properties
spring.modulith.detection-strategy=direct-subpackages
```

Không khai báo thuộc tính này cũng dùng hành vi mặc định. `direct-subpackages` chọn các package con trực tiếp của root package; nó không quét mọi package lồng sâu để biến tất cả thành module.

## 2. Chuyển sang explicitly-annotated có thể làm module biến mất

Strategy `explicitly-annotated` chỉ chọn các package được đánh dấu rõ ràng bằng Spring Modulith `@ApplicationModule` hoặc jMolecules `@Module`.

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Giả sử trước đó ứng dụng có các module được phát hiện theo vị trí package:

```text
com.acme.shop
├── ShopApplication.java
├── orders
├── catalog
└── customers
```

Nếu chưa package nào được đánh dấu, sau khi bật `explicitly-annotated`, `orders`, `catalog` và `customers` có thể không còn xuất hiện trong module model. Strategy không tự suy ra annotation từ tên package hoặc từ việc package chứa `@Service`.

Để giữ các module đó, thêm `@ApplicationModule` vào package gốc của từng module. Trong Java, cách rõ ràng nhất là dùng `package-info.java`:

```java
// src/main/java/com/acme/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.orders;
```

```java
// src/main/java/com/acme/shop/catalog/package-info.java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.catalog;
```

```java
// src/main/java/com/acme/shop/customers/package-info.java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.customers;
```

Với jMolecules, có thể dùng `@Module` thay cho `@ApplicationModule` nếu dependency và metadata jMolecules đã được cấu hình phù hợp. Chỉ thêm annotation vào package thật sự là module base package; không đánh dấu mọi package `internal`, `api`, `persistence` hoặc `web` thành module độc lập.

## 3. Đặt annotation đúng package gốc

Một lỗi thường gặp là đặt `@ApplicationModule` ở package con thay vì package gốc của module. Ví dụ:

```text
com.acme.shop
└── orders
    ├── OrderManagement.java
    ├── internal
    │   ├── package-info.java  ← annotation đặt nhầm ở đây
    │   └── OrderRepository.java
    └── api
        └── OrderLookup.java
```

Nếu `package-info.java` đánh dấu `com.acme.shop.orders.internal`, strategy có thể nhận diện `internal` là một module riêng, trong khi package gốc `orders` vẫn không được chọn. Hãy chuyển annotation về `com.acme.shop.orders` nếu `orders` mới là capability module.

Phân biệt mục đích của các annotation:

| Annotation | Mục đích |
|---|---|
| `@ApplicationModule` | Đánh dấu package là application module và khai báo metadata của module |
| `@Module` của jMolecules | Đánh dấu module theo mô hình jMolecules; được strategy `explicitly-annotated` nhận diện |
| `@NamedInterface` | Công khai package/type như một phần API của module đã tồn tại; không thay thế marker module |
| `@PackageInfo` | Cung cấp type metadata thay thế `package-info.java` trong ngôn ngữ như Kotlin; bản thân nó không phải marker module |

Một package `api` chỉ có `@NamedInterface` không tự trở thành application module. Nó là API package thuộc module cha. Tương tự, một package có `@PackageInfo` nhưng không mang `@ApplicationModule` hoặc `@Module` sẽ không được chọn bởi strategy `explicitly-annotated` chỉ nhờ `@PackageInfo`.

## 4. Kiểm tra root package của lớp ứng dụng

Spring Modulith bắt đầu phát hiện module từ package chứa lớp Spring Boot application. Nếu di chuyển lớp chính từ `com.acme.shop` xuống `com.acme.shop.bootstrap`, root package cũng thay đổi:

```text
com.acme.shop
├── bootstrap
│   └── ShopApplication.java  ← root mới
├── orders
├── catalog
└── customers
```

Với strategy `direct-subpackages`, root mới là `com.acme.shop.bootstrap`. Các module `orders`, `catalog` và `customers` là package ngang hàng, không phải package con của root mới, nên không còn được phát hiện từ root đó.

Ưu tiên đặt lớp application ở package chung phía trên các module:

```text
com.acme.shop                 ← ShopApplication.java
├── orders
├── catalog
├── customers
└── bootstrap                 ← cấu hình khởi động nếu cần
```

Nếu không thể di chuyển lớp chính, có thể dùng `@Modulithic(additionalPackages = ...)` để khai báo root bổ sung:

```java
package com.acme.shop.bootstrap;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@SpringBootApplication
@Modulithic(additionalPackages = "com.acme.shop")
public class ShopApplication {
}
```

`additionalPackages` khai báo thêm root package để Spring Modulith chạy detection strategy. Package được thêm là root để quét; theo strategy `direct-subpackages`, các package con trực tiếp của root mới là module. Kiểm tra kết quả để chắc chắn package `bootstrap` không vô tình trở thành module ngoài ý muốn.

## 5. Module nằm ngoài root package

Nếu một capability nằm ở namespace khác, ví dụ `com.acme.fulfillment.shipping`, root mặc định `com.acme.shop` không bao phủ package đó.

```text
com.acme.shop
├── ShopApplication.java
├── orders
└── catalog

com.acme.fulfillment
└── shipping
```

Thêm `com.acme.fulfillment` làm root bổ sung:

```java
@SpringBootApplication
@org.springframework.modulith.Modulithic(
        additionalPackages = "com.acme.fulfillment"
)
public class ShopApplication {
}
```

Sau đó strategy đang cấu hình sẽ được áp dụng cho root bổ sung. Với `direct-subpackages`, `shipping` được nhận diện như module con của `com.acme.fulfillment`. Nếu dùng `explicitly-annotated`, package `shipping` cũng phải có `@ApplicationModule` hoặc `@Module`.

`additionalPackages` chỉ điều chỉnh module discovery. Nó không tự mở rộng Spring component scan, JPA entity scan hoặc repository scan. Nếu bean hoặc entity nằm ngoài phạm vi scan tương ứng, cần cấu hình cơ chế scan đó riêng.

## 6. Kiểm tra custom detection strategy có trả đúng package không

Khi hai strategy dựng sẵn không phù hợp, có thể cài đặt `ApplicationModuleDetectionStrategy`. Interface này nhận root package và trả về `Stream<JavaPackage>` chứa các module base package cần được nhận diện.

Ví dụ, ứng dụng dùng marker riêng `@BusinessModule` trên package gốc:

```java
package com.acme.shop.architecture;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
public @interface BusinessModule {
}
```

Đánh dấu package module:

```java
@com.acme.shop.architecture.BusinessModule
package com.acme.shop.orders;
```

Strategy lọc các package con trực tiếp có marker:

```java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getDirectSubPackages().stream()
                .filter(candidate -> candidate
                        .getAnnotation(BusinessModule.class)
                        .isPresent());
    }
}
```

Đăng ký class strategy bằng tên đầy đủ:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
```

Ví dụ trên giả định module nằm ở package con trực tiếp của root. Nếu cấu trúc thật là `com.acme.shop.modules.orders`, strategy chỉ lấy direct sub-package sẽ thấy `modules`, không tự đi sâu tới `orders`. Khi đó cần điều chỉnh thuật toán duyệt package để trả về đúng module base package theo cấu trúc thực tế.

Một custom strategy dễ làm mất module khi:

- Predicate lọc sai tên hoặc sai package.
- Annotation marker không được đặt ở package gốc.
- Strategy chỉ duyệt direct sub-package trong khi module nằm sâu hơn.
- Hàm trả về stream rỗng do không tìm thấy marker.
- Strategy trả về package cha hoặc package con không phải module base package.

Đừng chỉ nhìn việc class strategy được khởi tạo thành công. Hãy in danh sách package mà nó chọn hoặc kiểm tra kết quả `ApplicationModules` sau khi strategy được áp dụng.

## 7. Đăng ký strategy ở đúng nơi

Với Spring Modulith hiện hành, thuộc tính `spring.modulith.detection-strategy` chấp nhận:

| Giá trị | Ý nghĩa |
|---|---|
| Không khai báo | Dùng strategy mặc định `direct-subpackages` |
| `direct-subpackages` | Chọn package con trực tiếp của mỗi root package |
| `explicitly-annotated` | Chỉ chọn package được đánh dấu `@ApplicationModule` hoặc jMolecules `@Module` |
| Tên đầy đủ của class | Dùng custom `ApplicationModuleDetectionStrategy` đó |

Nếu chỉ dùng strategy cho architecture test và sinh tài liệu, đặt class custom cùng đăng ký của nó trong test sources theo hướng dẫn Spring Modulith. Nếu dùng runtime components như `ApplicationModuleInitializer`, actuator hoặc observability support, cần có `spring-modulith-core` ở compile-time classpath và cung cấp strategy trong phần code được đóng gói cho runtime.

Khi điều tra cấu hình cũ, kiểm tra cả `application.properties`, `application.yml`, profile đang active và các cấu hình test. Một file profile có thể ghi đè giá trị mong đợi. Cơ chế đăng ký strategy cũ qua `META-INF/spring.properties` đã deprecated; nên chuyển sang property `spring.modulith.detection-strategy`.

## 8. Kiểm tra module model trước khi gọi verify()

Trước khi đọc lỗi từ `verify()`, hãy in các module mà Spring Modulith thực sự phát hiện:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.forEach(System.out::println);
```

Đầu ra hiển thị logical name, base package và các Spring bean được nhận diện. Có thể trích xuất danh sách base package để so sánh với danh sách mong đợi:

```java
import java.util.stream.Collectors;

var detectedPackages = modules.stream()
        .map(module -> module.getBasePackage().getName())
        .sorted()
        .collect(Collectors.toList());

detectedPackages.forEach(System.out::println);
```

Nếu `orders` không xuất hiện trong danh sách, vấn đề nằm ở discovery hoặc root/package layout. Nếu `orders` xuất hiện nhưng `verify()` thất bại, đó là vấn đề khác: dependency cycle, truy cập internal package hoặc `allowedDependencies`. Không dùng `verify()` như bước đầu tiên để đoán module có được phát hiện hay không.

Trong architecture test, có thể khóa danh sách module mong đợi bằng assertion:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void detectsAllExpectedModules() {
        var modules = ApplicationModules.of(ShopApplication.class);

        var packages = modules.stream()
                .map(module -> module.getBasePackage().getName())
                .collect(Collectors.toSet());

        assertThat(packages).contains(
                "com.acme.shop.orders",
                "com.acme.shop.catalog",
                "com.acme.shop.customers");
    }
}
```

Assertion này giúp phát hiện việc đổi strategy làm mất module ngay tại test discovery, trước khi những kiểm tra phụ thuộc hoặc tài liệu kiến trúc cho kết quả khó hiểu.

## 9. Phân biệt module discovery với Spring component scanning

Một package có thể được Spring Boot quét để tạo bean nhưng không được Spring Modulith nhận diện là application module. Ngược lại, module có thể xuất hiện trong module model nhưng bean bên trong không được component scan hoặc persistence scan cấu hình đúng.

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| Spring Modulith detection strategy | Package nào là application module base package? |
| Spring component scan | Class nào được đăng ký thành Spring bean? |
| JPA entity scan | Entity nào được persistence provider nhận diện? |
| Repository scan | Repository interface nào được đăng ký? |

Vì vậy, khi module biến mất khỏi `ApplicationModules`, hãy kiểm tra strategy và package root. Nếu module vẫn hiện nhưng bean không được khởi tạo, kiểm tra component scan, điều kiện bean và cấu hình Spring tương ứng.

## 10. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tất cả module biến mất sau khi bật `explicitly-annotated` | Các package chưa được đánh dấu | Thêm `@ApplicationModule` hoặc `@Module` vào từng module base package |
| Chỉ một số module biến mất | Một vài package thiếu annotation hoặc annotation đặt sai chỗ | Kiểm tra `package-info.java` của từng module |
| Chỉ còn package `internal` như một module | Annotation được đặt ở package con thay vì package gốc | Chuyển marker về package capability/module gốc |
| Module biến mất sau khi di chuyển `ShopApplication` | Root package mới không còn là package cha của module | Đặt lớp chính ở root chung hoặc cấu hình `additionalPackages` |
| Module nằm ở namespace khác không xuất hiện | Root ngoài chưa được bổ sung | Dùng `@Modulithic(additionalPackages = ...)` hoặc `ApplicationModuleSourceFactory` khi phù hợp |
| Custom strategy trả về không có module | Predicate sai, annotation không được đọc hoặc duyệt sai độ sâu | In các package ứng viên và kiểm tra `getModuleBasePackages()` |
| Module xuất hiện sai cấp | Strategy trả package cha/con không đúng base package mong muốn | Điều chỉnh thuật toán lựa chọn package |
| Module model đúng nhưng bean thiếu | Component scan hoặc cấu hình bean không bao phủ package | Kiểm tra Spring component scan riêng |
| Test và runtime thấy module khác nhau | Property, profile hoặc custom strategy khác nhau giữa test và runtime | Đồng bộ cấu hình và vị trí class strategy |

## 11. Quy trình khôi phục sau khi đổi strategy

1. **Ghi lại strategy hiện tại:** kiểm tra `spring.modulith.detection-strategy` trong cấu hình chung và profile đang active.
2. **Xác định root package:** xem package của lớp `@SpringBootApplication` và các root bổ sung trong `@Modulithic`.
3. **Liệt kê module mong đợi:** ghi rõ package gốc nào phải xuất hiện trong `ApplicationModules`.
4. **So khớp quy tắc strategy:** nếu dùng `direct-subpackages`, xác nhận module là package con trực tiếp; nếu dùng `explicitly-annotated`, xác nhận annotation ở đúng package gốc.
5. **Kiểm tra custom strategy:** xác nhận predicate, độ sâu duyệt, marker và stream trả về.
6. **In module model:** dùng `ApplicationModules.of(...).forEach(System.out::println)` để quan sát kết quả thực tế.
7. **Thêm discovery assertion:** khóa các base package mong đợi trong architecture test.
8. **Chạy verification:** chỉ sau khi module được phát hiện đúng, gọi `verify()` để kiểm tra dependency và API boundary.
9. **Đồng bộ runtime/test:** bảo đảm cùng strategy và root package được sử dụng ở nơi sinh tài liệu, architecture test và runtime components.

Nếu mục tiêu chỉ là thay đổi cách đặt tên module hoặc kiểm soát quyền truy cập API, không nhất thiết phải đổi detection strategy. Hãy giữ `direct-subpackages` nếu cấu trúc package đã phù hợp; dùng `explicitly-annotated` khi muốn quản lý rõ package nào được xem là module; chỉ dùng custom strategy khi hai quy tắc dựng sẵn không đáp ứng được cấu trúc thực tế.

## 12. Checklist trước khi kết luận module đã biến mất

- [ ] Đã xác định đúng package của lớp `@SpringBootApplication`.
- [ ] Đã kiểm tra `additionalPackages` nếu module nằm ngoài root mặc định.
- [ ] Đã ghi nhận giá trị `spring.modulith.detection-strategy` thực tế sau khi áp dụng profile.
- [ ] Nếu dùng `explicitly-annotated`, mọi module mong đợi đều có `@ApplicationModule` hoặc `@Module` tại package gốc.
- [ ] Không nhầm `@NamedInterface` hoặc `@PackageInfo` với marker module.
- [ ] Nếu dùng custom strategy, `getModuleBasePackages()` trả đúng các `JavaPackage` và đúng độ sâu.
- [ ] Custom strategy và cấu hình của nó có mặt trong test/runtime source set phù hợp.
- [ ] Đã in `ApplicationModules` và so sánh base package với danh sách mong đợi.
- [ ] Đã phân biệt module discovery với component/entity/repository scanning.
- [ ] Chỉ chạy `verify()` sau khi xác nhận module model đã được tạo đúng.

Module biến mất sau khi đổi detection strategy thường là hệ quả của việc strategy mới không còn chọn package theo quy ước cũ. Khi kiểm tra lần lượt root package, annotation, package depth, custom strategy và cấu hình đang active, có thể xác định chính xác điểm làm module bị bỏ sót và khôi phục module model mà không phải mở rộng ranh giới một cách tùy tiện.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals: Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Appendix B: Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [JavaPackage API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
