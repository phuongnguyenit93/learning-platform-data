# Vị trí lớp main và ảnh hưởng tới phạm vi tìm thành phần

Trong Spring Boot, việc đặt lớp khởi động (thường gọi là **lớp main**) ở package nào có thể quyết định những controller, service, repository, lớp cấu hình và thực thể dữ liệu nào được framework phát hiện. Hai dự án có cùng mã nghiệp vụ, cùng dependency nhưng vị trí lớp khởi động khác nhau có thể cho kết quả khởi động khác nhau: một dự án tạo đủ bean, dự án còn lại báo thiếu bean hoặc không đăng ký endpoint.

Nguyên nhân nằm ở **package gốc** mà các cơ chế quét và tự cấu hình sử dụng. Hiểu phạm vi đó giúp tổ chức mã nguồn dễ mở rộng, tránh phải thêm cấu hình thủ công chỉ để sửa lỗi phát hiện thành phần.

## 1. “Lớp main” trong Spring Boot có nghĩa gì?

Một ứng dụng Spring Boot thường bắt đầu từ lớp sau:

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

Có hai khái niệm cần phân biệt:

1. **Phương thức `public static void main(String[] args)`** là điểm khởi đầu của chương trình Java khi chạy lớp đó.
2. **Lớp cấu hình được gắn `@SpringBootApplication`** là nguồn cấu hình quan trọng mà Spring Boot dùng để xây dựng application context.

Thông thường hai vai trò cùng nằm trong `ShopApplication`, nên ta gọi chung là lớp main. Tuy nhiên, **phạm vi quét mặc định gắn với package của lớp cấu hình Spring**, chứ không dựa vào tên `main`, thư mục đang chạy lệnh, tên file JAR hay vị trí của phương thức `main`.

Ví dụ, nếu một launcher khác gọi:

~~~java
SpringApplication.run(ShopApplication.class, args);
~~~

thì package chứa `ShopApplication` vẫn là căn cứ cho các cơ chế mặc định liên quan, dù launcher được đặt ở package khác.

## 2. `@SpringBootApplication` khởi tạo cơ chế tìm thành phần như thế nào?

`@SpringBootApplication` là annotation tổng hợp, bao gồm ba chức năng chính:

| Annotation thành phần | Vai trò |
|---|---|
| `@SpringBootConfiguration` | Đánh dấu lớp là nguồn cấu hình Spring Boot; dựa trên `@Configuration`. |
| `@EnableAutoConfiguration` | Cho phép Boot tự cấu hình theo dependency, thuộc tính, bean và điều kiện hiện có. |
| `@ComponentScan` | Tìm các component trong phạm vi package được chỉ định, hoặc phạm vi mặc định nếu không chỉ định. |

Khi không khai báo phạm vi riêng, **component scan xuất phát từ package chứa lớp có `@SpringBootApplication` và duyệt các package con**.

Giả sử:

~~~text
com.example.shop
├── ShopApplication
├── api
│   └── OrderController
├── service
│   └── OrderService
├── repository
│   └── OrderRepository
└── config
    └── ShopConfiguration
~~~

Lớp `ShopApplication` đặt ở `com.example.shop`. Component scan mặc định sẽ xét những lớp phù hợp trong:

~~~text
com.example.shop
com.example.shop.api
com.example.shop.service
com.example.shop.repository
com.example.shop.config
... và các package con sâu hơn
~~~

**Package cha không bị quét ngược lên**, và **package anh em không tự động được quét**:

~~~text
com.example
├── shop                 ← nơi đặt ShopApplication
│   ├── api              ← trong phạm vi
│   └── service          ← trong phạm vi
├── shared               ← ngoài phạm vi component scan mặc định
└── admin                ← ngoài phạm vi component scan mặc định
~~~

Đây là quan hệ của **Java package**, không đơn thuần là vị trí hiển thị trong IDE. Cấu trúc thư mục dưới `src/main/java` nên phản ánh đúng khai báo `package` trong mỗi file.

## 3. Những lớp nào được component scan đăng ký thành bean?

Component scanning tìm các lớp có annotation phù hợp, chẳng hạn:

| Annotation | Ý nghĩa thường gặp | Có thể được component scan phát hiện? |
|---|---|---|
| `@Component` | Bean ứng dụng chung | Có |
| `@Service` | Thành phần xử lý nghiệp vụ | Có; bản chất là một stereotype của `@Component` |
| `@Repository` | Thành phần truy cập dữ liệu viết dưới dạng class | Có; cũng là một stereotype của `@Component` |
| `@Controller` | Spring MVC/WebFlux controller | Có |
| `@RestController` | Controller trả dữ liệu HTTP, thường là JSON | Có |
| `@Configuration` | Lớp khai báo cấu hình và các phương thức `@Bean` | Có |
| `@Entity` | Entity ánh xạ dữ liệu JPA | **Không**; thuộc cơ chế quản lý entity của JPA |
| `@ConfigurationProperties` | Mô tả ánh xạ cấu hình sang object | Không tự động chỉ nhờ annotation này; cần cơ chế đăng ký phù hợp |

Ví dụ:

~~~java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long discountedPrice(long originalPrice) {
        return originalPrice * 90 / 100;
    }
}
~~~

~~~java
package com.example.shop.api;

import com.example.shop.service.PriceService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    private final PriceService priceService;

    public PriceController(PriceService priceService) {
        this.priceService = priceService;
    }

    @GetMapping("/prices/discounted")
    public long discountedPrice() {
        return priceService.discountedPrice(100);
    }
}
~~~

Do hai lớp đều nằm bên dưới `com.example.shop`, Spring có thể đăng ký `PriceService` và `PriceController`; constructor injection kết nối hai bean khi khởi tạo context.

Lưu ý: **ở đúng package chưa đủ** để một lớp Java thông thường trở thành Spring bean. Lớp đó còn cần được đăng ký thông qua `@Component`/stereotype, phương thức `@Bean`, `@Import`, cơ chế tự cấu hình hoặc cách đăng ký bean thích hợp khác.

## 4. Vì sao đặt lớp main quá sâu dễ gây lỗi?

Xét cấu trúc sau:

~~~text
src/main/java/
└── com/example/shop/
    ├── api/
    │   ├── ShopApplication.java  ← @SpringBootApplication
    │   └── OrderController.java
    ├── service/
    │   └── OrderService.java
    └── config/
        └── DatabaseConfiguration.java
~~~

Nếu `ShopApplication` khai báo:

~~~java
package com.example.shop.api;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

thì phạm vi component scan mặc định bắt đầu tại `com.example.shop.api`. `OrderController` có thể được phát hiện nhưng `OrderService` ở `com.example.shop.service` và `DatabaseConfiguration` ở `com.example.shop.config` nằm ngoài phạm vi.

Nếu controller yêu cầu `OrderService` qua constructor, việc tạo bean có thể thất bại với thông báo kiểu:

~~~text
Parameter 0 of constructor in ...OrderController
required a bean of type '...OrderService'
that could not be found.
~~~

Nếu không có dependency bắt buộc, ứng dụng thậm chí **có thể khởi động thành công nhưng thiếu endpoint hoặc tính năng**. Ví dụ: đặt controller ngoài vùng scan khiến handler không được đăng ký; request đến URL tương ứng có thể nhận HTTP 404.

### Cách sửa đơn giản nhất

Đưa lớp `ShopApplication` lên package gốc chung:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java        ← @SpringBootApplication
    ├── api/
    ├── service/
    ├── repository/
    └── config/
~~~

Lúc này `com.example.shop` bao phủ tất cả nhóm package con. Đây là cấu trúc nên ưu tiên trong ứng dụng thông thường vì phạm vi rõ ràng và không cần khai báo `scanBasePackages` một cách thủ công.

## 5. Vị trí main còn liên quan đến entity và Spring Data repository, nhưng theo cơ chế khác

Một hiểu nhầm phổ biến là “`@ComponentScan` sẽ tìm mọi thứ, bao gồm cả JPA entity và interface Spring Data repository”. Trên thực tế có **những hệ thống phát hiện riêng**:

| Loại | Cơ chế chính | Phạm vi mặc định liên quan tới |
|---|---|---|
| Controller, service, component, configuration | Spring component scan | Package của `@SpringBootApplication` (nếu không tùy chỉnh) |
| Spring Boot auto-configuration | Chọn cấu hình theo classpath và các điều kiện | Không hoạt động như việc quét mọi class; một số auto-configuration dùng “auto-configuration packages” |
| JPA entity | Entity scanning/JPA persistence-unit configuration | Thường dựa vào auto-configuration packages nếu không cấu hình rõ |
| Spring Data JPA repository interface | Spring Data repository scanning | Thường dựa vào auto-configuration packages nếu không cấu hình rõ |
| `@ConfigurationProperties` class | Configuration-properties scanning/registration | Phụ thuộc `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cơ chế đăng ký bean khác |

`@EnableAutoConfiguration` gián tiếp thiết lập **auto-configuration package** theo vị trí lớp cấu hình Boot. Nhiều auto-configuration, trong đó có các tích hợp Spring Data/JPA, dùng thông tin package này để chọn mặc định. Nó không đồng nhất với component scan.

Giả sử ta có:

~~~text
com.example.shop
├── ShopApplication           ← @SpringBootApplication
├── api                       ← controller
└── service                   ← service

com.example.storage
├── entity
│   └── OrderEntity           ← @Entity
└── repository
    └── OrderJpaRepository    ← extends JpaRepository
~~~

`OrderEntity` và `OrderJpaRepository` nằm ngoài các package mặc định của ứng dụng. Dù thêm `com.example.storage` vào **component scan**, Spring Data JPA vẫn có thể không phát hiện entity/repository, vì hai đối tượng này dùng đường đăng ký khác.

Khi thực sự cần giữ các package tách biệt, có thể khai báo rõ:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.storage"
})
@EntityScan(basePackages = "com.example.storage.entity")
@EnableJpaRepositories(
        basePackages = "com.example.storage.repository"
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Trong ví dụ này:

- `scanBasePackages` mở rộng **component scan** cho các component và configuration thông thường.
- `@EntityScan` xác định phạm vi tìm các entity do JPA quản lý.
- `@EnableJpaRepositories` xác định phạm vi tìm interface Spring Data JPA repository.

Không phải dự án nào cũng cần cả ba. Cấu hình tường minh chỉ nên thêm khi cấu trúc package hoặc yêu cầu tích hợp khiến mặc định chưa phù hợp. Ví dụ trên giả định ứng dụng đã có starter Spring Data JPA, driver dữ liệu và cấu hình kết nối hợp lệ.

### Phân biệt lỗi bean với lỗi entity

Hai trường hợp có thể xuất hiện ở những giai đoạn khác nhau:

~~~text
No qualifying bean of type '...OrderService'
~~~

Lỗi này thường gợi ý kiểm tra việc đăng ký bean: annotation, vị trí package, điều kiện tạo bean, profile và cấu hình.

~~~text
Not a managed type: class ...OrderEntity
~~~

Lỗi này hướng tới việc entity chưa nằm trong persistence unit/không được ánh xạ như mong đợi. Chỉ thêm `@ComponentScan` thường không giải quyết đúng nguyên nhân.

## 6. Các cách điều chỉnh phạm vi một cách có chủ đích

### 6.1. Đặt `@SpringBootApplication` ở package gốc chung

Đây là lựa chọn mặc định dễ hiểu nhất:

~~~text
com.example.inventory
├── InventoryApplication.java
├── product
│   ├── ProductController.java
│   ├── ProductService.java
│   └── ProductRepository.java
└── order
    ├── OrderController.java
    ├── OrderService.java
    └── OrderRepository.java
~~~

Tổ chức theo **tính năng** (product/order) hay theo **tầng** (controller/service/repository) đều có thể hoạt động, miễn tất cả thuộc package con thích hợp. Không bắt buộc phải đặt các thành phần trực tiếp cạnh lớp main.

### 6.2. Chỉ định `scanBasePackages`

Khi các component thực sự ở nhiều package tách biệt:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example.inventory",
        "com.example.shared.audit"
})
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Chỉ những package được chỉ định và các package con của chúng mới là nguồn quét của cấu hình này. Tránh mở rộng vô tội vạ tới `com` hoặc `org`, vì có thể phát hiện nhiều bean không mong muốn, trùng bean name hoặc gây xung đột cấu hình.

Nếu muốn giảm lỗi do đổi tên package, có thể dùng **marker class**:

~~~java
// com.example.shared.audit.AuditPackageMarker
package com.example.shared.audit;

public interface AuditPackageMarker {
}
~~~

~~~java
// com.example.inventory.InventoryApplication
package com.example.inventory;

import com.example.shared.audit.AuditPackageMarker;

@SpringBootApplication(
        scanBasePackageClasses = {
                InventoryApplication.class,
                AuditPackageMarker.class
        }
)
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

`scanBasePackageClasses` sử dụng package của các class được chỉ định. Marker không cần là Spring bean và không cần chứa logic.

### 6.3. Nhập cấu hình cụ thể với `@Import`

Nếu chỉ cần một cấu hình bên ngoài phạm vi quét, không nhất thiết quét cả package:

~~~java
package com.example.shop;

import com.example.shared.config.AuditConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(AuditConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@Import` đăng ký cấu hình được chọn một cách tường minh. Với `@Configuration` chứa các phương thức `@Bean`, đây thường là lựa chọn phù hợp khi cần tái sử dụng một phần cấu hình từ module khác.

### 6.4. Tùy chỉnh cấu hình dữ liệu theo đúng công nghệ

Nếu đặt các JPA repository ở bên ngoài auto-configuration packages, dùng `@EnableJpaRepositories` với base package phù hợp; nếu đặt entity bên ngoài, dùng `@EntityScan`. Với MongoDB, Redis, R2DBC hoặc công nghệ khác, hãy dùng **cơ chế cấu hình repository tương ứng**, không mặc định `@EnableJpaRepositories` áp dụng cho mọi Spring Data module.

Với class chứa cấu hình kiểu:

~~~java
@ConfigurationProperties(prefix = "app.billing")
public record BillingProperties(String currency, boolean enabled) {
}
~~~

có thể đăng ký bằng `@EnableConfigurationProperties(BillingProperties.class)` hoặc quét bằng `@ConfigurationPropertiesScan` đặt ở vị trí thích hợp. Việc mở rộng `scanBasePackages` không tự động thay thế mọi cơ chế đăng ký configuration properties.

## 7. Multi-module: cùng classpath vẫn chưa chắc cùng phạm vi quét

Trong ứng dụng chia thành nhiều Gradle/Maven module, ví dụ:

~~~text
shop-app/
  com.example.shop.ShopApplication
shop-core/
  com.example.shop.core.PricingService
shop-integration/
  com.example.integration.ExternalClient
~~~

Nếu cả ba module được khai báo dependency hợp lệ, class của chúng có thể cùng xuất hiện trên **runtime classpath**. Tuy nhiên, classpath và component scan là hai điều kiện khác nhau:

1. Spring chỉ có thể sử dụng những class mà runtime **thực sự có quyền tải** từ dependency/classpath.
2. Component scan chỉ phát hiện những class **nằm trong phạm vi package được quét** và đáp ứng điều kiện đăng ký bean.

Vì `com.example.shop.core` là package con của `com.example.shop`, `PricingService` có thể được quét mặc định khi có dependency. Nhưng `com.example.integration.ExternalClient` là package anh em; nếu muốn dùng bean của nó, cần chỉ rõ cách đăng ký.

Không nên giải quyết tình huống bằng cách đưa toàn bộ thư viện bên thứ ba vào component scan. Thư viện tái sử dụng có thể cung cấp cấu hình thông qua `@Import`, starter và auto-configuration được khai báo đúng chuẩn, hoặc API đăng ký bean cụ thể. Lựa chọn nào phù hợp phụ thuộc hợp đồng tích hợp của thư viện.

## 8. Đặt lớp main sai ở “default package” còn nguy hiểm hơn

Java cho phép viết class mà không khai báo `package`:

~~~java
// Không có: package com.example.shop;
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Đây là **default package** (package không tên). Spring Boot khuyến nghị tránh cách đặt này vì những annotation dựa trên package như `@ComponentScan`, `@EntityScan` hoặc `@SpringBootApplication` có thể khiến hệ thống xem xét một phạm vi rất rộng trên classpath. Hậu quả có thể là phát hiện class ngoài ý muốn, xung đột cấu hình, thời gian khởi động tăng hoặc lỗi khó truy nguyên.

Thay vào đó, luôn đặt lớp khởi động trong một package có tên, ví dụ `com.example.shop`, ở mức bao trùm các package thuộc ứng dụng.

## 9. Tác động đến testing và cách Spring Boot tìm cấu hình kiểm thử

Vị trí lớp `@SpringBootApplication` còn ảnh hưởng tới cách một số Spring Boot test tìm lớp cấu hình:

~~~text
src/main/java/com/example/shop/ShopApplication.java
src/main/java/com/example/shop/service/OrderService.java
src/test/java/com/example/shop/service/OrderServiceTest.java
~~~

Trong nhiều bài test Spring Boot, nếu không chỉ định classes, hệ thống có thể **tìm ngược lên cây package từ vị trí lớp test** để tìm `@SpringBootConfiguration`. Khi `ShopApplication` đặt ở `com.example.shop`, test trong `com.example.shop.service` thường tìm được cấu hình.

Ngược lại, nếu lớp main được đặt trong `com.example.shop.api` còn test nằm ở `com.example.shop.service`, việc tìm kiếm theo package cha có thể không gặp lớp cấu hình cần thiết.

Một cách chỉ định tường minh khi cần:

~~~java
package com.example.shop.service;

import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = ShopApplication.class)
class OrderServiceIntegrationTest {
    @Test
    void contextLoads() {
        // Kiểm thử tích hợp sẽ bổ sung các assertion theo yêu cầu.
    }
}
~~~

Test này chỉ minh họa cơ chế chọn lớp cấu hình, không tự khẳng định logic nghiệp vụ đã đúng. Với các test slice như `@WebMvcTest` hoặc `@DataJpaTest`, phạm vi bean và cơ chế bootstrap còn phụ thuộc annotation của slice. Vì vậy, đặt lớp main ở package gốc vẫn giúp cấu trúc test dễ dự đoán hơn.

## 10. Cách chẩn đoán khi Spring không tìm thấy thành phần

Khi thêm `@Service` hoặc `@RestController` nhưng ứng dụng không nhận ra, hãy điều tra theo thứ tự:

1. **Xác định lớp cấu hình thực tế** được truyền vào `SpringApplication.run(...)` và xem package chứa `@SpringBootApplication`.
2. **Đọc dòng `package ...;`** ở lớp không được tìm thấy. So sánh quan hệ cha/con của hai package.
3. **Kiểm tra annotation đăng ký bean**: `@Component`, `@Service`, `@RestController`, `@Configuration`, `@Bean` hoặc phương thức đăng ký riêng của framework.
4. **Kiểm tra classpath/runtime dependency**, nhất là khi lớp nằm trong một Gradle/Maven module khác.
5. **Phân biệt loại thành phần thiếu**: Spring component, Spring Data repository, JPA entity hay configuration properties cần các cách quét/đăng ký khác nhau.
6. **Kiểm tra điều kiện tạo bean**: `@Profile`, `@Conditional`, cấu hình tự động, bean bị loại trừ bởi filter hoặc cấu hình trùng lặp có thể khiến bean không tồn tại ngay cả khi package đúng.

Một số triệu chứng thường gặp:

| Triệu chứng | Hướng kiểm tra |
|---|---|
| `NoSuchBeanDefinitionException` / báo thiếu dependency constructor | Bean có được đăng ký không? Package có nằm trong scan không? Có bị điều kiện/profile loại trừ không? |
| Gọi URL luôn nhận 404 dù controller đã viết | Controller có được đăng ký không, mapping có đúng không, path/context-path có phù hợp không? |
| `Not a managed type` khi dùng JPA repository | Entity có annotation JPA phù hợp và nằm trong phạm vi entity scanning không? |
| Spring Data repository interface không được tạo bean | Module Spring Data và cấu hình repository scanning có nhận package chứa interface không? |
| Lỗi không tìm thấy `@SpringBootConfiguration` trong test | Vị trí lớp test so với lớp main và thuộc tính `classes` của annotation test. |
| Cùng ứng dụng nhưng khác kết quả khi chuyển module/package | Kiểm tra lại runtime classpath, package scan và cấu hình được import. |

Spring Boot có thể cung cấp báo cáo điều kiện auto-configuration khi bật chế độ debug, ví dụ thiết lập `debug=true` trong cấu hình hoặc truyền `--debug` lúc chạy. Báo cáo đó giúp hiểu vì sao một auto-configuration được chọn hoặc bị loại. Tuy nhiên, **condition report không phải danh sách đầy đủ mọi class mà component scan đã xem xét**. Khi cần kiểm tra bean thực tế, có thể quan sát `ApplicationContext` hoặc endpoint `beans` của Actuator nếu dự án đã bật và bảo vệ endpoint phù hợp.

## 11. Các nguyên tắc tổ chức mã nguồn dễ duy trì

**Nguyên tắc 1 — Chọn một package gốc rõ ràng.** Ví dụ `vn.example.orders` hoặc `com.example.shop`; đặt `@SpringBootApplication` ngay trong package đó, các feature và layer nằm ở package con.

**Nguyên tắc 2 — Phân biệt cơ chế quét.** Component scanning, entity scanning, Spring Data repository scanning và configuration-properties scanning có phạm vi và cách kích hoạt khác nhau.

**Nguyên tắc 3 — Chỉ mở rộng phạm vi khi có lý do.** Nếu chia sẻ component giữa nhiều ứng dụng, ưu tiên khai báo package cụ thể hoặc import cấu hình cụ thể. Tránh quét toàn bộ namespace lớn chỉ để sửa một bean thiếu.

**Nguyên tắc 4 — Khi thay đổi package, kiểm tra cả runtime và test.** Di chuyển lớp main có thể thay đổi những bean được quét, phạm vi entity/repository mặc định và khả năng test tự tìm cấu hình.

**Nguyên tắc 5 — Dùng cấu trúc thư mục để phản ánh kiến trúc.** Package theo tính năng hay theo tầng đều được; điều quan trọng là lớp main ở đúng gốc ứng dụng và sự phụ thuộc giữa các module rõ ràng.

Ví dụ cấu trúc gọn, thuận tiện cho một ứng dụng Spring Boot:

~~~text
src/
├── main/java/
│   └── com/example/shop/
│       ├── ShopApplication.java
│       ├── order/
│       │   ├── OrderController.java
│       │   ├── OrderService.java
│       │   ├── OrderRepository.java
│       │   └── OrderEntity.java
│       ├── product/
│       │   ├── ProductController.java
│       │   ├── ProductService.java
│       │   └── ProductRepository.java
│       └── config/
│           └── ShopConfiguration.java
└── test/java/
    └── com/example/shop/
        ├── order/
        └── product/
~~~

Trong cấu trúc này, **vị trí lớp main tạo nên một ranh giới mặc định có thể dự đoán**. Spring Boot chịu trách nhiệm thiết lập application context, component scan tìm những bean phù hợp, và các cơ chế dữ liệu hoặc cấu hình khác sử dụng phạm vi riêng của chúng. Khi xác định đúng ranh giới đó từ đầu, dự án có thể thêm controller, service và tính năng mới mà không liên tục gặp lỗi “không tìm thấy bean” do đặt sai package.
