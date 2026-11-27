# Dependency tới bean, event listener và configuration property

Một application module không chỉ có phần code mà nó sở hữu. Nó còn có những hợp đồng cung cấp cho module khác và những hợp đồng mà nó cần sử dụng. Trong Spring Modulith, các quan hệ đó thường xuất hiện qua ba hình thức: module gọi Spring bean của module khác, module đăng ký listener cho application event do module khác phát ra, và module công bố hoặc sử dụng cấu hình thông qua configuration properties.

Ba hình thức này đều ảnh hưởng đến cách hiểu về ranh giới module, nhưng chúng không có cùng cơ chế. Bean dependency là quan hệ gọi thành phần trực tiếp; event listener là quan hệ phản ứng với một sự kiện; configuration property là hợp đồng cấu hình. Hiểu sự khác biệt giúp đọc dependency graph đúng và tránh tạo những phụ thuộc khó thấy qua tên property hoặc cấu hình dùng chung.

## 1. Provided interface và required interface

Spring Modulith mô tả một application module bằng ba phần:

1. **Provided interface:** API mà module cung cấp cho module khác. API này có thể gồm Spring bean được công bố và application event mà module phát ra.
2. **Internal implementation:** các thành phần triển khai chỉ phục vụ bên trong module.
3. **Required interface:** những hợp đồng module cần từ module khác, bao gồm Spring bean dependency, application event mà module lắng nghe và configuration properties được công bố.

Ví dụ, module `inventory` cung cấp bean `InventoryManagement` để kiểm tra tồn kho và phát event `StockReserved` sau khi giữ hàng. Module `order` có thể gọi `InventoryManagement` trong quy trình tạo đơn. Module `shipping` có thể lắng nghe `OrderPlaced` để chuẩn bị giao hàng. Mỗi module cũng có thể công bố các cấu hình riêng như ngưỡng cảnh báo tồn kho.

Giả sử package gốc ứng dụng là `com.acme.shop`:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal
│       └── OrderService.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       ├── InventoryService.java
│       └── config
│           └── InventoryProperties.java
└── shipping
    └── ShippingOrderEvents.java
```

Theo quy tắc phát hiện mặc định, `order`, `inventory` và `shipping` là các application module. Package gốc của từng module là API mặc định; package con như `internal` là phần nội bộ, trừ khi được công bố bằng Named Interface hoặc cấu hình phù hợp.

## 2. Dependency tới Spring bean

Bean dependency xuất hiện khi một Spring bean trong module A cần một Spring bean do module B cung cấp. Đây là quan hệ gọi trực tiếp: module A biết một abstraction hoặc type của module B và yêu cầu Spring inject implementation tương ứng.

Ví dụ, module `inventory` công bố một API kiểm tra tồn kho trong package gốc:

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean hasAvailableStock(Sku sku, int quantity);
}
```

Implementation nằm bên trong module `inventory`:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.InventoryManagement;
import com.acme.shop.inventory.Sku;
import org.springframework.stereotype.Service;

@Service
class InventoryService implements InventoryManagement {

    @Override
    public boolean hasAvailableStock(Sku sku, int quantity) {
        // Kiểm tra số lượng tồn kho.
        return true;
    }
}
```

Module `order` sử dụng API đó qua constructor injection:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import com.acme.shop.inventory.Sku;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    boolean canPlaceOrder(Sku sku, int quantity) {
        return inventory.hasAvailableStock(sku, quantity);
    }
}
```

Quan hệ kiến trúc có hướng `order -> inventory`: code trong `order` phụ thuộc vào bean/API của `inventory`. Spring Modulith phân loại quan hệ component này là `USES_COMPONENT`. Điều đó thể hiện module nguồn cần module đích được bootstrap để chạy module nguồn, vì Spring phải cung cấp component mà module nguồn đang sử dụng.

Một số điểm cần chú ý:

- Module tiêu thụ chỉ nên inject type thuộc package API hoặc Named Interface đã công bố của module cung cấp.
- Không inject repository, service nội bộ hoặc adapter của module khác chỉ vì lớp đó đang được khai báo `public`.
- Constructor injection giúp dependency nhìn thấy ngay trong chữ ký constructor và thuận tiện cho kiểm thử.
- Dependency được tạo bởi bean wiring là quan hệ cấu trúc. Nó khác với việc hai module cùng đọc một giá trị trong `application.yml`.

Nếu muốn giới hạn module `order` chỉ được phụ thuộc vào `inventory`, khai báo trên package của `order`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

`allowedDependencies` làm rõ module nào được phép dùng. Khi kiểm tra kiến trúc, một dependency đến module không có trong danh sách sẽ bị xem là vi phạm.

## 3. Dependency tới event listener

Event listener tạo ra một quan hệ khác. Module phát event công bố một sự thật nghiệp vụ; module khác đăng ký listener để phản ứng với sự thật đó. Module phát không cần gọi trực tiếp listener hoặc biết danh sách consumer.

Giả sử `order` phát event `OrderPlaced`:

```java
package com.acme.shop.order.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
```

Vì event nằm trong package con `order.events`, module `order` cần công bố package này nếu muốn module khác sử dụng nó. Tạo `package-info.java`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Module `shipping` đăng ký listener:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderEvents {

    private final ShippingService shipping;

    ShippingOrderEvents(ShippingService shipping) {
        this.shipping = shipping;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        shipping.prepareShipment(event.orderId());
    }
}
```

Quan hệ được biểu diễn theo hướng `shipping -> order`: module `shipping` cần hợp đồng event do `order` công bố. Spring Modulith phân loại nó là `EVENT_LISTENER`. Đây là dependency trong mô hình module, nhưng có semantics khác `USES_COMPONENT`: module đích không cần được bootstrap chỉ để chạy module nguồn, bởi module nguồn đang đăng ký phản ứng với event thay vì gọi component của module đích.

`@ApplicationModuleListener` là cách khai báo listener thường dùng cho giao tiếp giữa application module. Annotation này kết hợp xử lý bất đồng bộ, transactional event listener và transaction riêng cho listener. Spring Modulith cũng nhận diện các listener khai báo bằng Spring `@EventListener`, `@TransactionalEventListener` hoặc bean triển khai `ApplicationListener` khi xây dựng thông tin module.

Để giới hạn dependency của `shipping` vào Named Interface `events` của `order`, khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Cú pháp `module :: interface` xác định rõ phần API được phép sử dụng. Nếu `shipping` còn cần một API khác ở package gốc của `order`, phải khai báo thêm dependency tương ứng.

## 4. So sánh bean dependency và event listener dependency

Hai module có thể trao đổi thông tin nhưng mức độ ràng buộc khác nhau:

| Đặc điểm | Bean dependency (`USES_COMPONENT`) | Event listener (`EVENT_LISTENER`) |
| --- | --- | --- |
| Cách tương tác | Module gọi method trên bean của module khác | Module nhận event và thực hiện phản ứng |
| Hướng dependency | Module gọi phụ thuộc module cung cấp bean | Module lắng nghe phụ thuộc module công bố event |
| Mức độ biết nhau | Consumer biết abstraction hoặc type bean | Consumer biết event contract |
| Thời điểm | Thường theo luồng gọi trực tiếp | Theo cơ chế listener, có thể sau commit và bất đồng bộ |
| Bootstrap | Module đích cần được bootstrap để cung cấp component cho module nguồn | Module đích không cần bootstrap chỉ vì module nguồn đăng ký listener |
| Trường hợp phù hợp | Cần kết quả ngay để tiếp tục quyết định nghiệp vụ | Thông báo một sự thật để một hoặc nhiều module tự phản ứng |

Ví dụ trong luồng tạo đơn: `order` có thể gọi `inventory.hasAvailableStock()` vì cần biết còn hàng trước khi xác nhận đơn. Sau khi đơn đã được lưu thành công, `order` phát `OrderPlaced` để `shipping` và `notification` tự xử lý công việc tiếp theo.

Không nên thay một lời gọi cần kết quả tức thời bằng event rồi giả định listener sẽ trả lời ngay. Cũng không cần tạo bean dependency chỉ để thông báo một sự thật mà nhiều module có thể quan tâm.

## 5. Configuration property là hợp đồng cấu hình của module

Configuration property thể hiện cách một module cho phép môi trường bên ngoài điều chỉnh hành vi của nó. Ví dụ, `inventory` có thể công bố ngưỡng tồn kho để quyết định khi nào cần phát cảnh báo.

Khai báo lớp cấu hình có prefix riêng:

```java
package com.acme.shop.inventory.internal.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.shop.inventory")
public record InventoryProperties(int restockThreshold) {
}
```

Đăng ký configuration properties trong module:

```java
package com.acme.shop.inventory.internal.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
class InventoryConfiguration {
}
```

Module `inventory` sử dụng cấu hình của chính nó:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.internal.config.InventoryProperties;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final InventoryProperties properties;

    InventoryService(InventoryProperties properties) {
        this.properties = properties;
    }

    boolean shouldRestock(int currentQuantity) {
        return currentQuantity < properties.restockThreshold();
    }
}
```

Giá trị có thể được đặt trong cấu hình Spring Boot:

```yaml
acme:
  shop:
    inventory:
      restock-threshold: 20
```

Prefix `acme.shop.inventory` cho biết cấu hình thuộc module `inventory`. Module sở hữu prefix đó cần quản lý tên property, kiểu dữ liệu, giá trị mặc định, ý nghĩa và cách thay đổi của nó. Nhờ vậy, người vận hành có thể cấu hình module mà không phải sửa code nghiệp vụ.

### Configuration property khác bean dependency như thế nào?

Trong ví dụ trên, `InventoryService` inject `InventoryProperties`, nhưng đây là bean thuộc cùng module `inventory`. Nó không tạo ra dependency giữa hai application module. Các property được bind từ `Environment` hoặc file cấu hình của ứng dụng.

Spring Modulith xem configuration properties là một phần hợp đồng cấu hình được module công bố và có thể đưa vào Application Module Canvas. Tuy nhiên, property key không phải một loại `DependencyType` riêng tương đương `USES_COMPONENT` hay `EVENT_LISTENER`. Một module khác đọc chuỗi như `acme.shop.inventory.restock-threshold` bằng `Environment.getProperty()` có thể tạo ra coupling ngầm mà quan hệ bean hoặc event listener không thể hiện rõ trong dependency graph.

Vì vậy:

- Mỗi module nên sở hữu prefix cấu hình của mình, chẳng hạn `acme.shop.order`, `acme.shop.inventory` và `acme.shop.shipping`.
- Không dùng property nội bộ của module khác như một API để điều khiển nghiệp vụ của mình.
- Nếu module khác cần dữ liệu hoặc hành vi từ `inventory`, hãy công bố bean API hoặc event phù hợp.
- Chỉ dùng một property chung khi đó thực sự là cấu hình cấp ứng dụng có chủ sở hữu và ngữ nghĩa thống nhất.

## 6. Ghi nhận configuration properties trong Application Module Canvas

Spring Modulith có thể tạo Application Module Canvas để mô tả module, Spring bean, event được phát, event được lắng nghe và configuration properties. Để trích xuất metadata của các property, cần thêm Spring Boot configuration processor vào build.

Ví dụ với Gradle:

```kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
```

Với Maven, khai báo `spring-boot-configuration-processor` như một annotation processor theo cấu hình build của dự án. Processor tạo metadata cho các lớp `@ConfigurationProperties`; Documenter sử dụng metadata đó để liệt kê property key, kiểu dữ liệu và mô tả trong Canvas.

Có thể tạo tài liệu module như sau:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void writesModuleDocumentation() {
        var modules = ApplicationModules.of(ShopApplication.class);

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
```

Component diagram cho thấy module nào phụ thuộc module nào. Canvas bổ sung thông tin cấu hình do module công bố, ví dụ:

| Module | Property | Ý nghĩa |
| --- | --- | --- |
| `inventory` | `acme.shop.inventory.restock-threshold` | Ngưỡng số lượng để quyết định cần bổ sung hàng |
| `shipping` | `acme.shop.shipping.default-carrier` | Nhà vận chuyển mặc định |
| `order` | `acme.shop.order.maximum-items` | Số mặt hàng tối đa trong một đơn |

Những dòng trên là ví dụ minh họa cách đặt prefix. Canvas giúp người phát triển và vận hành thấy module nào sở hữu cấu hình nào, đồng thời phát hiện những key dùng chung không rõ chủ sở hữu.

## 7. Kiểm tra dependency và boundary

Sau khi xác định bean, event và configuration contract, hãy kiểm tra dependency graph bằng `ApplicationModules.verify()`:

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

Việc kiểm tra bao gồm các quy tắc như:

- Không có chu trình dependency giữa các application module.
- Module chỉ truy cập API package hoặc Named Interface được công bố của module khác.
- Nếu khai báo `allowedDependencies`, dependency thực tế phải nằm trong danh sách cho phép.

Các dependency do component wiring và event listener tạo ra có thể được phân biệt trong mô hình. Trong các tính năng runtime hoặc actuator tương ứng, module arrangement cũng có thể hiển thị target module và loại dependency, ví dụ `USES_COMPONENT` hoặc `EVENT_LISTENER`.

Configuration property cần được kiểm tra theo cách bổ sung: xem prefix có đúng owner không, có bị module khác đọc trực tiếp không, metadata có được tạo và Canvas có liệt kê đúng không. `verify()` không thay thế việc rà soát các chuỗi property được truy cập qua `Environment` hoặc cấu hình YAML; những tham chiếu kiểu này có thể không tạo ra type dependency rõ ràng.

## 8. Một luồng nghiệp vụ kết hợp cả ba hình thức

Giả sử khách hàng đặt một đơn hàng:

1. `order` gọi bean `InventoryManagement` của `inventory` để kiểm tra số lượng. Đây là bean dependency `order -> inventory`.
2. `inventory` sử dụng `InventoryProperties` của chính nó để áp dụng ngưỡng tồn kho. Property prefix thuộc module `inventory`.
3. Sau khi đơn hàng được tạo thành công, `order` phát `OrderPlaced`.
4. `shipping` lắng nghe `OrderPlaced` qua `@ApplicationModuleListener`. Đây là event listener dependency `shipping -> order`.
5. `shipping` sử dụng `ShippingProperties` do chính module sở hữu để chọn nhà vận chuyển mặc định.

Có thể biểu diễn các quan hệ module như sau:

```text
order -------- USES_COMPONENT --------> inventory
shipping ----- EVENT_LISTENER --------> order
```

Sơ đồ nhấn mạnh hai dependency edge giữa các module. Các hợp đồng cấu hình nằm bên trong module sở hữu chúng: `inventory` quản lý prefix `acme.shop.inventory`, còn `shipping` quản lý prefix `acme.shop.shipping`. Property prefix không phải một module hoặc một dependency edge độc lập; nó là một phần hợp đồng cấu hình của module.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Inject một bean bất kỳ từ module khác cũng giống lắng nghe event. | Bean dependency là `USES_COMPONENT`; event listener là `EVENT_LISTENER` với semantics bootstrap khác nhau. |
| Module phát event phụ thuộc vào mọi listener. | Quan hệ được ghi nhận từ module listener tới module công bố event; module phát không cần biết các consumer. |
| Mọi `@ConfigurationProperties` đều là dependency giữa hai module. | Đây là hợp đồng cấu hình được module sở hữu và có thể được tài liệu hóa; không phải một loại `DependencyType` riêng. |
| Đặt property trong `application.yml` là đủ để Spring Modulith hiểu ownership. | Cần lớp `@ConfigurationProperties`, prefix rõ và metadata processor để Canvas trích xuất cấu hình. |
| Module khác có thể đọc property prefix của module này vì mọi module dùng chung `Environment`. | Khả năng đọc được không đồng nghĩa với dependency được thiết kế; việc đọc key của module khác tạo coupling ngầm. |
| `allowedDependencies` tự động phát hiện mọi chuỗi property được chia sẻ. | Allowlist kiểm tra các dependency mà mô hình nhận diện; cần rà soát thêm các property key truy cập qua chuỗi. |
| Cứ chuyển mọi cấu hình vào một `CommonProperties` là giảm coupling. | Cấu hình nên được nhóm theo module sở hữu và chỉ dùng prefix chung cho chính sách cấp ứng dụng thực sự thống nhất. |

## 10. Ghi nhớ

Dependency tới bean, event listener và configuration property thể hiện ba cách module kết nối với hợp đồng của module khác. Bean dependency (`USES_COMPONENT`) là lời gọi trực tiếp đến component; event listener (`EVENT_LISTENER`) là phản ứng với sự kiện được công bố; configuration properties là hợp đồng cấu hình mà module sở hữu và có thể công bố cho môi trường vận hành.

Hãy công bố bean và event qua API hoặc Named Interface phù hợp, khai báo `allowedDependencies` để giới hạn module được phép sử dụng và chạy `ApplicationModules.verify()` để kiểm tra cấu trúc. Với configuration properties, đặt prefix theo module, bổ sung `spring-boot-configuration-processor` để tạo metadata và dùng Application Module Canvas để tài liệu hóa. Tránh đọc property key nội bộ của module khác như một cách giao tiếp ngầm.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith Reference — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith API — `DependencyType`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
