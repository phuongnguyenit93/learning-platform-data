# Bean implementation trong internal package

Trong một modular monolith, một module thường cần cung cấp dịch vụ cho module khác nhưng vẫn giữ cách triển khai bên trong. Spring cho phép đặt implementation của một Spring bean trong package nội bộ và đăng ký nó bằng component scanning. Spring Modulith tiếp tục xem package con đó là phần triển khai của module; module tiêu thụ nên phụ thuộc vào kiểu API được công khai, thay vì phụ thuộc trực tiếp vào lớp implementation.

Cách tổ chức này giúp nhóm thay đổi thuật toán, adapter hoặc cấu hình bean mà không buộc các module khác biết chi tiết bên trong. Bài học trình bày cách đặt interface và implementation, cách Spring tạo bean, cách module khác tiêm phụ thuộc và cách kiểm chứng ranh giới bằng Spring Modulith.

## 1. Phân biệt API của module và package nội bộ

Spring Modulith mô hình hóa application module dựa trên package Java. Một module thường có package gốc riêng. Các kiểu public nằm trực tiếp trong package gốc tạo thành API mặc định của module. Các package con được xem là nội bộ, trừ khi chúng được công khai có chủ đích, chẳng hạn bằng named interface.

Ví dụ, module `pricing` có cấu trúc:

```text
com.acme.shop
├── ShopApplication.java
├── pricing
│   ├── PricingPolicy.java
│   └── internal
│       ├── DefaultPricingPolicy.java
│       └── PricingConfiguration.java
└── order
    └── internal
        └── CheckoutService.java
```

Trong cấu trúc này:

- `com.acme.shop.pricing` là package gốc của module `pricing`. `PricingPolicy` là kiểu API mà module khác có thể sử dụng.
- `com.acme.shop.pricing.internal` chứa implementation và cấu hình riêng của module. Các kiểu ở đây không thuộc API mặc định.
- `com.acme.shop.order` là module khác. Nó có thể phụ thuộc vào API `PricingPolicy` nếu nghiệp vụ đặt hàng cần chức năng tính giá.

Từ `internal` chỉ là quy ước đặt tên package của nhóm. Điều làm package trở thành nội bộ trong mô hình Spring Modulith là vị trí của nó trong cấu trúc module và việc nhóm không công khai package đó như một named interface. Chỉ đặt tên package là `internal` không tự tạo ra một cơ chế bảo mật ở runtime.

## 2. Đặt interface ở API và implementation ở internal

Giả sử module `pricing` cung cấp khả năng tính giá cuối cùng từ giá trị đơn hàng. Khai báo contract trong package gốc:

```java
package com.acme.shop.pricing;

import java.math.BigDecimal;

public interface PricingPolicy {

    BigDecimal calculate(BigDecimal subtotal);
}
```

Lớp thực thi nằm trong package `internal`:

```java
package com.acme.shop.pricing.internal;

import com.acme.shop.pricing.PricingPolicy;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Component
public final class DefaultPricingPolicy implements PricingPolicy {

    private static final BigDecimal TAX_RATE = new BigDecimal("0.10");

    @Override
    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ONE.add(TAX_RATE))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

`DefaultPricingPolicy` là Spring bean nhờ `@Component`. Lớp này thực thi contract `PricingPolicy`, nhưng được đặt trong package nội bộ. Module khác chỉ cần biết phương thức `calculate` và kiểu dữ liệu công khai mà contract sử dụng.

Khi quy tắc tính giá thay đổi, nhóm có thể thay `DefaultPricingPolicy` bằng implementation khác, ví dụ `PromotionAwarePricingPolicy`, mà không phải sửa module `order`, miễn là contract `PricingPolicy` vẫn đáp ứng nhu cầu của bên gọi.

## 3. Spring đăng ký bean trong package nội bộ như thế nào?

Spring Modulith mô hình hóa ranh giới module; Spring Framework chịu trách nhiệm tạo và quản lý bean. Với cấu trúc package ở trên, nếu lớp ứng dụng Spring Boot nằm tại `com.acme.shop`, component scanning mặc định bắt đầu từ package đó và quét các package con. Vì vậy, `DefaultPricingPolicy` trong `com.acme.shop.pricing.internal` được phát hiện và đăng ký làm bean.

Ví dụ lớp khởi động:

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

`@SpringBootApplication` bao gồm cấu hình component scanning theo package của lớp ứng dụng. Đặt lớp này ở package gốc phù hợp giúp Spring tìm thấy các component trong những module và package con.

Điều đó có nghĩa là một bean vẫn có thể được Spring tạo và tiêm vào các bean khác dù lớp implementation nằm trong package nội bộ. Tính nội bộ là quy tắc kiến trúc về cách các module được phép phụ thuộc vào nhau; nó không có nghĩa Spring bỏ qua package đó khi quét component.

Nếu dự án dùng `@ComponentScan` với `basePackages`, include filter hoặc exclude filter tùy chỉnh, hãy kiểm tra cấu hình đó có bao phủ package implementation hay không. Mô hình module được Spring Modulith phân tích và tập bean thực tế được Spring tạo cần thống nhất với nhau.

## 4. Module tiêu thụ chỉ tiêm kiểu API

Module `order` cần tính giá trong quá trình checkout. Service của module này nhận `PricingPolicy` qua constructor:

```java
package com.acme.shop.order.internal;

import com.acme.shop.pricing.PricingPolicy;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;

@Service
public class CheckoutService {

    private final PricingPolicy pricingPolicy;

    public CheckoutService(PricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    public BigDecimal calculateOrderTotal(BigDecimal subtotal) {
        return pricingPolicy.calculate(subtotal);
    }
}
```

Spring tìm bean có thể đáp ứng kiểu `PricingPolicy` và tiêm nó vào `CheckoutService`. Trong ví dụ này, `DefaultPricingPolicy` là implementation phù hợp. Module `order` chỉ tham chiếu `com.acme.shop.pricing.PricingPolicy`, nên phụ thuộc kiến trúc của nó hướng tới API công khai của module `pricing`.

Khi viết code cho module tiêu thụ, hãy tránh import trực tiếp implementation:

```java
// Không nên: phụ thuộc vào chi tiết triển khai nội bộ.
import com.acme.shop.pricing.internal.DefaultPricingPolicy;

// Nên: phụ thuộc vào contract công khai.
import com.acme.shop.pricing.PricingPolicy;
```

Nếu `CheckoutService` nhận `DefaultPricingPolicy` trong constructor, module `order` đã phụ thuộc vào một kiểu nội bộ. Việc lớp đó có modifier `public` trong Java không làm nó trở thành API của Spring Modulith. `public` kiểm soát khả năng truy cập của Java; Spring Modulith áp dụng thêm quy tắc về package và ranh giới module.

## 5. Giữ các bean cộng tác bên trong cùng module

Một implementation có thể cần thêm nhiều bean nội bộ, chẳng hạn bộ đọc cấu hình thuế hoặc bộ áp dụng khuyến mại. Các collaborator này có thể nằm trong cùng package `internal` và được tiêm qua constructor:

```java
package com.acme.shop.pricing.internal;

import org.springframework.stereotype.Component;

import java.math.BigDecimal;

@Component
public class TaxRateProvider {

    public BigDecimal currentRate() {
        return new BigDecimal("0.10");
    }
}
```

Đoạn mã tiếp theo minh họa một implementation thay thế cho `DefaultPricingPolicy` ở mục trước. Khi chọn implementation này, hãy bảo đảm chỉ có một bean `PricingPolicy` được đăng ký bằng cách bỏ hoặc vô hiệu hóa bean còn lại:

```java
package com.acme.shop.pricing.internal;

import com.acme.shop.pricing.PricingPolicy;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Component
public final class ConfigurablePricingPolicy implements PricingPolicy {

    private final TaxRateProvider taxRateProvider;

    public ConfigurablePricingPolicy(TaxRateProvider taxRateProvider) {
        this.taxRateProvider = taxRateProvider;
    }

    @Override
    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ONE.add(taxRateProvider.currentRate()))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

Các bean trong cùng module có thể cộng tác qua những kiểu nội bộ. Điều cần giữ là module khác không phải import `TaxRateProvider` hoặc `ConfigurablePricingPolicy` để hoàn thành công việc của nó. Chỉ contract cần thiết cho bên gọi mới nên xuất hiện trong API.

Trong một ứng dụng thực tế, không nên đăng ký đồng thời `DefaultPricingPolicy` và `ConfigurablePricingPolicy` như hai bean cùng implement `PricingPolicy` nếu không có cơ chế chọn bean rõ ràng. Ví dụ thứ hai minh họa một implementation thay thế; nhóm có thể bỏ `@Component` ở implementation cũ, dùng `@Primary`, `@Qualifier` hoặc cấu hình bean phù hợp với chính sách lựa chọn đã thiết kế.

## 6. Khi nào cần `@Bean` thay cho `@Component`?

Nếu implementation cần được tạo bằng factory method, hoặc không thể gắn stereotype trực tiếp lên lớp, module có thể khai báo bean trong một lớp cấu hình nội bộ:

```java
package com.acme.shop.pricing.internal;

import com.acme.shop.pricing.PricingPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PricingConfiguration {

    @Bean
    PricingPolicy pricingPolicy(TaxRateProvider taxRateProvider) {
        return new ConfigurablePricingPolicy(taxRateProvider);
    }
}
```

Lớp cấu hình và factory method vẫn nằm trong package nội bộ. Phương thức `@Bean` khai báo kiểu trả về là contract `PricingPolicy`, nhờ đó cách cấu hình thể hiện rõ bean mà module cung cấp. `TaxRateProvider` và `ConfigurablePricingPolicy` vẫn là chi tiết triển khai của module `pricing`. Nếu đăng ký `ConfigurablePricingPolicy` bằng factory method này, hãy bỏ `@Component` trên chính lớp đó và vô hiệu hóa `DefaultPricingPolicy` để chỉ còn một bean `PricingPolicy`.

Chọn `@Component` khi lớp tự mô tả vai trò bean và có thể được component scanning phát hiện. Chọn `@Bean` khi cần kiểm soát cách khởi tạo, cấu hình tham số, hoặc đăng ký một đối tượng từ thư viện bên ngoài. Cả hai cách đều có thể dùng trong package nội bộ; điều quan trọng là giữ API module rõ ràng và bảo đảm cấu hình Spring thực sự được quét.

## 7. Kiểm chứng module không truy cập implementation nội bộ

Sau khi sắp xếp API và implementation, hãy dùng Spring Modulith để kiểm tra cấu trúc module. Một bài kiểm tra kiến trúc cơ bản có thể gọi `verify()`:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void moduleDependenciesShouldRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu một module tham chiếu kiểu trong package nội bộ của module khác, kiểm tra cấu trúc có thể báo vi phạm quyền truy cập API. Bài kiểm tra này giúp phát hiện trường hợp một lập trình viên vô tình import `DefaultPricingPolicy` thay vì `PricingPolicy`.

Ngoài kiểm tra kiến trúc, một bài kiểm tra Spring context có thể xác nhận bean được tạo và contract được tiêm đúng:

```java
package com.acme.shop;

import com.acme.shop.pricing.PricingPolicy;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PricingBeanIntegrationTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void pricingPolicyShouldBeAvailableAsBean() {
        assertThat(applicationContext.getBean(PricingPolicy.class))
                .isNotNull();
    }
}
```

Ví dụ kiểm tra context cần các import và dependency kiểm thử tương ứng của dự án, chẳng hạn Spring Boot Test và AssertJ. Nó kiểm tra khả năng khởi tạo bean ở runtime; `ApplicationModules.verify()` kiểm tra quy tắc phụ thuộc kiến trúc. Hai loại kiểm tra trả lời hai câu hỏi khác nhau và có thể cùng xuất hiện trong bộ test.

## 8. Những lỗi tổ chức thường gặp

| Cách tổ chức | Vấn đề | Cách xử lý |
|---|---|---|
| Đặt implementation trong package gốc của module | Implementation dễ trở thành một phần API mặc định ngoài ý muốn | Đưa implementation vào package nội bộ. |
| Module tiêu thụ inject lớp implementation cụ thể | Tạo phụ thuộc trực tiếp vào chi tiết triển khai | Inject interface hoặc contract công khai. |
| Cho rằng package `internal` khiến Spring không tạo bean | Bean có thể không được đăng ký nếu hiểu sai component scanning | Đặt lớp ứng dụng ở package gốc hoặc cấu hình scan phù hợp. |
| Cho rằng modifier `public` đồng nghĩa với API module | Java visibility không thay thế quy tắc module | Dựa vào package gốc và named interface để thiết kế API. |
| Để kiểu nội bộ xuất hiện trong chữ ký API | Bên gọi vẫn phải biết một chi tiết nội bộ | Dùng kiểu dữ liệu công khai trong tham số và giá trị trả về. |
| Đăng ký nhiều implementation cùng contract mà không chọn rõ ràng | Spring có thể không xác định được bean cần tiêm | Dùng một implementation phù hợp hoặc cấu hình `@Primary` / `@Qualifier`. |

## 9. Quy tắc thực hành

Khi một module cần cung cấp một Spring bean cho module khác, hãy xác định contract trước, đặt contract trong package API của module, rồi đặt lớp thực thi và các collaborator trong package nội bộ. Để Spring đăng ký bean bằng `@Component` hoặc `@Bean`; module tiêu thụ chỉ inject contract. Cuối cùng, chạy kiểm tra cấu trúc Spring Modulith để bảo vệ ranh giới khi code thay đổi.

Nếu module cần công khai một nhóm kiểu nằm trong package con riêng, hãy cân nhắc khai báo package đó thành named interface theo mô hình Spring Modulith. Việc công khai package cần là quyết định thiết kế có chủ đích; không nên mở toàn bộ package nội bộ chỉ để giải quyết một lỗi tiêm phụ thuộc.

## Tài liệu tham khảo

- [Spring Modulith – Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Framework – Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
