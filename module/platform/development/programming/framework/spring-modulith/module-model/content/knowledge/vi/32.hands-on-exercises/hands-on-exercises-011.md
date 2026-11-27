# Thêm event listener và quan sát dependency graph

Trong modular monolith, một module có thể thông báo rằng nghiệp vụ của nó vừa xảy ra bằng application event. Module khác đăng ký listener để phản ứng với sự kiện đó. Cách tích hợp này giúp module phát sự kiện không phải biết trước có những module nào đang quan tâm.

Trong bài thực hành này, module **orders** phát sự kiện **OrderPlaced**; module **inventory** lắng nghe và giữ hàng. Sau khi triển khai, bạn sẽ dùng Spring Modulith để quan sát dependency graph và phân biệt hai hướng:

- **Dependency ở mã nguồn:** **inventory** phụ thuộc vào hợp đồng sự kiện được công bố bởi **orders**.
- **Luồng sự kiện lúc chạy:** **orders** phát **OrderPlaced**, sau đó listener trong **inventory** nhận sự kiện.

Hai hướng này khác nhau. Hiểu được sự khác biệt là mục tiêu quan trọng của bài thực hành.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

1. Công bố event type trong Named Interface của module phát sự kiện.
2. Phát event bằng **ApplicationEventPublisher** bên trong transaction nghiệp vụ.
3. Đăng ký listener bằng **@ApplicationModuleListener** trong module nhận sự kiện.
4. Khai báo **allowedDependencies** đúng với Named Interface chứa event.
5. Kiểm tra dependency có loại **DependencyType.EVENT_LISTENER**.
6. Quan sát dependency graph và giải thích vì sao hướng dependency khác hướng truyền event.
7. Chẩn đoán các lỗi thường gặp khi event type chưa được công bố hoặc dependency chưa được cho phép.

## Chuẩn bị dependency

Ví dụ sử dụng **ApplicationModuleListener** từ Spring Modulith Events API. Nếu dự án chưa có artifact này, thêm dependency trong Maven; version có thể được quản lý bởi Spring Modulith BOM:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-events-api</artifactId>
</dependency>
~~~

Các API **ApplicationModules**, **ApplicationModule** và **DependencyType** thuộc core module của Spring Modulith. Bài thực hành giả định dự án đã có core module và Spring transaction support.

## 2. Kịch bản và cấu trúc ban đầu

Giả sử ứng dụng có hai Application Module nằm dưới package root **com.acme.shop**:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── events
│   └── internal
└── inventory
    ├── package-info.java
    └── internal
        ├── InventoryService.java
        └── OrderPlacedListener.java
~~~

Module **orders** chịu trách nhiệm tạo và quản lý đơn hàng. Module **inventory** quản lý lượng hàng có thể giữ cho đơn hàng.

Trong quá trình phát triển, giả sử **OrderManagement** gọi trực tiếp bean **InventoryService**:

~~~java
@Service
public class OrderManagement {

    private final InventoryService inventory;

    OrderManagement(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(UUID orderId) {
        // Lưu đơn hàng.
        inventory.reserve(orderId);
    }
}
~~~

Đây là một component dependency từ **orders** sang **inventory**. Module orders phải biết bean của inventory để hoàn thành use case. Nếu sau này có thêm module gửi email, tính điểm thưởng hoặc cập nhật phân tích bán hàng, **OrderManagement** có thể tiếp tục tích lũy các dependency mới.

Ta sẽ thay lời gọi trực tiếp đó bằng một event có ý nghĩa nghiệp vụ.

## 3. Bước 1 — Công bố event contract trong module orders

Tạo package dành cho event contract:

~~~text
src/main/java/com/acme/shop/orders/events
~~~

Đặt **package-info.java** tại package này:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Named Interface **events** công bố các event type mà module khác được phép tham chiếu. Tạo event **OrderPlaced.java**:

~~~java
package com.acme.shop.orders.events;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {
}
~~~

Event chỉ mang dữ liệu cần thiết để consumer xử lý. Trong ví dụ này, **orderId** là đủ để inventory tìm dữ liệu thuộc quyền sở hữu của nó. Tránh đưa JPA entity hoặc repository của orders vào event vì điều đó sẽ làm consumer phụ thuộc vào chi tiết triển khai của module phát sự kiện.

**Điểm kiểm tra:** **OrderPlaced** nằm trong **com.acme.shop.orders.events**, và package đó được công bố bằng **@NamedInterface("events")**.

## 4. Bước 2 — Khai báo dependency được phép ở module inventory

Module inventory là consumer vì nó sẽ import event type từ orders. Đặt allowlist ở package gốc của inventory, trong **inventory/package-info.java**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.acme.shop.inventory;
~~~

Biểu thức **orders :: events** gồm:

- **orders**: logical identifier của module phát sự kiện.
- **events**: tên Named Interface công bố event type.

Khai báo này cho phép inventory tham chiếu event contract. Nó không cho phép inventory truy cập repository hoặc package **orders.internal**.

Nếu module inventory đã có **allowedDependencies**, hãy thêm **orders :: events** vào danh sách hiện có thay vì thay thế các dependency hợp lệ khác.

## 5. Bước 3 — Phát event từ module orders

Thay dependency trực tiếp tới **InventoryService** bằng Spring **ApplicationEventPublisher**.

Ví dụ **OrderManagement.java**:

~~~java
package com.acme.shop.orders.internal;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.shop.orders.events.OrderPlaced;

@Service
public class OrderManagement {

    private final ApplicationEventPublisher events;

    public OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void placeOrder(UUID orderId) {
        // 1. Tạo và lưu đơn hàng.
        // 2. Hoàn tất các thay đổi nghiệp vụ của orders.
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

**OrderManagement** không import **InventoryService** và không cần biết có bao nhiêu listener đang quan tâm **OrderPlaced**. Nó chỉ công bố sự kiện sau khi thực hiện thay đổi nghiệp vụ của mình.

Đặt việc phát event bên trong transaction giúp listener dạng transactional chỉ xử lý sau khi transaction phát sự kiện commit thành công. Nếu transaction rollback, listener **@TransactionalEventListener** không xử lý event theo phase mặc định **AFTER_COMMIT**.

## 6. Bước 4 — Thêm event listener trong module inventory

Tạo listener ở package nội bộ của inventory, ví dụ **inventory/internal/OrderPlacedListener.java**:

~~~java
package com.acme.shop.inventory.internal;

import org.springframework.stereotype.Component;
import org.springframework.modulith.events.ApplicationModuleListener;

import com.acme.shop.orders.events.OrderPlaced;

@Component
public class OrderPlacedListener {

    private final InventoryService inventory;

    public OrderPlacedListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        inventory.reserve(event.orderId());
    }
}
~~~

Listener sử dụng **InventoryService** thuộc cùng module inventory. Dependency liên module duy nhất trong ví dụ là event type **OrderPlaced** thuộc Named Interface **orders :: events**.

**@ApplicationModuleListener** của Spring Modulith là shortcut cho một transactional event listener chạy bất đồng bộ và trong transaction riêng với propagation **REQUIRES_NEW**. Listener được gọi sau khi transaction phát event commit thành công. Nếu ứng dụng chưa bật hỗ trợ async, hãy bật bằng **@EnableAsync** tại cấu hình ứng dụng:

~~~java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {
}
~~~

Nếu ứng dụng đã cấu hình async execution, không cần khai báo **@EnableAsync** lần nữa.

**Lưu ý:** vì listener chạy bất đồng bộ, phương thức **placeOrder()** có thể kết thúc trước khi **inventory.reserve()** hoàn tất. Đừng viết test runtime giả định listener đã chạy ngay tại thời điểm publisher trả về.

## 7. Bước 5 — Kiểm tra dependency graph bằng ApplicationModules

Tạo architecture test trong test source set:

~~~java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.DependencyType;

class ModuleDependencyGraphTests {

    @Test
    void inventoryDependsOnOrdersThroughAnEventListener() {
        ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class).verify();

        ApplicationModule inventory = modules.getModuleByName("inventory")
            .orElseThrow();

        var eventDependencies = inventory.getDirectDependencies(
            modules, DependencyType.EVENT_LISTENER);

        assertThat(eventDependencies.containsModuleNamed("orders")).isTrue();

        var componentDependencies = inventory.getDirectDependencies(
            modules, DependencyType.USES_COMPONENT);

        assertThat(componentDependencies.containsModuleNamed("orders")).isFalse();
    }
}
~~~

Test thực hiện các việc:

1. **ApplicationModules.of(ShopApplication.class)** tạo application model từ class ứng dụng.
2. **verify()** kiểm tra dependency graph, API exposure và **allowedDependencies**.
3. **getModuleByName("inventory")** lấy module consumer.
4. **getDirectDependencies(modules, DependencyType.EVENT_LISTENER)** chỉ lấy các dependency trực tiếp được nhận diện là event listener.
5. **containsModuleNamed("orders")** xác nhận inventory có dependency kiểu event listener tới orders.
6. Kiểm tra **USES_COMPONENT** để xác nhận ví dụ không còn dependency component trực tiếp từ inventory tới orders.

Có thể xác nhận event type mà inventory lắng nghe:

~~~java
import com.acme.shop.orders.events.OrderPlaced;

assertThat(inventory.getEventsListenedTo(modules))
    .extracting(eventType -> eventType.getName())
    .contains(OrderPlaced.class.getName());
~~~

**getEventsListenedTo(modules)** trả về các event type mà module hiện tại khai báo listener. Đây là cách kiểm tra event contract đã được nhận diện trong application model, độc lập với việc listener đã chạy lúc runtime hay chưa.

## 8. Bước 6 — In chi tiết cạnh dependency

**ApplicationModuleDependencies.stream()** cung cấp các **ApplicationModuleDependency** để quan sát source type, target type và dependency type.

Thêm đoạn sau vào test hoặc một phương thức chẩn đoán:

~~~java
eventDependencies.stream().forEach(dependency ->
    System.out.printf(
        "%s --[%s]--> %s | source=%s | target=%s%n",
        inventory.getIdentifier(),
        dependency.getDependencyType(),
        dependency.getTargetModule().getIdentifier(),
        dependency.getSourceType().getName(),
        dependency.getTargetType().getName()
    )
);
~~~

Kết quả minh họa:

~~~text
inventory --[EVENT_LISTENER]--> orders
  source=com.acme.shop.inventory.internal.OrderPlacedListener
  target=com.acme.shop.orders.events.OrderPlaced
~~~

Kết quả cho thấy:

- **Source type** là type trong module inventory khai báo listener.
- **Target type** là event type được công bố bởi orders.
- **Target module** là module sở hữu event contract.
- **Dependency type** là **EVENT_LISTENER**.

Mũi tên trong dependency graph đi từ module consumer tới module sở hữu type mà consumer tham chiếu. Vì vậy, cạnh là **inventory -> orders**.

## 9. Phân biệt dependency graph với luồng event lúc runtime

Đây là điểm cần quan sát kỹ nhất trong bài thực hành.

**Dependency graph ở mã nguồn:**

~~~text
inventory
    |
    | EVENT_LISTENER
    v
orders :: events
~~~

**Luồng event lúc runtime:**

~~~text
orders
  |
  | publishes OrderPlaced
  v
inventory listener
  |
  v
InventoryService.reserve(...)
~~~

Hai hình biểu diễn hai câu hỏi khác nhau:

| Góc nhìn | Hướng | Ý nghĩa |
|---|---|---|
| Dependency graph | **inventory -> orders** | Listener trong inventory tham chiếu event contract do orders sở hữu |
| Runtime event flow | **orders -> inventory** | Orders phát event, inventory nhận và xử lý |

Module phát event không cần tham chiếu bean hoặc class của consumer. Vì thế, khi chỉ dùng event contract, orders không tạo dependency component tới inventory.

**DependencyType.EVENT_LISTENER** cũng khác **DependencyType.USES_COMPONENT**. Với **USES_COMPONENT**, module đích cần được bootstrap để module nguồn sử dụng component của nó. Với **EVENT_LISTENER**, dependency được tạo bởi listener cho event được expose; module đích không cần bootstrap như một component dependency để chạy module nguồn.

## 10. Bước 7 — Quan sát toàn bộ module graph

Có thể in dependency trực tiếp của từng module:

~~~java
modules.stream().forEach(module -> {
    var dependencies = module.getDirectDependencies(modules);

    dependencies.stream().forEach(dependency ->
        System.out.printf(
            "%s --[%s]--> %s%n",
            module.getIdentifier(),
            dependency.getDependencyType(),
            dependency.getTargetModule().getIdentifier()
        )
    );
});
~~~

Để tạo component diagram bằng PlantUML, sử dụng **Documenter**:

Đoạn này là tùy chọn và cần artifact **spring-modulith-docs** trong test classpath:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-docs</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~java
import org.springframework.modulith.docs.Documenter;

new Documenter(modules)
    .writeModulesAsPlantUml()
    .writeIndividualModulesAsPlantUml();
~~~

Diagram tổng quan thể hiện các Application Module và quan hệ giữa chúng. Diagram riêng của module giúp tập trung vào module cùng những module mà nó phụ thuộc trực tiếp. Có thể đối chiếu diagram với kết quả in **ApplicationModuleDependencies** để xác định cạnh nào là **EVENT_LISTENER**.

Documenter mặc định ghi diagram vào thư mục **spring-modulith-docs** trong build directory, ví dụ **target/spring-modulith-docs** với Maven.

## 11. Bước 8 — So sánh trước và sau khi dùng event

Nếu trước bài thực hành, orders gọi trực tiếp bean inventory:

~~~text
orders --[USES_COMPONENT]--> inventory
~~~

Sau khi chuyển sang publish event và listener:

~~~text
inventory --[EVENT_LISTENER]--> orders
~~~

Ở runtime, event vẫn được phát từ orders tới inventory. Việc chuyển đổi thay đổi cách module tham chiếu nhau trong mã nguồn:

- Orders chỉ phụ thuộc **ApplicationEventPublisher** của Spring và event type do chính nó sở hữu.
- Inventory phụ thuộc event contract công khai **orders :: events**.
- Inventory không cần import **OrderManagement** hoặc gọi trực tiếp bean của orders.
- Orders không cần biết **OrderPlacedListener** tồn tại.

Nếu vẫn còn một class trong orders inject **InventoryService**, dependency **orders -> inventory** vẫn tồn tại. Thêm event listener không tự xóa các lời gọi trực tiếp cũ; hãy tìm và loại bỏ chúng nếu mục tiêu là tích hợp qua event.

## 12. Thử nghiệm âm để hiểu quy tắc bảo vệ

Thực hiện từng thay đổi dưới đây một lần, chạy lại architecture test và khôi phục cấu hình sau khi quan sát lỗi.

### Thử nghiệm A — Bỏ Named Interface events

Tạm xóa hoặc đổi tên **@NamedInterface("events")** khỏi **orders/events/package-info.java**.

Kỳ vọng: inventory đang import **OrderPlaced** từ một package chưa được expose. **ApplicationModules.verify()** sẽ báo access violation.

Khôi phục **@NamedInterface("events")** để event contract được công bố trở lại.

### Thử nghiệm B — Bỏ allowlist của inventory

Tạm bỏ **orders :: events** khỏi **allowedDependencies** của inventory trong khi module vẫn khai báo allowlist.

Kỳ vọng: dependency tới orders không còn nằm trong danh sách được phép, verification sẽ báo disallowed dependency.

Khôi phục entry **orders :: events**.

### Thử nghiệm C — Đổi listener thành lời gọi bean trực tiếp

Tạm inject một bean từ module orders vào inventory hoặc gọi **OrderManagement** trực tiếp.

Kỳ vọng: dependency được nhận diện theo loại component/type reference tương ứng, không còn chỉ là **EVENT_LISTENER**. Nếu module consumer chưa cho phép dependency đó, verification sẽ thất bại.

Khôi phục listener event để giữ thiết kế ban đầu.

## 13. Lưu ý về transaction và độ tin cậy của event

**@ApplicationModuleListener** kết hợp xử lý bất đồng bộ, transactional event listener và transaction riêng với **REQUIRES_NEW**. Điều này giúp listener chạy sau khi transaction phát event commit thành công và tách transaction xử lý của inventory khỏi transaction ban đầu của orders.

Một số hệ quả cần nhớ:

- Nếu không có transaction đang hoạt động khi publish event, listener dựa trên **@TransactionalEventListener** không được kích hoạt theo phase mặc định.
- Vì listener bất đồng bộ, lỗi xử lý không nhất thiết làm transaction ban đầu của orders rollback.
- Khi listener có thể thất bại hoặc tiến trình dừng giữa lúc event được phát và listener xử lý, nên cân nhắc Event Publication Registry của Spring Modulith để ghi nhận publication và hỗ trợ phục hồi.
- Event Publication Registry cần persistence implementation phù hợp nếu muốn lưu publication bền vững. Chỉ thêm listener không tự chứng minh rằng mọi event đã được lưu trữ bền vững.

Trong bài thực hành này, architecture test chỉ xác nhận event contract và dependency graph. Nó không chứng minh listener đã thực thi thành công trong một Spring ApplicationContext.

## 14. Checklist hoàn thành

- [ ] **OrderPlaced** là event type public trong package **orders.events**.
- [ ] Package **orders.events** được công bố bằng **@NamedInterface("events")**.
- [ ] Module inventory cho phép **orders :: events**.
- [ ] **OrderManagement** publish event qua **ApplicationEventPublisher** trong transaction.
- [ ] **OrderPlacedListener** dùng **@ApplicationModuleListener**.
- [ ] Listener chỉ gọi service nội bộ của inventory.
- [ ] **ApplicationModules.verify()** PASS.
- [ ] **inventory.getDirectDependencies(modules, EVENT_LISTENER)** chứa orders.
- [ ] **inventory.getDirectDependencies(modules, USES_COMPONENT)** không chứa orders trong kịch bản đã loại bỏ lời gọi trực tiếp.
- [ ] Đã giải thích được vì sao dependency graph có hướng **inventory -> orders** trong khi runtime event flow đi từ **orders -> inventory**.
- [ ] Đã quan sát dependency chi tiết hoặc component diagram.

## 15. Câu hỏi tự kiểm tra

1. Vì sao **OrderPlaced** cần nằm trong Named Interface nếu inventory import event type đó?
2. Module nào sở hữu event contract và module nào sở hữu listener?
3. Vì sao dependency graph ghi **inventory -> orders** trong khi event được phát từ orders sang inventory?
4. **EVENT_LISTENER** khác **USES_COMPONENT** ở điểm nào khi bootstrap module?
5. Nếu inventory vẫn inject **OrderManagement**, graph sẽ xuất hiện thêm loại dependency nào?
6. Vì sao **ApplicationModules.verify()** có thể PASS dù listener runtime chưa từng được gọi?
7. Điều gì có thể xảy ra nếu publish event ngoài transaction trong khi listener dùng **@ApplicationModuleListener**?
8. Khi listener xử lý thất bại, Event Publication Registry hỗ trợ điều gì?

## Tài liệu tham khảo

- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): publish event, **@ApplicationModuleListener**, transaction semantics và Event Publication Registry.
- [Spring Modulith Javadoc — ApplicationModuleListener](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html): annotation kết hợp async transactional event listener và transaction **REQUIRES_NEW**.
- [Spring Modulith Javadoc — DependencyType](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html): ý nghĩa **EVENT_LISTENER**, **USES_COMPONENT**, **ENTITY** và **DEFAULT**.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): **getDirectDependencies()**, **getEventsListenedTo()** và các API dependency.
- [Spring Modulith Javadoc — ApplicationModuleDependencies](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependencies.html): **containsModuleNamed()**, **stream()** và **uniqueModules()**.
- [Spring Modulith Javadoc — ApplicationModuleDependency](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html): source type, target type, target module và dependency type.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): **ApplicationModules.verify()** và các quy tắc module boundary.
- [Spring Modulith Javadoc — Documenter](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html): tạo component diagram PlantUML cho toàn bộ module và từng module.
