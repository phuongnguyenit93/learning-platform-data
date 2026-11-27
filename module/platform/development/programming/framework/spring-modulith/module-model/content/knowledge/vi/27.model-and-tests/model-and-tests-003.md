# `sharedModules` và module luôn được đưa vào test

Khi dùng `@ApplicationModuleTest`, Spring Modulith thường chỉ khởi động module đang được kiểm thử cùng phạm vi dependency mà bootstrap mode yêu cầu. Cách làm này giúp test tập trung vào một capability và tránh khởi động toàn bộ ứng dụng. Tuy nhiên, có những module chứa cấu hình Spring hoặc component hạ tầng được nhiều module sử dụng, chẳng hạn cấu hình bảo mật chung, clock, audit infrastructure hoặc các bean nền tảng.

Nếu mỗi module test đều cần những thành phần đó, ta có thể khai báo chúng là shared module bằng thuộc tính `sharedModules` của `@Modulithic`. Spring Modulith sẽ luôn đưa các module được khai báo vào bootstrap của application module integration tests, bất kể test đang dùng `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`.

## 1. Bài toán khi test từng module độc lập

Giả sử ứng dụng bán hàng có các module:

```text
com.acme.shop
├── ShopApplication.java
├── shared
│   ├── SharedInfrastructureConfiguration.java
│   └── ClockProvider.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── PlaceOrderService.java
├── inventory
│   └── InventoryManagement.java
└── customer
    └── CustomerManagement.java
```

Module `order` sử dụng một `Clock` do cấu hình dùng chung cung cấp:

```java
package com.acme.shop.shared;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class SharedInfrastructureConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service của module `order` inject `Clock`:

```java
package com.acme.shop.order.internal;

import java.time.Clock;

import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final Clock clock;

    PlaceOrderService(Clock clock) {
        this.clock = clock;
    }
}
```

Một integration test đặt trong package `order` và dùng `@ApplicationModuleTest` mặc định chạy ở mode `STANDALONE`. Nếu chỉ module `order` được bootstrap mà không có module `shared`, Spring không tìm thấy bean `Clock` để tạo `PlaceOrderService`. Test có thể thất bại ngay ở bước khởi tạo ApplicationContext, dù `Clock` là hạ tầng mà mọi module đều được thiết kế để sử dụng.

Ta có thể đưa `shared` vào mọi module test bằng `@Modulithic(sharedModules = "shared")`.

## 2. Khai báo shared module ở cấp ứng dụng

Đặt `@Modulithic` trên lớp Spring Boot application và liệt kê logical name của các module dùng chung:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(sharedModules = "shared")
@SpringBootApplication
public class ShopApplication {
}
```

Nếu có nhiều module dùng chung, truyền nhiều tên:

```java
@Modulithic(sharedModules = {
    "shared",
    "security",
    "observability"
})
@SpringBootApplication
public class ShopApplication {
}
```

`sharedModules` là thuộc tính kiểu `String[]`; mỗi giá trị là tên module theo module arrangement mà Spring Modulith nhận diện. Trong ví dụ, `shared` phải là một application module đã được phát hiện. Thuộc tính này đánh dấu module đã có là shared; nó không tự tạo module mới từ một package bất kỳ.

Với cách phát hiện mặc định, package con trực tiếp `com.acme.shop.shared` được nhận diện là module. Nếu ứng dụng dùng `explicitly-annotated` hoặc custom detection strategy, package đó vẫn phải đáp ứng quy tắc discovery tương ứng.

`@Modulithic` có thể được dùng cùng `@SpringBootApplication` như ví dụ trên. Spring Modulith cũng cung cấp `@Modulith`, một annotation tổng hợp cho ứng dụng Spring Boot theo quy ước Modulith và có các thuộc tính tương ứng, bao gồm `sharedModules`.

## 3. Shared module được đưa vào mọi `@ApplicationModuleTest`

Để dùng `@ApplicationModuleTest`, thêm Spring Modulith test starter vào test classpath. Ví dụ với Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
```

Nếu dự án quản lý phiên bản bằng Spring Modulith BOM, không cần ghi version riêng cho dependency này.

Tạo integration test cho module `order`:

```java
package com.acme.shop.order;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderIntegrationTests {

    // Test các luồng nghiệp vụ của module order.
}
```

Với `sharedModules = "shared"`, bootstrap của test sẽ bao gồm:

```text
ApplicationContext của OrderIntegrationTests
├── order       module đang được kiểm thử
└── shared      module được khai báo dùng chung
```

Nhờ đó, bean `Clock` từ `shared` có mặt khi Spring tạo các component của `order`. Test vẫn được giới hạn theo module, nhưng có thêm những module nền tảng đã được nhóm xác định là cần thiết ở mọi lần bootstrap.

Quy tắc này áp dụng cho application module integration tests dùng `@ApplicationModuleTest` (được xây dựng trên `@ModuleSlicing`). Nó không có nghĩa mọi JUnit test, unit test thuần hoặc mọi `@SpringBootTest` trong dự án đều tự động nạp shared module.

## 4. `sharedModules` tương tác với bootstrap mode thế nào?

`@ApplicationModuleTest` có ba bootstrap mode chính:

| Mode | Module được đưa vào test | Shared module |
| --- | --- | --- |
| `STANDALONE` | Chỉ module chứa test | Luôn được thêm |
| `DIRECT_DEPENDENCIES` | Module chứa test và các module mà nó phụ thuộc trực tiếp | Luôn được thêm |
| `ALL_DEPENDENCIES` | Module chứa test và toàn bộ cây dependency trực tiếp, bắc cầu | Luôn được thêm |

Ví dụ, giả sử dependency graph là:

```text
order ------> inventory ------> catalog
  |
  +---------> customer

shared: được đưa vào mọi module test
```

Test của `order` có thể khai báo mode:

```java
@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)
class OrderIntegrationTests {
}
```

Khi đó, bootstrap bao gồm `order`, `inventory`, `customer` và `shared`. Module `catalog` là dependency bắc cầu của `order` qua `inventory`, nên không thuộc phạm vi `DIRECT_DEPENDENCIES` chỉ vì quan hệ bắc cầu đó.

Nếu đổi sang `ALL_DEPENDENCIES`, `catalog` cũng được đưa vào vì mode này mở rộng tới toàn bộ dependency tree. `shared` vẫn được thêm theo cấu hình toàn ứng dụng, độc lập với lựa chọn mode.

## 5. Phân biệt `sharedModules` và `extraIncludes`

Không phải module nào cần thêm vào một test cũng nên được đánh dấu shared. Spring Modulith có thuộc tính `extraIncludes` của `@ApplicationModuleTest` để thêm module cho riêng test đó, bất kể bootstrap mode.

Ví dụ, chỉ một test của `order` cần module `reporting`:

```java
package com.acme.shop.order;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(extraIncludes = "reporting")
class OrderReportingIntegrationTests {
}
```

So sánh hai cách:

| Cấu hình | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| `@Modulithic(sharedModules = "shared")` | Toàn bộ application module integration tests | Module nền tảng cần có trong mọi bootstrap |
| `@ApplicationModuleTest(extraIncludes = "reporting")` | Chỉ test class được gắn annotation | Module bổ sung chỉ cần trong một số kịch bản |
| `mode = DIRECT_DEPENDENCIES` | Theo dependency trực tiếp của module đang test | Muốn chạy tích hợp với các module mà module hiện tại phụ thuộc trực tiếp |
| `mode = ALL_DEPENDENCIES` | Theo toàn bộ dependency tree | Muốn kiểm tra cả chuỗi module phụ thuộc bắc cầu |

Đừng đưa một module vào `sharedModules` chỉ vì một test cụ thể cần nó. Làm như vậy khiến mọi module test đều phải bootstrap module đó, làm tăng thời gian và phạm vi ApplicationContext không cần thiết.

## 6. Shared module vẫn là application module

Shared module không biến mất khỏi module model và cũng không phải package bị bỏ qua. Nó vẫn là một application module có base package, Spring beans, API và implementation nội bộ như các module khác.

Có thể quan sát các module đã được đánh dấu shared qua API:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModules;

class ModuleInspection {

    void inspectSharedModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.getSharedModules().forEach(System.out::println);
    }
}
```

`getSharedModules()` trả về tập `ApplicationModule` được đăng ký là shared trong module arrangement. Đây là cách xác nhận cấu hình `@Modulithic` đã được phản ánh trong module model.

Shared module vẫn tuân thủ các quy tắc package boundary. Nếu module `shared` có package `shared.internal`, module khác không tự động được quyền truy cập package đó chỉ vì `shared` được đánh dấu dùng chung. Consumer vẫn phải sử dụng API package gốc hoặc Named Interface mà module `shared` công bố.

## 7. Shared module và `allowedDependencies`

`sharedModules` còn có ý nghĩa với kiểm tra dependency. Spring Modulith xem các shared module là dependency được phép của các module khác. API `ApplicationModule.getAllowedDependencies(modules)` mô tả tập dependency được phép, bao gồm dependency khai báo tường minh và dependency được đánh dấu shared trên `ApplicationModules`.

Ví dụ, `order` cần dùng API của module `shared`. Khi `shared` đã được khai báo trong `@Modulithic(sharedModules = "shared")`, module đó được tính vào tập allowed dependencies của `order`.

Điều này không có nghĩa mọi dependency đều được cho phép. Nếu `order` gọi `reporting` mà module đó không phải shared và không nằm trong allowlist, verification vẫn có thể báo vi phạm. Shared chỉ mở rộng quyền dependency tới đúng các module đã khai báo shared.

Shared module cũng không mở toàn bộ package nội bộ. Hai câu hỏi vẫn cần được phân biệt:

- Module nào được phép phụ thuộc? `sharedModules` và `allowedDependencies` liên quan đến câu hỏi này.
- Module tiêu thụ được phép truy cập package/type nào? API package, Named Interface và quy tắc closed/open module quyết định phạm vi này.

Vì vậy, hãy công bố API của shared module rõ ràng và giữ implementation nội bộ ở package con phù hợp.

## 8. Chọn module nào để đánh dấu shared?

Một module phù hợp để đưa vào `sharedModules` thường chứa các thành phần nền tảng thực sự cần có trong hầu hết module test:

| Nhóm chức năng | Ví dụ |
| --- | --- |
| Cấu hình Spring dùng chung | Bean `Clock`, converter chung, cấu hình serialization |
| Hạ tầng cross-cutting | Audit infrastructure, observability, correlation ID |
| Thành phần nền tảng | Security configuration hoặc một abstraction chung mà mọi module cần |
| Chính sách dùng chung | Các thành phần kỹ thuật thực thi một quy ước toàn ứng dụng |

Không nên đưa toàn bộ code tiện ích vào một module `shared` lớn chỉ vì nhiều nơi có thể import nó. Hãy phân biệt một module nền tảng có ownership rõ với một package `common` tích lũy mọi class không biết đặt ở đâu.

Nếu module chứa nghiệp vụ riêng, dữ liệu riêng hoặc có dependency nặng tới một hệ thống ngoài, hãy cân nhắc để nó là module bình thường. Những test cần nó có thể chọn `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES` hoặc `extraIncludes` phù hợp.

## 9. Chi phí khi shared module được nạp ở mọi test

Mỗi shared module làm tăng phạm vi bootstrap của tất cả application module integration tests. Nếu shared module chứa nhiều bean, auto-configuration, kết nối hạ tầng hoặc dependency ngoài, thời gian khởi động test có thể tăng và test có thể phụ thuộc vào môi trường nhiều hơn.

Ví dụ, một module `shared` chứa cả cấu hình `DataSource`, client HTTP, message broker, cache và các component không liên quan sẽ khiến nhiều test phải nạp những thành phần đó dù test chỉ kiểm tra một luồng nghiệp vụ nhỏ.

Để giữ test nhanh và ổn định:

1. Chỉ đánh dấu module thực sự cần cho mọi module test.
2. Tách các cấu hình hạ tầng nặng thành module riêng nếu không phải test nào cũng cần.
3. Dùng `extraIncludes` cho các test đặc biệt thay vì mở rộng phạm vi toàn cục.
4. Dùng `@MockitoBean` để thay component ở module khác khi chỉ cần mô phỏng một dependency.
5. Bật log `DEBUG` cho `org.springframework.modulith` khi cần xem module nào được đưa vào bootstrap.

Nếu một module nghiệp vụ phải nạp quá nhiều bean từ các module khác, hãy xem lại mức coupling. Có thể module đó đang cần một hợp đồng hẹp hơn hoặc có thể phản ứng với domain event thay vì phụ thuộc vào nhiều component trực tiếp.

## 10. Kiểm chứng cấu hình shared module

Có thể tạo một bài test nhỏ để xác nhận shared module xuất hiện trong module model:

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class SharedModuleConfigurationTests {

    @Test
    void registersSharedModule() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getSharedModules())
                .anyMatch(module -> module.getBasePackage().getName()
                        .equals("com.acme.shop.shared"));
    }
}
```

Sau đó, chạy một `@ApplicationModuleTest` trong module cần sử dụng bean shared. Nếu muốn xem phạm vi bootstrap, đặt logging:

```yaml
logging:
  level:
    org.springframework.modulith: DEBUG
```

Log của module test thể hiện logical name, base package, dependency trực tiếp và các bean được đưa vào ApplicationContext. Kiểm tra log giúp xác nhận shared module thực sự được bootstrap cùng module đang test.

`ApplicationModules.verify()` vẫn có thể được dùng để kiểm tra module boundary và dependency:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Verification kiểm tra module arrangement; `@ApplicationModuleTest` kiểm tra khả năng bootstrap và hành vi tích hợp của module. Hai hình thức kiểm tra bổ sung cho nhau.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| `sharedModules` tạo một module mới từ package được ghi tên | Module phải được phát hiện trong module arrangement; thuộc tính chỉ đánh dấu module hiện có là shared |
| Shared module chỉ được nạp khi module test phụ thuộc trực tiếp vào nó | Shared module được đưa vào mọi application module integration test, bất kể bootstrap mode |
| `STANDALONE` luôn chỉ nạp đúng một module | Nó nạp module hiện tại cùng các shared module đã khai báo |
| `sharedModules` và `extraIncludes` giống nhau | Một cấu hình áp dụng toàn cục; cấu hình kia chỉ áp dụng cho test class cụ thể |
| Shared module không còn chịu module verification | Nó vẫn là application module và vẫn có API/internal boundary |
| Đánh dấu shared đồng nghĩa mở toàn bộ package nội bộ | Shared ảnh hưởng bootstrap và allowed dependency; nó không tự biến module thành `OPEN` |
| Mọi test trong dự án đều nạp shared module | Quy tắc áp dụng cho application module integration tests, không tự động áp dụng cho mọi unit test hoặc `@SpringBootTest` |
| Càng nhiều shared module càng tốt | Mỗi module được thêm làm tăng phạm vi bootstrap và có thể làm test chậm, phụ thuộc môi trường |

## 12. Ghi nhớ

`@Modulithic(sharedModules = { ... })` khai báo các application module dùng chung. Spring Modulith luôn đưa chúng vào bootstrap của mọi `@ApplicationModuleTest`, không phụ thuộc `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`. Shared module cũng được tính là dependency được phép khi Spring Modulith xây dựng allowed dependencies.

Hãy dùng shared module cho cấu hình Spring và component nền tảng thật sự cần trong mọi module test. Dùng `extraIncludes` khi chỉ một test cần thêm module; dùng bootstrap mode khi muốn mở rộng theo dependency trực tiếp hoặc bắc cầu. Shared module vẫn là application module và vẫn tuân thủ API boundary, Named Interface cùng các quy tắc kiến trúc thông thường. Giữ danh sách shared nhỏ để tránh làm mọi test khởi động quá nhiều hạ tầng.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Customizing the Application Modules Arrangement](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith 2.2 — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith API — `@Modulithic`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API — `ApplicationModuleTest`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html)
- [Spring Modulith API — `ApplicationModule.getAllowedDependencies(…)`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
