# Migration từ detection mặc định sang explicit detection

Spring Modulith mặc định phát hiện application module bằng cách xem các package con trực tiếp của package chứa lớp `@SpringBootApplication` là module. Cách này thuận tiện khi package cấp cao đã được tổ chức theo năng lực nghiệp vụ. Khi ứng dụng có nhiều package kỹ thuật ở cùng cấp, hoặc nhóm muốn kiểm soát chính xác package nào là module, có thể chuyển sang chiến lược `explicitly-annotated`.

Với chiến lược tường minh, Spring Modulith chỉ chọn các package được đánh dấu bằng `@ApplicationModule` hoặc annotation `@Module` của jMolecules làm module base package. Việc chuyển đổi cần được thực hiện có kế hoạch: kiểm kê mô hình hiện tại, đánh dấu đầy đủ các module mong muốn, bật chiến lược mới, rồi kiểm tra lại các module, dependency và module test. Nếu bỏ sót annotation, một package trước đây là module có thể biến mất khỏi mô hình kiến trúc.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, explicit detection giúp nhóm xác định rõ ranh giới nghiệp vụ và API công khai trong ứng dụng Spring Boot. Chiến lược này kiểm soát việc Spring Modulith nhận diện module; nó không thay thế component scanning của Spring Boot và không tự thay đổi cách ứng dụng khởi tạo bean.

## 1. Khác biệt giữa default detection và explicit detection

Giả sử ứng dụng có root package `com.acme.shop`:

```text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
├── customers
├── config
├── mapper
└── persistence
```

Với chiến lược mặc định, các package con trực tiếp đều được xem là module base package nếu chúng hiện diện trong mô hình classpath. Do đó, `orders`, `inventory`, `customers` và cả `config`, `mapper`, `persistence` đều có thể được phát hiện thành module. Spring Modulith không phân loại package theo việc nó chứa nghiệp vụ hay chỉ chứa technical class.

Với `explicitly-annotated`, package chỉ trở thành module nếu được đánh dấu bằng `@ApplicationModule` hoặc jMolecules `@Module`. Nếu nhóm chỉ đánh dấu `orders`, `inventory` và `customers`, các package `config`, `mapper` và `persistence` không còn là module riêng. Những class đó vẫn có thể được Spring Boot quét và sử dụng; chúng chỉ không còn là ranh giới application module độc lập trong mô hình Modulith.

| Đặc điểm | Default detection | Explicit detection |
|---|---|---|
| Cách chọn module | Package con trực tiếp của application root | Package có `@ApplicationModule` hoặc jMolecules `@Module` |
| Cần annotation trên mỗi module | Không | Có |
| Package kỹ thuật ở cấp trực tiếp | Có thể thành module | Không thành module nếu không được đánh dấu |
| Kiểm soát ranh giới | Dựa nhiều vào package arrangement | Ý định module được khai báo trực tiếp |
| Công việc bảo trì | Ít khai báo hơn | Phải duy trì annotation khi thêm hoặc đổi module |

## 2. Kiểm kê mô hình hiện tại trước khi chuyển đổi

Không nên bật chiến lược mới trước khi biết default detection đang tạo ra những module nào. Hãy tạo mô hình từ lớp ứng dụng và liệt kê identifier cùng package nền:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .map(module -> module.getIdentifier() + " -> "
        + module.getBasePackage().getName())
    .sorted()
    .forEach(System.out::println);
```

Ví dụ đầu ra:

```text
config -> com.acme.shop.config
customers -> com.acme.shop.customers
inventory -> com.acme.shop.inventory
mapper -> com.acme.shop.mapper
orders -> com.acme.shop.orders
persistence -> com.acme.shop.persistence
```

Từ danh sách này, phân loại từng package:

- **Module nghiệp vụ cần giữ:** `orders`, `inventory`, `customers`.
- **Package kỹ thuật thuộc một module:** `mapper`, `persistence` hoặc `config` nếu chúng chỉ phục vụ một năng lực cụ thể.
- **Module dùng chung thực sự:** một package như `identity`, `messaging` hoặc `audit` có thể vẫn là module riêng nếu nó sở hữu trách nhiệm và API độc lập.

Ghi lại module nào đang được consumer sử dụng, những dependency nào được khai báo và các bài test nào bootstrap theo tên module. Danh sách này là baseline để so sánh sau khi chuyển đổi.

## 3. Đánh dấu từng module bằng @ApplicationModule

Với explicit detection, đặt `@ApplicationModule` trong `package-info.java` của từng package module. Ví dụ, `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.orders;
```

`inventory/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
```

`customers/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.customers;
```

`@ApplicationModule` đánh dấu package là module base package. Có thể bổ sung metadata ngay trên annotation khi cần, ví dụ identifier hoặc quy tắc phụ thuộc:

```java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Order Management",
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Không cần khai báo `id` nếu tên module mặc định đã phù hợp. Hãy chỉ thêm metadata thực sự cần thiết và bảo đảm giá trị `allowedDependencies` tham chiếu đúng identifier cùng named interface của module đích.

Có thể dùng jMolecules `@Module` thay cho `@ApplicationModule` làm dấu hiệu explicit detection nếu dự án đã dùng annotation đó. Trong một dự án mới hoặc khi chỉ cần khả năng phát hiện của Spring Modulith, `@ApplicationModule` thường là lựa chọn trực tiếp và dễ hiểu hơn.

Lưu ý `@NamedInterface` không thay thế `@ApplicationModule` trong chiến lược này. `@NamedInterface` đánh dấu một package API bên trong module đã được xác định; nó không phải annotation để chọn module base package cho explicit detection.

## 4. Đưa technical package ra khỏi danh sách module

Giả sử `mapper` và `persistence` chỉ phục vụ đơn hàng. Thay vì đánh dấu chúng là module, hãy đặt class bên trong module sở hữu:

```text
com.acme.shop
├── ShopApplication.java
├── orders                              // @ApplicationModule
│   ├── package-info.java
│   ├── OrderManagement.java
│   ├── mapper
│   │   └── OrderMapper.java
│   ├── persistence
│   │   └── OrderRepository.java
│   └── internal
│       └── OrderPolicy.java
├── inventory                           // @ApplicationModule
│   ├── package-info.java
│   ├── api
│   │   ├── package-info.java
│   │   └── InventoryOperations.java
│   └── internal
│       └── InventoryRepository.java
└── customers                           // @ApplicationModule
    ├── package-info.java
    └── CustomerManagement.java
```

Các package `orders.mapper` và `orders.persistence` không có `@ApplicationModule`, nên thuộc module `orders` thay vì trở thành module riêng. Cách này giúp mô hình phản ánh năng lực nghiệp vụ và giữ technical implementation bên trong module sở hữu.

Không nên xóa hoặc di chuyển package chỉ để làm danh sách module ngắn hơn. Nếu `messaging` thật sự có hợp đồng, chính sách retry và vòng đời riêng, nó có thể xứng đáng là module được đánh dấu. Quyết định cần dựa trên ownership và trách nhiệm, không chỉ dựa vào tên package.

## 5. Bật explicitly-annotated

Sau khi đã đánh dấu các module cần giữ, cấu hình chiến lược phát hiện trong `application.properties`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Hoặc trong `application.yml`:

```yaml
spring:
  modulith:
    detection-strategy: explicitly-annotated
```

Khi tạo `ApplicationModules` từ lớp ứng dụng, Spring Modulith sẽ dùng chiến lược này để xác định module base package. Hãy bảo đảm cấu hình đang được áp dụng trong đúng profile và môi trường dùng để chạy kiểm thử kiến trúc.

Nếu dự án có custom `ApplicationModuleDetectionStrategy` được cấu hình trước đó, cần kiểm tra và quyết định rõ có thay nó bằng `explicitly-annotated` hay tiếp tục dùng chiến lược tùy chỉnh. Không nên giả định hai chiến lược được tự động kết hợp.

## 6. Kiểm tra các package không còn là module

Sau khi bật explicit detection, chạy lại đoạn code liệt kê module:

```java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

modules.stream()
    .map(module -> module.getIdentifier() + " -> "
        + module.getBasePackage().getName())
    .sorted()
    .forEach(System.out::println);
```

Kết quả kỳ vọng có thể là:

```text
customers -> com.acme.shop.customers
inventory -> com.acme.shop.inventory
orders -> com.acme.shop.orders
```

Nếu `config`, `mapper` hoặc `persistence` không còn xuất hiện, điều đó có nghĩa chúng không còn là module độc lập theo mô hình explicit. Các class bên trong vẫn thuộc ứng dụng; component scanning của Spring Boot vẫn hoạt động theo phạm vi cấu hình riêng.

Hãy xác minh package kỹ thuật có được đặt trong module sở hữu hay không. Một package không được đánh dấu có thể được xem là phần của module cha phù hợp, nhưng nếu nó nằm ngoài mọi module base package thì nó có thể không được quản lý như một module. Đừng để package nghiệp vụ quan trọng biến mất khỏi mô hình chỉ vì thiếu annotation.

## 7. Rà soát dependency và module test

Việc thay đổi danh sách module có thể làm thay đổi ý nghĩa của các dependency. Ví dụ, nếu `mapper` trước đây là một module và `orders` khai báo phụ thuộc vào nó, sau khi `mapper` trở thành package nội bộ của `orders`, dependency đó không còn phù hợp và cần được loại bỏ hoặc thiết kế lại.

Kiểm tra các vị trí sau:

| Vị trí | Điều cần xác minh |
|---|---|
| `@ApplicationModule(allowedDependencies = ...)` | Chỉ tham chiếu các module và named interface còn tồn tại |
| `ApplicationModules.getModuleByName(...)` | Tên module vẫn hợp lệ sau khi thay đổi detection |
| `ApplicationModuleTest(module = ...)` | Module test trỏ tới module đã được phát hiện |
| `ApplicationModuleTest(extraIncludes = ...)` | Các module được thêm vào test slice còn tồn tại và cần thiết |
| `@Modulithic(sharedModules = ...)` | Danh sách shared module không chứa package đã bị loại khỏi mô hình |
| Architecture tests và báo cáo | Kỳ vọng về số lượng, tên và package module được cập nhật |

Ví dụ, nếu `orders` chỉ dùng API `api` của `inventory`, giữ dependency:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Và đánh dấu named interface ở package `inventory/api`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Explicit detection chỉ thay đổi cách tìm module base package. Quy tắc API và dependency vẫn cần được thiết kế, khai báo và kiểm tra như trước.

## 8. Kiểm chứng bằng ApplicationModules.verify()

Sau khi cập nhật annotation và cấu hình, chạy kiểm tra kiến trúc:

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

`verify()` giúp phát hiện các dependency không hợp lệ và chu trình phụ thuộc theo mô hình mới. Tuy nhiên, test chỉ có ý nghĩa khi nó chạy với đúng cấu hình detection mà ứng dụng sử dụng. Nếu test chạy trong profile khác hoặc tạo mô hình với cấu hình khác, kết quả có thể không phản ánh cấu trúc runtime mong muốn.

Nên có thêm kiểm thử xác nhận các module quan trọng đã được phát hiện:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleDetectionTests {

    @Test
    void detectsBusinessModulesExplicitly() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("orders")).isPresent();
        assertThat(modules.getModuleByName("inventory")).isPresent();
        assertThat(modules.getModuleByName("customers")).isPresent();
        assertThat(modules.getModuleByName("mapper")).isEmpty();
    }
}
```

Test này bảo vệ cả hai phía: module nghiệp vụ cần có mặt và package kỹ thuật không còn là module độc lập. Điều chỉnh assertion theo cấu trúc thực tế của dự án.

## 9. Rủi ro khi migration không đầy đủ

### Bỏ sót annotation

Nếu quên đánh dấu `inventory`, module này không còn xuất hiện trong mô hình explicit. Các dependency tới `inventory::api`, truy vấn `getModuleByName("inventory")` hoặc module test có thể thất bại.

### Đánh dấu quá nhiều package

Nếu nhóm thêm `@ApplicationModule` cho mọi package kỹ thuật, danh sách module vẫn bị phân mảnh. Explicit detection cho quyền lựa chọn tường minh, nhưng không tự quyết định ranh giới nghiệp vụ đúng.

### Nhầm Named Interface với module marker

Đánh dấu `@NamedInterface("api")` cho `inventory.api` chỉ công khai package API của module `inventory`; nó không thay thế `@ApplicationModule` ở package gốc `inventory` khi dùng `explicitly-annotated`.

### Quên cấu hình test hoặc profile

Ứng dụng có thể dùng explicit detection trong runtime nhưng test lại khởi tạo mô hình với cấu hình khác. Hãy kiểm tra property source, profile và cách tạo `ApplicationModules` trong test.

### Cho rằng component scanning thay đổi theo detection strategy

Spring Modulith detection strategy chỉ quyết định package nào là application module. `@SpringBootApplication` và component scanning của Spring Boot vẫn tuân theo package gốc hoặc cấu hình scan riêng. Một class có thể vẫn được Spring tạo bean dù package chứa nó không phải module độc lập.

## 10. Quy trình migration đề xuất

Có thể thực hiện chuyển đổi theo các bước sau:

1. **Chụp baseline.** Dùng `ApplicationModules` liệt kê module identifier và base package theo chiến lược mặc định.
2. **Phân loại package.** Xác định module nghiệp vụ, module dùng chung thực sự và technical package chỉ phục vụ một module khác.
3. **Điều chỉnh package nếu cần.** Đưa mapper, persistence, config và helper vào module sở hữu chúng khi đó là chi tiết triển khai.
4. **Đánh dấu module cần giữ.** Tạo `package-info.java` và thêm `@ApplicationModule` cho từng module base package mong muốn; kiểm tra các nested module nếu dự án sử dụng.
5. **Bật explicit detection.** Đặt `spring.modulith.detection-strategy=explicitly-annotated` trong cấu hình được dùng khi chạy ứng dụng và test.
6. **So sánh module list.** Xác nhận các module nghiệp vụ vẫn xuất hiện và package kỹ thuật dự kiến đã biến khỏi danh sách module.
7. **Cập nhật dependency và test.** Sửa `allowedDependencies`, module lookup, module test, shared modules và các assertion liên quan.
8. **Chạy verification.** Gọi `ApplicationModules.verify()` và các module integration tests.
9. **Ghi lại quy ước.** Hướng dẫn nhóm phải thêm `@ApplicationModule` khi tạo module mới để package không bị bỏ sót khỏi mô hình.

Trong hệ thống lớn, có thể thực hiện theo từng vùng nghiệp vụ ở nhánh refactor riêng. Tuy nhiên, trước khi bật explicit detection trên cấu hình chính, cần bảo đảm mọi module dự kiến đều được đánh dấu; nếu không, mô hình sẽ không đầy đủ.

## 11. Checklist sau khi chuyển đổi

- [ ] Mọi module nghiệp vụ dự kiến đều có `@ApplicationModule` hoặc jMolecules `@Module`.
- [ ] Package kỹ thuật không còn bị phát hiện thành module riêng ngoài ý muốn.
- [ ] `@NamedInterface` chỉ dùng để công khai API bên trong module đã được nhận diện.
- [ ] `allowedDependencies` chỉ tham chiếu module và named interface còn tồn tại.
- [ ] Các lời gọi `getModuleByName()` dùng identifier đúng.
- [ ] `ApplicationModuleTest`, `extraIncludes` và `sharedModules` đã được rà soát.
- [ ] Runtime và test sử dụng cùng detection strategy dự kiến.
- [ ] `ApplicationModules.verify()` chạy thành công.
- [ ] Có kiểm thử xác nhận module cần có và package không nên là module.
- [ ] Quy trình tạo module mới đã nhắc đến annotation bắt buộc.

## Kết luận

Migration sang `explicitly-annotated` chuyển quyền chọn module từ quy ước package con trực tiếp sang khai báo có chủ đích bằng `@ApplicationModule` hoặc jMolecules `@Module`. Trước khi bật chiến lược mới, hãy kiểm kê mô hình mặc định, phân biệt module nghiệp vụ với technical package và đánh dấu đầy đủ các module cần giữ. Sau khi chuyển, kiểm tra lại module list, dependency, module test và cấu hình runtime; dùng `ApplicationModules.verify()` cùng các test phát hiện module để bảo đảm mô hình mới phản ánh đúng kiến trúc mong muốn. Explicit detection làm ý định rõ hơn, nhưng chất lượng ranh giới vẫn phụ thuộc vào cách nhóm chọn trách nhiệm và API của từng module.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
