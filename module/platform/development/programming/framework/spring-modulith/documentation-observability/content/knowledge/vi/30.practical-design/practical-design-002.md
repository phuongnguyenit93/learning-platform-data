# Xác định module API cần instrument

> **Chương:** Thiết kế thực tế
> **Hệ thống áp dụng:** Spring Modulith Documentation & Observability trong ứng dụng Spring Boot có các application module.
> **Câu hỏi thiết kế:** Đâu là ranh giới giao tiếp cần có span/metric để nhìn rõ tương tác giữa các module, và làm sao xác nhận Spring Modulith thực sự quan sát đúng các ranh giới ấy?

## 1. Bài toán: nhìn thấy nghiệp vụ đi qua những module nào

Một ứng dụng thương mại điện tử có các module `orders`, `inventory`, `payments` và `notifications`. Khi khách đặt hàng, hệ thống đi qua nhiều bước:

1. `orders` tiếp nhận yêu cầu và cập nhật trạng thái đơn hàng.
2. `orders` gọi một API của `inventory` để giữ hàng.
3. `orders` công bố một domain event, chẳng hạn `OrderPlaced`.
4. `payments` xử lý sự kiện để bắt đầu thanh toán; `notifications` gửi thông báo sau đó.

Đội phát triển đã có module graph sinh từ Spring Modulith, nhưng trace chỉ có HTTP request và các lời gọi cơ sở dữ liệu. Người vận hành khó biết một request đi qua ranh giới `orders → inventory` mất bao lâu, module nào là nơi bắt đầu xử lý hoặc listener của `payments` thất bại ở bước nào.

Để giải quyết, không cần tự thêm một span cho từng hàm Java. Trước hết phải xác định **API mà mỗi application module cố ý cung cấp cho các module khác**. Chính mô hình API này là đầu vào trọng yếu để Spring Modulith tự động quan sát tương tác module. Khi cần đo chi tiết nội bộ hơn, bổ sung instrumentation có chủ đích bằng Micrometer Observation thay vì biến nội bộ thành API công khai.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt **module API** với REST endpoint, Java `public` bất kỳ và các component nội bộ.
- Từ package structure, named interface, module graph và module canvas, lập danh sách Spring bean/đường event đáng quan sát.
- Sắp xếp ưu tiên theo rủi ro nghiệp vụ, độ trễ, lỗi liên module và chi phí telemetry.
- Thiết kế một ví dụ có `@NamedInterface`, `@ApplicationModuleListener`, kiểm tra kiến trúc và quan sát tại runtime.
- Đọc span attributes, event metrics, Actuator để xác minh phạm vi instrumentation.
- Nhận ra trường hợp thiếu span do AOP/proxy, sampling, async context, exporter hoặc thiết kế module chưa đúng.

## 2. Module API là gì trong Spring Modulith?

Theo mô hình Spring Modulith, một application module cung cấp hai dạng giao tiếp chính:

- **Spring beans được expose** cho code bên ngoài module gọi qua các kiểu giao tiếp cho phép.
- **Application events** được module công bố để module khác đăng ký xử lý; bên phát không cần nắm trực tiếp implementation của bên nhận.

Code xử lý chi tiết trong `internal` là phần triển khai của module, không nên bị các module khác gọi trực tiếp. Với cấu trúc mặc định, mỗi subpackage trực tiếp dưới package chứa lớp `@SpringBootApplication` là một application module. Các public type đặt trong **base package của module** thuộc API mặc định; subpackage thường được xem là nội bộ, trừ khi được expose rõ ràng bằng named interface hoặc có cấu hình phát hiện khác.

~~~text
com.example.shop
├── ShopApplication.java
├── orders                         # Application module orders
│   ├── OrderManagement.java       # Public Spring bean trong base package: API
│   ├── internal
│   │   └── OrderPricing.java      # Chi tiết triển khai: internal
│   └── events
│       ├── package-info.java      # @NamedInterface("events")
│       └── OrderPlaced.java       # Event được expose qua named interface
├── inventory                      # Application module inventory
│   ├── InventoryOperations.java   # Public Spring bean: API
│   └── internal
│       └── StockPolicy.java       # Internal
├── payments                       # Application module payments
│   └── internal
│       └── PaymentEventListener.java
└── notifications                  # Application module notifications
    └── internal
        └── NotificationEventListener.java
~~~

Chú ý ba tầng khái niệm khác nhau:

| Khái niệm | Ví dụ | Hệ quả với instrumentation |
| --- | --- | --- |
| **API theo kiến trúc module** | `orders.OrderManagement`, `inventory.InventoryOperations`; type trong một named interface | Các Spring component thuộc API là đối tượng được Spring Modulith observability trang trí bằng aspect để tạo module-entry observation/span. |
| **API HTTP của ứng dụng** | `POST /orders`, `GET /orders/{id}` trong lớp controller | Có thể tạo HTTP server span qua Spring Boot; điều đó không tự chứng minh tương tác giữa các module đã được ghi nhận. |
| **Chi tiết triển khai bên trong module** | `orders.internal.OrderPricing`, private helper, repository nội bộ | Không phải đối tượng cần expose chỉ để quan sát; nếu cần đo sâu thì tạo observation nghiệp vụ riêng. |
| **Sự kiện liên module** | `OrderPlaced`, listener `payments` | Metric sự kiện và event-listener span có ý nghĩa khác module API bean span; cần kiểm tra cả thời điểm publish và xử lý. |

**Điểm quan trọng:** `public class` là điều kiện ngôn ngữ Java, nhưng **không tự biến một kiểu trong `internal` thành API hợp lệ của module**. Ngược lại, một `@RestController` không nhất thiết là API module được expose; nó có thể chỉ là adapter HTTP thuộc nội bộ `orders`.

### Base package, named interface và allowedDependencies

Nếu muốn cho module khác sử dụng type trong subpackage `orders.events` mà không mở toàn bộ code nội bộ:

~~~java
// File: src/main/java/com/example/shop/orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Để giới hạn `payments` chỉ được phụ thuộc vào named interface đó:

~~~java
// File: src/main/java/com/example/shop/payments/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events")
package com.example.shop.payments;
~~~

`orders::events` là cú pháp `moduleName::namedInterfaceName`. `allowedDependencies` là **quy tắc kiến trúc** được `ApplicationModules.verify()` kiểm tra; nó không phải bộ lọc để bật/tắt tracing hay giới hạn quyền HTTP. Phạm vi thực tế có thể khác nếu dự án dùng open modules, nested modules hoặc `ApplicationModuleDetectionStrategy` tùy chỉnh. Đọc mô hình module đã được phát hiện trước khi suy ra API từ tên thư mục.

## 3. Điều gì thực sự được Spring Modulith instrument?

Với dependency observability phù hợp, Spring Modulith có cơ chế trang trí **Spring component thuộc application module API** bằng aspect/interceptor để thu thập Micrometer Observation. Các lần gọi được intercept tạo **module-entry spans**, có thể được gửi đến tracing backend nếu Spring Boot đã cấu hình bridge, tracer, exporter và sampling.

~~~mermaid
flowchart LR
    H["HTTP request"] --> O["orders: OrderManagement"]
    O -->|"Gọi bean API"| I["inventory: InventoryOperations"]
    O -->|"publish OrderPlaced"| E["Spring event bus"]
    E -->|"listener async / transactional"| P["payments: PaymentEventListener"]
    E -->|"listener"| N["notifications: NotificationEventListener"]
    O -. "module span" .-> T["Micrometer tracing"]
    I -. "module-entry span" .-> T
    P -. "event-listener span nếu được instrument" .-> T
    N -. "event-listener span nếu được instrument" .-> T
    E -. "event publication metrics" .-> M["Micrometer MeterRegistry"]
    T --> X["Trace exporter / collector"]
    M --> Y["Metrics registry / scrape"]
~~~

Không có quan hệ một-một giữa **mỗi method Java** và **một span Modulith**. Hãy nhớ:

1. Bean phải được Spring quản lý, thuộc cấu trúc application module được nhận diện và nằm trong phạm vi mà cơ chế observability của phiên bản đang dùng hỗ trợ.
2. Lời gọi cần đi qua interception phù hợp. `this.method()` (self-invocation), đối tượng tự khởi tạo bằng `new` hoặc method không thể được proxy có thể không tạo span như kỳ vọng.
3. `module-entry span` mô tả việc đi vào điểm giao tiếp được quan sát; một lời gọi hoàn toàn bên trong cùng module có thể không có span riêng.
4. `ApplicationModuleListener` là lối tích hợp sự kiện bất đồng bộ, không có nghĩa mọi listener hay mọi callback tự động xuất hiện với quan hệ parent-child liên tục. Kiểm tra sự kiện, proxy, thread hop và context propagation.
5. Trên một hệ thống thực tế, **không thấy span ở backend** còn có thể do thiếu tracing bridge/exporter, sampling hoặc Collector; không vội kết luận API được khai báo sai.

### Loại tín hiệu và ý nghĩa

| Tín hiệu | Nguồn | Trả lời câu hỏi |
| --- | --- | --- |
| **Module-entry span** | Interception tại Spring component thuộc module API hoặc luồng listener được hỗ trợ | Module nào được gọi, vào method nào, thời lượng/lỗi của lời gọi? |
| **`module.events.published`** | Metric domain-event publication của Spring Modulith | Có bao nhiêu event được phát theo module/loại? |
| **`module.events.published.{moduleIdentifier}.{simpleEventTypeName}`** | Metric của một event type cụ thể | Event loại nào được phát ở module nào? |
| **HTTP/DB spans** | Instrumentation của Spring Boot/Micrometer và thư viện liên quan | Request hoặc truy vấn DB mất bao lâu? |
| **Module graph** | `ApplicationModules`, `Documenter`, `/actuator/modulith` | Các module và mối phụ thuộc tĩnh dự kiến là gì? |

**Event publication counter tăng không chứng minh listener xử lý thành công.** Với listener giao dịch, trạng thái xử lý sự kiện (nếu có Event Publication Registry) và trace của listener là các bằng chứng bổ sung. Module graph là cấu trúc tĩnh; span là hành vi xảy ra ở runtime.

## 4. Bắt đầu từ use case và ranh giới nghiệp vụ

Không nên chọn API để instrument bằng cách liệt kê mọi file `@Service`. Hãy chọn **đường đi nghiệp vụ** mà đội vận hành thực sự muốn thấy rõ.

Ví dụ use case `PlaceOrder`:

~~~mermaid
sequenceDiagram
    actor U as Client
    participant W as OrderController
    participant O as orders.OrderManagement
    participant I as inventory.InventoryOperations
    participant B as ApplicationEventPublisher
    participant P as payments.PaymentEventListener
    U->>W: POST /orders
    W->>O: placeOrder(command)
    O->>I: reserve(sku, quantity)
    I-->>O: Sẵn sàng
    O->>B: publish(OrderPlaced)
    O-->>W: Kết quả đặt hàng
    W-->>U: 201 Created
    B-->>P: Delivery sau commit (khi dùng @ApplicationModuleListener)
    P->>P: Bắt đầu thanh toán
~~~

Để chọn điểm cần instrument, hỏi theo thứ tự:

1. **Nơi nào đi qua ranh giới module?** `orders → inventory` là lời gọi bean API, `orders → payments` là event; cả hai cần có bằng chứng.
2. **Hành động nào có rủi ro khách hàng?** Giữ hàng thất bại và tạo thanh toán trễ ảnh hưởng trực tiếp đơn hàng.
3. **Đo thời gian nào có ý nghĩa?** Thời gian `reserve` và độ trễ từ phát event tới hoàn tất listener khác nhau; không đánh đồng hai thước đo.
4. **Có tác vụ bất đồng bộ không?** Sau commit, listener có thể chạy trên thread khác; kiểm tra trace context và eventual consistency.
5. **Có thông tin nhạy cảm không?** Chỉ cần tên module, tên method, loại event, kết quả chung; không cần ghi số thẻ, mã khách hàng hay toàn bộ payload.
6. **Kết quả này giúp xử lý sự cố nào?** Nếu một span không hỗ trợ điều tra, SLO hoặc xác định ranh giới thì cân nhắc bỏ khỏi phạm vi đo sâu.

### Ma trận ứng viên

| Ứng viên | Vai trò | Mức ưu tiên | Hướng quan sát |
| --- | --- | --- | --- |
| `orders.OrderManagement.placeOrder` | API xử lý use case được HTTP adapter gọi | Cao | Kiểm tra module-entry span của bean được expose; đối chiếu HTTP span. |
| `inventory.InventoryOperations.reserve` | API liên module đồng bộ, quyết định có giữ hàng được không | Rất cao | Kiểm tra module-entry span, duration, error và ranh giới caller/callee. |
| `orders.events.OrderPlaced` | Contract sự kiện cung cấp cho module khác | Cao | Theo dõi publication counter; xem span của listener và trạng thái Event Publication Registry nếu dùng. |
| `payments.internal.PaymentEventListener` | Bên nhận event, có thể xử lý async | Rất cao | Xác minh hỗ trợ instrumentation của event listener; theo dõi lỗi và độ trễ hoàn tất thực tế. |
| `inventory.internal.StockPolicy.evaluate` | Chi tiết tính toán cùng module | Theo nhu cầu | Không expose chỉ để có span; tạo observation nghiệp vụ riêng nếu đây là điểm nghẽn. |
| `orders.internal.OrderRepository` | Lưu trữ dữ liệu nội bộ | Thấp | Dùng DB/repository instrumentation sẵn có, không biến repository thành API. |
| `/actuator/modulith` | Endpoint cung cấp graph | Kiểm tra cấu trúc | So graph với thiết kế; không xem là span của module nghiệp vụ. |

Mức ưu tiên chỉ là **ví dụ minh họa phương pháp**, không phải thứ tự mặc định cho mọi ứng dụng. Dự án thanh toán có thể ưu tiên cổng thanh toán hơn giữ hàng; dự án batch có thể ưu tiên event listener hơn HTTP entrypoint.

## 5. Thiết kế API theo package và code

Sau đây là **bộ khung minh họa**, với logic nghiệp vụ lược giản. Giả định lớp `ShopApplication` thuộc `com.example.shop`, có Spring Boot và Spring Modulith cùng phiên bản tương thích.

### 5.1. Module `inventory` expose một bean rõ ràng

~~~java
// File: com/example/shop/inventory/InventoryOperations.java
package com.example.shop.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryOperations {

    public void reserve(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid inventory reservation");
        }
        // Minh họa: trong ứng dụng thực, ủy quyền xuống internal repository/policy.
    }
}
~~~

`InventoryOperations` là public Spring bean ở **base package `inventory`**. Nó là hợp đồng kỹ thuật hợp lý cho `orders` gọi. Các repository hoặc policy bên trong `inventory.internal` vẫn là chi tiết triển khai, ngay cả khi Java phải dùng `public` để tương tác qua package.

### 5.2. Module `orders` dùng API đó và phát domain event

~~~java
// File: com/example/shop/orders/events/OrderPlaced.java
package com.example.shop.orders.events;

public record OrderPlaced(String orderId) {}
~~~

~~~java
// File: com/example/shop/orders/OrderManagement.java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryOperations;
import com.example.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderManagement {

    private final InventoryOperations inventory;
    private final ApplicationEventPublisher events;

    public OrderManagement(InventoryOperations inventory,
                           ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    @Transactional
    public void placeOrder(String orderId, String sku, int quantity) {
        inventory.reserve(sku, quantity);
        // Minh họa: lưu đơn hàng trước khi thông báo các module khác.
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Ví dụ dùng `@Transactional` để chỉ ra ranh giới nghiệp vụ; trong dự án thực phải có datasource, transaction manager, xử lý lỗi/idempotency và persistence phù hợp. `publishEvent` không tự tạo hợp đồng delivery bền vững; event listener giao dịch cần cơ chế event publication registry/retry nếu không được phép mất xử lý.

Giới hạn phụ thuộc của `orders`:

~~~java
// File: com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory")
package com.example.shop.orders;
~~~

Chỉ `inventory` được khai báo là module mà `orders` có thể phụ thuộc trực tiếp. `OrderPlaced` nằm trong named interface `orders::events` như đã khai báo ở mục 2. Tại chỗ này, **việc expose type event không có nghĩa Spring Modulith sẽ gắn module-entry span lên constructor của record**; event được quan sát qua publication và listener.

### 5.3. Module `payments` nhận event qua listener

~~~java
// File: com/example/shop/payments/internal/PaymentEventListener.java
package com.example.shop.payments.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Minh họa: khởi động quy trình thanh toán theo orderId.
        // Logic thực tế cần idempotency và ghi nhận trạng thái xử lý.
    }
}
~~~

`@ApplicationModuleListener` là shortcut cho asynchronous transactional event listener với giao dịch riêng. Nếu muốn event được chuyển đúng sau commit và không mất khi ứng dụng dừng, phải thiết kế transaction/event registry theo đặc tính bảo đảm cần có. Trong trace có thể nhìn thấy lời gọi kiểu **event listener**, nhưng cần **kiểm tra phiên bản và đường thực thi thật**, vì async context hoặc sampling có thể khiến listener span tách khỏi trace của HTTP request.

Đừng chuyển `PaymentEventListener` từ `payments.internal` lên base package chỉ để cố gắng tạo thêm span. Đây là thành phần **nhận** sự kiện từ module khác, không phải lời gọi API mà `orders` phải trực tiếp phụ thuộc vào. Hành vi tracing event listener được kiểm chứng bằng luồng sự kiện và cấu hình observability.

## 6. Kiểm chứng ranh giới bằng Spring Modulith trước khi đo

Không nên tuyên bố đã instrument đúng nếu mô hình module đang phát hiện sai package. Trước tiên tạo mô hình từ lớp khởi động và chạy verification:

~~~java
// File test: com/example/shop/ModuleArchitectureTests.java
package com.example.shop;

import com.example.shop.orders.OrderManagement;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ModuleArchitectureTests {

    @Test
    void checksModuleBoundaries() {
        var modules = ApplicationModules.of(ShopApplication.class);

        modules.forEach(System.out::println); // Xem danh sách module và beans.
        modules.verify();                      // Kiểm tra vòng phụ thuộc và API.

        var orders = modules.getModuleByName("orders").orElseThrow();
        assertTrue(orders.isExposed(OrderManagement.class));
    }
}
~~~

`verify()` phát hiện những phụ thuộc đi vào internal package, chu trình module và vi phạm `allowedDependencies` đã khai báo. Đây là **kiểm thử kiến trúc tĩnh**, không xác nhận span được tạo ở runtime.

### Kết hợp module graph và module canvas

Nếu thêm test dependency `org.springframework.modulith:spring-modulith-docs`, có thể sinh tài liệu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {
    @Test
    void writesModuleGraphAndCanvases() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

Đặt test vào package phù hợp với `ShopApplication` hoặc import lớp khởi động rõ ràng. `Documenter` tạo diagrams và application module canvas trong vùng output của build. Canvas hữu ích vì liệt kê Spring components, events được nghe/phát, cấu hình liên quan; từ đây nhóm phát triển mới đối chiếu với danh sách **API đáng quan sát**.

| Nguồn | Thông tin hữu ích | Giới hạn |
| --- | --- | --- |
| `ApplicationModules.of(...)` | Module model, beans, exposed types, quan hệ phụ thuộc | Phân tích code, không thể hiện traffic thực tế. |
| `ApplicationModules.verify()` | Lỗi kiến trúc: vòng phụ thuộc, internal access, allowed dependencies | Không phát hiện exporter/sampling hoặc runtime AOP bị thiếu. |
| `Documenter` / module canvas | Sơ đồ, Spring beans, listener, sự kiện, cấu hình | Là tài liệu build, không là một trace. |
| `/actuator/modulith` | Module identifiers, base package, dependencies tại runtime | Không phải danh sách mọi method đã instrument. |
| Tracing backend | Spans thực tế theo request/transaction, module tags, duration | Sampling/propagation có thể khiến một tương tác không hiển thị. |

Đặc biệt, nếu dự án có chiến lược phát hiện module tùy chỉnh thì phải bảo đảm cấu hình đó **có mặt trong production sources**. Nếu chỉ dùng test configuration, module graph lúc build và Actuator/observability ở runtime có thể khác nhau.

## 7. Bật observability và các thành phần đường truyền

Spring Modulith cung cấp hỗ trợ quan sát module; Spring Boot/Micrometer cung cấp đường đo và xuất telemetry. Ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    // BOM phiên bản Modulith phải khớp Spring Boot đang dùng.
    // Nếu Spring Boot BOM đã quản lý Modulith, có thể dùng quản lý sẵn.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Dùng cho các test kiến trúc và tài liệu ví dụ trên.
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-docs'

    // Thêm tracer bridge / exporter hoặc tracing starter tương thích
    // với đúng nhánh Spring Boot nếu muốn xuất spans ra backend.
}
~~~

`spring-modulith-starter-insight` gồm Actuator và hỗ trợ observability. Nếu chỉ cần quan sát module, có thể dùng artifact `spring-modulith-observability-core` tương ứng; khi muốn Actuator graph dùng `spring-modulith-actuator` và Spring Boot Actuator. Ở nhánh Spring Modulith cũ (ví dụ 1.x), tên artifact observability có thể khác. **Không trộn tên artifact từ các nhánh khác nhau** và không giả định Insight tự cài sẵn collector/tracing backend.

Ví dụ cấu hình staging đơn giản để kiểm tra Actuator và sampling:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith,metrics"
  tracing:
    sampling:
      probability: 1.0
~~~

`management.tracing.sampling.probability=1.0` chỉ nên dùng cho **kiểm thử có kiểm soát**. Endpoint `/actuator/modulith` cần phù hợp với thiết lập availability/exposure/security của Spring Boot và chỉ truy cập trong mạng được bảo vệ. Để đưa span ra Zipkin, Tempo hoặc Collector, cấu hình tracer/exporter, endpoint OTLP/Zipkin và credentials theo phiên bản Boot thực tế. **Có instrumentation ở ứng dụng không đồng nghĩa exporter đã thành công.**

Lưu ý thêm: `@Observed` hoặc một observation thủ công có thể hữu ích để đo nghiệp vụ sâu, nhưng không bắt buộc để mọi Spring component thuộc module API có module-entry observation do Spring Modulith cung cấp.

## 8. Chọn nhãn và granularity phù hợp

Spring Modulith module-entry spans có các tag/attribute hữu ích:

| Thuộc tính | Ý nghĩa | Cách dùng khi điều tra |
| --- | --- | --- |
| `module.identifier` | Định danh kỹ thuật của module | Nhóm spans theo `orders`, `inventory`, `payments`. |
| `module.name` | Tên module dùng để hiển thị | Hiểu module nghiệp vụ trong trace. |
| `module.method` | Method được thực thi | Xác định điểm vào API nào chậm hoặc lỗi. |
| `module.invocation-type` | Kiểu gọi, ví dụ `bean` hoặc `event listener` | Phân biệt lời gọi đồng bộ và xử lý sự kiện. |

Khi thiết kế thêm attributes và metrics:

- Dùng tag thấp cardinality như `module.identifier`, `operation` dạng tập giá trị cố định, `outcome`, `event.type`.
- Tránh `orderId`, email, access token, số thẻ, payload XML/JSON hoặc exception message chứa dữ liệu nhạy cảm trong **metric labels**.
- Nếu cần tương quan một yêu cầu, ưu tiên trace ID và log correlation đã kiểm soát quyền. Với span attribute có thể cân nhắc ID nghiệp vụ đã được xử lý theo chính sách dữ liệu, nhưng không biến ID đó thành metric tag.
- Đo **boundary duration** bằng span; đo số lượng event/operation bằng counter; đo backlog, thời gian chờ của listener bằng metric tùy chỉnh nếu thực sự phục vụ SLO.
- Với một workflow có ít nhánh, số span cần thiết thường thấp hơn số method của cả module. Không instrument sâu vô hạn vì làm trace khó đọc và tăng chi phí xuất/lưu trữ.

### Thêm observation khi phải xem một bước nội bộ

Giả sử `inventory.internal.StockPolicy` tính toán phương án giữ hàng lâu hơn đáng kể. Nếu đội vận hành cần biết riêng bước này, hãy tạo Observation **nội bộ**, không expose policy ra `inventory` base package:

~~~java
// Phần minh họa trong implementation của inventory module.
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

class StockCalculation {
    private final ObservationRegistry observations;

    StockCalculation(ObservationRegistry observations) {
        this.observations = observations;
    }

    void runCalculation() {
        Observation.createNotStarted("inventory.stock.calculation", observations)
                .observe(() -> {
                    // Logic tính toán của module (lược giản).
                });
    }
}
~~~

Đoạn này chỉ mô tả cách tạo span/observation thủ công; dự án thực cần đăng ký `StockCalculation` thành Spring bean hoặc inject đúng cách qua bean khác. Nếu chỉ tạo Java object bằng `new` mà không truyền `ObservationRegistry`, cơ chế này không hoạt động. Đừng tạo observation thủ công trùng lặp một cách không cần thiết với module-entry span.

## 9. Kiểm thử xem module API có thực sự được instrument

Sau khi xác minh kiến trúc bằng unit test, dùng một ứng dụng **chạy đầy đủ runtime configuration** để kiểm tra hành vi. Có thể dùng môi trường staging với sampling 100% ngắn hạn, tracer/exporter và backend thật hoặc Collector kiểm thử. Một `@SpringBootTest` mặc định không nhất thiết tự xuất trace ra backend theo cách ứng dụng production thực hiện.

### Kịch bản 1 — Lời gọi bean API đồng bộ

**Input:** gửi `POST /orders` chứa dữ liệu thử hợp lệ, điều hướng tới `OrderManagement.placeOrder(...)`; method gọi `InventoryOperations.reserve(...)`.

**Kỳ vọng:**

1. HTTP server span xuất hiện khi có Spring Boot HTTP instrumentation.
2. Có module-entry observation/span cho API bean được Spring Modulith intercept, bao gồm module identifier, method và invocation type thích hợp.
3. `inventory` có dấu vết khi được gọi qua Spring bean `InventoryOperations`, thời lượng không bị tính nhầm với xử lý HTTP/DB.
4. Nếu gọi method nội bộ trong `OrderManagement` bằng `this.helper()` mà không thấy span riêng, đó có thể là hành vi hợp lệ của interception bằng proxy; không sửa bằng cách làm `helper` thành API.

### Kịch bản 2 — Domain event và listener

**Input:** thực hiện tác vụ tạo `OrderPlaced` với transaction hợp lệ, để `PaymentEventListener` nhận sự kiện.

**Kỳ vọng:**

1. `module.events.published` tăng sau khi event thực sự được phát.
2. Counter theo module/type event hiển thị khi có registry thu thập.
3. Listener đã xử lý như dự kiến; nếu có Event Publication Registry, đối chiếu trạng thái hoàn tất với kết quả nghiệp vụ.
4. Với tracing được bật, kiểm tra event-listener span nếu cấu hình/version hỗ trợ. Nếu listener async chạy sau commit, sự liên kết trace phụ thuộc cơ chế truyền context.
5. Dữ liệu trên dashboard chỉ được xem là đạt khi kiểm chứng thời gian và service filter phù hợp, kể cả chu kỳ xuất metric và sampling.

Truy vấn Actuator tại cổng quản trị nội bộ (ví dụ `19090`):

~~~bash
curl -fsS http://localhost:19090/actuator/health
curl -fsS http://localhost:19090/actuator/modulith
curl -fsS http://localhost:19090/actuator/metrics/module.events.published
~~~

`/actuator/modulith` trả về **module graph** (tên module, base package, dependencies), **không phải endpoint liệt kê mọi API method được instrument**. Dùng output đó để đối chiếu module identifier và cạnh phụ thuộc với trace. Cổng, HTTP base path và quyền truy cập được quyết định bởi cấu hình ứng dụng.

### Kịch bản 3 — Ranh giới bất đồng bộ

Với `@ApplicationModuleListener`, lời gọi listener xảy ra bất đồng bộ và trong transaction riêng. Kiểm tra:

- Trace có `orders` và `payments` hay chỉ có từng span ở các trace khác nhau?
- Có `traceId`/`spanId` tương ứng trong log đã cấu hình không, và backend có nhận đúng trace không?
- Executor được cấu hình bằng `ContextPropagatingTaskDecorator` / Micrometer Context Propagation hoặc cơ chế tương thích hay chưa?
- Nếu luồng đi qua Reactor, broker hoặc HTTP client, các header/Context cần thiết có được truyền đúng không?
- Lỗi listener có hiện ở event publication state hoặc retry queue không, dù counter đã tăng?

**Không đồng nhất “không thấy span liên kết” với “event bị mất”.** Nguồn dữ liệu, event handling, trace context và đường export phải được kiểm tra độc lập.

## 10. Khi nào không nên instrument module API một cách tự động?

### (a) Module quá mở

Trong một legacy module dùng `@ApplicationModule(type = OPEN)`, nhiều type ở internal packages có thể được expose theo cơ chế open module. Đây thường là lựa chọn chuyển đổi tạm thời, không phải dấu hiệu mọi class đều là API có giá trị nghiệp vụ. Nếu trace quá ồn, **xem lại thiết kế ranh giới**, chuyển dần sang closed module với named interfaces rõ ràng, sau đó đo lại. Không vội filter mất các luồng nghiệp vụ quan trọng.

### (b) Có quá nhiều phương thức nội bộ

`OrderPricing.calculate()` chạy trong `orders` không nhất thiết phải là API. Chỉ vì muốn nhìn chi tiết performance không nên chuyển nó ra base package hoặc tạo `@NamedInterface`. Sử dụng Observation nội bộ có tên rõ ràng khi đã chứng minh đây là nút nghẽn.

### (c) API có tần suất rất cao

Một API gọi hàng chục nghìn lần/giây có thể sinh số span lớn, tạo chi phí sampling/processing và che khuất các hoạt động quan trọng khác. Giữ ranh giới kiến trúc vì đúng nghiệp vụ, rồi dùng chính sách sampling và exporter phù hợp với tải. Tránh “định nghĩa lại module API” chỉ để giảm số lượng telemetry.

### (d) Tên method hoặc dữ liệu nhạy cảm

Đo độ trễ và trạng thái lỗi không đòi hỏi đưa dữ liệu khách hàng lên trace. Đánh giá span names, attributes, event tags và cấu hình exception recording để tránh lộ thông tin. Hệ thống thanh toán phải đặc biệt thận trọng với token, card data và payload riêng tư.

## 11. Xử lý các tình huống không nhìn thấy module spans

| Triệu chứng | Giả thuyết phù hợp | Cách xác minh |
| --- | --- | --- |
| `/actuator/modulith` có modules nhưng trace chỉ có HTTP span | Chưa có observability support, tracer bridge/exporter hoặc component không thuộc API được instrument | Đối chiếu runtime dependency, module model và trace sampling; gọi một bean API thật. |
| `orders` có span, `inventory` không có | Bean ở `inventory.internal`, lời gọi không qua proxy, bean không được quản lý hoặc API không được nhận diện | Kiểm tra vị trí type, `ApplicationModules`, injection qua Spring, kiểu proxy và lời gọi thực. |
| API của module xuất hiện trong code nhưng `verify()` báo lỗi | Phụ thuộc đi vào internal package, hoặc `allowedDependencies` không cho phép | Chuyển sang public API/named interface đúng mục đích và kiểm chứng lại. |
| Graph ở test khác graph tại runtime | Custom module detection chỉ đặt ở test source hoặc artifact không đồng nhất | Đặt strategy trong production sources, kiểm tra build artifact và context. |
| Có module spans nhưng không có trên dashboard | Exporter, sampling, Collector/tenant hoặc filter thời gian | Theo dõi app → exporter → Collector → backend; kiểm tra trace ID. |
| Event publication counter tăng nhưng không có listener span | Listener chưa chạy, lỗi, không được instrument hoặc async context mất | Xác minh listener delivery, trạng thái publication, proxy, context propagation. |
| Listener xử lý thành công nhưng tách sang trace khác | Thread hop/broker không giữ context hoặc tracing policy | Kiểm tra executor, task decorator, trace propagation/links. |
| Span số lượng quá lớn và nhiều tên khó đọc | Module API quá rộng hoặc đo trùng ở nhiều tầng | Kiểm tra cấu trúc module, lọc/định nghĩa observation có chủ đích, áp dụng sampling. |

**Mấu chốt về Spring AOP:** `@Service` tạo bean nhưng không bảo đảm mọi lời gọi tới bean được aspect chặn. Những tình huống như `new InventoryOperations()`, self-invocation, method final hoặc visibility/proxy không tương thích thường làm thay đổi kết quả. Đừng đánh dấu “instrumented” trên sơ đồ thiết kế khi chưa có bằng chứng từ request runtime.

## 12. Mẫu quyết định và tiêu chí nghiệm thu

Một bảng thiết kế trước khi bật quan sát giúp thống nhất trách nhiệm giữa developer, kiến trúc sư và vận hành:

| Mục cần ghi | Ví dụ: `inventory` | Vì sao quan trọng |
| --- | --- | --- |
| Module identifier | `inventory` | Đối chiếu graph, span tags, metric labels. |
| Exposed API | `InventoryOperations.reserve` | Ranh giới hỗ trợ nghiệp vụ. |
| Caller | `orders.OrderManagement.placeOrder` | Nối luồng xuyên module. |
| Kiểu tích hợp | Lời gọi bean đồng bộ | Dự đoán thời lượng và trace linkage. |
| Quan sát mặc định | Module-entry span | Xác định module và method. |
| Đo bổ sung | Reservation rejected count, nếu có SLO | Phân biệt lỗi nghiệp vụ và lỗi hạ tầng. |
| Tags an toàn | `module.identifier`, `outcome` | Tránh độ lớn nhãn khó kiểm soát. |
| Dữ liệu không ghi | SKU/khách hàng/order ID trong metric tags | Giới hạn cardinality và rò thông tin. |
| Phép thử | Đơn hàng hợp lệ và số lượng không hợp lệ | Kiểm tra cả success/error path. |
| Nghiệm thu | Có trace/span đúng module khi gọi API trong môi trường kiểm thử | Chứng minh instrumentation hoạt động. |

### Tiêu chí hoàn thành thiết kế

1. **Ranh giới module đúng:** `ApplicationModules.verify()` thành công; không có phụ thuộc sang internal package hoặc vòng phụ thuộc không mong muốn.
2. **API có chủ ý:** Spring bean public được expose qua base package/named interface phù hợp; không mở rộng API để thỏa yêu cầu telemetry.
3. **Graph và tài liệu đồng nhất:** diagram và module canvas thể hiện đúng các module, dependencies và event contracts quan trọng.
4. **Instrumentation đúng đối tượng:** phép gọi bean API và luồng event được kiểm tra trên runtime với đúng dependency.
5. **Tín hiệu có thể truy vấn:** spans/metrics đến backend, hiển thị module identifiers, method/event types theo kỳ vọng và không chứa dữ liệu nhạy cảm.
6. **Async có giải thích:** nếu listener tạo trace mới hoặc span link, nguyên nhân và cơ chế propagation đã được kiểm chứng.
7. **Có kế hoạch bảo trì:** sau khi thêm/bớt API hoặc đổi package, cập nhật danh sách điểm cần đo và test hồi quy.

## 13. Bài tập thực hành

**Đề bài:** Một hệ thống bán vé có ba module `booking`, `seating` và `billing`. Code hiện tại cho phép `booking` gọi trực tiếp `seating.internal.SeatAllocator` và chỉ trace HTTP controller. `booking` phát event `TicketBooked`, listener `billing` xử lý bất đồng bộ.

Hãy thực hiện trên sơ đồ và một project mẫu:

1. Đề xuất API rõ ràng trong `seating` (ví dụ `SeatReservationService.reserve` tại base package), chuyển lời gọi của `booking` sang API đó.
2. Đặt `TicketBooked` trong package sự kiện được expose qua `@NamedInterface("events")`; chỉ cho `billing` phụ thuộc vào `booking::events` nếu đây là contract cần dùng.
3. Chạy `ApplicationModules.verify()`; sinh module diagram/canvas để chứng minh `booking` không chọc vào `seating.internal`.
4. Bật Spring Modulith observability và tracing exporter phù hợp phiên bản, rồi tạo một giao dịch đặt vé.
5. Quan sát module-entry span cho API `seating`, event publication counter của `booking` và trạng thái xử lý của listener `billing`.
6. Tạo tình huống `SeatReservationService.reserve` từ chối do hết ghế. Đảm bảo lỗi ở đúng bước, không ghi thông tin khách hàng vào metric tags.
7. Thử chạy listener async và giải thích vì sao span `billing` có thể tách sang trace khác nếu context propagation thiếu.

**Tiêu chí đạt:** sửa ranh giới trước, sau đó mới cấu hình và đo telemetry; có sơ đồ kiến trúc hợp lệ, trace có module identifiers phù hợp và bảng kiểm kết quả phát/nhận event; mô tả rõ trường hợp không thể có span vì lời gọi không đi qua Spring proxy.

## 14. Ghi nhớ và tài liệu đối chiếu

- **Module API** là hợp đồng module cung cấp ra bên ngoài, gồm Spring bean được expose và application events; REST endpoint hoặc một Java `public` trong `internal` không tự động là API module.
- **Spring Modulith observability** tự trang trí các Spring component thuộc API module để tạo module-entry observations/spans tại các lời gọi được intercept. Không cần expose toàn bộ implementation để có khả năng quan sát.
- **`@NamedInterface`** mở một phần contract có chủ ý; **`allowedDependencies`** giới hạn phụ thuộc và được kiểm tra bằng `verify()`; chúng không trực tiếp cấu hình exporter.
- **Module graph/Documenter** mô tả kiến trúc tĩnh; **metrics/traces** mô tả hoạt động runtime. Cần cả hai để kiểm chứng kiến trúc mô-đun.
- **Event publication metric** phản ánh sự kiện đã công bố; kết quả listener và truyền trace context phải được kiểm chứng riêng.
- Khi thiếu span, kiểm tra **API model → Spring bean/proxy → instrumentation → tracing bridge/sampling → exporter → backend** trước khi sửa cấu trúc code.

Tài liệu chính thức:

1. [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): base package, exposed API, named interfaces và allowed dependencies.
2. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight starter, module-entry spans, các tag `module.*` và event metrics.
3. [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): diagrams, Application Module Canvas và `Documenter`.
4. [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm thử phụ thuộc giữa các module với `ApplicationModules.verify()`.
5. [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `@ApplicationModuleListener`, event publication registry và xử lý bất đồng bộ.
6. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation, propagation và instrumentation.
7. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, sampler và exporter.

Hãy đối chiếu tài liệu và API của **phiên bản Spring Boot/Spring Modulith thực tế được khóa trong build**. Tên starter, cách thiết lập tracer/exporter và behavior của các hook có thể khác giữa các nhánh; không đánh giá một thiết kế chỉ bằng việc span có xuất hiện ở một dashboard hay không.
