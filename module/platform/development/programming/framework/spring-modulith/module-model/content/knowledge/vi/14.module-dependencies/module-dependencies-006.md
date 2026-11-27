# Dependency từ configuration property

Trong Spring Modulith, một module có thể phụ thuộc vào module khác thông qua Spring bean, application event hoặc một configuration properties type được module đó công khai. Trường hợp cuối dễ bị bỏ sót vì class `@ConfigurationProperties` thường chỉ được xem như một object chứa giá trị cấu hình. Khi một module inject type này từ module khác, nó đang tham chiếu tới một hợp đồng kiểu dữ liệu thuộc module sở hữu; Spring Modulith nhận diện tham chiếu đó như bean dependency.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, việc nhận diện dependency từ configuration properties giúp mô hình kiến trúc phản ánh đúng các module cần có mặt để một module hoạt động. Cần phân biệt dependency vào một configuration properties bean với việc đọc một chuỗi property key từ `application.yml`, `@Value` hoặc `Environment`: key dạng chuỗi không mang thông tin kiểu và không tự xác định module sở hữu nó.

## 1. Configuration properties có thể là một phần của hợp đồng module

Spring Boot cho phép nhóm các cấu hình liên quan vào một class hoặc record được đánh dấu bằng `@ConfigurationProperties`. Khi type đó được đăng ký thành bean, các thành phần khác có thể inject nó như những Spring bean thông thường.

Giả sử module `inventory` công khai một nhóm cấu hình cho client tích hợp tồn kho:

```java
package com.acme.shop.inventory.configuration;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.inventory.client")
public record InventoryClientProperties(
    URI baseUrl,
    Duration timeout
) {}
```

Các giá trị được bind từ `application.yml`:

```yaml
shop:
  inventory:
    client:
      base-url: https://inventory.internal.example
      timeout: 3s
```

`InventoryClientProperties` là một Java type có package và module owner cụ thể. Prefix `shop.inventory.client` xác định namespace của các key cấu hình; package `com.acme.shop.inventory.configuration` xác định type thuộc module `inventory` trong mô hình Spring Modulith.

Nếu module khác sử dụng type này, dependency đi theo tham chiếu kiểu dữ liệu. Spring Modulith nhận diện các class `@ConfigurationProperties` như Spring bean khi phân tích component dependency. Do đó, dependency phát sinh từ constructor hoặc field injection của configuration properties type được tính vào quan hệ module.

## 2. Đăng ký configuration properties bean

Để Spring Boot bind và đăng ký `InventoryClientProperties`, có thể dùng configuration properties scanning trên lớp ứng dụng:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
```

`@ConfigurationPropertiesScan` quét các type được đánh dấu `@ConfigurationProperties` bên dưới package gốc theo phạm vi scanning của Spring Boot. Nếu muốn đăng ký rõ một số type, có thể dùng `@EnableConfigurationProperties`:

```java
package com.acme.shop.inventory;

import com.acme.shop.inventory.configuration.InventoryClientProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryConfiguration {
}
```

Hai cách trên phục vụ việc đăng ký bean ở Spring Boot. Spring Modulith không cần đọc giá trị thực trong `application.yml` để suy ra dependency; nó phân tích type được sử dụng và package sở hữu type đó.

## 3. Expose configuration properties qua API của module

Package con của một module thường là nội bộ. Nếu `orders` cần sử dụng `InventoryClientProperties`, module `inventory` phải công khai type đó qua package gốc hoặc một named interface.

Ví dụ, đánh dấu package `configuration` là named interface:

```java
@org.springframework.modulith.NamedInterface("configuration")
package com.acme.shop.inventory.configuration;
```

Sau đó module `orders` chỉ cho phép phụ thuộc vào named interface này trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::configuration"
)
package com.acme.shop.orders;
```

Biểu thức `inventory::configuration` gồm hai phần:

- `inventory`: logical identifier của module cung cấp type.
- `configuration`: tên named interface mà module đó công khai.

Việc khai báo này làm rõ rằng `orders` được phép sử dụng hợp đồng cấu hình đã công khai của `inventory`. Nếu không muốn công khai configuration properties cho module khác, hãy giữ class ở package nội bộ và thiết kế một API nghiệp vụ phù hợp để consumer không phải phụ thuộc vào cấu hình nội bộ.

## 4. Dependency được hình thành khi module inject properties type

Giả sử `OrderPlacement` thuộc module `orders` nhận `InventoryClientProperties` qua constructor:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.configuration.InventoryClientProperties;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacement {

    private final InventoryClientProperties inventoryProperties;

    public OrderPlacement(InventoryClientProperties inventoryProperties) {
        this.inventoryProperties = inventoryProperties;
    }

    public String inventoryEndpoint() {
        return inventoryProperties.baseUrl().toString();
    }
}
```

Mối quan hệ module được tạo ra là:

```text
orders  ───────>  inventory::configuration
```

`orders` cần module `inventory` để Spring có thể cung cấp bean `InventoryClientProperties`. Spring Modulith nhận diện dependency này như một component/bean dependency, cùng nhóm với các dependency phát sinh từ việc inject một Spring service hoặc component khác. `DependencyType` không có một hằng số riêng tên `CONFIGURATION_PROPERTIES`; loại dependency được biểu diễn bằng `USES_COMPONENT`.

Điều này cũng có nghĩa một configuration properties type đặt trong package nội bộ của `inventory` vẫn là dependency nội bộ không hợp lệ nếu `orders` tham chiếu trực tiếp. Việc type được đăng ký thành bean không tự động làm package đó trở thành API công khai.

## 5. Phân biệt bean dependency với việc đọc raw property key

Không phải mọi lần một module đọc property đều tạo ra dependency tới module khác. Hãy phân biệt hai cách sau:

| Cách sử dụng | Có tham chiếu type thuộc module khác? | Quan hệ module được nhận diện |
|---|---:|---|
| Inject `InventoryClientProperties` từ module `inventory` | Có | Có component/bean dependency tới `inventory` |
| Inject một `@ConfigurationProperties` type thuộc chính module hiện tại | Không | Không tạo dependency sang module khác chỉ vì đó là configuration properties |
| Đọc `@Value("${shop.inventory.client.base-url}")` | Không | Không suy ra module owner từ chuỗi key |
| Gọi `environment.getProperty("shop.inventory.client.base-url")` | Không | Không suy ra module owner từ chuỗi key |
| Có key `shop.inventory.client.base-url` trong `application.yml` | Không | File cấu hình không tự tạo dependency edge giữa module |

Ví dụ, đoạn code sau chỉ tham chiếu một key dạng chuỗi:

```java
@Value("${shop.inventory.client.base-url}")
private URI inventoryBaseUrl;
```

Tên prefix có thể gợi ý rằng giá trị liên quan tới inventory, nhưng Spring Modulith không thể xác định ownership module chỉ từ chuỗi đó trong một dependency graph dựa trên type. Nếu muốn dependency được biểu diễn và kiểm tra rõ ràng, hãy dùng một type công khai thuộc module sở hữu hoặc một hợp đồng nghiệp vụ phù hợp.

## 6. Kiểm tra dependency trong ApplicationModules

Có thể tạo mô hình và kiểm tra cấu trúc bằng `ApplicationModules.verify()`:

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

Nếu `orders` inject một properties type trong package nội bộ của `inventory`, verification có thể báo vi phạm truy cập API module. Sau khi package đó được công khai qua `NamedInterface` và dependency được cho phép, kiểm tra sẽ chấp nhận quan hệ này.

Để quan sát riêng các dependency dạng component, có thể truy vấn mô hình:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders").orElseThrow();

orders.getDirectDependencies(modules, DependencyType.USES_COMPONENT)
    .uniqueModules()
    .forEach(module -> System.out.println(module.getIdentifier()));
```

`getDirectDependencies(..., DependencyType.USES_COMPONENT)` trả về các dependency component trực tiếp của `orders`. `uniqueModules()` giúp liệt kê mỗi module đích một lần, kể cả khi có nhiều bean hoặc nhiều properties type trong cùng module được sử dụng.

Có thể thêm assertion để bảo vệ dependency dự kiến:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

class ConfigurationPropertiesDependencyTests {

    @Test
    void ordersDependsOnInventoryConfiguration() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders").orElseThrow();
        ApplicationModule inventory = modules.getModuleByName("inventory").orElseThrow();

        assertThat(orders.getDirectDependencies(modules, DependencyType.USES_COMPONENT)
            .contains(inventory)).isTrue();
    }
}
```

Test này xác nhận quan hệ trực tiếp đã xuất hiện trong mô hình. Nó không thay thế `verify()`, vì `verify()` còn kiểm tra dependency có tuân thủ package API, named interface và `allowedDependencies` hay không.

## 7. Ảnh hưởng tới module integration test

Module integration test thường bootstrap module đang kiểm thử cùng các dependency cần thiết tùy bootstrap mode. Nếu một bean trong `orders` inject `InventoryClientProperties` từ `inventory`, module `inventory` là một dependency cần được bootstrap khi chạy test theo chế độ bao gồm direct dependencies.

Ví dụ:

```java
package com.acme.shop.orders;

import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(bootstrapMode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderModuleIntegrationTests {
    // Các test của module orders.
}
```

Nếu dùng chế độ chỉ bootstrap module hiện tại (`STANDALONE`), Spring có thể không tạo bean thuộc `inventory`; khi đó constructor injection có thể thất bại nếu không cung cấp mock hoặc test configuration phù hợp. Không nên mở rộng test slice một cách máy móc nếu dependency chỉ tồn tại vì consumer đang lấy cấu hình nội bộ của module khác. Hãy xem xét liệu configuration properties type đó có thực sự cần là hợp đồng liên mô-đun hay consumer nên sở hữu cấu hình riêng.

## 8. Thiết kế ownership cho configuration properties

Không nên công khai mọi class `@ConfigurationProperties` chỉ vì class đó được Spring đăng ký thành bean. Hãy xác định ai sở hữu ý nghĩa của các key và ai cần sử dụng chúng.

| Tình huống | Cách tổ chức phù hợp |
|---|---|
| Properties chỉ cấu hình nội bộ cho `inventory` | Đặt class trong package nội bộ của `inventory`; không cho module khác inject |
| Nhiều module cần một hợp đồng cấu hình dùng chung có chủ đích | Đặt type trong package API/named interface được công khai rõ ràng |
| `orders` cần cấu hình endpoint của một client do `orders` sở hữu | Đặt `OrdersInventoryClientProperties` trong module `orders`; không phụ thuộc vào cấu hình nội bộ của `inventory` |
| Một giá trị là kết quả nghiệp vụ hoặc trạng thái runtime của module khác | Dùng API hoặc event thay vì chia sẻ configuration properties |
| Nhiều module chỉ cần cùng một hằng số hoặc kiểu cấu hình dùng chung | Cân nhắc một module cấu hình/shared có ownership và API rõ ràng, tránh tạo package tiện ích không có ranh giới |

Configuration properties mô tả cấu hình triển khai, không phải lúc nào cũng là hợp đồng nghiệp vụ. Nếu `orders` chỉ cần biết URL để gọi một dịch vụ ngoài, class cấu hình thuộc `orders` thường phù hợp hơn. Nếu `orders` cần cấu hình do `inventory` sở hữu và module đó chủ động công khai, dependency tới properties type có thể là quyết định kiến trúc hợp lý.

## 9. Những ngộ nhận thường gặp

- **“Configuration properties chỉ là dữ liệu nên không tạo dependency.”** Khi type được đăng ký thành Spring bean và module khác tham chiếu nó, Spring Modulith xem đó là bean/component dependency.
- **“Có prefix của module là đã tạo dependency.”** Prefix là namespace cấu hình; module dependency được suy ra từ type/package được tham chiếu, không phải từ tên key dạng chuỗi.
- **“`@ConfigurationProperties` tự động công khai class.”** Class vẫn tuân theo ranh giới package và named interface của module sở hữu.
- **“Có một `DependencyType.CONFIGURATION_PROPERTIES`.”** Dependency này được biểu diễn trong nhóm `USES_COMPONENT`, không phải một enum riêng.
- **“Đăng ký bằng `@ConfigurationPropertiesScan` là đủ để module khác được phép dùng.”** Scanning đăng ký bean; quyền truy cập kiến trúc vẫn phụ thuộc package API và quy tắc `allowedDependencies`.
- **“Có thể dùng properties nội bộ vì Spring inject được.”** Khả năng inject của Spring không đồng nghĩa dependency hợp lệ theo ranh giới Spring Modulith.
- **“`verify()` kiểm tra giá trị cấu hình có hợp lệ hay không.”** Verification kiểm tra cấu trúc và dependency module; validation giá trị cấu hình thuộc Spring Boot validation và kiểm thử cấu hình ứng dụng.

## 10. Quy trình rà soát dependency từ configuration properties

Khi thấy một module phụ thuộc vào configuration properties type của module khác, hãy thực hiện:

1. **Tìm type được inject.** Xác định class/record `@ConfigurationProperties` và package khai báo của nó.
2. **Xác định module owner.** Dùng package nền và `ApplicationModules` để xác nhận module sở hữu type.
3. **Xác nhận bean registration.** Kiểm tra `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` đang đăng ký type.
4. **Xem xét mục đích chia sẻ.** Xác định type đó là hợp đồng công khai, cấu hình nội bộ hay cấu hình mà consumer nên tự sở hữu.
5. **Công khai có chủ đích nếu cần.** Đặt type ở package gốc hoặc named interface phù hợp.
6. **Giới hạn dependency.** Dùng `allowedDependencies` để consumer chỉ được phép dùng module/interface cần thiết.
7. **Kiểm chứng mô hình.** Kiểm tra `USES_COMPONENT` dependency và chạy `ApplicationModules.verify()`.
8. **Kiểm thử bootstrap.** Chạy module integration test ở bootstrap mode phù hợp, xác nhận bean và giá trị bind được đúng.

## Kết luận

Configuration properties type có thể trở thành một phần của required interface khi module khác inject nó như Spring bean. Spring Modulith nhận diện tham chiếu này như bean/component dependency (`USES_COMPONENT`), nên package của properties type phải được công khai đúng cách và dependency phải tuân thủ `allowedDependencies`. Prefix hoặc raw property key trong `@Value`, `Environment` hay `application.yml` không tự tạo dependency edge theo module owner. Hãy phân biệt cấu hình nội bộ với hợp đồng được chia sẻ, xác nhận bean registration và dùng `ApplicationModules.verify()` cùng kiểm thử module để bảo vệ ranh giới.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — DependencyType API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [Spring Modulith — ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Modulith 0.1 M1 release notes — Configuration properties dependencies](https://github.com/spring-projects/spring-modulith/discussions/50)
