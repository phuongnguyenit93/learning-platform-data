# Document dependency type trong module graph

## 1. Vì sao cần ghi rõ loại dependency?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, module **order** có thể cung cấp API để module **inventory** gọi trực tiếp, đồng thời phát event `OrderPlaced` để module **notification** xử lý. Cả hai cách đều tạo quan hệ giữa module, nhưng ý nghĩa kiến trúc khác nhau: một bên phụ thuộc vào Spring component của module khác, bên kia phụ thuộc vào hợp đồng event.

Nếu module graph chỉ ghi một mũi tên `inventory → order`, người đọc chưa biết đó là lời gọi component đồng bộ, tham chiếu entity hay quan hệ event listener. **Dependency type** giúp mô tả bản chất cạnh trong graph, từ đó hỗ trợ review coupling, xác định thứ tự bootstrap, đánh giá khả năng tách module và giải thích luồng tương tác cho nhóm vận hành.

Bài thuộc chương **Tài liệu vận hành** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Chủ đề trực tiếp là **document dependency type trong module graph**: hiểu các loại cạnh, đọc chiều dependency, tạo component diagram bằng `Documenter`, lọc graph theo loại quan hệ và kết hợp tài liệu với kiểm chứng kiến trúc.

Sau bài học, bạn có thể:

1. Giải thích chiều source → target của một module dependency.
2. Phân biệt `DEFAULT`, `ENTITY`, `EVENT_LISTENER` và `USES_COMPONENT`.
3. Đọc loại dependency cùng source type, target type và target module.
4. Sinh C4/UML component diagrams bằng Spring Modulith `Documenter`.
5. Lọc diagram để chỉ hiển thị một hoặc một nhóm dependency type.
6. Kết hợp module graph, Application Module Canvas và `ApplicationModules.verify()` thành tài liệu có thể review và tái tạo.

## 2. Module graph biểu diễn quan hệ theo chiều nào?

Một module dependency được hiểu từ **module nguồn** đến **module đích**:

- **Source module:** module có code tạo ra quan hệ phụ thuộc.
- **Target module:** module chứa type mà source đang tham chiếu hoặc module công bố event mà source lắng nghe.

Ví dụ, `inventory` lắng nghe `OrderPlaced` do `order` công bố. Cạnh được đọc theo hướng `inventory → order`, vì `inventory` phụ thuộc vào event contract do `order` cung cấp.

~~~mermaid
flowchart LR
    Inventory["inventory module"]
    Order["order module"]
    Customer["customer module"]
    Inventory -->|"EVENT_LISTENER"| Order
    Inventory -->|"USES_COMPONENT"| Customer
~~~

Chiều cạnh là một quy ước quan trọng khi đọc graph. Không đảo mũi tên thành “order gọi inventory” chỉ vì event được phát từ order. Với event listener, module nhận event là source của dependency; module công bố event là target.

Một cặp module có thể có nhiều quan hệ cùng lúc. Ví dụ `inventory` vừa inject một component từ `order`, vừa khai báo listener cho event của `order`. Khi đó graph có thể chứa hai cạnh khác loại giữa cùng hai module. Đừng gộp chúng thành một quan hệ duy nhất nếu mục tiêu là tài liệu hóa dependency type.

## 3. Bốn loại DependencyType trong Spring Modulith

Spring Modulith biểu diễn loại quan hệ bằng enum `org.springframework.modulith.core.DependencyType`. API hiện hành có bốn giá trị:

| Dependency type | Ý nghĩa | Cách đọc kiến trúc |
| --- | --- | --- |
| `DEFAULT` | Quan hệ dependency tổng quát, không được phân loại thành một loại chuyên biệt trong các loại còn lại. | Module nguồn phụ thuộc vào type/module đích. |
| `ENTITY` | Module nguồn tham chiếu một entity thuộc module đích. | Có liên kết trực tiếp tới mô hình dữ liệu/domain entity của module khác. |
| `EVENT_LISTENER` | Module nguồn khai báo event listener cho event được module đích công bố. | Quan hệ theo event contract; module đích không cần được bootstrap như một Spring component dependency để chạy source module. |
| `USES_COMPONENT` | Module nguồn phụ thuộc vào component của module đích. | Module đích cần được bootstrap để module nguồn hoạt động với component dependency đó. |

### 3.1. DEFAULT — dependency tổng quát

`DEFAULT` là loại tổng quát trong mô hình dependency. Trong component diagram, quan hệ tổng quát thường được diễn đạt bằng nhãn như `depends on`. Khi đọc một cạnh loại này, hãy xem thêm source type và target type để hiểu code reference cụ thể.

Không nên tự gán `DEFAULT` cho mọi lời gọi method. Spring Modulith phân tích cấu trúc code và có thể phân loại một quan hệ thành `USES_COMPONENT`, `ENTITY` hoặc `EVENT_LISTENER` khi nó thỏa ngữ nghĩa tương ứng.

### 3.2. ENTITY — tham chiếu entity của module khác

Ví dụ module `reporting` tham chiếu entity `Customer` thuộc module `customer`:

~~~java
package com.example.shop.reporting;

import com.example.shop.customer.Customer;

class CustomerReport {

    String customerName(Customer customer) {
        return customer.getName();
    }
}
~~~

Khi type `Customer` được nhận diện là entity thuộc module `customer`, quan hệ có thể được phân loại `ENTITY`. Đây là dấu hiệu cần review vì module nguồn đang phụ thuộc trực tiếp vào mô hình entity của module khác.

Tham chiếu entity có thể làm tăng coupling giữa schema/persistence model và consumer. Nếu module khác chỉ cần một phần dữ liệu, cân nhắc cung cấp API hoặc projection/DTO phù hợp thay vì để nhiều module cùng phụ thuộc vào entity nội bộ.

Ví dụ trên minh họa code reference; để Spring Modulith phân loại cụ thể thành `ENTITY`, target type phải được nhận diện là entity theo metadata/abstraction mà phiên bản và stack đang dùng. Hãy kiểm tra `getDependencyType()` của graph thực tế thay vì suy loại chỉ từ tên class.

### 3.3. EVENT_LISTENER — phụ thuộc qua event contract

Ví dụ module `inventory` lắng nghe event do module `order` công bố:

~~~java
package com.example.shop.order;

public record OrderPlaced(String orderId) {
}
~~~

~~~java
package com.example.shop.inventory;

import com.example.shop.order.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOrderListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        reserveItems(event.orderId());
    }

    private void reserveItems(String orderId) {
        // Xử lý reservation trong module inventory.
    }
}
~~~

Quan hệ được đọc là `inventory → order` với loại `EVENT_LISTENER`. `inventory` phụ thuộc vào event contract `OrderPlaced`, nhưng không cần inject một Spring bean của `order` để xử lý event.

Các listener được nhận diện từ Spring event listener APIs, gồm `@EventListener`, `@TransactionalEventListener` và bean triển khai `ApplicationListener`; `@ApplicationModuleListener` là shortcut của Spring Modulith cho transactional application module listener.

`EVENT_LISTENER` chỉ mô tả quan hệ cấu trúc trong code. Nó không chứng minh event đã được publish trong production, listener đã chạy hoặc publication đã hoàn tất. Muốn biết runtime execution, cần kết hợp event publication metrics/registry, logs và traces.

### 3.4. USES_COMPONENT — phụ thuộc Spring component

Ví dụ module `inventory` inject component API từ module `customer`:

~~~java
package com.example.shop.customer;

import org.springframework.stereotype.Service;

@Service
public class CustomerLookup {

    public boolean isActive(String customerId) {
        return true;
    }
}
~~~

~~~java
package com.example.shop.inventory;

import com.example.shop.customer.CustomerLookup;
import org.springframework.stereotype.Service;

@Service
class ReservationService {

    private final CustomerLookup customers;

    ReservationService(CustomerLookup customers) {
        this.customers = customers;
    }

    void reserve(String customerId) {
        if (!customers.isActive(customerId)) {
            throw new IllegalStateException("Customer is inactive");
        }
        // Tiếp tục reservation.
    }
}
~~~

Quan hệ `inventory → customer` được phân loại `USES_COMPONENT` khi dependency được nhận diện là component dependency. Module `customer` phải được bootstrap để component đó có mặt khi `inventory` chạy.

Đây thường là lời gọi trực tiếp giữa các module. Khi thiết kế ranh giới, cần kiểm tra consumer đang phụ thuộc vào API được expose hay một implementation type thuộc package nội bộ.

## 4. DependencyType được suy ra từ code, không phải nhãn tự đặt

Spring Modulith xây dựng `ApplicationModules` từ cấu trúc package và các quan hệ type mà nó phân tích được. Một dependency có thể được truy cập qua `ApplicationModuleDependency`, với các thông tin:

| API | Ý nghĩa |
| --- | --- |
| `getDependencyType()` | Loại dependency. |
| `getSourceType()` | Java type tạo ra dependency. |
| `getTargetType()` | Java type được tham chiếu. |
| `getTargetModule()` | Application module chứa target type. |

Điều này giúp truy từ cạnh ở cấp module về đúng class/type tạo ra quan hệ. Khi một cạnh cần review, đừng chỉ ghi “inventory phụ thuộc order”; hãy lưu cả `InventoryOrderListener → OrderPlaced` hoặc `ReservationService → CustomerLookup`.

`@ApplicationModule` và `@NamedInterface` phục vụ khai báo ranh giới/contract được expose; chúng không phải annotation để gắn thủ công `DependencyType` lên từng cạnh. Loại quan hệ được suy ra từ cấu trúc code mà Spring Modulith phát hiện.

## 5. Tạo ApplicationModules model để đọc graph

Điểm bắt đầu là `ApplicationModules.of(...)`, truyền vào class ứng dụng Spring Boot:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
class Application {
}
~~~

Tạo model:

~~~java
import com.example.shop.Application;
import org.springframework.modulith.core.ApplicationModules;

class ModuleGraphInspection {

    ApplicationModules modules = ApplicationModules.of(Application.class);
}
~~~

Theo mặc định, Spring Modulith phát hiện application modules từ các package con trực tiếp bên dưới package chứa application class. Nếu dùng nested modules, explicit detection hoặc additional packages, kết quả phụ thuộc arrangement/configuration tương ứng.

Có thể in arrangement để xem module và các component được phát hiện:

~~~java
ApplicationModules modules = ApplicationModules.of(Application.class);
modules.forEach(System.out::println);
~~~

Đây là bước kiểm tra đầu vào trước khi sinh diagram. Nếu package detection sai, module graph sinh ra cũng sẽ thiếu hoặc gộp module không đúng ý định.

## 6. Đọc danh sách dependency cùng source/target type

Để tạo báo cáo chi tiết theo từng cạnh, dùng `getDirectDependencies(modules)` và duyệt `ApplicationModuleDependency`:

~~~java
import com.example.shop.Application;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

class DependencyInventory {

    void printDependencies() {
        ApplicationModules modules = ApplicationModules.of(Application.class);

        for (ApplicationModule source : modules) {
            source.getDirectDependencies(modules)
                    .stream()
                    .forEach(dependency -> System.out.printf(
                            "%s --%s--> %s | %s -> %s%n",
                            source.getDisplayName(),
                            dependency.getDependencyType(),
                            dependency.getTargetModule().getDisplayName(),
                            dependency.getSourceType().getName(),
                            dependency.getTargetType().getName()));
        }
    }
}
~~~

Output minh họa:

~~~text
inventory --EVENT_LISTENER--> order
  com.example.shop.inventory.InventoryOrderListener
  -> com.example.shop.order.OrderPlaced

inventory --USES_COMPONENT--> customer
  com.example.shop.inventory.ReservationService
  -> com.example.shop.customer.CustomerLookup

reporting --ENTITY--> customer
  com.example.shop.reporting.CustomerReport
  -> com.example.shop.customer.Customer
~~~

Tên class/package ở trên là ví dụ. Trong ứng dụng thật, kết quả phụ thuộc các type được phát hiện và cách code tham chiếu chúng.

### Direct dependency và transitive dependency

- `getDirectDependencies(modules)` trả các quan hệ trực tiếp của module hiện tại.
- `getAllDependencies(modules, ...)` có thể bao gồm cả dependency bắc cầu.
- `ApplicationModuleDependencies.stream()` giữ từng dependency edge, gồm source/target type và dependency type.
- `uniqueModules()` chỉ lấy module đích duy nhất; nếu một cặp module có nhiều dependency type, thao tác này sẽ làm mất chi tiết từng cạnh.

Khi làm tài liệu dependency type, ưu tiên duyệt `stream()` để giữ đầy đủ các edge. Chỉ dùng `uniqueModules()` khi câu hỏi thực sự là “module này phụ thuộc vào những module nào?” mà không cần phân biệt cách phụ thuộc.

## 7. Sinh component diagram bằng Documenter

Spring Modulith cung cấp `Documenter` để sinh PlantUML component diagrams từ `ApplicationModules`. Đặt đoạn gọi trong test hoặc task tài liệu hóa:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    ApplicationModules modules = ApplicationModules.of(Application.class);

    @Test
    void writeModuleDiagrams() {
        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml();
    }
}
~~~

Hai lệnh tạo ra:

1. **Overview diagram:** một component diagram chứa toàn bộ application modules và quan hệ giữa chúng.
2. **Individual diagrams:** một diagram cho mỗi module, tập trung vào module đó và các module nó phụ thuộc trực tiếp theo options đang dùng.

Mặc định, `Documenter` ghi tài liệu vào thư mục `spring-modulith-docs` bên trong build output. Ví dụ với Maven, thư mục thường nằm dưới `target`; với Gradle, nằm dưới build directory của project.

`Documenter` hỗ trợ C4 và UML component diagram. Spring Modulith 2.x chuyển style mặc định sang C4; nếu cần UML truyền thống, đặt style rõ ràng để tài liệu ổn định giữa các phiên bản:

~~~java
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;
import org.springframework.modulith.docs.Documenter.DiagramOptions.DiagramStyle;

DiagramOptions umlOptions = DiagramOptions.defaults()
        .withStyle(DiagramStyle.UML);

new Documenter(modules)
        .writeModulesAsPlantUml(umlOptions)
        .writeIndividualModulesAsPlantUml(umlOptions);
~~~

## 8. Lọc module graph theo dependency type

`DiagramOptions.withDependencyTypes(...)` chọn loại dependency được đưa vào diagram. Mặc định `DiagramOptions.defaults()` dùng **tất cả dependency types**.

### 8.1. Chỉ hiển thị event listener edges

Khi review kiến trúc event-driven, chỉ hiển thị `EVENT_LISTENER`:

~~~java
import org.springframework.modulith.core.DependencyType;
import org.springframework.modulith.docs.Documenter;
import org.springframework.modulith.docs.Documenter.DiagramOptions;

DiagramOptions eventOptions = DiagramOptions.defaults()
        .withDependencyTypes(DependencyType.EVENT_LISTENER);

new Documenter(modules)
        .writeModulesAsPlantUml(eventOptions)
        .writeIndividualModulesAsPlantUml(eventOptions);
~~~

Diagram kết quả giúp trả lời:

- Module nào phát event contract mà module khác lắng nghe?
- Một module có đang nhận event từ quá nhiều module nguồn không?
- Có module nào chỉ kết nối với phần còn lại qua event không?

Nếu diagram lọc chỉ còn một số module có event relationship, các module không có cạnh liên quan có thể bị ẩn theo mặc định. Có thể yêu cầu giữ các module cô lập:

~~~java
DiagramOptions eventOptions = DiagramOptions.defaults()
        .withDependencyTypes(DependencyType.EVENT_LISTENER)
        .withElementsWithoutRelationships(
                DiagramOptions.ElementsWithoutRelationships.VISIBLE);
~~~

### 8.2. Chỉ hiển thị component/entity dependencies

Để xem các quan hệ trực tiếp hơn giữa các module:

~~~java
DiagramOptions componentOptions = DiagramOptions.defaults()
        .withDependencyTypes(
                DependencyType.USES_COMPONENT,
                DependencyType.ENTITY);

new Documenter(modules)
        .writeModulesAsPlantUml(componentOptions);
~~~

Diagram này hữu ích khi review coupling do component injection hoặc tham chiếu entity. Nếu một module chỉ có quan hệ event listener, nó sẽ không xuất hiện như một cạnh trong view này.

### 8.3. Hiển thị mọi loại dependency

Để xem graph tổng thể, dùng mặc định hoặc khai báo tường minh:

~~~java
DiagramOptions allDependencyTypes = DiagramOptions.defaults()
        .withDependencyTypes(
                DependencyType.DEFAULT,
                DependencyType.ENTITY,
                DependencyType.EVENT_LISTENER,
                DependencyType.USES_COMPONENT);

new Documenter(modules)
        .writeModulesAsPlantUml(allDependencyTypes);
~~~

Lọc graph không thay đổi module model hoặc code. Nó chỉ thay đổi các cạnh được render trong diagram.

## 9. Đọc nhãn quan hệ trong component diagram

Diagram do Spring Modulith sinh có thể hiển thị các nhãn dễ đọc như `depends on`, `uses` và `listens to`. Nhãn giúp người đọc hiểu nhanh quan hệ, còn enum `DependencyType` là thông tin có cấu trúc để filter và kiểm tra.

| Nhãn thường gặp | Cách diễn giải |
| --- | --- |
| `depends on` | Quan hệ dependency tổng quát. Xem thêm source/target type để hiểu code reference. |
| `uses` | Quan hệ sử dụng component hoặc type/entity được expose từ module đích. Kiểm tra `DependencyType` để biết loại cụ thể. |
| `listens to` | Module nguồn khai báo listener cho event do module đích expose; tương ứng `EVENT_LISTENER`. |

Ví dụ:

~~~text
inventory -> order : listens to
inventory -> customer : uses
reporting -> customer : depends on
~~~

Không nên suy luận toàn bộ semantics chỉ từ nhãn ngắn trên hình. Khi cần review chi tiết, đọc dependency inventory bằng `ApplicationModuleDependency.getDependencyType()`, `getSourceType()` và `getTargetType()`.

## 10. Một cặp module có thể có nhiều loại cạnh

Giả sử `inventory` vừa inject `OrderQuery` từ `order`, vừa lắng nghe `OrderPlaced`:

~~~mermaid
flowchart LR
    Inventory["inventory"]
    Order["order"]
    Inventory -->|"USES_COMPONENT"| Order
    Inventory -->|"EVENT_LISTENER"| Order
~~~

Đây là hai dependency khác nhau:

- `USES_COMPONENT`: `inventory` gọi component của `order`.
- `EVENT_LISTENER`: `inventory` nhận event contract từ `order`.

Tài liệu nên giữ hai cạnh để người review thấy cả coupling trực tiếp lẫn event-based integration. Nếu chỉ lưu danh sách module đích duy nhất, thông tin quan trọng này sẽ biến mất.

## 11. Module graph và Application Module Canvas bổ sung cho nhau

Component diagram trả lời **module nào phụ thuộc module nào và qua loại quan hệ gì**. Application Module Canvas trả lời **module cung cấp những gì và chứa các thành phần quan trọng nào**.

Canvas do `Documenter.writeModuleCanvases()` sinh có thể liệt kê:

- Base package của module.
- Spring components được expose, nhóm theo stereotype.
- Aggregate roots được nhận diện.
- Application events được publish.
- Event listeners và event types chúng lắng nghe.
- Configuration properties được expose.

Ví dụ:

~~~java
new Documenter(modules)
        .writeModuleCanvases();
~~~

Canvas không thay thế dependency diagram. Khi đọc một cạnh `EVENT_LISTENER`, mở canvas của source module để tìm listener và event type; mở canvas của target module để tìm event được publish. Kết hợp hai tài liệu giúp kiểm tra quan hệ từ cả hai phía.

Có thể sinh toàn bộ tài liệu và file tổng hợp:

~~~java
new Documenter(modules)
        .writeDocumentation();
~~~

`writeDocumentation()` tạo overview diagram, individual diagrams, canvases và file tổng hợp `all-docs.adoc`. Nếu trước đó đã sinh riêng diagram/canvas, có thể gọi `writeAggregatingDocument()` để tạo lại file tổng hợp. Nếu chưa có diagram/canvas nào, file tổng hợp có thể không được tạo.

## 12. Phân biệt dependency type với allowed dependency và named interface

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Trả lời câu hỏi |
| --- | --- |
| **Dependency type** | Code đang phụ thuộc theo cách nào: component, entity, event listener hay quan hệ tổng quát? |
| **Allowed dependency** | Module được phép phụ thuộc vào module/named interface nào? |
| **Named interface** | Module expose package/API nào để module khác được phép sử dụng? |

### 12.1. Khai báo allowed dependencies

Ví dụ chỉ cho module `inventory` phụ thuộc vào module `order`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order"
)
package com.example.shop.inventory;
~~~

Khai báo này đặt giới hạn cho dependency được phép. Nó không tạo dependency edge nếu code không thực sự tham chiếu `order`, và cũng không biến edge hiện có thành một `DependencyType` cụ thể.

### 12.2. Dùng named interface để expose SPI

Ví dụ module `order` expose package SPI:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.order.spi;
~~~

Module `inventory` có thể giới hạn dependency tới named interface đó:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order :: spi"
)
package com.example.shop.inventory;
~~~

Named interface giúp làm rõ contract công khai. Dependency type vẫn được suy ra từ code thực tế sử dụng interface hoặc component được expose.

## 13. Kiểm chứng module graph bằng verify()

Diagram là tài liệu để con người đọc. Để kiểm tra các ràng buộc cấu trúc, gọi:

~~~java
import com.example.shop.Application;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Việc verify bao gồm các quy tắc chính:

1. Không có chu trình dependency ở cấp application module; graph phải là directed acyclic graph.
2. Module khác chỉ truy cập API packages/named interfaces được expose, theo quy tắc module arrangement.
3. Nếu module khai báo `allowedDependencies`, các dependency thực tế phải nằm trong tập được phép.

`verify()` không phải runtime test và không chứng minh event đã được giao thành công. Nó kiểm tra cấu trúc code và các quy tắc kiến trúc đã khai báo.

## 14. Quy trình review dependency type

Khi cập nhật module graph, thực hiện theo thứ tự:

1. **Tạo model:** dùng `ApplicationModules.of(Application.class)` với đúng root package.
2. **Liệt kê cạnh:** lấy direct dependencies và ghi source type, target type, target module, dependency type.
3. **Sinh overview diagram:** gọi `writeModulesAsPlantUml()` để nhìn toàn cảnh.
4. **Sinh focused diagrams:** lọc `EVENT_LISTENER` hoặc `USES_COMPONENT` khi cần review từng kiểu coupling.
5. **Đối chiếu Canvas:** kiểm tra event listener, event được publish, bean và named interfaces của module liên quan.
6. **Verify:** chạy `ApplicationModules.verify()` để phát hiện cycle, access nội bộ và dependency ngoài allowlist.
7. **Review thay đổi:** so sánh graph trước/sau thay đổi package, constructor injection, event listener hoặc entity reference.
8. **Lưu tài liệu:** đưa output generated vào quy trình build/docs phù hợp; không chỉnh sửa thủ công các diagram được sinh lại tự động.

~~~mermaid
flowchart TD
    A["Scan ApplicationModules"] --> B["Inspect dependency edges"]
    B --> C["Generate overview diagram"]
    C --> D["Filter by DependencyType"]
    D --> E["Review Module Canvas"]
    E --> F["Run ApplicationModules.verify()"]
    F --> G{"Architecture rules pass?"}
    G -->|No| H["Fix package/API/dependency"]
    H --> A
    G -->|Yes| I["Publish generated docs"]
~~~

## 15. Các lỗi đọc và ghi tài liệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mũi tên bị đọc ngược | Nhầm source module với target module. | Đọc cạnh từ module có source type sang module chứa target type. |
| Event listener bị hiểu là lời gọi đồng bộ | Chỉ nhìn thấy hai module có quan hệ. | Xem `EVENT_LISTENER`; đây là event contract, không phải component injection. |
| Không thấy module trong event-only diagram | Module không có event edge hoặc node không có relationship bị ẩn. | Bật `ElementsWithoutRelationships.VISIBLE` nếu cần hiển thị node cô lập. |
| Hai module chỉ có một cạnh trong báo cáo tùy chỉnh | Dùng `uniqueModules()` và làm mất các dependency edge khác loại. | Duyệt `ApplicationModuleDependencies.stream()`. |
| Diagram quá dày | Hiển thị mọi loại dependency và mọi module cùng lúc. | Tách overview, event-only, component/entity-only và individual diagrams. |
| Module có trong diagram nhưng verify thất bại | Diagram mô tả dependency thực tế, còn allowedDependencies giới hạn dependency được phép. | Đối chiếu `@ApplicationModule(allowedDependencies = …)` và named interfaces. |
| Canvas không liệt kê event mong đợi | Event type chưa được nhận diện theo quy ước hoặc listener không thuộc tập API được scan. | Kiểm tra event/listener declaration và package arrangement. |
| Diagram cũ sau khi đổi code | Tài liệu chưa được generate lại. | Chạy lại task/test tạo `Documenter` và kiểm tra output build. |
| Event edge xuất hiện nhưng không thấy event trong production | Graph là phân tích cấu trúc code, không phải bằng chứng runtime. | Kiểm tra event publication registry, logs, metrics và traces. |
| Diagram thiếu module không liên quan | Mặc định ẩn elements không có relationships. | Dùng `withElementsWithoutRelationships(VISIBLE)` hoặc điều chỉnh filter. |

## 16. Tự động hóa tài liệu trong build

Một cách phổ biến là đặt việc sinh tài liệu trong test class để có thể chạy cùng CI:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class GenerateModuleDocumentation {

    @Test
    void generateDocs() {
        ApplicationModules modules = ApplicationModules.of(Application.class);

        new Documenter(modules)
                .writeDocumentation();
    }
}
~~~

Artifact cần cho `Documenter` là `spring-modulith-docs`, thường khai báo ở test scope:

~~~groovy
dependencies {
    testImplementation 'org.springframework.modulith:spring-modulith-docs'
}
~~~

Quản lý version bằng Spring Modulith BOM tương thích với Spring Boot của ứng dụng. Không trộn các module Spring Modulith khác version trong cùng classpath.

### Tổ chức output

- Giữ generated diagrams trong build output như `spring-modulith-docs`.
- Nếu cần đưa vào developer portal hoặc Asciidoc site, dùng `all-docs.adoc` làm entry point.
- Lưu source của tài liệu vận hành và cấu hình generator trong repository; tái tạo diagram từ code thay vì sửa tay file PlantUML generated.
- Có thể tạo overview diagram cho tài liệu kiến trúc và focused diagrams cho từng module trong cùng pipeline.

## 17. Checklist review dependency type

- [ ] `ApplicationModules` được tạo từ đúng application root class.
- [ ] Package arrangement phát hiện đúng module và nested modules.
- [ ] Mỗi dependency edge được ghi source module, target module, source type và target type.
- [ ] Đã phân biệt `DEFAULT`, `ENTITY`, `EVENT_LISTENER`, `USES_COMPONENT`.
- [ ] Đã kiểm tra chiều source → target, nhất là cạnh `EVENT_LISTENER`.
- [ ] Không gộp nhiều dependency edges giữa cùng một cặp module.
- [ ] Overview diagram hiển thị đủ loại dependency cần review.
- [ ] Có focused diagram cho event listener hoặc component/entity coupling khi cần.
- [ ] Đã xem xét các module cô lập bị ẩn khỏi diagram mặc định.
- [ ] Đã đối chiếu dependency với named interfaces và allowed dependencies.
- [ ] Đã đọc Module Canvas của các module liên quan.
- [ ] Đã chạy `ApplicationModules.verify()`.
- [ ] Đã phân biệt static dependency graph với runtime traces/events.
- [ ] Generated docs được tái tạo trong build/CI và không chỉnh sửa thủ công.
- [ ] `all-docs.adoc` được tạo nếu cần tài liệu tổng hợp.

## 18. Tài liệu tham khảo chính thức

- **Spring Modulith — Documenting Application Modules:** https://docs.spring.io/spring-modulith/reference/documentation.html — `Documenter`, C4/UML component diagrams, Module Canvas và tài liệu tổng hợp.
- **Spring Modulith — DependencyType API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html — các loại `DEFAULT`, `ENTITY`, `EVENT_LISTENER`, `USES_COMPONENT`.
- **Spring Modulith — ApplicationModuleDependency API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDependency.html — source type, target type, target module và dependency type.
- **Spring Modulith — ApplicationModule API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html — direct/transitive dependencies và API của module model.
- **Spring Modulith — Documenter.DiagramOptions API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.DiagramOptions.html — lọc dependency types, dependency depth, style và isolated elements.
- **Spring Modulith — Fundamentals:** https://docs.spring.io/spring-modulith/reference/fundamentals.html — application modules, allowed dependencies và named interfaces.
- **Spring Modulith — Verifying Application Module Structure:** https://docs.spring.io/spring-modulith/reference/verification.html — cycle detection, API access và allowed dependency verification.
- **Spring Modulith — Appendix:** https://docs.spring.io/spring-modulith/reference/appendix.html — artifact `spring-modulith-docs` và output folder.

## 19. Tổng kết

Dependency type cho biết **module nguồn phụ thuộc module đích theo cách nào**. Spring Modulith phân loại các quan hệ thành `DEFAULT`, `ENTITY`, `EVENT_LISTENER` và `USES_COMPONENT`; `ApplicationModuleDependency` còn cung cấp source type, target type và target module để truy nguyên cạnh về code cụ thể.

Dùng `Documenter` để sinh overview và individual component diagrams, rồi dùng `DiagramOptions.withDependencyTypes(...)` để tạo focused views theo từng loại quan hệ. Kết hợp diagram với Module Canvas và `ApplicationModules.verify()` để vừa giải thích dependency vừa kiểm tra ranh giới. Hãy nhớ module graph là tài liệu cấu trúc tĩnh; khi cần biết event đã chạy hoặc component được gọi trong production, hãy đối chiếu thêm metrics, Event Publication Registry, logs và traces.
