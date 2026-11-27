# Không phát hiện được module mong đợi

Khi một application module không xuất hiện trong module model, hãy kiểm tra điểm bắt đầu quét package, cấu trúc package và detection strategy trước. Theo mặc định, Spring Modulith lấy package chứa lớp Spring Boot application làm root và tìm module trong các package con trực tiếp của root đó. Một module nằm ngoài root, nằm sâu hơn một cấp hoặc không khớp strategy đang cấu hình có thể không được nhận diện.

Spring Modulith cung cấp `ApplicationModules` để quan sát kết quả detection, `@Modulithic(additionalPackages = ...)` để bổ sung root package, strategy `explicitly-annotated` để chỉ chọn module được đánh dấu và `ApplicationModuleDetectionStrategy` để triển khai quy tắc riêng. Việc chẩn đoán theo từng bước giúp phân biệt lỗi module detection với lỗi tra cứu sai identifier hoặc lỗi API visibility.

Sau bài học, bạn có thể:

- Kiểm tra root package mà Spring Modulith dùng để phát hiện module.
- Giải thích phạm vi của `direct-subpackages` và `explicitly-annotated`.
- Bổ sung root package bằng `@Modulithic(additionalPackages = ...)`.
- Đánh dấu package module bằng `@ApplicationModule`.
- Cấu hình `ApplicationModuleDetectionStrategy` tùy chỉnh.
- Phân biệt module không được phát hiện với module được phát hiện nhưng tra cứu bằng identifier sai.
- Lập quy trình chẩn đoán có thể lặp lại cho cả architecture test và runtime.

## 1. Bắt đầu bằng module model thực tế

Đừng suy luận rằng một package đã là module chỉ vì nó tồn tại trong source tree. Hãy tạo module model từ đúng lớp Spring Boot application và in các module mà Spring Modulith thực sự nhận diện:

```java
import com.acme.shop.ShopApplication;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.forEach(System.out::println);
    }
}
```

Kết quả hiển thị logical name, base package và các Spring bean được nhận diện trong từng module. Đối chiếu danh sách này với package mà bạn mong đợi.

Nếu `order` không xuất hiện, vấn đề thuộc bước detection hoặc classpath. Nếu module `order` đã xuất hiện nhưng `getModuleByName("order")` không tìm thấy, hãy kiểm tra logical identifier đang được sử dụng. Nếu module xuất hiện nhưng `verify()` báo lỗi truy cập API, đó là vấn đề visibility/dependency sau detection, không phải lỗi phát hiện module.

## 2. Kiểm tra package của lớp Spring Boot application

Root package mặc định là package chứa lớp được truyền vào `ApplicationModules.of(...)`, thường là lớp có `@SpringBootApplication`. Với detection strategy mặc định, Spring Modulith tìm các module trong package con trực tiếp của root đó.

Ví dụ cấu trúc phù hợp:

```text
com.acme.shop                         <- package của ShopApplication
├── ShopApplication.java
├── order                             <- module order
├── inventory                         <- module inventory
└── catalog                           <- module catalog
```

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic
@SpringBootApplication
public class ShopApplication {
}
```

Với cấu trúc này, `order`, `inventory` và `catalog` là các package con trực tiếp của `com.acme.shop`.

Một lỗi thường gặp là đặt lớp ứng dụng quá sâu:

```text
com.acme.shop
├── order
├── inventory
└── bootstrap
    └── ShopApplication.java         <- root thực tế: com.acme.shop.bootstrap
```

Nếu truyền `ShopApplication.class`, root package là `com.acme.shop.bootstrap`. Các package `com.acme.shop.order` và `com.acme.shop.inventory` nằm ngoài root đó nên không được phát hiện theo mặc định.

Có hai hướng xử lý thường dùng:

- Di chuyển lớp ứng dụng lên package cha chung `com.acme.shop` nếu đó là cấu trúc phù hợp với Spring Boot component scanning của ứng dụng.
- Giữ lớp ứng dụng ở vị trí hiện tại và khai báo các root package bổ sung bằng `@Modulithic(additionalPackages = ...)`.

Hãy kiểm tra cả lớp được truyền vào `ApplicationModules.of(...)`. Nếu test dùng một application class khác với runtime, hai nơi có thể tạo ra module arrangement khác nhau.

## 3. Kiểm tra độ sâu package với `direct-subpackages`

Detection strategy mặc định `direct-subpackages` chỉ chọn package con trực tiếp của root làm module base package. Các package sâu hơn thường là package con bên trong module đã chọn.

Ví dụ:

```text
com.acme.shop                         <- root
└── business
    ├── order
    ├── inventory
    └── catalog
```

Với root `com.acme.shop`, module được phát hiện là `business`, không phải ba module `order`, `inventory` và `catalog`, vì chỉ `business` là package con trực tiếp. Các package `business.order`, `business.inventory` và `business.catalog` nằm sâu hơn nên thuộc cấu trúc bên trong module `business` theo strategy mặc định.

Nếu mục tiêu là ba module nghiệp vụ riêng, có thể:

- Chuyển `order`, `inventory`, `catalog` thành package con trực tiếp của root; hoặc
- Dùng `explicitly-annotated` để đánh dấu các package module; hoặc
- Viết custom detection strategy chọn các package theo quy ước hiện tại.

Đừng nhầm package con sâu hơn với module lồng nhau tự động. Việc một thư mục tồn tại trong source tree không khiến nó trở thành application module riêng.

## 4. Kiểm tra detection strategy đang được cấu hình

Spring Modulith hỗ trợ hai strategy dựng sẵn:

| Giá trị | Quy tắc phát hiện |
|---|---|
| `direct-subpackages` | Chọn tất cả package con trực tiếp của root package |
| `explicitly-annotated` | Chỉ chọn package được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module` |

Nếu không cấu hình, `direct-subpackages` là fallback mặc định. Kiểm tra `application.properties` hoặc `application.yml` để biết dự án có đang ghi đè strategy hay không.

```properties
spring.modulith.detection-strategy=direct-subpackages
```

Hoặc:

```yaml
spring:
  modulith:
    detection-strategy: direct-subpackages
```

Nếu dự án chuyển sang `explicitly-annotated`, các package trước đây được phát hiện tự động nhưng chưa có annotation sẽ biến mất khỏi module model. Đây là nguyên nhân thường gặp khi module từng xuất hiện rồi không còn xuất hiện sau một thay đổi cấu hình.

## 5. Khi dùng `explicitly-annotated`, hãy đánh dấu package module

Với strategy `explicitly-annotated`, package module phải có annotation `@ApplicationModule` hoặc jMolecules `@Module`.

Ví dụ dùng `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.order;
```

Đặt file tại:

```text
src/main/java/com/acme/shop/order/package-info.java
```

Sau đó cấu hình:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Trong Kotlin, có thể đặt annotation `@ApplicationModule` lên một type ở package gốc của module thay vì dùng `package-info.java`:

```kotlin
package com.acme.shop.order

import org.springframework.modulith.ApplicationModule

@ApplicationModule
class ModuleMetadata
```

Nếu đã chọn `explicitly-annotated` nhưng quên annotation, package sẽ không được chọn làm module. Hãy kiểm tra annotation được biên dịch vào đúng package, không đặt `package-info.java` ở thư mục khác và không nhầm `@NamedInterface` với `@ApplicationModule`: `@NamedInterface` công khai một API package con, không thay thế việc đánh dấu module khi dùng explicit detection.

## 6. Bổ sung root package bằng `@Modulithic`

Nếu module nằm ở một namespace khác với package của lớp ứng dụng, dùng `additionalPackages` để yêu cầu Spring Modulith chạy detection cho các root bổ sung.

Ví dụ:

```text
com.acme.shop                         <- root của ShopApplication
├── ShopApplication.java
├── order
└── inventory

com.acme.shared                       <- root bổ sung
├── customer
└── reference
```

Khai báo:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.acme.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Spring Modulith sẽ phát hiện module dưới cả `com.acme.shop` và `com.acme.shared`. Các package `customer` và `reference` có thể xuất hiện trong module model tùy detection strategy đang sử dụng.

Nếu nhiều root có module con trùng tên cục bộ, chẳng hạn cả hai root đều có package `catalog`, bật `useFullyQualifiedModuleNames = true` để phân biệt identifier:

```java
@Modulithic(
        additionalPackages = "com.acme.shared",
        useFullyQualifiedModuleNames = true
)
@SpringBootApplication
public class ShopApplication {
}
```

Khi đó identifier có thể là `com.acme.shop.catalog` và `com.acme.shared.catalog` thay vì cùng là `catalog`.

## 7. Kiểm tra module có tồn tại nhưng tra cứu sai identifier

Một module có thể đã được phát hiện nhưng lookup vẫn trả về empty vì tên dùng để tra cứu không khớp logical identifier.

Ví dụ, ứng dụng bật fully qualified naming:

```java
var modules = ApplicationModules.of(ShopApplication.class);

var catalog = modules.getModuleByName("com.acme.shared.catalog");
```

Trong trường hợp đó, lời gọi sau có thể không tìm thấy module:

```java
modules.getModuleByName("catalog");
```

Hãy in identifier của từng module trước khi sửa cấu hình:

```java
modules.forEach(module -> System.out.println(
        module.getIdentifier() + " -> " + module.getBasePackage()
));
```

`useFullyQualifiedModuleNames` thay đổi cách đặt identifier; nó không thay đổi package nào được chọn làm module. Nếu module hoàn toàn không có trong danh sách, hãy quay lại root package và detection strategy.

## 8. Kiểm tra custom detection strategy

Nếu package structure của legacy application không phù hợp với hai strategy dựng sẵn, triển khai `ApplicationModuleDetectionStrategy`. Interface này nhận root package và trả về stream các package được chọn làm module base package.

Ví dụ, một ứng dụng legacy đặt module dưới namespace `features`:

```text
com.acme.shop
├── ShopApplication.java
└── features
    ├── order
    ├── inventory
    └── catalog
```

Một strategy có thể chọn các package con của `features`:

```java
package com.acme.shop.architecture;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class FeatureModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage) {
        return rootPackage.getSubPackagesMatching((candidate, trailingName) -> {
            String[] segments = trailingName.split("\\.");
            return segments.length == 2 && segments[0].equals("features");
        });
    }
}
```

`getSubPackagesMatching(...)` nhận package ứng viên và tên tương đối tính từ root. Điều kiện giữ lại các package có đúng hai segment, ví dụ `features.order`, `features.inventory` và `features.catalog`; package sâu hơn như `features.order.internal` không trở thành module riêng.

Đăng ký class strategy qua property:

```properties
spring.modulith.detection-strategy=com.acme.shop.architecture.FeatureModuleDetectionStrategy
```

Custom strategy phải trả về đúng các package dự định làm module. Nếu strategy trả về package cha `features` thay vì các package `order`, `inventory`, `catalog`, module model sẽ có một module lớn hơn dự kiến.

Nếu strategy được dùng trong architecture test, đặt implementation và property vào test configuration cũng có thể đủ cho mục đích test. Nếu ứng dụng dùng runtime module model, runtime verification, `ApplicationModuleInitializer`, Actuator hoặc observability, hãy bảo đảm custom strategy và cấu hình của nó có mặt trên production classpath. Test và runtime cần sử dụng cùng quy tắc detection để không tạo hai module arrangement khác nhau.

## 9. Kiểm tra root package bổ sung và module source từ thư viện

`additionalPackages` phù hợp khi biết trước các root bổ sung. Nếu một thư viện hoặc module khác cần đóng góp application module từ package ngoài root của ứng dụng, Spring Modulith còn hỗ trợ `ApplicationModuleSource` và `ApplicationModuleSourceFactory`.

Factory có thể được đăng ký trong `META-INF/spring.factories` với key:

```properties
org.springframework.modulith.core.ApplicationModuleSourceFactory=com.acme.shared.SharedModuleSourceFactory
```

Factory trả về root package cần quét hoặc các module base package tường minh. Đây là cơ chế nâng cao cho kiến trúc nhiều artifact; không cần dùng nó nếu `additionalPackages` đã giải quyết được cấu trúc của ứng dụng.

Khi module từ dependency ngoài không xuất hiện, hãy xác định package đó có nằm trong root được quét, đã được thêm bằng `additionalPackages`, hay được đóng góp bằng `ApplicationModuleSourceFactory`. Chỉ thêm dependency JAR vào build chưa có nghĩa mọi package của JAR sẽ tự động trở thành application module của ứng dụng.

## 10. Kiểm tra exclusions và classpath

`ApplicationModules.of(applicationClass, ignored)` cho phép truyền predicate để loại một số Java type khỏi module inspection. Nếu predicate vô tình khớp với các type trong package module mong đợi, kết quả module model có thể thiếu hoặc khác dự kiến.

Ví dụ:

```java
import com.tngtech.archunit.core.domain.JavaClass;

var modules = ApplicationModules.of(
        ShopApplication.class,
        JavaClass.Predicates.resideInAPackage("com.acme.shop.inventory..")
);
```

Predicate trên loại toàn bộ type trong `inventory` khỏi inspection; đây là ví dụ minh họa một exclusion quá rộng. Nếu module `inventory` không xuất hiện, hãy xem lại predicate được truyền vào `ApplicationModules.of(...)`.

Ngoài ra, kiểm tra:

- Package có source file được biên dịch vào classpath của test hoặc runtime hay không.
- `package` declaration trong Java/Kotlin có khớp với package path dự kiến không.
- Test có đang chạy trên module/classpath chứa module cần phân tích không.
- Build đa module có đưa artifact chứa package cần tìm vào test/runtime classpath không.
- Không nhầm thư mục rỗng với Java package có type được biên dịch.

Module model chỉ có thể phân tích các type mà classpath và package scan cung cấp cho nó. Một thư mục source chưa được biên dịch hoặc không có type được nhận diện sẽ không tự trở thành module.

## 11. Phân biệt module detection với named interface detection

Đôi khi module đã xuất hiện nhưng package API con không được nhận diện như mong muốn. Đây là vấn đề named interface detection, không phải module detection.

Ví dụ:

```text
com.acme.shop.order                  <- module order đã được phát hiện
├── OrderManagement.java
├── spi
│   ├── package-info.java             <- @NamedInterface("spi")
│   └── OrderEvents.java
└── internal
    └── OrderRepository.java
```

Nếu `order` xuất hiện trong `ApplicationModules` nhưng `order::spi` không xuất hiện, kiểm tra `@NamedInterface` trong package `spi` hoặc custom named interface detection. Không đổi `spring.modulith.detection-strategy` chỉ để sửa một named interface bị thiếu.

Tương tự, `allowedDependencies` chỉ kiểm soát module nào được phép phụ thuộc vào module hoặc named interface khác. Nó không làm cho package chưa được phát hiện trở thành module.

## 12. Quy trình chẩn đoán theo thứ tự

Khi module mong đợi không xuất hiện, hãy thực hiện lần lượt:

1. Tạo `ApplicationModules` từ đúng lớp Spring Boot application.
2. In toàn bộ module và ghi lại base package, logical identifier.
3. Xác định root package thực tế từ package declaration của lớp ứng dụng.
4. Kiểm tra module có phải package con trực tiếp của root không.
5. Đọc `spring.modulith.detection-strategy` trong properties, YAML và test configuration.
6. Nếu dùng `explicitly-annotated`, xác nhận `@ApplicationModule` hoặc jMolecules `@Module` nằm đúng package.
7. Nếu module nằm ngoài root, thêm `additionalPackages` hoặc dùng cơ chế module source phù hợp.
8. Nếu dùng custom strategy, kiểm tra implementation trả về đúng package và có trên classpath cần thiết.
9. Kiểm tra exclusions, source set và dependency classpath.
10. Nếu module đã tồn tại, so sánh `getIdentifier()` với tên truyền vào `getModuleByName()`.
11. Nếu chỉ thiếu API package con, kiểm tra named interface metadata thay vì module detection.
12. Chạy lại architecture test và kiểm tra `verify()` sau khi module model đã đúng.

## 13. Ví dụ kiểm tra kết quả trong JUnit

Sau khi sửa cấu hình, tạo test để khóa kỳ vọng về module model:

```java
package com.acme.shop.architecture;

import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleDetectionTests {

    @Test
    void detectsExpectedModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("order")).isPresent();
        assertThat(modules.getModuleByName("inventory")).isPresent();

        modules.verify();
    }
}
```

Nếu bật fully qualified module names, thay tên trong assertion bằng identifier đầy đủ. Bài test vừa xác nhận module được phát hiện, vừa xác minh các quy tắc kiến trúc của module model.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không module nào hoặc thiếu nhiều module | Truyền sai application class hoặc root package quá sâu | Dùng đúng lớp `@SpringBootApplication`, kiểm tra package gốc |
| Chỉ thấy module `business`, không thấy `business.order` | `order` không phải package con trực tiếp của root | Điều chỉnh package hoặc dùng explicit/custom detection |
| Module biến mất sau khi đổi cấu hình | Strategy chuyển sang `explicitly-annotated` nhưng package chưa có annotation | Thêm `@ApplicationModule` hoặc jMolecules `@Module` |
| Package ngoài root không xuất hiện | Chưa khai báo `additionalPackages` hoặc module source | Bổ sung root package hoặc `ApplicationModuleSourceFactory` |
| Module xuất hiện nhưng lookup trả về empty | Dùng local name trong khi fully qualified naming đang bật | In `getIdentifier()` và tra cứu bằng identifier thực tế |
| Module không xuất hiện trong runtime nhưng test có | Custom strategy chỉ nằm trong test sources hoặc cấu hình khác nhau | Đưa strategy cần thiết vào production classpath và đồng bộ property |
| Module biến mất khi truyền predicate | Exclusion predicate khớp các type của module | Thu hẹp hoặc bỏ exclusion không phù hợp |
| Module có nhưng `::spi` không có | Nhầm module detection với named interface detection | Kiểm tra `@NamedInterface` và named interface strategy |
| `@ApplicationModule` không có tác dụng | Đang dùng strategy mặc định và kỳ vọng annotation tạo module ở vị trí bất kỳ | Dùng explicit/custom strategy hoặc điều chỉnh package structure |
| Module trong thư mục source không được thấy | Package chưa được biên dịch hoặc không thuộc classpath scan | Kiểm tra source set, package declaration và build classpath |

## 15. Ghi nhớ

Khi không phát hiện được module mong đợi, hãy kiểm tra root package của lớp ứng dụng, độ sâu package và detection strategy trước. `direct-subpackages` chỉ chọn package con trực tiếp; `explicitly-annotated` yêu cầu `@ApplicationModule` hoặc jMolecules `@Module`. Dùng `additionalPackages` cho root ngoài package ứng dụng và `ApplicationModuleDetectionStrategy` khi cần quy tắc riêng. Sau đó kiểm tra classpath, exclusions và identifier. Nếu module đã xuất hiện nhưng named interface không có, xử lý metadata API riêng. Luôn in module model thực tế và khóa kỳ vọng bằng architecture test để tránh lỗi detection quay lại.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals – ApplicationModules và Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Appendix – `spring.modulith.detection-strategy`](https://docs.spring.io/spring-modulith/reference/appendix.html)
- [Spring Modulith API – `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith API – `Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith API – `ApplicationModuleSourceFactory`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleSourceFactory.html)
