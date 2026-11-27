# Module package không có annotation được nhận diện ra sao?

Trong cấu hình mặc định, Spring Modulith nhận diện application module dựa trên cấu trúc package. Package chứa lớp ứng dụng Spring Boot là package gốc; mỗi package con trực tiếp của package gốc được xem là một application module. Vì vậy, một package như `com.acme.shop.catalog` vẫn được nhận diện là module `catalog` dù không có `package-info.java` hay annotation `@ApplicationModule`.

Các package con sâu hơn mặc định thuộc module đã được nhận diện. Chẳng hạn, `com.acme.shop.catalog.internal` là phần nội bộ của module `catalog`, không tự trở thành module độc lập. Quy tắc này giúp nhóm bắt đầu tổ chức modular monolith bằng package trước, rồi bổ sung metadata khi cần kiểm soát ranh giới chi tiết hơn.

Sau bài học, bạn có thể:

- Xác định package gốc mà Spring Modulith dùng để phát hiện module.
- Nhận diện module từ các package con trực tiếp mà không cần annotation.
- Phân biệt package con thuộc module với nested application module.
- Kiểm tra kết quả phát hiện bằng `ApplicationModules`.
- Biết khi nào cần chuyển sang chiến lược phát hiện tường minh hoặc tùy chỉnh.

## 1. Package gốc bắt đầu từ đâu?

Spring Modulith lấy package của lớp ứng dụng Spring Boot làm package gốc. Đây thường là lớp có annotation `@SpringBootApplication` và phương thức `main(…)`.

Ví dụ:

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

Trong ví dụ này, package gốc là `com.acme.shop`. Với chiến lược mặc định, Spring Modulith xem các package con trực tiếp của nó là những package module.

```text
com.acme.shop                         <- package gốc
├── ShopApplication.java
├── catalog                           <- application module: catalog
│   ├── CatalogService.java
│   └── internal
│       └── ProductRepository.java
├── order                             <- application module: order
│   ├── OrderService.java
│   └── internal
│       └── OrderRepository.java
└── customer                          <- application module: customer
    └── CustomerService.java
```

Từ cấu trúc này, Spring Modulith phát hiện ba module `catalog`, `order` và `customer`. Tên logic của module được lấy từ tên package cuối cùng: `com.acme.shop.catalog` có tên module là `catalog`.

Điểm cần nhớ là `catalog.internal` không phải package con trực tiếp của `com.acme.shop`; nó là package con của module `catalog`. Vì vậy, package này thuộc cấu trúc bên trong module `catalog`.

## 2. Không cần `@ApplicationModule` để được nhận diện

Với chiến lược mặc định `directSubPackage`, chỉ cần package nằm đúng vị trí trong cây package là đủ để Spring Modulith nhận diện module. Ví dụ, package `com.acme.shop.order` có thể chỉ chứa các lớp Java:

```java
package com.acme.shop.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public void placeOrder() {
        // Xử lý nghiệp vụ đặt hàng
    }
}
```

Package này được nhận diện là module `order` dù không có file `package-info.java`.

`@ApplicationModule` là annotation tùy chọn để khai báo metadata hoặc thay đổi cách module hoạt động, ví dụ:

- Chỉ định `allowedDependencies` để giới hạn module được phép phụ thuộc.
- Chuyển module sang kiểu `OPEN`.
- Khai báo một package con thành nested application module.

Ví dụ, khi cần giới hạn phụ thuộc của module `order`, bạn có thể thêm `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "catalog"
)
package com.acme.shop.order;
```

Việc thêm annotation ở đây bổ sung quy tắc cho module đã được nhận diện. Annotation không phải điều kiện bắt buộc để package `com.acme.shop.order` trở thành module trong chiến lược mặc định.

## 3. Package con sâu hơn thuộc module nào?

Một module có thể tổ chức mã thành nhiều package con. Ví dụ:

```text
com.acme.shop
└── order                              <- module order
    ├── OrderService.java
    ├── application
    │   └── PlaceOrder.java
    ├── domain
    │   └── Order.java
    └── internal
        └── OrderRepository.java
```

Nếu không có cấu hình phát hiện nested module, các package `application`, `domain` và `internal` đều thuộc module `order`. Chúng không tự trở thành các application module ngang hàng với `order`.

Nếu module package không có package con nào, đây là dạng simple application module. API của module khi đó gồm các kiểu `public` trong chính package đó; các kiểu package-private có thể được giữ làm chi tiết nội bộ vì mã ở package khác không thể tham chiếu chúng theo quy tắc truy cập Java.

Với module kiểu `CLOSED` mặc định, package gốc của module là API mặc định cho module khác. Các package con như `order.internal` được xem là nội bộ. Module khác không nên phụ thuộc vào các kiểu ở đó, kể cả khi kiểu Java được khai báo `public`. Quy tắc kiến trúc này được Spring Modulith kiểm tra qua `ApplicationModules.verify()`; Java compiler có thể vẫn cho phép biên dịch một tham chiếu `public` vi phạm ranh giới module.

Trong nội bộ module, các lớp ở package con có thể cần truy cập lẫn nhau. Vì package-private của Java chỉ cho phép truy cập trong cùng package, kiểu được chia sẻ giữa các package con có thể cần khai báo `public`. Điều đó không biến package con thành API công khai của module.

## 4. Khi nào package con trở thành nested application module?

Từ Spring Modulith 1.3, một module có thể chứa nested application module. Để package con trở thành module lồng bên trong, bạn phải khai báo tường minh bằng `@ApplicationModule`.

Ví dụ, muốn tách phần `shipping` khỏi module `order`, hãy tạo:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.order.shipping;
```

Cây package sau khi khai báo:

```text
com.acme.shop
└── order                              <- module cha
    ├── OrderService.java
    ├── internal
    │   └── OrderRepository.java
    └── shipping                       <- nested module
        ├── package-info.java          <- @ApplicationModule
        ├── ShippingService.java
        └── internal
            └── CarrierGateway.java
```

`order.shipping` lúc này là nested application module bên trong `order`. Các quy tắc truy cập giữa nested module và module cha được Spring Modulith quản lý riêng. Nếu package `order.shipping` không có annotation và không được một chiến lược tùy chỉnh chọn làm module, nó vẫn là package con thuộc module `order`.

## 5. Thay đổi chiến lược phát hiện module

Chiến lược mặc định phù hợp với cấu trúc package theo nghiệp vụ, nhưng một số dự án có thể muốn chỉ công nhận các package được đánh dấu rõ ràng.

Spring Modulith hỗ trợ chiến lược `explicitly-annotated`. Khi cấu hình:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Spring Modulith chỉ xem các package được đánh dấu bằng annotation `@ApplicationModule` của Spring Modulith hoặc `@Module` của jMolecules là module base package. Trong chế độ này, package `com.acme.shop.order` không có annotation sẽ không được phát hiện chỉ vì nó là package con trực tiếp của package gốc.

Do đó, cùng một cây package có thể tạo ra kết quả khác nhau tùy chiến lược:

| Package | `directSubPackage` (mặc định) | `explicitly-annotated` |
|---|---|---|
| `com.acme.shop.catalog` không có annotation | Được phát hiện | Không được phát hiện |
| `com.acme.shop.order` có `@ApplicationModule` | Được phát hiện | Được phát hiện |
| `com.acme.shop.order.shipping` có `@ApplicationModule`, bên trong module `order` đã được nhận diện | Được nhận diện là nested module | Được phát hiện theo cấu hình tường minh |

Khi cần cách chọn module theo quy ước riêng, bạn có thể triển khai `ApplicationModuleDetectionStrategy`. Strategy nhận package gốc và trả về các package được chọn làm module base package. Đăng ký implementation bằng thuộc tính `spring.modulith.detection-strategy` với tên lớp đầy đủ.

Ví dụ khung implementation:

```java
package com.acme.shop;

import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

class ShopModuleDetectionStrategy implements ApplicationModuleDetectionStrategy {

    @Override
    public Stream<JavaPackage> getModuleBasePackages(JavaPackage basePackage) {
        // Chọn các package module theo quy ước của dự án.
        return basePackage.getDirectSubPackages().stream()
                .filter(pkg -> pkg.getLocalName().endsWith("Module"));
    }
}
```

Đăng ký strategy:

```properties
spring.modulith.detection-strategy=com.acme.shop.ShopModuleDetectionStrategy
```

Ví dụ trên chỉ chọn các package con trực tiếp có tên kết thúc bằng `Module`. Hãy thay bộ lọc bằng quy ước của dự án. Nếu chiến lược mặc định đã khớp cấu trúc package, không cần tạo implementation tùy chỉnh.

## 6. Bổ sung package gốc bằng `@Modulithic`

Thông thường, Spring Modulith bắt đầu từ package chứa lớp ứng dụng. Nếu ứng dụng có thêm một namespace độc lập cần được phân tích như một root package khác, có thể cấu hình `additionalPackages` trên `@Modulithic`:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(additionalPackages = "com.acme.shared")
@SpringBootApplication
public class ShopApplication {
}
```

Với cấu hình này, Spring Modulith cũng áp dụng phát hiện module cho package gốc bổ sung `com.acme.shared`. Các package con trực tiếp của root bổ sung được xử lý theo detection strategy đang cấu hình.

`@Modulithic` là nơi tùy chỉnh cách Spring Modulith phân tích toàn ứng dụng, ví dụ root package bổ sung, tên hệ thống hoặc shared modules. Nó không thay thế quy tắc phát hiện package con trực tiếp của strategy mặc định.

## 7. Quan sát kết quả bằng `ApplicationModules`

Bạn có thể tạo mô hình module từ lớp ứng dụng và in ra kết quả để kiểm tra Spring Modulith đã nhận diện package nào:

```java
import org.springframework.modulith.core.ApplicationModules;

class ModuleInspection {

    void inspect() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println);
        modules.verify();
    }
}
```

Đầu ra liệt kê logical name, base package và các Spring bean thuộc từng module. Hãy kiểm tra các điểm sau:

1. Package gốc có đúng là package chứa `ShopApplication` không?
2. Mỗi package con trực tiếp có được nhận diện thành module như mong đợi không?
3. Package con sâu hơn có đang thuộc module cha hay đã được khai báo thành nested module?
4. Những package nội bộ có bị module khác tham chiếu trái quy tắc không?
5. Nếu dùng `explicitly-annotated`, tất cả module cần phát hiện đã có annotation phù hợp chưa?

`ApplicationModules.verify()` giúp phát hiện các phụ thuộc vi phạm quy tắc module. Nên đặt lời gọi này trong một bài kiểm tra kiến trúc JUnit để chạy cùng bộ kiểm tra tự động của dự án:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

## 8. Ghi nhớ

Trong cấu hình mặc định, Spring Modulith lấy package của lớp `@SpringBootApplication` làm root và tự nhận diện từng package con trực tiếp là một application module. Package con sâu hơn mặc định thuộc module cha; muốn tạo nested module phải khai báo tường minh bằng `@ApplicationModule`. Annotation không bắt buộc để nhận diện module theo strategy mặc định, nhưng có thể bổ sung metadata như `allowedDependencies` hoặc `type`. Nếu chuyển sang `explicitly-annotated`, package không có annotation sẽ không được phát hiện chỉ dựa vào vị trí trong cây package. Hãy dùng `ApplicationModules.of(ShopApplication.class)` và `verify()` để quan sát, kiểm chứng mô hình thực tế.

## Tài liệu tham khảo

- [Spring Modulith Fundamentals – Simple và Advanced Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules)
- [Spring Modulith Fundamentals – Nested Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.nested)
- [Spring Modulith Fundamentals – Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.detection)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
