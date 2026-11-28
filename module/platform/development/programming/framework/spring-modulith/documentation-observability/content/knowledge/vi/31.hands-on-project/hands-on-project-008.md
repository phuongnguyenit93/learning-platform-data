# Tùy biến convention bằng ModulithObservationConvention

> **Chương:** Thực hành tổng hợp
>
> **Phạm vi:** Spring Modulith Documentation & Observability trên Spring Boot. Xây dựng một convention cho observation tại ranh giới application module, bổ sung nhãn nghiệp vụ có số giá trị hữu hạn, bảo toàn nhãn mặc định, kiểm tra kết quả qua unit test, Actuator và tracing backend.

## 1. Bài toán và kết quả cần đạt

Một ứng dụng thương mại điện tử gồm ba application module: `orders`, `inventory` và `payments`. Nhóm phát triển đã dùng Spring Modulith để kiểm tra phụ thuộc, tạo module graph và bật quan sát các lời gọi xuyên module. Trong trace, các span có những nhãn kỹ thuật như `module.identifier`, `module.name` và `module.invocation-type`. Đội vận hành muốn nhóm các module theo lĩnh vực nghiệp vụ để trả lời câu hỏi: “Lỗi và độ trễ đang xuất hiện nhiều ở nhóm xử lý đơn hàng hay thanh toán?”.

Ta sẽ thêm nhãn **`business.area`** với tập giá trị có kiểm soát:

| Module identifier | `business.area` | Ý nghĩa |
| --- | --- | --- |
| `orders` | `fulfillment` | Xử lý đơn hàng |
| `inventory` | `fulfillment` | Quản lý tồn kho |
| `payments` | `billing` | Thanh toán |
| Module khác | `other` | Nhóm dự phòng |

Tập giá trị này được định nghĩa trong mã, không đọc từ order ID, customer ID, URL hay payload. Việc gắn nhãn giúp phân tích telemetry xuyên module nhưng **không thay đổi ranh giới kiến trúc, logic nghiệp vụ hoặc mô hình dữ liệu**.

Sau bài này, bạn có thể:

1. Xác định đúng vai trò của `ModulithObservationConvention`, `ModulithContext` và Micrometer `ObservationConvention`.
2. Tạo một class Java triển khai convention, giữ giá trị mặc định và bổ sung low-cardinality key value.
3. Đăng ký convention thành **một Spring bean** để Spring Modulith sử dụng cho module observations.
4. Viết bài kiểm thử trực tiếp cho logic nhãn và kiểm tra hành vi thực tế bằng trace.
5. Phân biệt convention của **module invocation observation** với tùy biến **domain-event metrics**.
6. Chẩn đoán khi nhãn không xuất hiện hoặc khiến hệ thống telemetry quá tải.

**Phiên bản áp dụng của ví dụ:** Spring Modulith **2.2.0** cùng một phiên bản Spring Boot 4.x tương thích. Những nhánh khác có thể khác tên artifact, package, annotation null-safety và cấu hình exporter; hãy kiểm tra dependency/Javadoc của phiên bản thực tế trước khi sao chép.

## 2. Convention nằm ở đâu trong kiến trúc quan sát?

Spring Modulith phát hiện các application module từ cấu trúc package và các quy tắc module, sau đó trang trí Spring component thuộc **module API** để quan sát việc gọi vào chúng. Micrometer sử dụng `Observation` và `ObservationConvention` để xác định **tên** và **key-values** cho những observation ấy. Khi có tracing handler/exporter phù hợp, observation trở thành span có thể được gửi tới hệ thống như Zipkin hoặc Grafana Tempo.

~~~mermaid
flowchart TD
    A["ApplicationModules: orders, inventory, payments"] --> B["Module API Spring beans"]
    B --> C["Spring Modulith module-entry instrumentation"]
    C --> D["ModulithContext"]
    D --> E["ModulithObservationConvention"]
    E --> F["Micrometer ObservationRegistry"]
    F --> G["Tracing bridge / ObservationHandler"]
    F --> H["MeterRegistry khi áp dụng handler/metric phù hợp"]
    G --> I["Trace exporter / Collector"]
    I --> J["Tracing backend"]
    K["Application event publication"] --> L["Modulith event counters"]
    L --> H
~~~

Hai luồng ở đây có vai trò khác nhau: `ModulithObservationConvention` mô tả tên/nhãn của **observation thuộc module invocation**, còn Spring Modulith có các bộ đếm riêng cho **application events**. Việc thay convention không đồng nghĩa đã đổi nhãn của mọi `module.events.published` counter.

### 2.1. Bốn phương thức thường gặp

`ModulithObservationConvention` thuộc package:

~~~java
org.springframework.modulith.observability.ModulithObservationConvention
~~~

Trong nhánh 2.2, interface này kế thừa `ObservationConvention<ModulithContext>`, có các phương thức mặc định:

| Phương thức | Vai trò | Khuyến nghị |
| --- | --- | --- |
| `getName()` | Tên observation dùng bởi Micrometer; mặc định `module.invocations`. | Giữ mặc định trừ khi chủ động quản lý đổi tên và dashboard. |
| `getContextualName(ModulithContext context)` | Tên hiển thị theo ngữ cảnh, thường được dùng làm tên span. | Có thể bổ sung prefix ổn định; không đưa request ID vào tên. |
| `getLowCardinalityKeyValues(context)` | Nhãn có tập giá trị hữu hạn, phù hợp cho metric aggregation. | Thêm `business.area` và giữ nhãn `module.*` mặc định. |
| `getHighCardinalityKeyValues(context)` | Thông tin phân biệt chi tiết hơn, phù hợp với trace khi exporter cho phép. | Giữ mặc định; chỉ thêm dữ liệu có chính sách riêng tư rõ ràng. |
| `supportsContext(Observation.Context)` | Xác định convention áp dụng được với kiểu context nào. | Giữ mặc định để chỉ xử lý `ModulithContext`. |

`ModulithContext` cung cấp `getModule()`, `getInvocation()`, `getApplicationName()`, `getLowCardinalityValues()`, `getHighCardinalityValues()` và `getContextualName()`. Giá trị `getModule().getIdentifier()` là định danh module mà Spring Modulith nhận diện, không phải tên service trong hệ thống tracing.

**Phân chia nhãn mặc định:** `module.identifier`, `module.name` và `module.invocation-type` là các low-cardinality keys; `module.method` được công bố là high-cardinality key trong tài liệu API. Giữ chúng giúp dashboard và truy vấn hiện có vẫn hiểu được ý nghĩa observation sau khi tùy biến.

## 3. Chuẩn bị dự án thực hành

Giả sử ứng dụng dùng Java 21, Gradle Groovy DSL, lớp khởi động `com.example.shop.ShopApplication` và có Spring Boot web starter. Ta dùng Spring Modulith Insight để có observability và Actuator runtime; dùng API observability ở **compile classpath** để biên dịch class convention.

### 3.1. Các dependency cần phân biệt

~~~groovy
dependencies {
    // Ví dụ với Spring Modulith 2.2.0.
    implementation platform("org.springframework.modulith:spring-modulith-bom:2.2.0")

    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.modulith:spring-modulith-observability-api"

    // Runtime instrumentation và actuator.
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"

    // Kiểm tra module model và tạo tài liệu trong test.
    testImplementation "org.springframework.modulith:spring-modulith-starter-test"
    testImplementation "org.springframework.modulith:spring-modulith-docs"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

Đây là **đoạn `dependencies`**, không phải toàn bộ `build.gradle`. Giả định Spring Boot Gradle plugin và dependency management đã được thiết lập. Trong dự án dùng Maven, tương ứng là dependency `spring-modulith-observability-api` ở compile scope và `spring-modulith-starter-insight` ở runtime scope; quản lý version bằng BOM tương thích.

Chỉ có Insight + Actuator chưa đủ để đẩy span ra backend: cần Micrometer Tracing, tracer và exporter như OpenTelemetry/Zipkin theo phiên bản Spring Boot. Ví dụ cấu hình tracer/collector nằm ở phần kiểm thử runtime, tách khỏi logic convention để không nhầm lỗi biên dịch API với lỗi gửi telemetry.

**Vì sao API phải có mặt lúc compile?** Class Java của ta `implements ModulithObservationConvention`, tham chiếu `ModulithContext` và return `KeyValues`. Nếu chỉ thêm `spring-modulith-starter-insight` ở `runtimeOnly` mà không có observability API trên compile classpath, compiler không nhận ra các kiểu của convention.

### 3.2. Cấu trúc package mục tiêu

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── ShopTelemetryConfiguration.java
├── ShopModulithObservationConvention.java
├── CheckoutController.java
├── orders/
│   ├── OrderManagement.java
│   └── OrderPlaced.java
├── inventory/
│   └── InventoryOperations.java
└── payments/
    └── PaymentListener.java

src/test/java/com/example/shop/
├── ShopModulithObservationConventionTests.java
└── ModuleArchitectureTests.java
~~~

Các class về **cấu hình và HTTP adapter** được đặt tại package gốc `com.example.shop` trong ví dụ, còn `orders`, `inventory` và `payments` là các application module được phát hiện theo cấu trúc con trực tiếp. Với dự án khác, nếu đặt `ShopTelemetryConfiguration` trong một package con mới, package ấy có thể trở thành một module; cần quyết định rõ thay vì vô tình làm đổi module graph.

## 4. Xây dựng luồng nghiệp vụ để tạo observation

Để kiểm tra custom convention, ta cần lời gọi thật đi vào Spring bean API của hai module. Ví dụ sau tối giản logic dữ liệu nhằm làm rõ luồng quan sát.

### 4.1. Inventory API

~~~java
// File: com/example/shop/inventory/InventoryOperations.java
package com.example.shop.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryOperations {

    public void reserve(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity < 1) {
            throw new IllegalArgumentException("Invalid reservation");
        }
        // Ví dụ học tập: ứng dụng thật sẽ cập nhật trạng thái tồn kho.
    }
}
~~~

`InventoryOperations` là Spring bean nằm tại **base package của module `inventory`** và được expose như một API theo quy tắc mặc định của Spring Modulith. Method `reserve` là ứng viên cho module-entry span khi được gọi qua Spring proxy.

### 4.2. Orders API và application event

~~~java
// File: com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {
}
~~~

~~~java
// File: com/example/shop/orders/OrderManagement.java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryOperations;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderManagement {

    private final InventoryOperations inventory;
    private final ApplicationEventPublisher events;

    public OrderManagement(InventoryOperations inventory,
                           ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    public void submit(String orderId, String sku, int quantity) {
        inventory.reserve(sku, quantity);
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Ví dụ cố ý không thêm transaction hay persistence. Vì vậy sự kiện `OrderPlaced` ở đây được phát đồng bộ thông qua `ApplicationEventPublisher`; trong hệ thống thật cần cân nhắc transaction boundary, xử lý lỗi và cơ chế event publication registry nếu cần độ tin cậy qua restart.

### 4.3. Listener và HTTP adapter

~~~java
// File: com/example/shop/payments/PaymentListener.java
package com.example.shop.payments;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentListener {

    @EventListener
    public void on(OrderPlaced event) {
        // Ví dụ học tập: ghi nhận một yêu cầu thanh toán.
        // Tránh log orderId hoặc payload nhạy cảm.
    }
}
~~~

~~~java
// File: com/example/shop/CheckoutController.java
package com.example.shop;

import com.example.shop.orders.OrderManagement;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CheckoutController {

    private final OrderManagement orders;

    CheckoutController(OrderManagement orders) {
        this.orders = orders;
    }

    @PostMapping("/checkout")
    String checkout(@RequestParam String orderId,
                    @RequestParam String sku,
                    @RequestParam int quantity) {
        orders.submit(orderId, sku, quantity);
        return "accepted";
    }
}
~~~

Gửi `POST /checkout?orderId=TEST-1&sku=BOOK-1&quantity=1` trong môi trường thử. Request đi từ adapter HTTP vào `orders`, gọi `inventory` rồi phát event đến listener `payments`. Chỉ dùng dữ liệu giả; trong production, tham số có định danh nghiệp vụ/khách hàng nên gửi qua body phù hợp thay vì để trên URL và log truy cập.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant A as CheckoutController
    participant O as orders.OrderManagement
    participant I as inventory.InventoryOperations
    participant E as Spring Event Bus
    participant P as payments.PaymentListener
    C->>A: POST /checkout (dữ liệu test)
    A->>O: submit(...)
    O->>I: reserve(...)
    I-->>O: Hoàn tất
    O->>E: publish OrderPlaced
    E->>P: on(OrderPlaced)
    O-->>A: Hoàn tất
    A-->>C: accepted
~~~

Các interaction vào Spring bean của module API là điểm cần kiểm tra trong tracing; publication của `OrderPlaced` còn có thể được đo bằng các metric sự kiện của Spring Modulith. Cần kiểm tra runtime để xác định bean, aspect và listener thực sự nằm trong phạm vi instrumentation của phiên bản đã khóa.

## 5. Tạo convention tùy chỉnh, bảo toàn mặc định

Đây là phần trọng tâm. Ta sẽ:

1. Triển khai `ModulithObservationConvention` từ API của **Spring Modulith 2.2.0**.
2. Gọi default implementation của interface để lấy **toàn bộ low-cardinality key-values gốc**.
3. Dựa vào **module identifier hữu hạn**, ánh xạ sang `business.area`.
4. Bổ sung key bằng `KeyValues.and(...)`, vốn trả về tập bất biến mới.
5. Giữ mặc định `getName()`, `getHighCardinalityKeyValues(...)` và `supportsContext(...)`.

~~~java
// File: com/example/shop/ShopModulithObservationConvention.java
package com.example.shop;

import io.micrometer.common.KeyValues;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

final class ShopModulithObservationConvention
        implements ModulithObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(ModulithContext context) {

        // Giữ module.identifier, module.name, module.invocation-type mặc định.
        KeyValues defaults =
                ModulithObservationConvention.super.getLowCardinalityKeyValues(context);

        String identifier = context.getModule().getIdentifier().toString();
        String businessArea = areaFor(identifier);

        // Chỉ thêm key mới; không làm mất nhãn của Modulith.
        return defaults.and("business.area", businessArea);
    }

    @Override
    public String getContextualName(ModulithContext context) {
        // Giữ tên theo module/method, chỉ thêm prefix cố định.
        return "shop " +
                ModulithObservationConvention.super.getContextualName(context);
    }

    static String areaFor(String moduleIdentifier) {
        return switch (moduleIdentifier) {
            case "orders", "inventory" -> "fulfillment";
            case "payments" -> "billing";
            default -> "other";
        };
    }
}
~~~

Phần `getContextualName(...)` là **tùy chọn**: nếu không muốn đổi tên span hiển thị, bỏ hẳn override này. Bằng cách giữ `getName()` mặc định, tên observation ổn định (`module.invocations`); đổi tên mặc định có thể làm các meter/dashboard hiện tại không tìm thấy dữ liệu hoặc tạo chuỗi số liệu mới. Không đưa `orderId`, `sku`, exception message hay input method vào tên observation.

### Giải thích từng thành phần

| Thành phần | Tác dụng | Rủi ro nếu làm sai |
| --- | --- | --- |
| `ModulithObservationConvention.super.getLowCardinalityKeyValues(context)` | Giữ key-values chuẩn do `ModulithContext` cung cấp | Nếu trả về chỉ `business.area`, mất `module.identifier` và các key gốc. |
| `context.getModule().getIdentifier()` | Lấy định danh module do Spring Modulith phát hiện | Không nên tự suy tên module từ request path hoặc đối số runtime. |
| `areaFor(...)` | Ánh xạ module sang nhóm hữu hạn | Không lấy trực tiếp từ mã đơn hàng, khách hàng hay input tuỳ ý. |
| `defaults.and("business.area", businessArea)` | Thêm một low-cardinality key | Tránh dùng key có sẵn với ý nghĩa khác; trùng key có thể làm thay giá trị mặc định. |
| `getContextualName(...)` | Điều chỉnh tên hiển thị của observation/span | Prefix động làm trace khó nhóm, gây số lượng tên rất lớn. |

Không có phần nào trong code trên thay đổi `ApplicationModules.verify()`, định nghĩa named interface, điểm AOP được chọn, sampling hay OTLP exporter. **Convention quyết định cách mô tả observation, không quyết định có intercept lời gọi hay không**.

### Vì sao dùng low-cardinality cho business.area?

Trong bài này `business.area` chỉ có ba giá trị: `fulfillment`, `billing` và `other`. Nó là nhãn nghiệp vụ ổn định để nhóm dữ liệu. Nếu thay bằng `order.id` hoặc `customer.email`, mỗi request có thể tạo một bộ nhãn mới, khiến hệ thống metrics tăng cardinality, tốn bộ nhớ và chi phí lưu trữ; đồng thời có nguy cơ lộ dữ liệu cá nhân.

Các key có ý nghĩa và cardinality khác nhau:

| Loại | Ví dụ | Cách dùng |
| --- | --- | --- |
| Low-cardinality | `module.identifier`, `module.name`, `module.invocation-type`, `business.area` | Nhóm/bộ lọc có số giá trị hữu hạn. |
| High-cardinality mặc định | `module.method` | Chi tiết method trên trace; không tự đẩy thành metric label nếu không có lý do rõ ràng. |
| Dữ liệu cần tránh | ID khách hàng, token, số thẻ, toàn bộ payload, URL có thông tin nhạy cảm | Không đưa vào convention; xem chính sách thu thập dữ liệu riêng. |

## 6. Đăng ký convention thành bean của Spring

Spring Modulith reference hướng dẫn cung cấp một bean kiểu `ModulithObservationConvention` để thay convention mặc định.

~~~java
// File: com/example/shop/ShopTelemetryConfiguration.java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
class ShopTelemetryConfiguration {

    @Bean
    ModulithObservationConvention modulithObservationConvention() {
        return new ShopModulithObservationConvention();
    }
}
~~~

**Chỉ có một bean convention mục tiêu** trong application context của ví dụ. Nếu bạn đã có cấu hình từ module khác cung cấp cùng kiểu, hãy kiểm tra quy tắc auto-configuration và lỗi nhiều bean trước khi thêm mới; không dùng `@Primary` hoặc `@ConditionalOnMissingBean` một cách máy móc để che giấu xung đột không rõ nguồn.

Ngoài ra:

- Class `@Configuration` phải thuộc component scan của Spring Boot. Đặt tại package gốc `com.example.shop` là phương án rõ ràng cho project mẫu.
- Trường hợp ứng dụng có nhiều `ApplicationContext`, hãy xác minh bean được tạo trong context đang thực hiện Modulith instrumentation.
- Nếu chỉ tạo `new ShopModulithObservationConvention()` trong unit test mà không khai báo bean runtime, Spring Modulith sẽ không tự động biết tới tùy biến đó.
- Giữ phiên bản Modulith API và runtime implementation đồng bộ; việc import một interface khác package theo tài liệu cũ có thể dẫn tới `ClassNotFoundException`/`NoSuchMethodError` sau nâng cấp.

## 7. Kiểm chứng sớm bằng unit test

Để kiểm tra đúng **logic convention** trước khi chạy telemetry, có thể mock `ModulithContext` và `ObservedModule`. Đây là phép thử cô lập, dùng JUnit 5 và Mockito từ `spring-boot-starter-test` của phiên bản Boot tương ứng.

~~~java
// File: com/example/shop/ShopModulithObservationConventionTests.java
package com.example.shop;

import io.micrometer.common.KeyValues;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ObservedModule;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ShopModulithObservationConventionTests {

    private final ShopModulithObservationConvention convention =
            new ShopModulithObservationConvention();

    @Test
    void addsAreaWithoutLosingDefaultModuleKeys() {
        var context = mock(ModulithContext.class);
        var module = mock(ObservedModule.class);

        when(context.getModule()).thenReturn(module);
        when(module.getIdentifier())
                .thenReturn(ApplicationModuleIdentifier.of("orders"));
        when(context.getLowCardinalityValues()).thenReturn(KeyValues.of(
                "module.identifier", "orders",
                "module.name", "Orders",
                "module.invocation-type", "bean"));

        KeyValues result = convention.getLowCardinalityKeyValues(context);

        assertEquals("fulfillment", value(result, "business.area"));
        assertEquals("orders", value(result, "module.identifier"));
        assertEquals("Orders", value(result, "module.name"));
        assertEquals("bean", value(result, "module.invocation-type"));
    }

    @Test
    void sendsUnrecognizedModuleToBoundedFallback() {
        assertEquals("other",
                ShopModulithObservationConvention.areaFor("reporting"));
        assertEquals("billing",
                ShopModulithObservationConvention.areaFor("payments"));
    }

    @Test
    void keepsDefaultObservationName() {
        assertEquals("module.invocations", convention.getName());
    }

    private static String value(KeyValues values, String key) {
        return values.stream()
                .filter(it -> it.getKey().equals(key))
                .map(it -> it.getValue())
                .findFirst()
                .orElseThrow();
    }
}
~~~

`ModulithContext` và `ObservedModule` đã được mock nên phép thử không cần khởi động Spring Boot. Giá trị `module.*` được stub có chủ đích để khẳng định code **không loại bỏ các nhãn mặc định**. Phép thử chưa chứng minh bean runtime được nạp hoặc exporter gửi span; đó là nhiệm vụ của kiểm thử ở phần 9.

Nếu muốn kiểm tra `getContextualName`, có thể stub `context.getContextualName()` thành một giá trị cố định rồi xác nhận prefix `shop ` được thêm đúng một lần. Khi tên contextual là thành phần của dashboard hoặc truy vấn, nên có test hồi quy để phát hiện việc đổi tên ngoài ý muốn.

### Bổ sung kiểm tra mô hình module

Tạo một test riêng để xác nhận graph/module API mẫu hợp lệ:

~~~java
// File: com/example/shop/ModuleArchitectureTests.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra phụ thuộc giữa các module và ranh giới API ở source. Nó **không phải test exporter hoặc convention**. Nếu bài kiểm tra kiến trúc chưa đạt, hãy sửa model module rồi mới kiểm tra trace, vì danh sách Spring bean được instrument phụ thuộc module model đã phát hiện.

## 8. Quan sát ở runtime và xác minh tên/nhãn

Chạy ứng dụng mẫu với cấu hình Actuator/tracing phù hợp phiên bản. Một cấu hình kiểm thử tối giản:

~~~yaml
# application-staging.yaml; dùng trong môi trường kiểm thử có kiểm soát.
spring:
  application:
    name: shop

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
  tracing:
    sampling:
      probability: 1.0
~~~

`management.tracing.sampling.probability=1.0` dùng **tạm** để bảo đảm request test được sample; không áp dụng mặc định cho production có lưu lượng lớn. Spring Modulith Insight không tự tạo backend lưu trace. Muốn quan sát span tại Zipkin/Tempo/Collector, thêm đúng tracing bridge/exporter và endpoint theo phiên bản Spring Boot. Nếu sử dụng OpenTelemetry, nhớ cấu hình exporter và receiver phù hợp với OTLP/HTTP hoặc gRPC; đừng chỉ trỏ host rồi giả định tín hiệu đã tới nơi.

### Trình tự kiểm tra

1. Khởi động đúng executable JAR/profile và xác nhận class `ShopTelemetryConfiguration` được Spring scan.
2. Truy vấn `/actuator/modulith` để đối chiếu identifiers `orders`, `inventory`, `payments` và các cạnh phụ thuộc trong graph.
3. Gọi HTTP API thử bằng dữ liệu giả. Lặp lại một số lần và quan sát traces của `service.name=shop`.
4. Tìm các **module-entry spans** khi code đi vào `orders`, `inventory`; kiểm tra span của listener nếu phiên bản/đường xử lý đang được instrument.
5. Xác minh có `business.area=fulfillment` tại span `orders` và `inventory`, `business.area=billing` tại span `payments` nếu có observation được tạo.
6. Đối chiếu các keys có trước: `module.identifier`, `module.name`, `module.invocation-type` và `module.method` (high cardinality); kiểm tra tên contextual có prefix `shop ` nếu giữ override.
7. So kết quả trước/sau thay convention trên cùng một đường request để phát hiện mất nhãn chuẩn hoặc tăng số lượng nhãn ngoài ý muốn.

Ví dụ gửi request:

~~~bash
curl -X POST "http://localhost:8080/checkout?orderId=TEST-1&sku=BOOK-1&quantity=1"

# Actuator có thể chạy tại cổng khác tùy management.server.port.
curl -fsS http://localhost:8080/actuator/modulith
curl -fsS http://localhost:8080/actuator/metrics/module.events.published
~~~

**Lưu ý:** endpoint `/actuator/metrics/module.events.published` hiển thị **counter phát event**; không phải endpoint liệt kê mọi low-cardinality value của `ModulithObservationConvention`. Tùy observation handler, meter registration và backend, nhãn custom có thể được nhìn thấy trong trace. Kiểm tra tên và nhãn cuối cùng tại hệ thống nhận, đừng kết luận thành công chỉ dựa vào số lượng request.

### Kết quả minh họa khi có module-entry observation

~~~text
service.name = shop
observation.name = module.invocations
span.name = shop <tên module / method do context định dạng>
module.identifier = inventory
module.name = Inventory
module.invocation-type = bean
module.method = reserve
business.area = fulfillment
~~~

Đây là **mẫu kết quả mục tiêu**, không phải JSON thực tế của Zipkin/Tempo. Tên `module.method` và format của span name phụ thuộc context/phiên bản. Custom convention của ta thêm `business.area`, không tạo mới các field `module.*`. Nếu module `payments` chưa có span, hãy xác minh listener có thật sự được instrument trước khi kết luận mapping `billing` sai.

## 9. Tùy biến observation khác tùy biến event metrics

Spring Modulith có các metric domain event được công bố như:

- `module.events.published`: counter tổng hợp các event publication.
- `module.events.published.{moduleIdentifier}.{simpleEventTypeName}`: counter theo module và loại event.

`ModulithObservationConvention` xử lý **`ModulithContext` của module observations**. Khi muốn bổ sung tags theo nội dung event vào các counter riêng, Spring Modulith cung cấp SPI khác là **`ModulithEventMetricsCustomizer`**. Không nên ép dữ liệu từ một event cụ thể vào `ModulithObservationConvention`, bởi convention tại module entry không nhất thiết nhận object domain event đó.

Ví dụ minh họa khác biệt:

| Nhu cầu | Extension point | Dữ liệu có thể sử dụng |
| --- | --- | --- |
| Nhóm module-entry spans theo khu vực nghiệp vụ | `ModulithObservationConvention` | Module identifier, invocation/context |
| Thêm tag loại đơn hàng đã chuẩn hóa vào metric của một event cụ thể | `ModulithEventMetricsCustomizer` | Event type và dữ liệu event phù hợp chính sách |
| Ghi một bước xử lý nội bộ `pricing.calculate` | `ObservationRegistry` hoặc `@Observed` nếu cấu hình hỗ trợ | Context nghiệp vụ, operation name có kiểm soát |
| Thay đổi tỷ lệ export traces | Tracing sampler/exporter của Spring Boot | Cấu hình môi trường/runtime |
| Thay đổi module graph | Package/module configuration, `ApplicationModules` | Kiến trúc ứng dụng |

Đặc biệt tránh biến `orderId`, user ID, token hoặc field đầu vào tự do thành **metric tags**. Nếu cần thêm `sales.channel` cho event count, ánh xạ dữ liệu về các nhóm cố định như `web`, `store`, `partner` và kiểm soát cardinality. Việc tùy biến một event metric không làm biến `OrderPlaced` thành API bean cần instrument.

## 10. Các bẫy API và phiên bản

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `cannot find symbol ModulithObservationConvention` | Thiếu `spring-modulith-observability-api` trong compile classpath hoặc import theo package của bản khác. | Đồng bộ BOM và kiểm tra Javadoc của phiên bản đích. |
| Bean tạo được nhưng không thấy `business.area` | Cấu hình không được scan, nhiều bean convention, hoặc không có module-entry observation. | Kiểm tra context, bean type, đường gọi Spring API, span và logging cấu hình. |
| Mất `module.identifier` sau khi tùy biến | Trả về `KeyValues.of(...)` thay cho việc mở rộng default keys. | Gọi `ModulithObservationConvention.super.getLowCardinalityKeyValues(context)` trước `and(...)`. |
| Dashboard không tìm thấy metric/span cũ | Đổi `getName()` hoặc contextual name mà chưa cập nhật truy vấn. | Giữ tên mặc định khi không bắt buộc đổi; quản lý migration dashboard. |
| Metric cardinality tăng mạnh | Sử dụng order ID, URL/exception/payload làm low-cardinality tag. | Giữ danh sách giá trị hữu hạn, loại dữ liệu nhạy cảm. |
| Có span HTTP nhưng thiếu span module | Thiếu instrumentation, bean không thuộc exposed module API, self-invocation, sampling. | So runtime dependencies, module graph, Spring proxy và trace pipeline. |
| Test convention PASS nhưng backend không có trace | Unit test chỉ kiểm tra mapping; chưa có tracer/exporter, collector hoặc request thực. | Thực hiện kiểm tra runtime end-to-end. |
| Event counter tăng nhưng tag `business.area` không có | Event counter dùng SPI khác, không dùng Modulith module-entry convention. | Dùng `ModulithEventMetricsCustomizer` khi thật sự cần tùy biến event metrics. |

**Khác biệt API đáng lưu ý:** `ModulithObservationConvention` xuất hiện từ nhánh 1.4; trong một số tài liệu/bản tiền phát hành, tổ chức package có thể khác. Mã trong bài cố ý sử dụng **`org.springframework.modulith.observability.ModulithObservationConvention`** và **`ModulithContext`** từ Javadoc Spring Modulith 2.2.0. Không lấy import từ bài blog viết cho milestone/RC rồi áp vào một bản ổn định khác.

Trong 2.2, phần lớn phương thức của convention có default implementation nên chỉ override phần cần tùy biến. Ở phiên bản khác, hãy đọc Javadoc chính xác trước khi xóa method. Không sao chép nguyên source framework để thay thế chỉ vì muốn thêm một nhãn.

## 11. Test theo tình huống lỗi và đường bất đồng bộ

### 11.1. Lời gọi không qua Spring proxy

Thử đổi `orders` để gọi một object tự tạo bằng `new InventoryOperations()` thay vì inject Spring bean (chỉ trong môi trường test). Khi đó lời gọi không đi qua cơ chế trang trí bean của Spring Modulith, nên không thể kỳ vọng module-entry observation của `inventory` xuất hiện. Convention vẫn đúng; nguồn observation không được tạo.

Tương tự, với `this.someInternalMethod()`, lời gọi cùng object có thể không đi qua proxy. Không đổi mọi helper thành public module API để “cứu” trace; hãy đặt một custom observation ở bước nội bộ nếu có nhu cầu thực sự.

### 11.2. Event listener bất đồng bộ

Trong mẫu này, `PaymentListener` dùng `@EventListener` đồng bộ để có thể quan sát luồng đơn giản. Khi thay bằng `@ApplicationModuleListener`, listener có thể chạy bất đồng bộ sau commit với transaction riêng; điều đó đòi hỏi cấu hình transaction và context propagation thích hợp.

Nếu `orders` và `payments` xuất hiện trong **hai trace rời nhau**, kiểm tra `@Async`, task executor, `ContextPropagatingTaskDecorator`, Micrometer Context Propagation và propagation qua message broker hoặc Reactor. Custom `ModulithObservationConvention` **không truyền trace context giữa threads**.

### 11.3. Ngoại lệ hoặc thiếu exporter

Khi `InventoryOperations.reserve(...)` ném exception do `quantity < 1`, một module observation có thể ghi nhận lỗi tùy handler; cần kiểm tra span status/tag và mã HTTP thực tế. Không sửa convention để log cả exception message, bởi message có thể chứa dữ liệu cá nhân trong bài toán thật.

Nếu observation được tạo mà Collector không nhận được span, chẩn đoán tracing bridge, sampling, exporter endpoint/protocol, TLS, auth, Collector pipeline và backend. Không xem việc `/actuator/modulith` hoạt động là bằng chứng exporter đã thành công.

## 12. Nâng cấp convention có kiểm soát

Khi thay convention trong hệ thống đã vận hành, bạn nên:

1. Ghi lại `getName()`, `getContextualName()`, low/high keys hiện tại từ một trace mẫu.
2. Chọn nhãn cần thêm với tên có ý nghĩa, tránh trùng key chuẩn `module.*`.
3. Ước tính **tập giá trị tối đa** của từng low-cardinality tag (module x area x invocation-type), kể cả trường hợp module mới.
4. Viết unit test cho nhãn mới, nhãn mặc định và trường hợp fallback `other`.
5. Gắn bean convention trên staging với sample rate cao trong thời gian ngắn; phát một vài giao dịch giả.
6. So sánh trace trước và sau nâng cấp; kiểm tra độ trễ instrumentation, cardinality và chi phí backend nếu có dữ liệu phù hợp.
7. Cập nhật dashboard nếu chủ động thay tên span/observation; ưu tiên giữ `getName()` gốc để tránh làm đứt chuỗi số liệu.
8. Theo dõi sau triển khai và duy trì ánh xạ `areaFor` khi thêm một application module mới.

Trong môi trường có nhiều replica, triển khai đồng bộ convention theo phiên bản ứng dụng. Nếu một replica gắn `business.area` còn replica khác không gắn, query tổng hợp theo nhãn có thể bỏ sót một phần traffic. Lưu artifact/version và theo dõi hiệu lực cấu hình khi so sánh.

## 13. Bài tập mở rộng

**Đề bài:** Hệ thống bán vé có bốn module `booking`, `seat`, `payment` và `notification`. Đội vận hành muốn dashboard theo lĩnh vực `reservation`, `billing` và `engagement`.

Hãy phát triển dự án mẫu theo các bước:

1. Dùng `ApplicationModules.of(ShopApplication.class).verify()` (đổi lớp khởi động theo ứng dụng thật) để xác định module graph, API và phụ thuộc. Kiểm tra đúng các identifiers trước khi viết mapping.
2. Tạo `TicketingModulithObservationConvention` dựa trên mẫu bài: `booking`/`seat` → `reservation`, `payment` → `billing`, `notification` → `engagement`, module khác → `other`.
3. Giữ `getName()` và các default `module.*` keys. Thêm unit test kiểm tra từng nhóm và fallback; không thêm user ID hoặc ticket ID vào nhãn.
4. Đăng ký đúng một bean `ModulithObservationConvention` trong production context.
5. Dùng request thử làm phát sinh lời gọi `booking → seat` và một event gửi tới `payment`. Kiểm tra span theo module, tên contextual, `business.area` và counter event.
6. Mô phỏng lỗi `seat.reserve`, quan sát lỗi và lý giải vì sao một trace vẫn có thể chứa nhiều spans của các module khác nhau.
7. Chuyển listener sang bất đồng bộ (nếu đã cấu hình transaction phù hợp), quan sát quan hệ trace và bổ sung context propagation khi cần.
8. Viết biên bản ngắn gồm ảnh/snapshot trace, kết quả test, tập giá trị tags và những telemetry không thu thập vì quyền riêng tư.

**Tiêu chí đạt:** module graph hợp lệ, convention được Spring Boot phát hiện, nhãn `business.area` xuất hiện trên module-entry observation của những module được gọi, nhãn mặc định không mất, domain-event metrics không bị giả định chịu tác động trực tiếp bởi convention, và không có nhãn tăng vô hạn theo request.

## 14. Checklist nghiệm thu dự án

| Cổng | Cách kiểm tra | Kết quả cần có |
| --- | --- | --- |
| **A — Ranh giới module** | `ApplicationModules.verify()` và module graph | Không có phụ thuộc vào internal type ngoài ý muốn; module identifiers đã xác định. |
| **B — Compile API** | Kiểm tra `spring-modulith-observability-api` trên compile classpath | Class `ShopModulithObservationConvention` biên dịch được với version đã khóa. |
| **C — Bean wiring** | Kiểm tra application context | Có một bean convention được Spring Modulith sử dụng. |
| **D — Unit test** | Test `areaFor` và `getLowCardinalityKeyValues` | Mapping đúng, fallback đúng, giữ default module keys. |
| **E — Module observations** | Gửi HTTP request thật, mở trace | Có spans từ đường gọi Spring bean API; tên và tags phù hợp. |
| **F — Runtime metrics** | Phát event, đọc Actuator metrics | Event publication counter xuất hiện; hiểu rõ event customizer là SPI khác. |
| **G — Export** | Kiểm tra exporter → Collector → backend | Trace được nhận và truy vấn, không chỉ nhìn thấy `traceId` ở log. |
| **H — An toàn dữ liệu** | Kiểm tra labels và span attributes | Không có token, PII, payload; low-cardinality tags chỉ có giá trị hữu hạn. |
| **I — Hồi quy** | So sánh trace/dashboard trước và sau | Không mất `module.identifier`, `module.name` hay tên metric ngoài ý muốn. |

Đừng báo “đã triển khai thành công convention” chỉ vì unit test pass hoặc bean khởi tạo được. Cần chứng minh **một lời gọi module thật tạo observation và thông tin tùy biến được nhìn thấy tại tầng thu thập dự kiến**.

## 15. Ghi nhớ và tài liệu tham khảo

**Ý chính cần nhớ:**

- `ModulithObservationConvention` dành cho **module observations**; custom convention được Spring Modulith tiếp nhận qua bean. Nó quyết định tên/nhãn của observation chứ không sửa kiến trúc module, AOP target hay exporter.
- Trong ví dụ Spring Modulith 2.2.0, các phương thức đã có default implementation. Khi chỉ muốn thêm `business.area`, dùng `super.getLowCardinalityKeyValues(context)` rồi `and(...)` để giữ nhãn chuẩn.
- `getName()` mặc định `module.invocations`; thay `getContextualName(...)` chỉ khi thật sự muốn đổi cách hiển thị span và đã cân nhắc hệ quả với truy vấn.
- `module.identifier`, `module.name`, `module.invocation-type` là low-cardinality keys; `module.method` là high-cardinality key. Không đưa dữ liệu request có cardinality cao vào metric tags.
- Metrics của domain event có SPI `ModulithEventMetricsCustomizer` riêng. Event counter tăng không tự chứng minh listener thành công, và module graph không chứng minh trace đã export.
- Kiểm tra đầy đủ **module model → Spring bean/proxy → observation convention → tracer/registry → exporter → backend**.

Tài liệu chính thức tham khảo:

1. [Spring Modulith 2.2.0 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Modulith Insight starter, module spans, domain-event metrics và đăng ký `ModulithObservationConvention`.
2. [Spring Modulith 2.2.0 — ModulithObservationConvention Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html): các phương thức `getName`, `getContextualName`, low/high key-values và `supportsContext`.
3. [Spring Modulith 2.2.0 — ModulithContext Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html): module, invocation, application name, key-values và contextual name.
4. [Spring Modulith 2.2.0 — ObservedModule Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ObservedModule.html): `getIdentifier()`, `getDisplayName()` và kiểu lời gọi.
5. [Spring Modulith 2.2.0 — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html) và [HighKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html): phân loại các module attributes.
6. [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cấu trúc application module và exposed API.
7. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation và context propagation.
8. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, sampling và exporter.
9. [Micrometer Commons — KeyValues](https://javadoc.io/doc/io.micrometer/micrometer-commons): `KeyValues.and(...)` và việc ghép key-values.

Các link `current` có thể chuyển sang nhánh mới trong tương lai. Khi áp dụng, đối chiếu **Javadoc của bản được khóa trong Maven/Gradle** và giữ các unit/integration test kiểm tra hành vi thật sau nâng cấp.
