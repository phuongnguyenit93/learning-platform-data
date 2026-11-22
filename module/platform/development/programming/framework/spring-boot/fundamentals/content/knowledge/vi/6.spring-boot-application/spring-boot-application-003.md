# `@ComponentScan` tìm ứng viên bean trong phạm vi nào?

Trong Spring Boot, bạn chỉ cần viết `@Service`, `@Repository` hoặc `@RestController` trên một lớp rồi dùng constructor injection để sử dụng lớp đó. Nhưng cơ chế này không áp dụng cho mọi lớp trong mọi package của dự án. **Spring phải biết phạm vi package cần quét**, nhận diện những lớp có thể trở thành bean, rồi đăng ký các bean definition phù hợp trong application context.

Đó là vai trò của `@ComponentScan`. Với ứng dụng Spring Boot thông thường, `@SpringBootApplication` đã bao gồm `@ComponentScan` thông qua meta-annotation, vì vậy bạn ít khi phải khai báo nó thủ công. Hiểu phạm vi quét mặc định sẽ giúp bạn sắp xếp package hợp lý và xử lý lỗi dependency injection như “không tìm thấy bean”.

## 1. `@ComponentScan` là gì?

`@ComponentScan` là annotation của Spring Framework, cho phép Spring **tìm các lớp ứng viên bean** trong một hoặc nhiều package dựa trên những điều kiện nhận diện đã cấu hình. Một lớp được đánh dấu `@Component` hoặc stereotype được xây trên `@Component` có thể được tìm thấy trong quá trình quét.

Ví dụ:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String productName() {
        return "Notebook";
    }
}
```

Khi package `com.example.shop.service` nằm trong phạm vi component scan, Spring thường có thể phát hiện `ProductService` và đăng ký bean definition tương ứng. Sau đó container tạo và quản lý bean theo cấu hình scope, lifecycle và dependency.

Phân biệt những khái niệm gần nhau:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Component scanning** | Tìm và nhận diện những lớp ứng viên bean trong các package được chỉ định |
| **Bean definition** | Thông tin Spring dùng để tạo, cấu hình và quản lý bean |
| **Bean** | Đối tượng được quản lý bởi Spring IoC container |
| **Dependency injection** | Container cung cấp các bean phụ thuộc cho một bean khác |
| **Auto-configuration** | Spring Boot tự áp dụng những cấu hình theo classpath, thuộc tính và điều kiện liên quan |

**Lưu ý:** “được phát hiện là ứng viên” không có nghĩa bean chắc chắn sẽ được tạo thành công. Bean definition có thể chịu điều kiện, profile, bộ lọc hoặc lỗi cấu hình; việc khởi tạo thực tế còn phụ thuộc lifecycle và scope.

## 2. Vì sao `@SpringBootApplication` có liên quan đến component scan?

Lớp khởi động Spring Boot thường có dạng:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp các chức năng chính:

```text
@SpringBootApplication
    ├── @SpringBootConfiguration
    ├── @EnableAutoConfiguration
    └── @ComponentScan
```

Trong đó:

- `@SpringBootConfiguration` chỉ ra lớp cấu hình chính của ứng dụng.
- `@EnableAutoConfiguration` cho phép Spring Boot áp dụng auto-configuration khi các điều kiện tương ứng được đáp ứng.
- `@ComponentScan` cho phép Spring tìm ứng viên bean từ package gốc thích hợp.

Trong ví dụ trên, do `ShopApplication` ở package `com.example.shop`, **phạm vi quét mặc định bắt đầu từ `com.example.shop`**, bao gồm package đó và tất cả các package con.

Không phải mọi bean của ứng dụng đều đến từ component scanning. Bean cũng có thể được tạo qua `@Bean`, `@Import`, auto-configuration, hoặc cơ chế đăng ký riêng của Spring Data và các thư viện tích hợp.

## 3. Phạm vi mặc định: package chứa lớp cấu hình và các package con

Khi `@ComponentScan` không được chỉ định `basePackages` hoặc `basePackageClasses`, Spring dùng **package của lớp khai báo `@ComponentScan`** làm gốc. Trong ứng dụng dùng `@SpringBootApplication` trực tiếp trên lớp main, đó thường là package chứa lớp main.

Ví dụ cấu trúc:

```text
src/main/java/
└── com/
    └── example/
        ├── shop/
        │   ├── ShopApplication.java       <-- @SpringBootApplication
        │   ├── controller/
        │   │   └── ProductController.java <-- được quét
        │   ├── service/
        │   │   └── ProductService.java    <-- được quét
        │   ├── repository/
        │   │   └── ProductCache.java      <-- được quét nếu là component phù hợp
        │   └── config/
        │       └── TimeConfig.java        <-- được quét nếu là component phù hợp
        └── shared/
            └── SharedFormatter.java       <-- nằm ngoài phạm vi mặc định
```

Đối với `ShopApplication` đặt tại `com.example.shop`, các package sau nằm trong vùng mặc định:

```text
com.example.shop
com.example.shop.controller
com.example.shop.service
com.example.shop.repository
com.example.shop.config
com.example.shop.service.internal
```

Các package này **không** nằm trong phạm vi mặc định:

```text
com.example
com.example.shared
com.example.billing
org.othercompany.common
```

Đây là quy tắc dựa trên **tên package Java**, không dựa trên việc các file cùng nằm trong một repository, cùng module Gradle/Maven hay cùng thư mục `src`. Một dependency JAR nằm trên classpath cũng không được quét toàn bộ theo mặc định nếu các package của nó không thuộc vùng quét.

### 3.1. Ví dụ ba lớp trong cùng ứng dụng

`ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`ProductService.java`:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String findName() {
        return "Keyboard";
    }
}
```

`ProductController.java`:

```java
package com.example.shop.controller;

import com.example.shop.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/product-name")
    public String productName() {
        return productService.findName();
    }
}
```

Trong ứng dụng có Spring Web phù hợp và chạy ở cổng mặc định, endpoint:

```text
GET http://localhost:8080/product-name
```

có thể trả về:

```text
Keyboard
```

Spring phát hiện `ProductService` và `ProductController` vì hai lớp ở trong các package con của `com.example.shop`, rồi resolve tham số constructor của controller đến bean `ProductService`.

### 3.2. Thử đặt lớp ở package anh em

Giả sử đổi package của `ProductService` thành:

```java
package com.example.shared;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String findName() {
        return "Keyboard";
    }
}
```

Sau khi sửa import của controller để chương trình vẫn biên dịch, lớp service **không còn nằm dưới `com.example.shop`**. Nếu không có cơ chế đăng ký bean nào khác, Spring có thể báo lỗi khi tạo controller:

```text
Parameter 0 of constructor in ...ProductController
required a bean of type '...ProductService' that could not be found.
```

Thông báo thật thay đổi tùy phiên bản Spring Boot và dạng injection. Điểm cần kiểm tra ở đây là **service có trong classpath nhưng nằm ngoài vùng component scan**. Việc Java import được lớp chỉ chứng minh lớp đó có thể được tham chiếu khi biên dịch; import không khiến Spring tự đăng ký một bean.

## 4. Spring nhận diện những ứng viên bean nào?

Trong component scan thông thường, Spring nhận diện những lớp mang `@Component` và các annotation chuyên biệt được xây trên `@Component` (*stereotype annotations*).

| Annotation | Ý nghĩa phổ biến | Có thể được component scan mặc định tìm thấy? |
| --- | --- | --- |
| `@Component` | Thành phần ứng dụng nói chung | Có |
| `@Service` | Tầng nghiệp vụ | Có |
| `@Repository` | Tầng truy cập dữ liệu theo kiểu Spring component | Có |
| `@Controller` | Spring MVC controller | Có |
| `@RestController` | REST controller (`@Controller` + `@ResponseBody`) | Có |
| `@Configuration` | Lớp cấu hình Spring (`@Component` chuyên biệt) | Có |
| Annotation tùy biến có meta-annotation `@Component` | Stereotype của dự án | Có thể có, theo quy tắc nhận diện của Spring |

Ví dụ một component thông thường:

```java
package com.example.shop.util;

import org.springframework.stereotype.Component;

@Component
public class OrderCodeGenerator {
    public String generate(long orderId) {
        return "ORD-" + orderId;
    }
}
```

Nếu lớp ở trong package được quét và không bị điều kiện/bộ lọc loại bỏ, Spring sẽ xem nó là ứng viên bean.

### 4.1. Meta-annotation cũng được tính

`@Service` có meta-annotation `@Component`. Vì vậy:

```java
@Service
public class PriceService {
}
```

có thể được nhận diện dù trên lớp không viết trực tiếp `@Component`. Bạn còn có thể tự khai báo stereotype:

```java
package com.example.shop.stereotype;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface UseCase {
}
```

```java
package com.example.shop.application;

import com.example.shop.stereotype.UseCase;

@UseCase
public class CheckoutUseCase {
}
```

`CheckoutUseCase` là ứng viên bean nếu nằm trong vùng quét. Annotation `@UseCase` chỉ đóng vai trò stereotype ở ví dụ này; nếu cần tên bean hay logic chuyên biệt, phải cấu hình thêm một cách tương ứng.

### 4.2. Không phải annotation nào cũng khiến lớp được quét

Một vài annotation dễ gây nhầm:

- `@Entity` mô tả entity JPA; nó **không tự biến entity thành Spring component**. Entity được cơ chế JPA quản lý theo cách riêng.
- `@Embeddable` và `@MappedSuperclass` cũng thuộc mô hình JPA, không phải stereotype của component scan.
- `@ControllerAdvice` là một stereotype chuyên biệt có liên quan đến `@Component`, nên có thể được component scan phát hiện trong vùng quét.
- Interface mở rộng `JpaRepository` thường được đăng ký qua cơ chế quét repository của Spring Data, **khác** component scan thông thường.
- Phương thức có `@Bean` được xử lý trong quá trình cấu hình Spring; bản thân phương thức không phải một lớp để component scan tìm.

Ví dụ:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CurrencyConfiguration {

    @Bean
    public CurrencyFormatter currencyFormatter() {
        return new CurrencyFormatter();
    }
}
```

Trong trường hợp này, component scan có thể phát hiện **lớp** `CurrencyConfiguration` vì `@Configuration` là một stereotype. Sau đó cơ chế xử lý configuration của Spring đọc `@Bean` và đăng ký bean do phương thức `currencyFormatter()` tạo. Hai bước này liên quan nhưng không đồng nhất.

## 5. Thay đổi phạm vi quét bằng `scanBasePackages`

Khi cấu trúc dự án bắt buộc đặt component ngoài package gốc, `@SpringBootApplication` có thuộc tính `scanBasePackages` để chỉ định những package cần component scan.

Ví dụ:

```text
com.example
├── shop
│   └── ShopApplication.java
├── shared
│   └── SharedFormatter.java
└── billing
    └── BillingService.java
```

Ứng dụng muốn quét `com.example.shop` và `com.example.shared`, nhưng chưa muốn quét `com.example.billing`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.shared"
    }
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Trong cấu hình này:

```text
com.example.shop               được quét
com.example.shop.controller    được quét
com.example.shared             được quét
com.example.shared.formatter   được quét
com.example.billing            không được thêm vào vùng quét này
```

Bạn cũng có thể chọn `scanBasePackages = "com.example"` để bao phủ tất cả package con. Tuy nhiên, vùng quét quá rộng dễ đưa vào context những component, cấu hình hoặc bean không dự định sử dụng. Hãy chọn package gốc vừa đủ theo cấu trúc ứng dụng.

### 5.1. `scanBasePackages` và `@ComponentScan(basePackages = ...)`

Hai cách viết sau biểu đạt ý tưởng cấu hình vùng component scan:

```java
@SpringBootApplication(
    scanBasePackages = {"com.example.shop", "com.example.shared"}
)
public class ShopApplication {
}
```

và ví dụ cấu hình Spring trực tiếp:

```java
@Configuration
@ComponentScan(
    basePackages = {"com.example.shop", "com.example.shared"}
)
public class ComponentScanConfiguration {
}
```

`scanBasePackages` của `@SpringBootApplication` là alias tới thuộc tính `basePackages` của `@ComponentScan`. Với ứng dụng Spring Boot thông thường, bạn nên ưu tiên cấu hình ngay trên `@SpringBootApplication` khi chỉ muốn đổi gốc quét; những tình huống cần bộ lọc nâng cao có thể dùng cấu hình `@ComponentScan` trực tiếp.

**Chú ý:** khi đặt `@ComponentScan` trực tiếp trên chính lớp `@SpringBootApplication`, khai báo trực tiếp có thể được ưu tiên hơn `@ComponentScan` do meta-annotation cung cấp. Tránh chồng nhiều cấu hình component scan mà không hiểu tác động.

### 5.2. `scanBasePackageClasses` tránh ghi cứng tên package

Tên package ghi bằng chuỗi dễ lỗi sau khi đổi cấu trúc mã nguồn. Spring Boot cũng hỗ trợ cách khai báo theo **class nằm trong package cần quét**:

```java
package com.example.shared;

public final class SharedPackageMarker {
    private SharedPackageMarker() {
    }
}
```

Trong lớp main:

```java
package com.example.shop;

import com.example.shared.SharedPackageMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        SharedPackageMarker.class
    }
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Spring sử dụng **package của mỗi class được chỉ định**, không nhất thiết chỉ quét riêng class đó:

- `ShopApplication.class` xác định package `com.example.shop`.
- `SharedPackageMarker.class` xác định package `com.example.shared`.
- Các package con tương ứng cũng nằm trong vùng quét.

`SharedPackageMarker` không cần là Spring bean. Nó chỉ là một kiểu đánh dấu để compiler và công cụ refactor có thể kiểm tra tham chiếu thay vì phụ thuộc tên package viết tay.

## 6. Vị trí lớp `@SpringBootApplication` quyết định phạm vi mặc định

Một cách tổ chức giúp hạn chế cấu hình là đặt lớp main ở **package gốc chung của các thành phần thuộc ứng dụng**:

```text
com.example.shop
├── ShopApplication.java
├── api
│   └── ProductController.java
├── application
│   └── ProductService.java
├── domain
│   └── Product.java
└── infrastructure
    └── ProductAdapter.java
```

Khi đó, `@SpringBootApplication` không cần `scanBasePackages` để tìm các component của ứng dụng trong package con.

Nếu đặt main quá sâu:

```text
com.example.shop
├── api
│   └── ProductController.java
└── bootstrap
    └── ShopApplication.java  <-- nằm tại com.example.shop.bootstrap
```

thì vùng quét mặc định sẽ bắt đầu ở `com.example.shop.bootstrap`; controller tại `com.example.shop.api` nằm ngoài vùng đó. Dời lớp main lên `com.example.shop` hoặc khai báo vùng quét phù hợp là hai hướng xử lý.

### 6.1. Tránh default package

Java cho phép lớp không khai báo `package`, nhưng điều đó không phù hợp để đặt ứng dụng Spring Boot:

```java
// Không khai báo package: nên tránh
@SpringBootApplication
public class Application {
}
```

Lớp main trong **default package** có thể khiến component scan quét phạm vi cực rộng của classpath, gây chậm hoặc nhận diện những lớp không mong muốn. Hãy luôn sử dụng package có tên, ví dụ `com.example.shop`.

### 6.2. Nhiều module không đồng nghĩa với nhiều vùng quét

Giả sử một project có hai module:

```text
shop-app
  com.example.shop.ShopApplication

shared-library
  com.example.shared.EmailFormatter
```

Ngay cả khi `shop-app` có dependency tới `shared-library`, component `EmailFormatter` vẫn không tự được quét nếu package của nó nằm ngoài vùng mặc định. Library có mặt trên classpath chỉ là điều kiện để Spring có thể nhìn thấy lớp; **component scan vẫn cần bao phủ package tương ứng** hoặc bean phải được đăng ký theo cơ chế khác.

Trong library tái sử dụng cho nhiều ứng dụng, lựa chọn thiết kế còn có thể là cung cấp cấu hình và để ứng dụng `@Import` cấu hình đó, hoặc dùng cơ chế auto-configuration của Spring Boot khi thích hợp. Không nhất thiết mở rộng toàn bộ vùng quét tới mọi package của thư viện.

## 7. Phạm vi component scan khác phạm vi entity và repository

Đây là điểm dễ nhầm khi bắt đầu dùng Spring Data JPA:

```java
@SpringBootApplication(scanBasePackages = "com.example")
```

Thuộc tính `scanBasePackages` (và `scanBasePackageClasses`) của `@SpringBootApplication` **chỉ điều chỉnh component scan**. Nó không tự thay đổi mọi phạm vi mà các cơ chế riêng khác dùng để tìm JPA entity hoặc Spring Data repository.

| Đối tượng cần tìm | Cơ chế tương ứng | Cấu hình phạm vi thường dùng |
| --- | --- | --- |
| `@Service`, `@Controller`, `@Component` | Spring component scanning | `@ComponentScan`, `@SpringBootApplication(scanBasePackages = ...)` |
| JPA `@Entity` | JPA entity scanning/auto-configuration | Mặc định theo package ứng dụng; có thể dùng `@EntityScan` |
| Interface `JpaRepository` | Spring Data repository scanning | Mặc định theo cấu hình ứng dụng; có thể dùng `@EnableJpaRepositories` |

Ví dụ cấu trúc có module JPA nằm ngoài package main:

```text
com.example.shop
  ShopApplication
  service/ProductService

com.example.persistence
  entity/ProductEntity
  repository/ProductRepository
```

Trong cấu hình cần chỉ định rõ các vùng tìm kiếm:

```java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.persistence"
    }
)
@EntityScan(basePackages = "com.example.persistence.entity")
@EnableJpaRepositories(basePackages = "com.example.persistence.repository")
public class ShopApplication {
}
```

Đoạn mã minh họa cách cấu hình từng phạm vi; một ứng dụng thật còn cần datasource, JPA provider và những dependency tương ứng. Trong nhiều dự án có cấu trúc package hợp lý, auto-configuration mặc định đã đủ và không cần hai annotation bổ sung.

**Không nên dùng `@Component` trên entity chỉ để ép nó vào component scan.** Entity JPA và Spring bean có vai trò, lifecycle và cách quản lý khác nhau.

## 8. Mở rộng hoặc thu hẹp phạm vi bằng filter

Ngoài chỉ định package, `@ComponentScan` cho phép chọn thêm hoặc loại bớt ứng viên bằng `includeFilters` và `excludeFilters`.

Ví dụ loại một component cụ thể khỏi quá trình quét:

```java
package com.example.shop;

import com.example.shop.integration.LegacyGateway;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyGateway.class
    )
)
public class ShopApplication {
}
```

Khi đó, lớp `LegacyGateway` không được đăng ký qua đường component scan vừa cấu hình. Nhưng nếu một `@Bean`, `@Import`, auto-configuration hoặc cơ chế khác đăng ký cùng kiểu bean, **filter không chặn những con đường đăng ký khác**.

Những kiểu filter thường gặp:

| `FilterType` | Cách chọn |
| --- | --- |
| `ANNOTATION` | Dựa trên annotation của ứng viên |
| `ASSIGNABLE_TYPE` | Dựa trên kiểu class/interface |
| `REGEX` | Dựa trên biểu thức chính quy khớp tên class |
| `ASPECTJ` | Dựa trên biểu thức kiểu AspectJ |
| `CUSTOM` | Logic lọc do bạn tự cài đặt |

### 8.1. `useDefaultFilters = false`

Theo mặc định, component scan nhận diện các stereotype Spring như `@Component`. Nếu cấu hình:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = MyFeature.class
    )
)
```

thì bạn đã **tắt bộ lọc mặc định**, và cần chỉ định rõ loại ứng viên muốn nhận diện trong `includeFilters`. Ví dụ này giả định `MyFeature` là annotation type được dự án định nghĩa. Tùy filter, Spring có thể chọn các class không mang `@Component` theo tiêu chí tương ứng, miễn đủ điều kiện để trở thành bean definition.

Việc thay đổi filter trong lớp cấu hình chính ảnh hưởng đến nhiều thành phần của ứng dụng. Với dự án đầu tiên, giải pháp đơn giản nhất thường vẫn là đặt main ở package gốc đúng và sử dụng component scan mặc định.

### 8.2. Profile và condition không phải là giới hạn package

Ví dụ:

```java
package com.example.shop.service;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("dev")
public class DevelopmentMailService {
}
```

Lớp `DevelopmentMailService` nằm trong vùng quét, nhưng bean chỉ được đăng ký khi profile `dev` phù hợp. Tương tự, các điều kiện như `@ConditionalOnProperty` có thể quyết định bean có được đăng ký hay không.

Vì vậy có hai câu hỏi độc lập:

1. **Spring có quét tới package chứa lớp này không?**
2. **Nếu tìm thấy lớp, những điều kiện đăng ký bean có được thỏa mãn không?**

Nếu không có bean tại runtime, nguyên nhân có thể đến từ cả hai bước.

## 9. Component scan có tải và khởi tạo mọi class không?

Không. Spring có thể dùng cơ chế đọc metadata từ các file `.class` để nhận diện ứng viên mà không cần tải và khởi tạo tất cả class ngay lúc quét. Sau khi nhận diện, framework đăng ký bean definition, áp dụng các điều kiện và tiến hành khởi tạo bean theo lifecycle/scopes tương ứng.

Một số bean singleton thường được khởi tạo trong quá trình khởi động context; bean lazy hoặc prototype có thể được tạo khi thực sự cần. Việc quét nhiều package làm tăng lượng class metadata phải xem xét nhưng không có nghĩa mọi class trong vùng quét đều trở thành bean.

Ngoài ra, nhiều bean thiết yếu của Spring Boot, Spring MVC, DataSource hay các module khác có thể xuất hiện nhờ auto-configuration hoặc `@Bean` trong configuration class. Không nên suy luận rằng mọi bean nhìn thấy trong `ApplicationContext` đều do `@ComponentScan` phát hiện trực tiếp.

## 10. Cách xác định bean có được Spring đăng ký không

Khi dependency injection thất bại, trước tiên xem lớp main và vị trí package của component. Tiếp theo, bạn có thể hỏi trực tiếp `ApplicationContext`.

Ví dụ:

```java
package com.example.shop;

import com.example.shop.service.ProductService;
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    @Bean
    CommandLineRunner inspectBeans(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(ProductService.class);
            System.out.println("ProductService beans: " + Arrays.toString(names));
        };
    }
}
```

Với `ProductService` được đăng ký theo tên mặc định, ví dụ đầu ra:

```text
ProductService beans: [productService]
```

Ví dụ trên minh họa cách tra cứu khi ứng dụng khởi động được; trong ứng dụng thực tế, nếu context thất bại sớm vì thiếu bean bắt buộc, đoạn `CommandLineRunner` sẽ không có cơ hội chạy. Khi đó cần đọc lỗi startup và sửa vấn đề khai báo/đăng ký bean trước.

Một cách khác để xem có bean cụ thể là dùng:

```java
boolean available = context.getBeansOfType(ProductService.class).size() > 0;
```

Tuy nhiên, thao tác `getBeansOfType` có thể làm phát sinh khởi tạo bean trong một số trường hợp. Trong bước chẩn đoán đơn giản, `getBeanNamesForType` thường phù hợp hơn để xem danh sách tên bean theo kiểu.

### 10.1. Phân biệt “không tìm thấy lớp” và “không tìm thấy bean”

| Hiện tượng | Ý nghĩa có thể có |
| --- | --- |
| Compiler báo `cannot find symbol` hoặc IDE không import được class | Vấn đề source code, dependency hoặc classpath biên dịch |
| Runtime báo `ClassNotFoundException`/`NoClassDefFoundError` | Thiếu hoặc không tương thích class trên runtime classpath |
| Spring báo `NoSuchBeanDefinitionException` / `No qualifying bean` | Class có thể tồn tại, nhưng container không có bean phù hợp |
| Spring báo `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp, container không biết chọn bean nào |
| Component nằm đúng package nhưng không có bean | Có thể vướng annotation, condition, profile, filter, kiểu class hoặc đường đăng ký bean |

Đừng sửa một lỗi “không có bean” bằng cách thêm `import` Java. `import` không mở rộng phạm vi component scan.

## 11. Những lỗi thiết kế package thường gặp

### 11.1. Main class nằm trong package quá sâu

```text
com.example.shop.bootstrap.ShopApplication
com.example.shop.api.ProductController
```

Với mặc định, scan từ `com.example.shop.bootstrap` không tìm được `com.example.shop.api`. Có thể chuyển main class lên `com.example.shop` hoặc chỉ định `scanBasePackages`.

### 11.2. Service nằm trong thư viện riêng, ngoài package gốc

```text
com.example.shop.ShopApplication
com.example.common.NotificationService
```

Phải bổ sung phạm vi scan có chủ đích hoặc cung cấp cấu hình đăng ký bean trong thư viện để ứng dụng import. Chỉ thêm dependency tới JAR của `common` chưa đủ để service tự được quét.

### 11.3. Lớp thiếu stereotype hoặc bị loại bởi filter

```java
package com.example.shop.service;

public class InvoiceService {
}
```

Lớp nằm đúng package nhưng không có `@Component`, `@Service`, meta-annotation phù hợp hoặc cơ chế đăng ký khác, nên component scan mặc định không đăng ký nó. Bạn có thể thêm `@Service` nếu muốn container quản lý lớp này, hoặc tạo bean bằng `@Bean` ở configuration.

### 11.4. Hiểu nhầm phạm vi của repository và entity

`@Entity` hoặc interface `JpaRepository` ở package ngoài vùng tự động tìm kiếm riêng của JPA/Spring Data có thể vẫn không được phát hiện dù bạn đã mở rộng component scan. Kiểm tra `@EntityScan`, `@EnableJpaRepositories` và package mặc định của ứng dụng khi cấu trúc nhiều module.

### 11.5. Quét package quá rộng

Khi quét một package cha chứa nhiều ứng dụng hoặc thư viện không liên quan, Spring có thể nhận những configuration/bean không mong muốn, gây trùng bean name, xung đột wiring hoặc tăng thời gian khởi động. Chọn vùng quét bao trùm thành phần cần dùng, nhưng không rộng hơn một cách tùy tiện.

## 12. Bài thực hành: dự đoán phạm vi scan

Cho cấu trúc:

```text
com.acme.store
├── StoreApplication.java        // @SpringBootApplication
├── web/OrderController.java     // @RestController
├── service/OrderService.java    // @Service
└── config/ClockConfig.java      // @Configuration

com.acme.shared
└── AuditService.java            // @Service

com.acme.billing
└── BillingService.java          // @Service
```

**Bài 1 — Mặc định.** Khi chỉ dùng `@SpringBootApplication` không có `scanBasePackages` trên `StoreApplication` ở `com.acme.store`, hãy xác định những class nào nằm trong vùng quét.

**Bài 2 — Mở rộng.** Muốn quét cả `AuditService` nhưng không quét `BillingService`, hãy sửa annotation của lớp main bằng `scanBasePackages` hoặc `scanBasePackageClasses`. Giải thích vì sao chọn `"com.acme"` có thể quá rộng so với yêu cầu.

**Bài 3 — Chuyển main.** Nếu đưa `StoreApplication` vào `com.acme.store.bootstrap` mà không đổi cấu hình khác, chuyện gì có thể xảy ra với `OrderController` và `OrderService`?

**Bài 4 — Không phải component.** Thêm `@Entity` vào một lớp `OrderEntity` nhưng không thêm `@Component`. Lớp này có trở thành Spring bean chỉ vì nằm trong vùng component scan không? Cơ chế nào quản lý entity JPA?

**Bài 5 — Điều kiện.** Gắn `@Profile("dev")` lên `OrderService`, rồi khởi động khi profile `dev` không active. Phạm vi scan có thay đổi không, và vì sao có thể thiếu bean khi inject `OrderService`?

Gợi ý tự đối chiếu:

- Bài 1: các thành phần dưới `com.acme.store` nằm trong vùng quét mặc định; `com.acme.shared` và `com.acme.billing` nằm ngoài.
- Bài 2: chọn `com.acme.store` và `com.acme.shared`, hoặc marker class tương ứng, để tránh quét cả `com.acme.billing`.
- Bài 3: package `bootstrap` không bao phủ các package anh em `web` và `service`; component scan mặc định có thể bỏ sót.
- Bài 4: entity được JPA provider quản lý qua entity scanning, không tự là Spring bean chỉ nhờ `@Entity`.
- Bài 5: vị trí package vẫn nằm trong vùng scan, nhưng điều kiện profile quyết định bean có được đăng ký.

## 13. Ghi nhớ khi xây dựng ứng dụng Spring Boot

`@ComponentScan` quyết định **tìm ứng viên bean ở package nào**. Khi gắn `@SpringBootApplication` lên lớp main, Spring Boot thường quét **package chứa lớp main và toàn bộ package con**, chứ không tự quét mọi package trong project.

Muốn mở rộng hoặc thay đổi vùng quét, có thể dùng `scanBasePackages`, `scanBasePackageClasses` hoặc cấu hình `@ComponentScan` phù hợp. Các annotation stereotype xác định **lớp nào** là ứng viên; profile, condition và filter tiếp tục ảnh hưởng đến **bean nào được đăng ký**. Đối với JPA entity và Spring Data repository, hãy nhớ rằng chúng có cơ chế tìm kiếm riêng.

Khi gặp lỗi thiếu bean, hãy xác định package của lớp `@SpringBootApplication`, package của dependency cần inject, annotation của lớp đó và những điều kiện cấu hình trước khi thay đổi code. Hiểu đúng ranh giới component scan là nền tảng để tổ chức cấu trúc dự án và sử dụng dependency injection một cách có chủ đích.
