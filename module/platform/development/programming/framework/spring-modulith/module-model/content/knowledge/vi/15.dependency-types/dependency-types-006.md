# Nhóm nhiều loại dependency khi phân tích

Một module có thể phụ thuộc vào module khác theo nhiều cách. Có lúc nó inject một Spring bean để gọi nghiệp vụ; có lúc nó lắng nghe application event; có lúc nó tham chiếu entity do module khác sở hữu. Nếu chỉ nhìn một đồ thị gồm các mũi tên giữa module, ta biết module nào liên quan đến module nào nhưng chưa hiểu bản chất của từng quan hệ.

Spring Modulith gắn loại cho dependency bằng `DependencyType`. Khi phân tích module model, ta có thể lọc nhiều loại dependency cùng lúc, lấy dependency trực tiếp hoặc bắc cầu, rồi nhóm các kết quả theo loại để tìm ra hình thái coupling của ứng dụng. Cách nhìn này giúp phân biệt lời gọi component, giao tiếp qua event và việc chia sẻ entity, thay vì xem tất cả quan hệ như một dạng phụ thuộc giống nhau.

## 1. Vì sao cần nhóm dependency theo loại?

Giả sử ứng dụng bán hàng có các module `order`, `inventory`, `customer`, `shipping` và `reporting`. Một số quan hệ có thể là:

```text
order ------ USES_COMPONENT ------> inventory
order ------ USES_COMPONENT ------> customer
shipping --- EVENT_LISTENER ------> order
reporting -- ENTITY --------------> order
```

Mỗi quan hệ phản ánh một cách tích hợp khác nhau:

- `order` gọi API tồn kho và khách hàng qua Spring bean.
- `shipping` nhận event `OrderPlaced` do `order` công bố.
- `reporting` tham chiếu entity thuộc module `order` để lập báo cáo.

Nếu chỉ đếm số mũi tên, ta có thể kết luận cả ba cách đều là “một dependency”. Nhưng ý nghĩa kiến trúc rất khác nhau. Bean dependency thường tạo ràng buộc bootstrap và lời gọi trực tiếp. Event listener tạo quan hệ từ consumer đến event owner nhưng không yêu cầu event owner được bootstrap chỉ để chạy consumer. Entity dependency cho thấy mô hình dữ liệu của một module đang được module khác tham chiếu.

Nhóm dependency theo loại giúp trả lời các câu hỏi cụ thể:

- Module nào có nhiều lời gọi component trực tiếp?
- Module nào đang phát event cho nhiều consumer?
- Module nào đang để lộ entity ra ngoài boundary?
- Các dependency trực tiếp có khác nhiều so với dependency bắc cầu không?
- Một module đang phụ thuộc vào nhiều module vì các lý do khác nhau hay chỉ vì một hợp đồng tích hợp chính?

## 2. Các giá trị của `DependencyType`

Spring Modulith 2.2 cung cấp enum `org.springframework.modulith.core.DependencyType` với bốn giá trị:

| Loại | Ý nghĩa | Dấu hiệu thường gặp |
| --- | --- | --- |
| `USES_COMPONENT` | Module nguồn phụ thuộc vào module đích qua component dependency; module đích cần được bootstrap để chạy module nguồn | Inject hoặc sử dụng Spring bean thuộc module khác |
| `EVENT_LISTENER` | Module nguồn phụ thuộc vào module đích bằng cách khai báo listener cho event do module đích công bố | `@EventListener`, `@TransactionalEventListener`, `@ApplicationModuleListener` hoặc `ApplicationListener` |
| `ENTITY` | Module nguồn tham chiếu entity thuộc module đích | Dùng JPA entity hoặc kiểu entity được module khác sở hữu |
| `DEFAULT` | Giá trị phân loại mặc định; API không gán cho nó một semantics giao tiếp chuyên biệt như ba loại còn lại | Cần đọc source type, target type và code tạo ra quan hệ |

`DEFAULT` là một giá trị hợp lệ của enum, không phải tên một kiểu giao tiếp nghiệp vụ. API mô tả rõ ý nghĩa của `USES_COMPONENT`, `EVENT_LISTENER` và `ENTITY`, còn `DEFAULT` không có mô tả chuyên biệt tương tự. Khi gặp nó, hãy kiểm tra `sourceType`, `targetType` và code tạo ra quan hệ để hiểu dependency thực tế. Không nên tự suy ra rằng `DEFAULT` đồng nghĩa với bean injection hoặc event listener.

Các loại này mô tả dependency được phát hiện trong module model. Chúng không phải danh sách đầy đủ mọi hình thức giao tiếp có thể có trong hệ thống. Ví dụ, một chuỗi cấu hình được đọc qua `Environment.getProperty()` hoặc một HTTP call được dựng thủ công có thể không tạo ra dependency edge cùng loại như một Spring bean reference.

## 3. Phân biệt bản chất từng loại dependency

### `USES_COMPONENT`: gọi component của module khác

Giả sử `order` cần kiểm tra tồn kho bằng API do `inventory` cung cấp:

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean hasAvailableStock(Sku sku, int quantity);
}
```

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }
}
```

Quan hệ `order -> inventory` được phân loại là `USES_COMPONENT`. Module `order` cần component của `inventory` để thực hiện luồng nghiệp vụ. Khi phân tích loại này, hãy xem API có thực sự cần trả lời đồng bộ hay không, và liệu consumer có đang phụ thuộc vào quá nhiều component của module đích.

### `EVENT_LISTENER`: phản ứng với event do module khác công bố

Module `order` phát `OrderPlaced`, còn `shipping` đăng ký listener:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderEvents {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Chuẩn bị shipment từ orderId.
    }
}
```

Quan hệ được ghi nhận theo hướng `shipping -> order` và có loại `EVENT_LISTENER`. Consumer phụ thuộc vào event contract của `order`; module phát event không cần biết danh sách consumer. Khi phân tích nhóm này, hãy xem event nào có nhiều consumer, payload nào đang trở thành hợp đồng quan trọng và listener nào cần xử lý sau commit hoặc bất đồng bộ.

### `ENTITY`: tham chiếu entity của module khác

Giả sử `reporting` dùng entity `OrderEntity` do module `order` sở hữu:

```java
package com.acme.shop.reporting.internal;

import com.acme.shop.order.persistence.OrderEntity;
import org.springframework.stereotype.Repository;

@Repository
class OrderReportRepository {

    // Truy vấn OrderEntity để lập báo cáo.
}
```

Quan hệ tham chiếu entity có thể được phân loại là `ENTITY`. Nó cho thấy module tiêu thụ biết mô hình lưu trữ hoặc entity type của module sở hữu dữ liệu. Đây thường là điểm cần xem xét kỹ: consumer có thật sự cần entity, hay chỉ cần một read model, API truy vấn hoặc event chứa dữ liệu đã công bố?

`ENTITY` không tự kết luận rằng thiết kế sai trong mọi trường hợp. Nó là tín hiệu để đánh giá ownership, coupling đến persistence model và khả năng thay đổi schema/domain model của module nguồn.

### `DEFAULT`: dependency cần đọc thêm ngữ cảnh

`DEFAULT` là loại mặc định trong enum. Tài liệu API mô tả chi tiết các loại chuyên biệt như component, event listener và entity; với `DEFAULT`, cần xem source/target type và đoạn code cụ thể để xác định bản chất quan hệ.

Khi thống kê, đừng gộp `DEFAULT` vào `USES_COMPONENT` chỉ vì cả hai đều là dependency giữa module. Hãy giữ nó thành một nhóm riêng để điều tra. Nếu nhóm `DEFAULT` tăng sau một đợt refactor, đó là lý do để xem lại các type được tham chiếu và cách framework phân loại chúng.

## 4. Lấy dependency trực tiếp của một module

Tạo module model và tìm module cần phân tích:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class DependencyAnalysis {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule order = modules.getModuleByName("order")
                .orElseThrow();

        var dependencies = order.getDirectDependencies(modules);
    }
}
```

`getDirectDependencies(modules)` trả về các dependency trực tiếp của module `order`. Nếu truyền các giá trị `DependencyType` vào varargs, kết quả chỉ gồm những loại được yêu cầu:

```java
var operationalDependencies = order.getDirectDependencies(
        modules,
        DependencyType.USES_COMPONENT,
        DependencyType.EVENT_LISTENER
);
```

Trong ví dụ, nhóm phân tích chỉ lấy component dependency và event listener dependency. Có thể thêm `ENTITY` hoặc `DEFAULT` nếu cần xem toàn bộ kiểu quan hệ khác.

Nếu không truyền loại nào, API trả về các dependency trực tiếp mà module model ghi nhận. Đây là điểm bắt đầu tốt để xem module đang phụ thuộc trực tiếp vào những module nào.

## 5. Nhóm dependency bằng `ApplicationModuleDependencies.stream()`

`ApplicationModuleDependencies` là tập dependency đã được materialize của một module. Nó cung cấp `stream()` để duyệt từng dependency. Có thể dùng `Collectors.groupingBy()` để nhóm theo `getDependencyType()`. Tiếp tục trong cùng ngữ cảnh `inspect()` ở ví dụ trên, biến `dependencies` là kết quả từ `order.getDirectDependencies(modules)`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.modulith.core.ApplicationModuleDependency;
import org.springframework.modulith.core.ApplicationModuleDependencies;
import org.springframework.modulith.core.DependencyType;

Map<DependencyType, List<ApplicationModuleDependency>> grouped =
        dependencies.stream()
                .collect(Collectors.groupingBy(
                        ApplicationModuleDependency::getDependencyType
                ));
```

Kết quả là một map: mỗi key là một `DependencyType`, mỗi value là danh sách dependency cùng loại. Sau khi tạo `grouped`, có thể in các nhóm để xem chi tiết:

```java
grouped.forEach((type, entries) -> {
    System.out.println("== " + type + " ==");

    entries.forEach(dependency -> System.out.printf(
            "%s -> %s [target module: %s]%n",
            dependency.getSourceType().getName(),
            dependency.getTargetType().getName(),
            dependency.getTargetModule().getBasePackage().getName()
    ));
});
```

Mỗi `ApplicationModuleDependency` cung cấp các thông tin quan trọng:

- `getDependencyType()` — loại dependency.
- `getSourceType()` — Java type tạo ra dependency ở phía module nguồn.
- `getTargetType()` — Java type được tham chiếu ở phía module đích.
- `getTargetModule()` — application module đích.

Nhờ các thông tin này, ta không chỉ biết module `order` phụ thuộc vào `inventory`, mà còn biết lớp nào trong `order` tạo ra quan hệ và type nào của `inventory` đang được sử dụng.

Lưu ý: số phần tử trong một nhóm là số dependency record mà module model cung cấp, không nhất thiết bằng số cặp module nguồn/đích duy nhất. Nhiều type ở cùng module nguồn có thể tham chiếu nhiều type ở cùng module đích.

## 6. Lọc một loại hoặc nhiều loại dependency

Nếu chỉ cần một loại, có thể dùng `withType()` trên `ApplicationModuleDependencies`:

```java
var eventDependencies = dependencies.withType(
        DependencyType.EVENT_LISTENER
);

var entityDependencies = dependencies.withType(
        DependencyType.ENTITY
);
```

`withType()` trả về một `ApplicationModuleDependencies` mới chỉ chứa loại được yêu cầu. Nó không thay đổi tập dependency ban đầu.

Nếu muốn lấy nhiều loại cùng lúc, truyền nhiều enum value vào API của `ApplicationModule`:

```java
var collaborationDependencies = order.getDirectDependencies(
        modules,
        DependencyType.USES_COMPONENT,
        DependencyType.EVENT_LISTENER
);
```

Đây là cách phù hợp khi câu hỏi phân tích tập trung vào hai kiểu cộng tác chính: gọi component và lắng nghe event.

`DependencyType.allBut(…)` hữu ích khi muốn tạo tập loại được giữ lại bằng cách loại một số loại khỏi enum:

```java
var typesToInspect = DependencyType.allBut(
        DependencyType.ENTITY
).collect(Collectors.toSet());

var dependenciesWithoutEntity = dependencies.stream()
        .filter(dependency -> typesToInspect.contains(
                dependency.getDependencyType()
        ))
        .toList();
```

Trong ví dụ, ta lấy mọi dependency record trừ loại `ENTITY`. Cách này hữu ích khi cần tạo báo cáo tùy biến hoặc khi danh sách loại cần loại trừ dễ diễn đạt hơn danh sách cần giữ lại.

## 7. Phân biệt dependency trực tiếp và bắc cầu

Dependency trực tiếp cho biết module đang tham chiếu module nào trong code của chính nó. Dependency bắc cầu cho biết những module có thể được tiếp cận qua các module trung gian.

Giả sử:

```text
order ------> inventory ------> catalog
  |
  +---------> customer
```

`order` có dependency trực tiếp đến `inventory` và `customer`. `catalog` là dependency bắc cầu thông qua `inventory`, nếu `order` không tham chiếu trực tiếp type của `catalog`.

Lấy dependency trực tiếp:

```java
var direct = order.getDirectDependencies(modules);
```

Lấy tất cả dependency, bao gồm bắc cầu:

```java
var all = order.getAllDependencies(modules);
```

Hoặc dùng `getDependencies()` khi muốn chỉ định độ sâu và loại dependency cùng lúc:

```java
import org.springframework.modulith.core.DependencyDepth;

var immediateComponentDependencies = order.getDependencies(
        modules,
        DependencyDepth.IMMEDIATE,
        DependencyType.USES_COMPONENT
);

var allEventAndComponentDependencies = order.getDependencies(
        modules,
        DependencyDepth.ALL,
        DependencyType.USES_COMPONENT,
        DependencyType.EVENT_LISTENER
);
```

`DependencyDepth.IMMEDIATE` giới hạn ở quan hệ trực tiếp; `DependencyDepth.ALL` mở rộng đến các quan hệ bắc cầu; `DependencyDepth.NONE` biểu thị không lấy dependency ở độ sâu nào. Khi phân tích coupling của một module, hãy bắt đầu bằng dependency trực tiếp. Dùng độ sâu `ALL` khi cần xem phạm vi ảnh hưởng gián tiếp hoặc các module có thể xuất hiện trong bootstrap.

Đừng coi dependency bắc cầu là quyền sử dụng API trực tiếp. Nếu `order` cần gọi API của `catalog`, dependency trực tiếp đó phải được thể hiện trong code và allowlist tương ứng; việc `inventory` phụ thuộc `catalog` không tự cấp quyền cho `order`.

## 8. Tổng hợp dependency theo loại trên toàn ứng dụng

Có thể duyệt tất cả module và gom dependency trực tiếp thành các nhóm toàn cục:

```java
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.modulith.core.ApplicationModuleDependency;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

Map<DependencyType, Long> countsByType = modules.stream()
        .flatMap(module -> module.getDirectDependencies(modules).stream())
        .collect(Collectors.groupingBy(
                ApplicationModuleDependency::getDependencyType,
                Collectors.counting()
        ));

countsByType.forEach((type, count) ->
        System.out.printf("%s: %d dependency records%n", type, count));
```

Báo cáo này cho thấy số dependency record của từng loại trong toàn bộ module model. Nếu muốn so sánh riêng từng module, hãy nhóm theo module nguồn trước, sau đó nhóm tiếp theo `DependencyType`. Với báo cáo quản trị, nên giữ cả tên module nguồn, module đích, source type và target type để người đọc có thể lần về code.

Số lượng chỉ là tín hiệu ban đầu. Một module có ít dependency nhưng phụ thuộc vào một entity trung tâm có thể rủi ro hơn module có nhiều event listener độc lập. Hãy đọc cả loại quan hệ, hướng dependency, ownership và mức độ ổn định của hợp đồng.

## 9. Đọc kết quả nhóm để tìm vấn đề kiến trúc

Sau khi nhóm, hãy diễn giải theo mục tiêu của từng loại:

| Nhóm nổi bật | Câu hỏi phân tích | Hướng xem xét |
| --- | --- | --- |
| Nhiều `USES_COMPONENT` | Module có gọi quá nhiều component của module khác không? Các lời gọi có cần đồng bộ không? | Thu hẹp API, gom thao tác qua facade nghiệp vụ hoặc chuyển phản ứng phụ sang event nếu phù hợp |
| Nhiều `EVENT_LISTENER` | Module đang tiêu thụ những sự kiện nào? Có event nào được nhiều consumer dùng chung? | Rà soát event contract, ý nghĩa nghiệp vụ, transaction phase và idempotency của listener |
| Nhiều `ENTITY` | Module có đang truy cập entity hoặc persistence model của module khác không? | Đưa truy vấn qua API/read model hoặc công bố dữ liệu cần thiết bằng hợp đồng phù hợp |
| Nhiều `DEFAULT` | Những dependency này được tạo ra từ type nào và code nào? | Kiểm tra từng source/target type để hiểu bản chất quan hệ trước khi đưa ra kết luận |
| Dependency bắc cầu tăng mạnh | Một module có đang phụ thuộc vào chuỗi module trung gian dài không? | Kiểm tra dependency trực tiếp, tránh dùng API gián tiếp và giảm chuỗi coupling |

Không có ngưỡng số lượng chung cho mọi ứng dụng. Một dependency có thể hợp lý nếu nó thể hiện hợp đồng ổn định và đúng ownership. Mục tiêu là phát hiện quan hệ khó giải thích, phụ thuộc vào implementation hoặc vượt khỏi ranh giới module đã thống nhất.

## 10. Kết hợp nhóm dependency với `allowedDependencies` và verification

`DependencyType` mô tả loại quan hệ thực tế; `allowedDependencies` mô tả module hoặc Named Interface mà module được phép sử dụng. Hai khái niệm này bổ sung cho nhau.

Ví dụ, `order` chỉ được phép phụ thuộc vào `inventory` và `customer`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "customer" }
)
package com.acme.shop.order;
```

Sau khi phân nhóm dependency, nhóm có thể xem loại quan hệ nào tạo ra mỗi dependency được phép. Nếu `order` có `ENTITY` đến `customer`, dù module nằm trong allowlist, vẫn cần xem xét liệu nó có đang chia sẻ entity ngoài ý muốn hay không.

Chạy kiểm tra kiến trúc:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các quy tắc kiến trúc như dependency cycle, truy cập package nội bộ và dependency ngoài allowlist. Nó không tự quyết định một nhóm `ENTITY` hoặc `USES_COMPONENT` có phải thiết kế tốt về mặt nghiệp vụ hay không. Phần diễn giải kết quả và quyết định refactor vẫn thuộc về nhóm phát triển.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Mọi dependency giữa hai module đều giống nhau. | `DependencyType` phân biệt component, event listener, entity và loại mặc định. |
| `EVENT_LISTENER` có nghĩa module phát event phụ thuộc consumer. | Hướng dependency đi từ module listener đến module sở hữu event. |
| `ENTITY` chỉ là một dạng `USES_COMPONENT`. | Nó chỉ ra module đang tham chiếu entity của module khác, thường liên quan đến coupling dữ liệu. |
| `DEFAULT` là một kiểu giao tiếp cụ thể như REST hoặc messaging. | Đây là loại mặc định; cần đọc source/target type để hiểu quan hệ thực tế. |
| `withType()` nhận nhiều loại cùng lúc. | `withType()` lọc một loại; các API của `ApplicationModule` nhận nhiều `DependencyType` qua varargs. |
| `getAllDependencies()` chỉ trả dependency trực tiếp. | API này bao gồm cả dependency bắc cầu; dùng `getDirectDependencies()` khi chỉ cần cạnh trực tiếp. |
| Đếm dependency record là đếm số module phụ thuộc duy nhất. | Một cặp module có thể có nhiều dependency record do nhiều type tham chiếu. |
| Dependency có trong allowlist nghĩa là thiết kế đã tốt. | Allowlist chỉ cho phép quan hệ; nó không đánh giá ownership hoặc mức coupling có hợp lý không. |

## 12. Ghi nhớ

Spring Modulith phân loại quan hệ giữa application module bằng `DependencyType`: `USES_COMPONENT`, `EVENT_LISTENER`, `ENTITY` và `DEFAULT`. Các loại này giúp nhận ra module đang gọi component, lắng nghe event, tham chiếu entity hay có một dependency cần được xem xét thêm.

Để phân tích, lấy module bằng `ApplicationModules.getModuleByName()`, truy vấn dependency trực tiếp hoặc bắc cầu qua `getDirectDependencies()`, `getAllDependencies()` hay `getDependencies()`, rồi nhóm các record bằng `ApplicationModuleDependencies.stream()` và `Collectors.groupingBy(ApplicationModuleDependency::getDependencyType)`. Dùng `withType()` khi cần một nhóm đơn lẻ, và truyền nhiều enum value vào varargs khi muốn lọc nhiều loại cùng lúc.

Khi đọc kết quả, luôn xem source type, target type, target module và hướng dependency. Kết hợp số lượng với loại quan hệ, độ sâu và ownership để nhận ra coupling đáng chú ý. Cuối cùng, dùng `allowedDependencies` và `ApplicationModules.verify()` để giữ dependency trong giới hạn kiến trúc, nhưng vẫn cần đánh giá thiết kế nghiệp vụ bằng ngữ cảnh thực tế.

## Tài liệu tham khảo

- [Spring Modulith API — `DependencyType`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModuleDependencies`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html)
- [Spring Modulith API — `ApplicationModuleDependency`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html)
- [Spring Modulith API — `DependencyDepth`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyDepth.html)
