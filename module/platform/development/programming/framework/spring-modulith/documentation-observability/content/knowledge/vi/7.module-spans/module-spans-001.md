# Module entry span là gì?

> **Chương:** Module spans  
> **Bối cảnh:** Spring Modulith Documentation & Observability — sử dụng module graph, Spring Boot Actuator, event metrics, tracing và context propagation để kiểm chứng ranh giới application module trong ứng dụng Spring Boot đang vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **module entry span** và nêu đúng thời điểm Spring Modulith tạo thông tin quan sát khi một lời gọi đi vào API của application module.
2. Phân biệt **module entry span**, **HTTP server span**, **span tùy chỉnh**, **module dependency graph** và **event publication metrics**.
3. Đọc bốn tag chính thức: `module.identifier`, `module.name`, `module.method` và `module.invocation-type`.
4. Hiểu quan hệ `traceId`, `spanId`, `parentSpanId` trong một luồng gọi giữa các module, kể cả event listener.
5. Cấu hình Spring Modulith observability và Micrometer Tracing để nhìn thấy module spans trong hệ thống quan sát.
6. Chẩn đoán trường hợp không xuất hiện module entry span, mất quan hệ cha–con sau khi chuyển thread hoặc nhầm lẫn giữa module graph với trace.

## 2. Module entry span: định nghĩa và giá trị thực tế

**Module entry span** là một đơn vị theo dõi thao tác được Spring Modulith tạo khi hệ thống quan sát một lời gọi **đi vào thành phần Spring thuộc API của một application module**. Nó cho biết thao tác nào ở module nào đã được thực thi và giúp đặt lời gọi đó vào cây trace đang hoạt động.

Spring Modulith nhận biết ranh giới application module từ cấu trúc package và metadata; phần **observability** dùng cơ chế interceptor/aspect trên các Spring component được nhận diện là API của module. Khi lời gọi đi qua điểm được instrument, Spring Modulith tạo một **Micrometer Observation**. Nếu ứng dụng đã có tracing bridge và exporter phù hợp, observation này được biểu diễn thành **span** trong trace backend.

Một câu dễ nhớ:

> Module graph mô tả **module nào có thể phụ thuộc module nào**; module entry span giúp nhìn thấy **một lời gọi đã đi vào module nào tại thời điểm chạy**.

Ví dụ người dùng gửi yêu cầu tạo đơn hàng. Lớp điều phối của module `orders` cần gọi module `payments` để ủy quyền thanh toán:

~~~mermaid
sequenceDiagram
    participant Browser as Client
    participant HTTP as HTTP Controller
    participant Orders as orders module
    participant Payments as payments module
    Browser->>HTTP: POST /orders/ORD-1
    Note over HTTP: HTTP server observation/span
    HTTP->>Orders: placeOrder(...)
    Note over Orders: Module entry span nếu method được instrument
    Orders->>Payments: authorize(...)
    Note over Payments: Module entry span của payments
    Payments-->>Orders: Hoàn thành
    Orders-->>Browser: HTTP response
~~~

Khi cả hai điểm vào module được instrument và ngữ cảnh trace được giữ, bạn có thể thấy một trace dạng minh họa:

~~~text
traceId = abc123...

HTTP POST /orders/{orderId}           spanId=01
└── orders > OrderService.placeOrder  spanId=02, parentSpanId=01
    └── payments > PaymentApi.authorize
                                    spanId=03, parentSpanId=02
~~~

Tên span cụ thể do observation convention, phiên bản framework và tên method quyết định; đây **không phải** cam kết rằng mọi dự án đều sinh đủ ba span hoặc đặt tên chính xác như ví dụ. Những lời gọi nội bộ cùng module hay code không đi qua Spring component được instrument không nhất thiết tạo thêm module entry span.

## 3. Trước tiên cần phân biệt observation, span và trace

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Observation** | Mô hình Micrometer ghi nhận một operation, có tên, ngữ cảnh và key-value; observation handler có thể chuyển thành metrics/tracing | Một lần vào `PaymentApi.authorize()` |
| **Span** | Đơn vị thời gian/quan hệ nhân quả trong distributed tracing, mang `traceId` và `spanId` | Span module `payments` tồn tại trong thời gian method được quan sát |
| **Trace** | Tập hợp các span liên quan cùng một operation hoặc chuỗi xử lý | Tạo đơn hàng gồm HTTP, module order và payment |
| **Parent span** | Span cấp trên trong quan hệ thực thi được truyền bằng tracing context | Span `orders` là parent của span `payments` |
| **Span attributes/tags** | Metadata về operation; hỗ trợ lọc, phân nhóm khi phân tích | `module.identifier=payments` |
| **Event publication metric** | Dữ liệu tổng hợp đếm lần công bố sự kiện, không phải một span | `module.events.published` |

Một trace bình thường có **cùng `traceId`**, trong khi mỗi span sở hữu **`spanId` riêng**. `parentSpanId` hoặc quan hệ parent được backend dùng để lắp ghép cây trace. Việc hai span cùng `traceId` không tự chứng minh hai module gọi nhau trực tiếp; hãy xem parent/child và thời điểm thực thi.

Một observation có thể được tạo trong ứng dụng nhưng **không nhìn thấy span** trên giao diện tracing vì chưa có tracer, không có exporter, bị sampling loại bỏ hoặc cấu hình test không bật reporting. Ngược lại, chỉ thấy HTTP span không chứng minh Spring Modulith observability đã instrument các ranh giới module.

### 3.1. Span ghi thời gian nào?

Với lời gọi Java đồng bộ qua interceptor, span thường bao quanh **thời gian thực thi lời gọi method được quan sát**, từ khi interceptor bắt đầu đến khi lời gọi kết thúc hoặc ném exception. Điều đó không có nghĩa span chỉ đo thời gian do chính module này sử dụng CPU: method có thể chờ database, gọi HTTP hoặc chờ module khác, nên span cha có thể **bao gồm** thời gian của span con.

Ví dụ:

~~~text
orders.placeOrder()                   |-----------------------------| 180 ms
  payments.authorize()                      |--------------|             90 ms
    JDBC insert                                  |-----|                25 ms
~~~

**Không cộng mù quáng** 180 + 90 + 25 thành tổng latency 295 ms: các khoảng thời gian lồng nhau. Nếu muốn định vị nút thắt, xem waterfall, thời gian chờ, thời gian độc lập của span và các operation cụ thể. Với API bất đồng bộ trả về `Mono`, `CompletionStage` hoặc giao việc nền, thời điểm method trả về có thể **sớm hơn** thời điểm công việc hoàn tất; cần đối chiếu instrumentation thực tế trước khi diễn giải duration.

## 4. Điều gì kích hoạt một module entry span?

Theo tài liệu Spring Modulith, hỗ trợ observability **trang trí các Spring component thuộc API của application module** bằng một interceptor để theo dõi các lời gọi. Trong implementation, `ModuleObservabilityBeanPostProcessor` gắn advice vào bean thích hợp và `ModuleEntryInterceptor` tạo Micrometer Observation.

Luồng khái niệm:

~~~mermaid
flowchart LR
    Caller["Caller / module khác"] --> Proxy["Spring bean proxy<br/>API của module"]
    Proxy --> Interceptor["Module entry interceptor"]
    Interceptor --> Registry["Micrometer<br/>ObservationRegistry"]
    Interceptor --> Target["Method nghiệp vụ"]
    Registry --> Handler["Tracing observation handler"]
    Handler --> Tracer["Micrometer Tracing"]
    Tracer --> Exporter["Exporter / collector"]
    Exporter --> UI["Trace backend UI"]
~~~

Cần phân biệt **hai điều kiện**:

1. **Được instrument:** lời gọi phải đi qua Spring component/proxy mà Spring Modulith chọn quan sát.
2. **Được xuất thành span:** ứng dụng phải có Micrometer Tracing, handler, sampler và đường xuất dữ liệu phù hợp.

Không phải mọi method trong source code đều tạo module entry span. Các trường hợp cần thận trọng:

- **Method nội bộ của module:** nếu chỉ là xử lý thuần Java không qua điểm instrument, đừng chờ có một span Modulith riêng cho từng method.
- **Tự gọi method trong cùng object (`this.someMethod()`):** thường bỏ qua Spring proxy, vì vậy lời gọi tự thân không tự kích hoạt interceptor.
- **Đối tượng tạo bằng `new` ngoài Spring:** không được Spring bean post-processor trang trí như Spring bean.
- **Bean nằm ở API hay bên trong module:** cách phát hiện module, public API và loại Spring component quyết định có được instrument không; tránh giả định cứ thêm `@Service` là sẽ có module entry span.
- **Kỹ thuật gọi đặc biệt:** Spring Data REST, event listener hoặc proxy có thể được xử lý riêng theo version và module observability extension tương ứng.

Ở mức ứng dụng, điều quan trọng là **phát hiện đúng application modules trong runtime**, vì cấu hình module detection chỉ nằm trong test có thể không được sử dụng bởi observability trong bản deploy.

## 5. Bốn tag của module entry span

Tài liệu Spring Modulith mô tả bốn tag cho loại span này:

| Tag | Chứa gì? | Ví dụ minh họa | Dùng để |
| --- | --- | --- | --- |
| `module.identifier` | Định danh kỹ thuật của module | `payments` | Nhóm/lọc theo application module |
| `module.name` | Tên module dành cho người đọc | `Payments` | Hiển thị trực quan trong trace |
| `module.method` | Method được thực thi ở điểm vào module | `authorize` | Xác định thao tác module đang phục vụ |
| `module.invocation-type` | Kiểu lời gọi được quan sát | `bean` hoặc `event listener` | Phân biệt cách đi vào module |

Một biểu diễn **giả định** của span:

~~~yaml
traceId: "b6d13cc80f364e849b48d708610b6d2a"
spanId: "bca82de2ea813be4"
parentSpanId: "06b2cb818a0c3d40"
name: "Payments > PaymentApi.authorize"
attributes:
  module.identifier: "payments"
  module.name: "Payments"
  module.method: "authorize"
  module.invocation-type: "bean"
~~~

Đây là **minh họa cho việc đọc tag**; không phải schema JSON/YAML mà Zipkin, Jaeger hoặc Tempo bắt buộc trả về. Tên span và cách hiển thị attribute có thể khác nhau tùy exporter và giao diện.

### 5.1. Hiểu `module.invocation-type`

- **`bean`:** lời gọi đi qua một Spring bean được quan sát, chẳng hạn service công bố trong API module.
- **`event listener`:** lời gọi đi vào module qua listener của application event được instrument.

Tag này **không có nghĩa** method `bean` đang chạy đồng bộ, hay event listener nhất thiết bất đồng bộ. Cách listener được gọi (đồng bộ, `@Async`, `@ApplicationModuleListener`, sau commit, retry) cần được xác định bằng cấu hình và vòng đời event cụ thể.

### 5.2. Giới hạn của tag

Tag được thiết kế để giải thích operation, không phải nơi lưu payload. Không tự gán `orderId`, email, access token, địa chỉ, nội dung thanh toán hoặc dữ liệu nhạy cảm vào tag. Giá trị có số lượng biến thể quá lớn còn có thể gây tăng cardinality nếu được sử dụng trong metrics.

Việc xuất hiện `module.identifier=payments` cho biết **operation được quy về module payments**, nhưng không chứng minh dependency graph cho phép lời gọi đó về mặt kiến trúc. Muốn kiểm tra allowed dependencies hoặc truy cập internals, cần Spring Modulith verification.

## 6. Ví dụ Java: một lời gọi đi qua API của module

Giả sử ứng dụng có các package module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderController.java
│   └── OrderService.java
└── payments
    └── PaymentApi.java
~~~

Đây là cấu trúc **minh họa** cho Spring Modulith; mặc định các package con trực tiếp dưới package ứng dụng là ứng viên application module.

**Module `payments` cung cấp API:**

~~~java
// com/example/shop/payments/PaymentApi.java
package com.example.shop.payments;

import org.springframework.stereotype.Service;

@Service
public class PaymentApi {

    public void authorize(String orderId) {
        // Gửi yêu cầu ủy quyền thanh toán, mô phỏng.
        // Không chứa tích hợp cổng thanh toán thật trong ví dụ.
    }
}
~~~

**Module `orders` sử dụng API đó:**

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.payments.PaymentApi;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentApi paymentApi;

    public OrderService(PaymentApi paymentApi) {
        this.paymentApi = paymentApi;
    }

    public void placeOrder(String orderId) {
        validateOrder(orderId);
        paymentApi.authorize(orderId);
    }

    private void validateOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
    }
}
~~~

**Tầng HTTP kích hoạt nghiệp vụ:**

~~~java
// com/example/shop/orders/OrderController.java
package com.example.shop.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders/{orderId}")
    public ResponseEntity<Void> place(@PathVariable String orderId) {
        orderService.placeOrder(orderId);
        return ResponseEntity.accepted().build();
    }
}
~~~

Khi người dùng gọi `POST /orders/ORD-1` và Spring Modulith observability nhận diện `PaymentApi` là một điểm vào module:

1. Spring Boot web instrumentation có thể mở HTTP server observation/span.
2. Khi lời gọi qua proxy tới module `orders` được instrument, một module entry observation có thể được tạo.
3. Khi `OrderService` gọi `paymentApi.authorize(...)` qua Spring bean, điểm vào `payments` được instrument và tạo observation tương ứng.
4. Nếu tracing context còn nguyên và handler/exporter đã được cấu hình, các observation có thể xuất hiện trong một trace với quan hệ cha–con.

**Giới hạn của ví dụ:** số lượng span và tên span chính xác cần kiểm tra trên bản Spring Modulith thực tế. Việc gọi `validateOrder()`, một private method trong cùng class, **không** đồng nghĩa có một module entry span riêng. Ví dụ cũng chưa có nghiệp vụ lưu đơn hàng hay thanh toán thật.

## 7. Event listener cũng có thể là điểm đi vào module

Một luồng event giúp giảm phụ thuộc gọi trực tiếp, nhưng listener ở module đích vẫn có thể là **module entry** quan sát được.

Ví dụ `orders` phát sự kiện:

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {}
~~~

Và trong ứng dụng, `orders` gọi `ApplicationEventPublisher.publishEvent(new OrderPlaced(orderId))` sau khi hoàn tất nghiệp vụ phù hợp. Module `notifications` có listener:

~~~java
// com/example/shop/notifications/NotificationListener.java
package com.example.shop.notifications;

import com.example.shop.orders.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotificationListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Mô phỏng gửi thông báo.
    }
}
~~~

`@ApplicationModuleListener` tích hợp cơ chế listener sau giao dịch và bất đồng bộ của Spring Modulith. Để ví dụ hoạt động, cần Spring Modulith event infrastructure, transaction phù hợp và cấu hình executor cần thiết; không nên xem đây là đoạn code chạy độc lập không cần hệ thống sự kiện.

Điểm cần đọc đúng:

~~~mermaid
flowchart TB
    subgraph Dependency["Module graph — quan hệ tĩnh"]
        N1["notifications"] -->|"cần kiểu OrderPlaced"| O1["orders"]
    end
    subgraph Runtime["Trace / event flow — tương tác khi chạy"]
        O2["orders"] -->|"publish OrderPlaced"| N2["notifications"]
        N2 --> ES["Module entry span<br/>module.invocation-type=event listener"]
    end
~~~

Hướng dependency tĩnh có thể là `notifications → orders` vì listener biết type của `orders`. Trong khi đó, event được phát từ `orders` và được listener `notifications` nhận. Module entry span mô tả **listener đã được gọi khi chạy**, khác hẳn module graph.

### 7.1. Điều gì xảy ra khi listener bất đồng bộ?

Listener có thể được chạy trên thread pool sau khi transaction đã commit. Vì vậy:

- **Có span cho listener** không mặc nhiên chứng minh nó nằm trong **cùng trace** với HTTP request phát event.
- **Context propagation** cần được xem xét tại ranh giới executor/thread; với event được lưu để retry sau restart, trace gốc không còn là một scope đang mở.
- Một trace mới, correlation ID hoặc **span link** có thể phản ánh tốt hơn quan hệ nhân quả đối với job chạy rất lâu sau request.
- Module event metrics cho biết **event được công bố**; để biết listener hoàn thành hay cần phát lại phải kết hợp event publication registry và kết quả xử lý.

Khi phân tích trace event, hãy kiểm tra `traceId`, parent/span links và timestamp, đừng suy ra quan hệ từ việc hai span cùng mang tên module.

## 8. Cấu hình để nhìn thấy module entry span

Cần giải quyết **hai lớp**: instrumentation của Spring Modulith và tracing pipeline của Spring Boot.

### 8.1. Thêm Spring Modulith observability

Cách thuận tiện là dùng starter Insight (module Actuator + observability + Actuator support):

~~~xml
<!-- pom.xml; BOM phù hợp quản lý version -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Nếu chỉ cần observability trong Spring Modulith 2.x, tài liệu hiện hành còn hỗ trợ artifact:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-core</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Với Gradle, ví dụ:

~~~groovy
dependencies {
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

Đừng khai báo trùng các artifact có trong Insight starter nếu không có lý do cụ thể. Dòng Spring Modulith 1.x từng sử dụng artifact `spring-modulith-observability`; tên dependency và mức hỗ trợ phụ thuộc dòng phiên bản. Đảm bảo dependency management dùng **BOM Spring Modulith tương thích với Spring Boot đang chạy**.

### 8.2. Bổ sung tracing bridge và exporter

Có observability của Modulith **chưa đủ** để thấy spans trong Zipkin/Tempo. Ví dụ với **Spring Boot 4.x** và OpenTelemetry/OTLP, tài liệu Boot hỗ trợ starter tracing/export như:

~~~xml
<!-- Dùng khi Spring Boot của dự án có starter này -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Backend/collector tương ứng cần nhận OTLP. Với các dự án **Spring Boot 3.x**, dependency thường là `micrometer-tracing-bridge-otel` kết hợp `opentelemetry-exporter-otlp` và cấu hình exporter tương ứng. Không sao chép bộ artifact Spring Boot 4.x vào dự án Boot 3.x mà chưa tra tài liệu dòng đang dùng.

Trong môi trường **thử nghiệm**, có thể bật ghi nhận mọi trace:

~~~yaml
spring:
  application:
    name: shop-modulith-demo

management:
  tracing:
    sampling:
      probability: 1.0
~~~

`1.0` giúp dễ nhìn thấy các request đã instrument khi backend và exporter hoạt động. Ở production, sampling cần cân bằng giữa nhu cầu quan sát, lượng dữ liệu, hiệu năng và chi phí. Việc bật sampling 100% **không tự tạo exporter**.

Nếu ứng dụng dùng Zipkin, Tempo, Jaeger hoặc backend khác, cần cấu hình endpoint/transport/exporter theo công cụ và version. Spring Boot Actuator `/actuator/modulith` cung cấp **module metadata**, không phải URL hiển thị traces.

### 8.3. Một bảng kiểm điều kiện quan sát

| Cần có | Nếu thiếu thì sao? | Cách kiểm tra |
| --- | --- | --- |
| Module detection runtime chính xác | Sai hoặc thiếu các module được xác định để instrument | Đối chiếu package, metadata và bản deploy |
| Spring Modulith observability runtime | Không có module entry observation | Kiểm tra dependency được thực sự tải |
| Lời gọi qua Spring component được instrument | Không có interceptor ở điểm cần quan sát | Gọi từ bean khác, kiểm tra API/module boundaries |
| Micrometer Tracing bridge/handler | Observation chưa chắc được chuyển thành tracing span | Kiểm tra tracer và các dependency của Boot |
| Exporter + collector hoạt động | Không thấy span trong tracing backend | Kiểm tra collector, endpoint, logs exporter |
| Sampling cho phép ghi nhận | Trace có thể bị loại trước khi xuất | Đặt sampling thích hợp ở profile test |
| Context propagation khi đổi thread | Span có thể tách trace hoặc mất parent | Kiểm tra executor và reactive scheduler |

## 9. Đọc module entry span trong giao diện trace

Giả sử request `POST /orders/ORD-1` trả thành công. Trong hệ thống tracing:

1. Tìm trace bằng khoảng thời gian, tên service `shop-modulith-demo` và endpoint HTTP nếu backend hỗ trợ.
2. Xem parent HTTP server span, sau đó các spans mang tags `module.identifier`.
3. Chọn span `payments`, đọc `module.method` để xác nhận đúng operation được instrument.
4. Xem `module.invocation-type`: có phải bean invocation hay listener hay không.
5. Đối chiếu thời gian, exception/status, parent-child và các span bên dưới như JDBC/HTTP client nếu instrumentation liên quan đã có.

Một waterfall minh họa:

~~~text
0ms                       50ms                      100ms
|-------------------------|--------------------------|
HTTP POST /orders  [=============================] 96ms
  module orders      [========================]     81ms
    module payments        [===============]        52ms
      JDBC write              [=====]               19ms
~~~

Không kết luận rằng `payments` chậm chỉ dựa vào tên span; cần xem duration của nó, các child spans, số lần gọi, phân phối latency qua nhiều request và dữ liệu tải. Một span dài có thể chủ yếu đang chờ I/O.

### 9.1. Kết hợp với module graph và Actuator

Giả sử module graph có cạnh `orders → payments`:

~~~mermaid
flowchart LR
    Orders["orders"] -->|"USES_COMPONENT"| Payments["payments"]
~~~

- **Graph:** mã `orders` phụ thuộc `payments` thông qua component; đây là quan hệ kiến trúc tĩnh.
- **Module entry span:** một lần đi vào API của `payments` đã được quan sát trong luồng thực thi.
- **HTTP span:** request HTTP nào đã kích hoạt chuỗi đó, nếu context được truyền và instrumentation phù hợp.
- **Actuator modulith endpoint:** trả JSON metadata của modules/dependencies đang được nhận diện, giúp xác nhận bản triển khai.
- **Event counter:** thống kê sự kiện đã publish; không chỉ ra cụ thể module entry method nào đã được gọi thành công.

Vì vậy mô hình Spring Modulith Documentation & Observability sử dụng **nhiều nguồn bằng chứng bổ sung**. Không một nguồn nào tự trả lời mọi câu hỏi về kiến trúc và hành vi.

## 10. Context propagation quyết định mối liên hệ giữa spans

Một module entry span trong thread của request có thể trở thành con của span hiện hành. Nhưng Java `ThreadLocal` không tự chuyển qua executor thread, còn Reactor pipeline có `Context` riêng.

~~~text
HTTP thread             Executor thread          Reactor scheduler
    |                         |                         |
    |-- submit task --------->|                         |
    |   (capture context)     |                         |
    |                         |-- restore context       |
    |                         |-- module span           |
    |                         |-- close scope           |
    |                         |                         |
    |-- subscribe pipeline ---------------------------->|
                              Reactor Context ---> module span
~~~

**Một số nguyên tắc:**

- Với Spring `ThreadPoolTaskExecutor`, có thể gắn `ContextPropagatingTaskDecorator` để truyền các context mà Micrometer accessor hỗ trợ.
- Với executor thuần Java, `ContextSnapshot` là một cách capture trước khi submit và restore trong task; luôn close scope để tránh rò ngữ cảnh khi worker thread được dùng lại.
- Với Reactor, `contextWrite`, `contextCapture` và cấu hình context propagation phù hợp giúp nối bối cảnh qua scheduler switch. Không giả định mọi `ThreadLocal` tự được đưa vào Reactor.
- Với event publication được lưu bền vững hoặc được thực thi lại sau restart, phải có cơ chế correlation/tracing qua event metadata nếu muốn theo dõi quan hệ giữa các lần xử lý.

Nếu hai spans cùng operation xuất hiện thành **hai trace khác nhau**, hãy kiểm tra ranh giới thread/async trước khi sửa code vẽ graph. Ngược lại, một trace cùng ID nhưng thiếu module span có thể do **instrumentation** chứ chưa chắc do propagation.

## 11. Module entry span và custom observation

Spring Modulith cung cấp module entry observation tự động cho **điểm vào module**. Khi cần đo một thao tác cụ thể bên trong module, ứng dụng có thể tạo một observation tùy chỉnh:

~~~java
package com.example.shop.payments;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class PaymentGatewayClient {

    private final ObservationRegistry registry;

    public PaymentGatewayClient(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void callGateway() {
        Observation.createNotStarted("payment.gateway.call", registry)
            .lowCardinalityKeyValue("gateway", "demo")
            .observe(this::sendRequest);
    }

    private void sendRequest() {
        // Mô phỏng gọi gateway.
    }
}
~~~

Khi tracing bridge được cài và scope hiện hành được bảo toàn, observation `payment.gateway.call` có thể xuất thành một **child span** dưới module entry span của `payments`. Nó **không phải** module entry span: tên, thời gian và metadata được định nghĩa bởi ứng dụng, trong khi module entry span theo convention Spring Modulith.

Ví dụ custom observation dùng tag `gateway=demo` có ít giá trị khác nhau. Không đưa order ID hoặc dữ liệu khách hàng vào low-cardinality tag.

### 11.1. Có thể tùy chỉnh tên hoặc tag module không?

Spring Modulith có extension point `ModulithObservationConvention` để tùy chỉnh convention cho module observations. Với trường hợp cần tên span/thẻ chuẩn hóa, có thể đăng ký bean triển khai interface đó:

~~~java
// Chỉ minh họa điểm mở rộng; class triển khai tùy theo
// interface và version Spring Modulith của dự án.
@Configuration
class ModuleObservationConfiguration {

    @Bean
    ModulithObservationConvention convention() {
        return new MyModulithObservationConvention();
    }
}
~~~

Lưu ý: `MyModulithObservationConvention` trong ví dụ là **placeholder cho class ứng dụng cần tự triển khai**, không phải class có sẵn. Trước khi triển khai, tra API của `ModulithObservationConvention` và `ModulithContext` đúng phiên bản đang dùng. Không sửa trực tiếp nội bộ interceptor để chỉ đổi cách đặt tên span.

## 12. Những lỗi thường gặp khi không nhìn thấy module span

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xác minh |
| --- | --- | --- |
| Có HTTP trace nhưng không có `module.*` tags | Chưa thêm Modulith observability; bean không thuộc API module được instrument | Kiểm tra runtime dependency, module detection và bean |
| Chỉ thấy span của module `orders`, thiếu `payments` | Lời gọi không đi qua bean proxy được instrument, hoặc `payments` không được nhận diện | Kiểm tra bean thực tế, API module và nơi gọi |
| Span không xuất hiện dù code chạy | Chưa có bridge/exporter, collector không hoạt động, sampling loại bỏ | Kiểm tra cấu hình Micrometer Tracing, collector và sampling |
| Tự gọi method không tạo span mới | `this.method()` bỏ qua Spring proxy | Gọi qua bean đúng ranh giới; không tạo span chỉ để minh họa mọi private method |
| Listener có span nhưng thuộc trace khác request | Bất đồng bộ, after-commit, retry hoặc mất context khi đổi thread | Kiểm tra executor, thời điểm listener chạy và cơ chế propagation/correlation |
| `module.invocation-type` là event listener nhưng không thấy event counter | Chưa cấu hình/publish theo đường metrics kỳ vọng; khác loại tín hiệu | Kiểm tra event publisher và registry metrics độc lập |
| Span duration nhỏ bất ngờ so với job thực tế | Method trả về async object trước khi phần việc chính chạy | Kiểm tra lifecycle thực thi và instrumentation của reactive/async operation |
| Tên module không khớp tài liệu sinh ở test | Runtime và test dùng module detection khác hoặc binary/version khác | Đối chiếu startup class, cấu hình runtime và bản build đã deploy |
| Log không có `traceId` nhưng backend có trace | MDC/logging correlation chưa được cấu hình hoặc context không có trong thread log | Kiểm tra tracer, pattern log, scope và thread |
| Span bị lặp bất thường | Chồng nhiều lớp instrumentation/custom observation hoặc caller đi qua nhiều entry point | Mở từng span theo parent/child, method và loại instrumentation |

Không nên khắc phục mọi lỗi bằng cách tăng sampling lên `1.0` vĩnh viễn; sampling chỉ giúp thu nhận nhiều trace hơn, không sửa việc thiếu interceptor, thiếu propagation hoặc khác biệt giữa các phiên bản.

## 13. Bài thực hành: xác minh một module entry span

**Đề bài:** xây ứng dụng Spring Boot gồm `orders` và `payments`, có controller gọi `OrderService.placeOrder()` và module `payments` công bố `PaymentApi.authorize()`. Sử dụng cấu trúc minh họa phần 6, thêm Spring Modulith observability cùng tracer/exporter và chạy một tracing backend thử nghiệm.

Thực hiện theo trình tự:

1. **Xác nhận graph:** dùng Spring Modulith module diagram hoặc `GET /actuator/modulith` (nếu Actuator được expose) để xác nhận ranh giới và dependency `orders → payments`.
2. **Bật instrumentation:** thêm `spring-modulith-starter-insight` hoặc dependency quan sát tương thích; cấu hình exporter phù hợp với dòng Spring Boot của dự án.
3. **Bật sampling test:** đặt `management.tracing.sampling.probability=1.0` trong profile test; đảm bảo collector nhận được spans.
4. **Thực hiện request:** gửi `POST /orders/ORD-1`; lưu lại thời điểm gọi và kết quả HTTP.
5. **Mở trace:** tìm trace tương ứng, xác định spans có `module.identifier=orders` hoặc `module.identifier=payments` nếu các entry point được instrument.
6. **Đọc metadata:** với mỗi module entry span tìm được, ghi `module.name`, `module.method`, `module.invocation-type`, `traceId`, `spanId`, quan hệ parent và duration.
7. **Đối chứng:** tạm thời gọi một helper Java thuần ở cùng class thay cho một external module call; giải thích vì sao nó không bắt buộc sinh module entry span mới. Không dùng “không thấy span” làm bằng chứng helper không chạy.
8. **Mở rộng:** đưa một lời gọi sang executor chưa truyền context trong môi trường thử nghiệm, quan sát quan hệ trace; thêm context propagation phù hợp rồi đối chiếu kết quả.

Mẫu ghi kết quả:

| Quan sát | Ví dụ dự kiến | Kết luận cần rút ra |
| --- | --- | --- |
| Module graph | `orders → payments` | Dependency kiến trúc đi từ consumer đến provider |
| HTTP span | `POST /orders/{orderId}` | HTTP request được instrument |
| Module entry span | `module.identifier=payments` | Điểm vào module payments được instrument và đã chạy |
| Parent/child | `payments` nằm dưới `orders` | Trace context và các điểm vào module được nối đúng trong tình huống này |
| Thêm executor | Mất/giữ quan hệ parent tùy cấu hình | Propagation ảnh hưởng quan hệ trace khi đổi thread |

**Tiêu chí hoàn thành:** trình bày được một span thật cùng bốn tag module; giải thích được vì sao span xuất hiện ở API module; phân biệt được kết quả trong trace với cạnh dependency tĩnh; chỉ ra ranh giới gây mất trace context.

## 14. Câu hỏi tự kiểm tra

1. Một module có xuất hiện trong `/actuator/modulith` thì chắc chắn đã có module entry span chưa?
2. Vì sao module entry observation có thể tồn tại nhưng UI tracing không hiển thị span?
3. `module.invocation-type=event listener` có chứng minh event đã được xử lý thành công không?
4. Hai spans cùng `traceId` nhưng có `spanId` khác nhau có phải dữ liệu lỗi không?
5. `OrderService.placeOrder()` gọi `this.validateOrder()` có chắc tạo span mới không?
6. Vì sao không cộng duration của span cha và span con khi phân tích tổng thời gian request?
7. Cần kiểm tra những gì nếu listener chạy bất đồng bộ và span của nó thuộc trace khác?

**Gợi ý trả lời:** (1) Không, endpoint cho cấu trúc, span yêu cầu execution và instrumentation; (2) có thể do sampling, bridge, exporter, collector; (3) không, chỉ cho loại invocation, cần xem outcome/registry; (4) không, các span trong cùng trace có ID riêng; (5) không, private/self-invocation thường không đi qua interceptor; (6) thời gian lồng nhau bị đếm trùng; (7) kiểm tra executor, context propagation, time gap, durable event và cơ chế correlation/link.

## 15. Ghi nhớ

Module entry span giúp quan sát **điểm một operation đi vào module**, gắn tên module và method với tracing context. Spring Modulith làm việc này bằng cơ chế interceptor quanh các Spring component thuộc API module; Micrometer Observation và tracing bridge quyết định cách thông tin trở thành span trên backend.

Khi sử dụng trong hệ thống thực tế, đọc cùng lúc **module graph** (kiến trúc được nhận diện), **module entry spans** (các điểm vào module đã được thực thi), **metrics/event publications** (tín hiệu tổng hợp và trạng thái event) và **context propagation** (mối liên hệ giữa các operation khi đổi thread hoặc tiến trình). Chỉ khi phân biệt đúng các lớp thông tin đó, bạn mới có thể dùng observability để kiểm chứng kiến trúc module trong Spring Boot.

### Tài liệu tham khảo

- [Spring Modulith – Production-ready Features: Observing Application Modules, Module Entry Span](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith – ModuleEntryInterceptor API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/support/ModuleEntryInterceptor.html).
- [Spring Modulith – ModuleObservabilityBeanPostProcessor API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/support/ModuleObservabilityBeanPostProcessor.html).
- [Spring Modulith – Observability API package](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/package-summary.html).
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith – Appendix: starters/dependencies](https://docs.spring.io/spring-modulith/reference/appendix.html).

> **Lưu ý phiên bản:** mã ví dụ minh họa cơ chế; tên artifact, API và cấu hình exporter giữa Spring Modulith 1.x/2.x, Spring Boot 3.x/4.x có thể khác nhau. Luôn dùng bộ phiên bản tương thích và đối chiếu reference guide của chính phiên bản đang chạy. Nội dung này là tài liệu học tập STEP 4; kiểm tra học thuật chuyên sâu sẽ được thực hiện ở bước QA riêng.
