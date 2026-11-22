# scanBasePackages và scanBasePackageClasses trong @SpringBootApplication

Khi bắt đầu với Spring Boot, bạn thường đặt class khởi động, controller và service trong cùng một cây package. Chỉ cần gắn **@SpringBootApplication** lên class chính, Spring có thể tự tìm và tạo các bean như **@RestController**, **@Service**, **@Repository** và **@Configuration**. Điều này làm cho dependency injection hoạt động mà không cần đăng ký thủ công từng class.

Nhưng điều gì xảy ra khi một service nằm ở **package bên cạnh**, hoặc bạn muốn tách ứng dụng thành nhiều module Java? Một lỗi quen thuộc là Spring báo **không tìm thấy bean** dù class đã được gắn **@Service**. Đó có thể là vấn đề **phạm vi component scanning**.

**scanBasePackages** và **scanBasePackageClasses** là hai thuộc tính của **@SpringBootApplication** dùng để chỉ định những package Spring cần quét để tìm component. Chúng có cùng mục đích, nhưng thể hiện package theo hai cách: **chuỗi tên package** và **tham chiếu tới class**.

## 1. Bắt đầu từ hành vi mặc định của @SpringBootApplication

Xét cấu trúc dự án:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── web/
    │   └── ProductController.java
    ├── service/
    │   └── ProductService.java
    └── config/
        └── ShopConfiguration.java
~~~

Class khởi động:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với cấu hình này, phạm vi **component scan mặc định** là:

~~~text
com.example.shop                 ← package chứa ShopApplication
├── ShopApplication
├── web                          ← được quét
│   └── ProductController
├── service                      ← được quét
│   └── ProductService
└── config                       ← được quét
    └── ShopConfiguration
~~~

Spring quét **package chứa class gắn @SpringBootApplication và các package con**. Khi tìm thấy class phù hợp với cơ chế component scanning, Spring đăng ký bean definition và tạo bean theo vòng đời của ApplicationContext.

Thông thường, Spring nhận diện các loại thành phần sau:

| Annotation | Vai trò thường gặp |
|---|---|
| **@Component** | Thành phần Spring tổng quát |
| **@Service** | Thành phần xử lý nghiệp vụ |
| **@Repository** | Thành phần truy cập dữ liệu |
| **@Controller** / **@RestController** | Thành phần xử lý request web |
| **@Configuration** | Class khai báo các cấu hình, có thể tạo bean qua **@Bean** |

Các annotation chuyên biệt như **@Service** hay **@RestController** đều liên quan tới cơ chế component stereotype. Vì vậy, khi nói “scan service”, thực chất ta đang nói tới **component scan**, chứ không có một bộ quét riêng chỉ dành cho service.

### Nếu class nằm ngoài package gốc thì sao?

Giả sử ứng dụng phát triển thành:

~~~text
com.example/
├── shop/
│   ├── ShopApplication.java          ← @SpringBootApplication
│   └── web/
│       └── ProductController.java
└── catalog/
    └── service/
        └── CatalogService.java       ← @Service
~~~

**com.example.catalog** là package **anh em** với **com.example.shop**, không nằm bên dưới nó:

~~~text
Mặc định quét: com.example.shop.**
Bao gồm:        com.example.shop.web.ProductController
Không bao gồm:  com.example.catalog.service.CatalogService
~~~

Nếu **ProductController** yêu cầu inject **CatalogService** nhưng Spring chưa đăng ký bean tương ứng bằng cách khác, ứng dụng có thể không khởi động được và báo lỗi kiểu **No qualifying bean of type ... available**.

Đây là trường hợp cần hiểu cách mở rộng phạm vi quét.

## 2. @SpringBootApplication liên quan gì tới @ComponentScan?

**@SpringBootApplication** là annotation tổng hợp nhiều hành vi khởi động quan trọng, thường được diễn giải như kết hợp:

- **@SpringBootConfiguration**: đánh dấu class là cấu hình chính của ứng dụng.
- **@EnableAutoConfiguration**: cho phép Spring Boot tự cấu hình dựa trên các điều kiện như dependency, bean hiện có và thuộc tính cấu hình.
- **@ComponentScan**: tìm những thành phần Spring trong các package được chỉ định.

Hai thuộc tính đang học là **alias** của thuộc tính tương ứng trên **@ComponentScan**:

| Thuộc tính trên @SpringBootApplication | Tương ứng trên @ComponentScan | Giá trị |
|---|---|---|
| **scanBasePackages** | **basePackages** | **String[]**: một hoặc nhiều tên package |
| **scanBasePackageClasses** | **basePackageClasses** | **Class<?>[]**: một hoặc nhiều class dùng làm mốc package |

Chúng thay đổi **phạm vi quét component của phần @ComponentScan** bên trong @SpringBootApplication. Chúng **không phải tùy chọn đổi toàn bộ cơ chế auto-configuration**, và cũng không tự động điều chỉnh mọi loại scanning khác như JPA entity scan hay repository scan.

Điểm khác biệt rất quan trọng:

~~~text
@SpringBootApplication
   ├── Cấu hình ứng dụng Spring
   ├── Auto-configuration
   └── Component scanning
          ├── scanBasePackages
          └── scanBasePackageClasses
~~~

Vì vậy, khi gặp lỗi thiếu bean, cần xác định đó là bean do **component scanning**, **@Bean**, **auto-configuration** hay một cơ chế đăng ký khác tạo ra. Không phải lỗi bean nào cũng được giải quyết bằng cách mở rộng package scan.

## 3. scanBasePackages: khai báo package bằng chuỗi

**scanBasePackages** nhận danh sách tên package Java theo kiểu **String[]**.

Ví dụ, muốn quét cả ứng dụng shop và module catalog:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi khởi động, Spring tìm component trong **cả hai package được liệt kê và các package con**.

~~~text
com.example/
├── shop/                           ← được quét
│   ├── ShopApplication.java
│   ├── web/ProductController.java  ← được tìm thấy nếu là component
│   └── service/CheckoutService.java
└── catalog/                        ← được quét
    ├── service/CatalogService.java ← được tìm thấy nếu là component
    └── config/CatalogConfiguration.java
~~~

Với một package duy nhất, có thể viết ngắn:

~~~java
@SpringBootApplication(scanBasePackages = "com.example")
public class ShopApplication {
    // ...
}
~~~

**Chú ý:** khai báo trên mở rộng phạm vi sang toàn bộ các package con của **com.example**, bao gồm những thành phần nằm ngoài hai chức năng shop và catalog nếu chúng cùng có mặt trong classpath. Điều này có thể là chủ ý, nhưng quét quá rộng dễ khiến bean không mong muốn cũng được đăng ký.

### Những quy tắc cần hiểu

**1. Danh sách khai báo là danh sách package gốc cần quét.**

Mỗi package gốc bao gồm chính nó cùng các package con. Nếu muốn quét **com.example.catalog**, không cần liệt kê thêm **com.example.catalog.service**.

**2. Thuộc tính ghi rõ package cần quét, không cộng ngầm package cũ.**

Khi đã chỉ định **scanBasePackages**, cần chủ động bao gồm **com.example.shop** nếu vẫn muốn quét các controller, service hay configuration ở đó. Ví dụ:

~~~java
@SpringBootApplication(
    scanBasePackages = "com.example.catalog"
)
public class ShopApplication {
}
~~~

Trong ví dụ trên, package **com.example.shop.web** không còn nằm trong các package gốc được chỉ định. Bản thân class **ShopApplication** vẫn là class cấu hình chính được SpringApplication sử dụng; điều đó không có nghĩa mọi bean bên dưới package của nó vẫn được tự động scan.

**3. Tên package là chuỗi ký tự.**

Nếu sau này đổi package **com.example.catalog** thành **com.example.inventory**, giá trị chuỗi cũ không tự đổi theo chỉ nhờ thao tác refactor Java. Cần nhớ cập nhật annotation.

**4. Class cần nằm trên runtime classpath.**

Viết đúng tên package không giúp Spring quét được một module hoặc JAR chưa được khai báo là dependency của ứng dụng. Class cần được biên dịch và có mặt trong classpath khi ứng dụng chạy.

**5. Scan không tự biến mọi class Java thành bean.**

Một class thông thường không có stereotype annotation, không được tạo qua **@Bean** hay cơ chế đăng ký khác sẽ không tự trở thành bean chỉ vì package được quét.

### Khi nào scanBasePackages tiện?

- Khi bạn cần khai báo rõ một vài package theo tên.
- Khi đang làm việc với cấu trúc mã hiện có và muốn thay đổi phạm vi scan nhanh chóng.
- Khi package nằm ở một phần ứng dụng nhưng chưa có class marker ổn định để tham chiếu.

Điểm cần cân nhắc là tên package viết bằng chuỗi **không được Java compiler kiểm tra như một tham chiếu class**, nên lỗi chính tả hoặc đổi tên package có thể chỉ bộc lộ khi chạy.

## 4. scanBasePackageClasses: khai báo package qua class

**scanBasePackageClasses** nhận một hoặc nhiều **Class<?>**. Với mỗi class được truyền vào, Spring lấy **package chứa class đó** làm package gốc để quét.

Giả sử có:

~~~text
com.example/
├── shop/
│   ├── ShopApplication.java
│   └── web/ProductController.java
└── catalog/
    ├── CatalogModuleMarker.java
    └── service/CatalogService.java
~~~

Tạo một class mốc trong package **com.example.catalog**:

~~~java
package com.example.catalog;

public final class CatalogModuleMarker {

    private CatalogModuleMarker() {
        // Chỉ dùng class này làm mốc nhận diện package.
    }
}
~~~

Sau đó cấu hình class khởi động:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModuleMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModuleMarker.class
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Spring sẽ dùng:

~~~text
ShopApplication.class
    └── package: com.example.shop
        └── quét com.example.shop và package con

CatalogModuleMarker.class
    └── package: com.example.catalog
        └── quét com.example.catalog và package con
~~~

**CatalogModuleMarker không cần gắn @Component, @Configuration hay @Service.** Nó chỉ là một **mốc xác định package**. Việc xuất hiện trong **scanBasePackageClasses** không có nghĩa Spring sẽ tự tạo bean của marker.

Thay vì class marker, bạn cũng có thể dùng một class hiện có:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogService.class
    }
)
public class ShopApplication {
}
~~~

Nhưng nếu **CatalogService** nằm ở **com.example.catalog.service**, Spring sẽ lấy **com.example.catalog.service** làm package gốc; các thành phần trong **com.example.catalog.config** hoặc **com.example.catalog.repository** không nằm dưới package đó. Vì vậy một **marker đặt ở package gốc** thường diễn đạt ý đồ rõ hơn.

### Marker interface cũng được

Bạn có thể dùng interface rỗng:

~~~java
package com.example.catalog;

public interface CatalogModule {
    // Marker đại diện cho gốc package catalog.
}
~~~

Và tham chiếu:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
public class ShopApplication {
}
~~~

Spring chỉ cần đối tượng **Class** để xác định package, nên marker class hay marker interface đều phù hợp. Trong nhiều codebase, marker có tên dễ nhận biết và đặt ở một package ổn định giúp cấu hình ít phụ thuộc vào tên một service cụ thể.

### Vì sao đây là cách type-safe hơn?

Khi viết **CatalogModule.class**, Java compiler và IDE nhận diện đó là một kiểu tồn tại. Nếu class bị xóa hoặc đổi tên nhưng cấu hình chưa cập nhật, lỗi tham chiếu thường được phát hiện trong quá trình biên dịch. IDE cũng có thể hỗ trợ đổi tên class và cập nhật import.

Tuy nhiên, **type-safe không có nghĩa tự động bảo đảm phạm vi scan đúng mãi mãi**. Nếu marker bị di chuyển sang một package khác, phạm vi scan cũng thay đổi theo. Cần đặt marker đúng cấp package gốc của module.

## 5. So sánh hai thuộc tính

| Tiêu chí | scanBasePackages | scanBasePackageClasses |
|---|---|---|
| Giá trị truyền vào | Chuỗi tên package | Class literal, ví dụ **CatalogModule.class** |
| Cách xác định gốc | Dùng tên package được khai báo | Lấy package chứa từng class |
| Phát hiện lỗi khi đổi tên class | Không áp dụng cho chuỗi | Tham chiếu class có thể được compiler/IDE kiểm tra |
| Khi đổi tên package | Cần sửa chuỗi cho khớp | Có thể giữ đúng phạm vi nếu marker được di chuyển đúng vị trí |
| Nguy cơ chọn package quá hẹp | Có, nếu chuỗi chỉ tên package con | Có, nếu tham chiếu class nằm trong package con |
| Đọc trong mã | Trực tiếp thấy tên package | Thấy những class đại diện cho package |
| Phù hợp | Dự án nhỏ hoặc cấu hình package theo tên | Dự án nhiều module muốn neo phạm vi scan bằng kiểu Java |

**Cả hai đều là cách chỉ định base packages cho component scan.** Không có thuộc tính nào khiến Spring quét entity, repository, DTO hay mọi class khác theo một cơ chế tổng quát duy nhất.

Trong codebase nhiều module, **scanBasePackageClasses** với marker ổn định thường giúp giảm lỗi do nhập sai tên package. Trong một project đơn giản chỉ có một package gốc, tốt nhất là giữ hành vi mặc định của **@SpringBootApplication** nếu nó đã đáp ứng nhu cầu.

## 6. Ví dụ hoàn chỉnh: controller và service nằm ở hai cây package

Ta tạo một ứng dụng Spring Boot REST nhỏ với hai phần:

- **shop** nhận HTTP request.
- **catalog** cung cấp nghiệp vụ trả thông tin sản phẩm.

Nếu tạo project qua Spring Initializr, chọn dependency **Spring Web**, ngôn ngữ Java, một phiên bản Spring Boot ổn định phù hợp và JDK tương ứng. Ví dụ dưới đây giả định **Java 21** và project dạng JAR. Với ứng dụng thật, catalog có thể nằm trong một module hoặc JAR riêng; khi đó **shop cần khai báo dependency build tới module/JAR catalog**.

### 6.1. Cây package

~~~text
src/main/java/
└── com/example/
    ├── shop/
    │   ├── ShopApplication.java
    │   └── web/
    │       └── ProductController.java
    └── catalog/
        ├── CatalogModule.java
        └── service/
            └── CatalogService.java
~~~

### 6.2. Service nghiệp vụ

File **com/example/catalog/service/CatalogService.java**:

~~~java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public String findProductName(long id) {
        if (id == 1L) {
            return "Spring Boot Handbook";
        }
        return "Unknown product";
    }
}
~~~

### 6.3. Marker tại gốc package catalog

File **com/example/catalog/CatalogModule.java**:

~~~java
package com.example.catalog;

public interface CatalogModule {
}
~~~

Marker chỉ dùng để xác định gốc package, không làm nghiệp vụ và không cần là Spring bean.

### 6.4. Web controller

File **com/example/shop/web/ProductController.java**:

~~~java
package com.example.shop.web;

import java.util.Map;

import com.example.catalog.service.CatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final CatalogService catalogService;

    public ProductController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/products/{id}")
    public Map<String, Object> getProduct(@PathVariable long id) {
        return Map.of(
                "id", id,
                "name", catalogService.findProductName(id));
    }
}
~~~

Controller sử dụng **constructor injection**. Nó nhận **CatalogService** như một dependency và chỉ chuyển request HTTP thành lời gọi Java.

### 6.5. Class khởi động dùng scanBasePackageClasses

File **com/example/shop/ShopApplication.java**:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModule;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi Spring Boot khởi động:

1. **ShopApplication** được sử dụng làm cấu hình chính.
2. Component scan tìm những thành phần trong **com.example.shop** và **com.example.catalog**, bao gồm package con của chúng.
3. Spring tìm thấy **ProductController** và **CatalogService**.
4. Spring tạo bean **CatalogService** và đưa nó vào constructor của **ProductController**.
5. Spring Web đăng ký mapping **GET /products/{id}** để nhận HTTP request.

Chạy ứng dụng bằng công cụ build mà project đã chọn. Với Gradle có thể dùng **bootRun**, với Maven có thể dùng **spring-boot:run**. Khi server đang chạy ở cổng mặc định 8080, thử:

~~~bash
curl http://localhost:8080/products/1
~~~

Response minh họa:

~~~json
{
  "id": 1,
  "name": "Spring Boot Handbook"
}
~~~

Trong ví dụ này, nếu chỉ để **@SpringBootApplication** mặc định trên class **com.example.shop.ShopApplication**, controller vẫn được scan nhưng **CatalogService** trong package anh em **com.example.catalog** không được tìm thấy qua component scan. Vì controller phụ thuộc vào service đó, quá trình tạo bean có thể thất bại.

### 6.6. Cấu hình tương đương bằng scanBasePackages

Có thể thay annotation trên bằng:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
    // main(...) giữ nguyên như ví dụ trên.
}
~~~

Kết quả component scan về mặt package gốc là tương đương. Chọn **một trong hai cách** cho ứng dụng mẫu để tránh cấu hình thừa và để người đọc dễ nhận ra phạm vi quét.

## 7. Một class có trong package được scan đã chắc chắn trở thành bean chưa?

**Chưa.** Package scan xác định nơi Spring **tìm kiếm các ứng viên component**. Spring vẫn cần nhận diện hoặc đăng ký bean theo cơ chế phù hợp.

Ví dụ:

~~~java
package com.example.catalog.service;

public class PriceCalculator {

    public long calculate(long basePrice) {
        return basePrice;
    }
}
~~~

Class này không có **@Component**, **@Service** hoặc annotation stereotype khác. Chỉ thêm package **com.example.catalog** vào scanBasePackages **không tự đăng ký PriceCalculator** thành bean.

Có thể sửa bằng cách dùng stereotype:

~~~java
@Service
public class PriceCalculator {
    // ...
}
~~~

Hoặc đăng ký qua một class cấu hình:

~~~java
package com.example.catalog.config;

import com.example.catalog.service.PriceCalculator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogConfiguration {

    @Bean
    PriceCalculator priceCalculator() {
        return new PriceCalculator();
    }
}
~~~

Trong trường hợp sau, cần để **CatalogConfiguration** được Spring xử lý qua component scan hoặc một cơ chế nhập cấu hình phù hợp như **@Import**. Khi đó phương thức **@Bean** mới đăng ký bean **PriceCalculator**. Cấu hình qua **@Bean** đặc biệt hữu ích khi bạn cần tạo object của một thư viện mà không thể sửa source code để thêm annotation.

Tương tự, nếu có nhiều bean cùng interface, việc mở rộng package scan có thể khiến Spring tìm thấy **quá nhiều** ứng viên. Khi đó cần dùng **@Qualifier**, **@Primary** hoặc cấu hình tường minh để chỉ rõ bean mong muốn.

## 8. Phân biệt component scan với entity scan và repository scan

Đây là phần dễ nhầm khi thêm module truy cập database.

Giả sử cấu trúc:

~~~text
com.example/
├── shop/
│   └── ShopApplication.java
└── catalog/
    ├── service/CatalogService.java           ← @Service
    ├── persistence/ProductEntity.java        ← @Entity
    └── repository/ProductRepository.java     ← JpaRepository
~~~

Bạn thêm:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
}
~~~

Điều này cho phép component scan tìm **CatalogService**. Nhưng không nên suy luận rằng nó đã cấu hình đầy đủ việc tìm **ProductEntity** và **ProductRepository**.

Spring Boot và Spring Data còn có những cơ chế tìm kiếm khác:

| Đối tượng cần tìm | Cơ chế thường áp dụng | Cấu hình rõ ràng khi nằm ngoài gốc mặc định |
|---|---|---|
| **@Service**, **@Component**, **@RestController**, **@Configuration** | Component scanning | **scanBasePackages** / **scanBasePackageClasses** |
| **@Entity** của JPA | Entity scanning của persistence provider/Spring Boot | **@EntityScan** |
| Interface **JpaRepository** | Repository scanning của Spring Data JPA | **@EnableJpaRepositories** |
| Class **@ConfigurationProperties** không có stereotype | Cơ chế đăng ký configuration properties | **@EnableConfigurationProperties** / **@ConfigurationPropertiesScan** |

Ví dụ cấu hình minh họa khi entity và JPA repository ở package catalog:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModule;
import com.example.catalog.persistence.ProductEntity;
import com.example.catalog.repository.ProductRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
@EntityScan(basePackageClasses = ProductEntity.class)
@EnableJpaRepositories(basePackageClasses = ProductRepository.class)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này:

- **scanBasePackageClasses** cho Spring tìm component.
- **@EntityScan** chỉ cho Boot nơi tìm entity.
- **@EnableJpaRepositories** chỉ cho Spring Data JPA nơi tìm repository interface.

Đối tượng **ProductEntity** và **ProductRepository** là các class/interface giả định thuộc ví dụ JPA; cần định nghĩa chúng cùng dependency Spring Data JPA và datasource thích hợp trong ứng dụng thực tế.

**Không phải lúc nào cũng cần ba annotation này.** Nếu entity và repository đã nằm trong phạm vi mặc định mà Spring Boot/Spring Data sử dụng, auto-configuration có thể tìm chúng mà không cần khai báo thủ công. Các annotation riêng hữu ích khi tổ chức package vượt ra ngoài phạm vi mặc định. Đặc biệt, đổi **scanBasePackages** không tự đổi package gốc mà các cơ chế auto-configuration khác dùng.

### Tại sao lại có nhiều loại scan?

Vì các đối tượng mang ý nghĩa khác nhau:

- **@Component** và những stereotype liên quan đại diện cho bean được Spring quản lý.
- **@Entity** là metadata mô tả kiểu dữ liệu persistence, không phải yêu cầu tạo một singleton bean thông thường bằng component scan.
- **JpaRepository** là hợp đồng repository mà Spring Data tạo proxy dựa trên cơ chế đăng ký repository.
- **@ConfigurationProperties** là kiểu mô tả dữ liệu cấu hình, cần được đăng ký bằng cơ chế phù hợp để được bind từ môi trường.

Hiểu ranh giới này tránh cách sửa sai phổ biến: cứ thấy lỗi entity hoặc repository là thêm một chuỗi package vào **scanBasePackages** rồi kỳ vọng mọi thứ hoạt động.

## 9. scanBasePackages có thay thế được @ComponentScan không?

Với mục đích **khai báo package gốc để tìm component**, hai thuộc tính trên **@SpringBootApplication** thường là cách ngắn gọn, rõ ràng cho ứng dụng Boot.

Ví dụ:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
}
~~~

tương ứng về mục đích chỉ định package với:

~~~java
@ComponentScan(
    basePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class SomeConfiguration {
}
~~~

Nhưng **@ComponentScan** là annotation có nhiều tùy chọn hơn, chẳng hạn **includeFilters**, **excludeFilters**, **lazyInit** và những thiết lập chi tiết khác. **scanBasePackages** và **scanBasePackageClasses** không phải bản sao toàn bộ các lựa chọn đó.

Một ứng dụng có cấu hình component scan chuyên biệt có thể cần **@ComponentScan** hoặc các class configuration được nhập qua **@Import**. Tuy nhiên, không nên tùy tiện đặt thêm một **@ComponentScan** trực tiếp trên class chính chỉ để lặp lại những thuộc tính đã khai báo, vì các annotation scan cục bộ và meta-annotation có quy tắc xử lý cần hiểu rõ; cấu hình có thể không còn hoạt động như người đọc dự đoán.

Với người mới, cách tổ chức đơn giản và dễ bảo trì nhất thường là:

1. Đặt class **@SpringBootApplication** ở package gốc chung nếu có thể.
2. Chỉ khai báo **scanBasePackages** hoặc **scanBasePackageClasses** khi thực sự cần nhiều package gốc.
3. Dùng các annotation scan chuyên biệt khi làm việc với entity, repository hoặc loại đối tượng khác.
4. Sử dụng **@Import** / **@Bean** cho cấu hình có chủ đích thay vì quét cả cây package rất lớn chỉ để lấy một bean.

## 10. Khi nhiều module cùng tham gia ứng dụng

Một project Spring Boot có thể được tách thành nhiều module build:

~~~text
project-root/
├── shop-app/
│   └── src/main/java/com/example/shop/ShopApplication.java
├── catalog-core/
│   └── src/main/java/com/example/catalog/
│       ├── CatalogModule.java
│       └── service/CatalogService.java
└── notification-adapter/
    └── src/main/java/com/example/notification/
        ├── NotificationModule.java
        └── EmailNotificationAdapter.java
~~~

Khi **shop-app** là ứng dụng chạy được, nó cần:

- Có **dependency build** tới những module mà nó sử dụng.
- Có các class đó trên **runtime classpath**.
- Đăng ký các bean cần thiết bằng component scan, configuration hoặc cơ chế khác.

Class khởi động có thể chọn:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class,
        NotificationModule.class
    }
)
public class ShopApplication {
}
~~~

Điểm cần phân biệt: **cấu hình Gradle/Maven** quyết định những module/JAR nào có mặt khi build và runtime; **component scan** chỉ quyết định Spring sẽ tìm những component nào trong các class đã có sẵn trên classpath.

~~~text
Build dependencies ──► Classes available on classpath
                                    │
                                    ▼
                         Component scanning
                                    │
                                    ▼
                            Spring bean definitions
                                    │
                                    ▼
                        Dependency injection at runtime
~~~

Nếu **shop-app** chưa khai báo dependency tới **catalog-core**, viết đúng tên package catalog trong **scanBasePackages** cũng không làm Spring “tải module” đó vào ứng dụng.

Mặt khác, không phải mọi thư viện cần được component scan. Nhiều starter và thư viện Spring Boot cung cấp bean thông qua **auto-configuration**, **@Import** hoặc cơ chế đăng ký khác. Không nên thêm toàn bộ package của thư viện vào danh sách scan nếu thư viện đã có cách tích hợp chính thức.

## 11. Những lỗi thường gặp và cách hiểu nguyên nhân

### Lỗi 1: Service ở package anh em

~~~text
com.example.shop.ShopApplication
com.example.catalog.CatalogService
~~~

**Biểu hiện:** controller inject CatalogService nhưng bean không tồn tại.

**Nguyên nhân có thể:** mặc định chỉ scan **com.example.shop**. Khắc phục bằng cách đặt class khởi động ở package gốc thích hợp, khai báo thêm **com.example.catalog**, hoặc nhập cấu hình/đăng ký bean một cách tường minh.

### Lỗi 2: Chỉ scan package ngoài, quên package của ứng dụng

~~~java
@SpringBootApplication(
    scanBasePackages = "com.example.catalog"
)
public class ShopApplication {
}
~~~

**Biểu hiện:** CatalogService có mặt nhưng các controller trong **com.example.shop.web** không được tìm thấy qua component scan.

**Cách xử lý:** liệt kê cả **com.example.shop** nếu vẫn cần các component ở đó, hoặc tham chiếu cả **ShopApplication.class** khi dùng **scanBasePackageClasses**.

### Lỗi 3: Marker đặt quá sâu

~~~text
com.example.catalog.service.CatalogService
com.example.catalog.config.CatalogConfiguration
~~~

Nếu bạn dùng **CatalogService.class** làm base-package class, Spring chỉ lấy package **com.example.catalog.service**. Cấu hình ở **com.example.catalog.config** nằm ngoài phạm vi.

**Cách xử lý:** dùng marker ở **com.example.catalog**, hoặc chủ động thêm nhiều class/package gốc.

### Lỗi 4: Class chưa được đăng ký thành bean

Class tồn tại trong đúng package nhưng thiếu **@Component**/**@Service**/**@Repository** (hoặc chưa được tạo qua **@Bean**). Component scan không tự đăng ký mọi Java class.

**Cách xử lý:** kiểm tra cơ chế tạo bean của loại class đó trước khi mở rộng phạm vi scan.

### Lỗi 5: Class nằm trong module chưa có dependency

Ứng dụng tham chiếu package của module khác nhưng class không nằm trong build/runtime classpath.

**Cách xử lý:** khai báo dependency Maven/Gradle tương ứng, bảo đảm class được đóng gói và hiện diện lúc chạy.

### Lỗi 6: Bean bị điều kiện cấu hình hoặc profile loại bỏ

Một bean có thể nằm trong package được scan nhưng vẫn không được tạo vì **@Profile**, **@Conditional** hoặc các điều kiện của cấu hình.

**Cách xử lý:** kiểm tra điều kiện tạo bean, profile đang bật và các dependency cần thiết. Thay đổi scanBasePackages không tự vô hiệu hóa các điều kiện đó.

### Lỗi 7: Có nhiều bean cùng kiểu

Quét thêm package làm Spring thấy hai implementation cùng interface, ví dụ hai **PaymentGateway**. Nếu injection chỉ yêu cầu kiểu interface, Spring có thể báo không xác định được ứng viên.

**Cách xử lý:** định rõ lựa chọn bằng **@Qualifier**, **@Primary** hoặc thiết kế lại cấu hình để chỉ đăng ký implementation phù hợp.

### Lỗi 8: Entity hoặc JPA repository không được tìm thấy

**@Entity** hoặc interface **JpaRepository** ở ngoài phạm vi mặc định của cơ chế JPA/Spring Data. Component scan không bảo đảm xử lý hai loại này.

**Cách xử lý:** kiểm tra dependency JPA, datasource, **@EntityScan**, **@EnableJpaRepositories** và package mà Spring Boot/Spring Data dùng cho auto-configuration.

### Lỗi 9: Quét package quá rộng

~~~java
@SpringBootApplication(scanBasePackages = "com")
public class ShopApplication {
}
~~~

Cấu hình quá rộng có thể kéo nhiều class không thuộc ứng dụng vào việc phát hiện component, tạo bean không mong muốn, xung đột tên bean hoặc đưa vào các configuration không phù hợp.

**Cách xử lý:** giới hạn package gốc theo ranh giới của ứng dụng hoặc module thực sự cần thiết. Quét rộng không phải là cách khắc phục lỗi dependency injection một cách an toàn.

## 12. Cách điều tra khi Spring không tìm thấy bean

Giả sử log khởi động có thông báo tương tự:

~~~text
Parameter 0 of constructor in
com.example.shop.web.ProductController
required a bean of type
com.example.catalog.service.CatalogService
that could not be found.
~~~

Bạn có thể lần theo theo thứ tự:

1. **Xác định bean đang thiếu.** Ở đây là CatalogService, không phải ProductController.
2. **Kiểm tra class có được đăng ký bean không.** Nó có **@Service**, **@Component**, **@Bean** hoặc cơ chế đăng ký tương ứng không?
3. **Kiểm tra package của class.** Nó có nằm trong những package được component scan hay không?
4. **Kiểm tra lớp khởi động và base packages.** Dùng mặc định hay đã khai báo **scanBasePackages** hoặc **scanBasePackageClasses**?
5. **Kiểm tra classpath.** Nếu service nằm trong module/JAR khác, ứng dụng đã phụ thuộc vào module đó chưa?
6. **Kiểm tra điều kiện tạo bean.** Profile hoặc conditional annotation có làm bean bị bỏ qua không?
7. **Kiểm tra nhiều implementation.** Lỗi có thực sự là “không có bean” hay là “nhiều bean cùng kiểu”?

Có thể bật mức log chi tiết phù hợp khi cần phân tích quá trình khởi động. Với các ứng dụng có Actuator được cấu hình thích hợp, thông tin về các bean đang tồn tại hoặc điều kiện auto-configuration cũng có thể hỗ trợ điều tra; cần bảo vệ các endpoint quản trị tương ứng.

**Không nên thấy lỗi injection là lập tức đổi scanBasePackages thành package cha cực rộng.** Việc đó có thể chỉ che nguyên nhân thiếu dependency, stereotype hoặc điều kiện bean, đồng thời mang thêm các component không mong muốn vào ứng dụng.

## 13. Thực hành so sánh hai thuộc tính

Từ ví dụ shop và catalog, có thể tự quan sát sự khác nhau bằng bốn lần thay đổi độc lập:

**Thử nghiệm A — Chỉ dùng mặc định.** Để **@SpringBootApplication** trên **ShopApplication** trong **com.example.shop**, không chỉ định scan. Khi controller yêu cầu CatalogService ở package anh em, quan sát lỗi thiếu bean khi khởi động.

**Thử nghiệm B — Dùng scanBasePackages.** Thêm hai chuỗi **com.example.shop** và **com.example.catalog**. Khởi động lại và gọi **GET /products/1** để thấy bean đã được nhận diện.

**Thử nghiệm C — Dùng scanBasePackageClasses.** Thay cấu hình chuỗi bằng **ShopApplication.class** và **CatalogModule.class**. Giữ nguyên package structure và endpoint; quan sát cùng hành vi.

**Thử nghiệm D — Di chuyển marker.** Đưa marker từ **com.example.catalog** sang **com.example.catalog.service**, cập nhật import rồi chạy lại. Quan sát tác động của việc thu hẹp package gốc, nhất là khi có một component khác trong **com.example.catalog.config**.

Bạn nên phân biệt **kết quả của scan** với **kết quả nghiệp vụ**. Nếu endpoint không xuất hiện, lỗi có thể nằm ở controller chưa được đăng ký. Nếu controller đã đăng ký nhưng application context không tạo được vì thiếu service, lỗi có thể nằm ở service ngoài phạm vi scan. Nếu JPA repository hoặc entity bị thiếu, cần xem cơ chế scan chuyên biệt.

## 14. Quy tắc lựa chọn trong dự án thực tế

Khi bắt đầu một Spring Boot application mới, hãy đặt class **@SpringBootApplication** ở package gốc bao trùm những package con thuộc ứng dụng. Đây là cách sử dụng ngắn gọn và dễ hiểu nhất:

~~~text
com.example.myapp/
├── MyAppApplication.java
├── api/
├── application/
├── domain/
├── persistence/
└── config/
~~~

Khi có nhiều package gốc độc lập hoặc nhiều module:

- Dùng **scanBasePackages** nếu muốn cấu hình trực tiếp bằng tên package và danh sách đó ít thay đổi.
- Dùng **scanBasePackageClasses** nếu muốn tham chiếu tới class/marker ổn định, để compiler và IDE hỗ trợ khi đổi tên class hoặc tái cấu trúc source.
- Đặt marker tại **package gốc thực sự muốn quét**, không đặt sâu trong một nhánh service rồi nghĩ rằng toàn bộ module sẽ được scan.
- Bao gồm package của ứng dụng chính nếu bạn đã chỉ định danh sách base packages và vẫn cần quét các thành phần ở đó.
- Xác định riêng cơ chế cho **entity**, **repository**, **configuration properties** và những thành phần được đăng ký bằng cơ chế khác.
- Tránh mở rộng scan không cần thiết; chọn dependency và cơ chế đăng ký rõ ràng theo ranh giới module.

## Kết luận

**scanBasePackages** và **scanBasePackageClasses** là hai cách khai báo phạm vi **component scanning** trên **@SpringBootApplication**:

- **scanBasePackages** dùng tên package dạng chuỗi.
- **scanBasePackageClasses** dùng package chứa những class được tham chiếu, thường là class hoặc interface marker.

Cả hai giúp Spring tìm controller, service, repository stereotype, configuration và các component khác trong những cây package được chọn. Khi sử dụng, cần nhớ rằng **component scan không tự quản lý mọi kiểu đăng ký của Spring Boot**: JPA entity, Spring Data repositories và configuration properties có cơ chế tương ứng.

Nắm rõ phạm vi package mặc định, cách chỉ định thêm nhiều package và sự khác biệt giữa **classpath**, **component scanning** và **auto-configuration** sẽ giúp bạn tổ chức ứng dụng nhiều package hoặc nhiều module mà vẫn giữ được dependency injection có thể dự đoán và dễ bảo trì.
