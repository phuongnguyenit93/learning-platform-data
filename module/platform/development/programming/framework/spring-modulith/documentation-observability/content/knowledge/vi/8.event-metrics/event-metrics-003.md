# Metric theo module identifier và event type

> **Chương:** Event metrics  
> **Phạm vi:** Spring Modulith Documentation & Observability trong ứng dụng Spring Boot: phân tích số lần công bố domain event theo application module và loại sự kiện bằng Micrometer, Actuator và hệ thống metrics.

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt **event publication counter** với số lần xử lý event thành công, trạng thái Event Publication Registry và số span trong trace.
2. Giải thích hai loại meter được Spring Modulith cung cấp: `module.events.published` và `module.events.published.$moduleIdentifier.$simpleEventTypeName`.
3. Sử dụng đúng ba tag của counter tổng hợp: `module.identifier`, `module.name` và `module.event.type`.
4. Đọc counter theo từng module, từng event type hoặc cả hai thông qua `/actuator/metrics` và Prometheus.
5. Hiểu cách Spring Modulith xác định module sở hữu event, vì sao metric không nên dùng ID đơn hàng làm tag và cách tùy biến metric với `ModulithEventMetricsCustomizer`.
6. Lập quy trình kiểm chứng kiến trúc mô-đun bằng cách kết hợp event metrics với module graph, Actuator, tracing và context propagation.

## 2. Vì sao cần metric theo module và event type?

Trong một modulith, các application module giao tiếp bằng public API hoặc domain event. Ví dụ, module `orders` công bố `OrderPlaced` để các module `notifications` và `analytics` nhận biết đơn hàng mới:

~~~mermaid
flowchart LR
    Orders["orders"] -->|"publish OrderPlaced"| Bus["Spring ApplicationEventPublisher"]
    Bus --> Notifications["notifications listener"]
    Bus --> Analytics["analytics listener"]
    Orders -->|"publish OrderCancelled"| Bus
~~~

Nếu chỉ biết tổng số sự kiện của toàn ứng dụng, bạn chưa trả lời được:

- **Module nào** phát sinh nhiều event nhất?
- **Loại event nào** đang tăng đột biến?
- Tỷ lệ `OrderCancelled` so với `OrderPlaced` trong cùng module thay đổi ra sao?
- Một lần triển khai mới có làm **lượng event được công bố** thay đổi bất thường không?

Vì thế Spring Modulith gắn thông tin **application module** và **event type** vào metrics. Việc lọc các chiều này giúp quan sát tương tác giữa các phần của ứng dụng mà không cần đưa toàn bộ payload sự kiện vào dashboard.

**Phạm vi tín hiệu:** đây là thống kê việc **công bố sự kiện** do hạ tầng quan sát của Spring Modulith ghi nhận. Nó không mặc định là số lần listener hoàn tất, số bản ghi trong Event Publication Registry, số thông điệp đã đến broker ngoài JVM hay số transaction được commit.

## 3. Hai loại event publication counter của Spring Modulith

Theo tài liệu Spring Modulith, ứng dụng có thể ghi nhận hai dòng metric:

| Nhóm | Tên Micrometer | Ý nghĩa |
| --- | --- | --- |
| Counter tổng hợp | `module.events.published` | Đếm các event publications được Spring Modulith quan sát, cho phép chia theo tag của module và loại event |
| Counter riêng từng event | `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Đếm cho một loại event gắn với một module cụ thể; có thể tùy biến thêm tag từ thuộc tính domain event |

Giả sử có module identifier `orders` và event class `OrderPlaced`. Tên counter riêng theo quy tắc trên là:

~~~text
module.events.published.orders.OrderPlaced
~~~

Ở đây:

- `orders` là **module identifier** mà Spring Modulith gắn cho sự kiện.
- `OrderPlaced` là **simple class name** của event.
- Dấu chấm trong metric name là một phần quy ước Micrometer; tên khi xuất sang Prometheus có thể được chuyển thành dạng khác theo naming convention của registry.

### 3.1. Không cộng hai counter với nhau

Hai metric có thể cùng tăng do **một lần publish**. Counter tổng hợp và counter riêng là **hai góc nhìn của cùng dữ liệu**, không phải hai giai đoạn xử lý cần cộng lại.

Ví dụ giả định sau khi chạy:

| Meter | Phân loại | Giá trị counter |
| --- | --- | ---: |
| `module.events.published` | `orders` / `OrderPlaced` | 12 |
| `module.events.published` | `orders` / `OrderCancelled` | 3 |
| `module.events.published.orders.OrderPlaced` | `orders` | 12 |
| `module.events.published.orders.OrderCancelled` | `orders` | 3 |

Trong ví dụ, có **15 lần công bố** thuộc hai loại được quan sát, không phải `12 + 3 + 12 + 3 = 30`. Các số này chỉ để luyện cách đọc, không phải dữ liệu từ ứng dụng đang chạy.

### 3.2. Counter là gì?

Micrometer `Counter` biểu diễn một đại lượng **tăng theo các sự kiện được đếm**. Trong vòng đời một instance, giá trị counter được cộng dồn; sau khi process restart, counter in-memory thường bắt đầu lại từ đầu.

Vì vậy:

- Giá trị `100` tại một thời điểm nói rằng instance/registry đã ghi nhận một lượng sự kiện nhất định kể từ khi meter được tạo, **không nói tốc độ hiện tại**.
- Muốn biết “bao nhiêu event mỗi phút”, cần tính tốc độ thay đổi từ các lần thu thập theo thời gian.
- Trong hệ thống nhiều instance, một dashboard muốn biểu diễn tổng hệ thống cần tổng hợp các time series phù hợp, đồng thời xử lý các lần restart và instance mất kết nối.
- Nếu quá trình quan sát không được kích hoạt hoặc event không đi qua đường instrumentation tương ứng, counter có thể không xuất hiện.

## 4. Hiểu đúng tag `module.identifier` và `module.event.type`

Counter tổng hợp `module.events.published` công bố các **low-cardinality keys** sau:

| Tag chính thức | Diễn giải | Ví dụ minh họa |
| --- | --- | --- |
| `module.identifier` | Định danh kỹ thuật của application module gắn với sự kiện | `orders` |
| `module.name` | Tên hiển thị của application module | `Orders` |
| `module.event.type` | Loại sự kiện được công bố | `OrderPlaced` |

Đây là tên **key** trong dữ liệu Micrometer. Giá trị thực tế của `module.event.type` cần đọc từ response của ứng dụng; không nên đoán nó luôn là simple class name hay fully-qualified class name ở mọi version và mọi exporter.

### 4.1. Module identifier là định danh kiến trúc

Module identifier thường gắn với tên application module được Spring Modulith phát hiện hoặc cấu hình, ví dụ `orders`, `payments`, `notifications`. Nó **không phải** ID của một request hoặc một object nghiệp vụ.

~~~text
module.identifier = orders       ✅ tập giá trị hữu hạn theo cấu trúc module
module.identifier = ORD-102485  ❌ ID đơn hàng, không phải tên module
~~~

Trong ví dụ dưới đây, class `OrderPlaced` thuộc module `orders` và được công bố từ code của chính module đó. Vì thế dữ liệu quan sát được gắn với `orders` là điều kỳ vọng. Tuy nhiên, ở hệ thống có cơ chế module detection tùy biến hoặc event được phát qua nhiều tầng trung gian, hãy kiểm tra metadata và tag thực tế thay vì tự suy ra module identifier chỉ từ tên bean đang gọi `publishEvent()`.

### 4.2. Event type đại diện cho loại thông điệp, không phải từng instance

Giả sử 1.000 đơn hàng khác nhau đều tạo object `new OrderPlaced(orderId)`. Tất cả vẫn thuộc **một event type**. Điều này làm metric có thể tổng hợp theo loại sự kiện:

~~~text
OrderPlaced("ORD-001") ──┐
OrderPlaced("ORD-002") ──┼─► module.event.type = OrderPlaced
OrderPlaced("ORD-003") ──┘
~~~

Việc đưa `orderId` hoặc `customerId` làm tag sẽ tạo số lượng time series rất lớn và tiềm ẩn rủi ro lộ dữ liệu. Nếu cần tìm một sự kiện cụ thể, dùng log có correlation ID, trace hoặc Event Publication Registry với phân quyền phù hợp.

### 4.3. Counter riêng có tập tag khác counter tổng hợp

Theo tài liệu, counter riêng `module.events.published.$moduleIdentifier.$simpleEventTypeName` mặc định có:

| Tag | Ý nghĩa |
| --- | --- |
| `module.identifier` | Module gắn với event |
| `module.name` | Tên hiển thị của module |

Đừng mặc định counter riêng cũng có tag `module.event.type`; **loại event đã hiện diện trong tên metric**. Nếu muốn phân loại sâu hơn theo một enum hữu hạn như `priority=STANDARD/EXPRESS`, có thể dùng extension point dành riêng cho counter từng loại event ở phần sau.

## 5. Một ví dụ nghiệp vụ có thể quan sát

Giả sử ứng dụng Spring Boot dùng các module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderPlaced.java
│   ├── OrderCancelled.java
│   └── OrderService.java
├── notifications
│   └── NotificationListener.java
└── analytics
    └── OrderAnalyticsListener.java
~~~

Trong module `orders`, định nghĩa event và phân loại ưu tiên có **tập giá trị nhỏ**:

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId, Priority priority) {

    public enum Priority {
        STANDARD, EXPRESS
    }
}
~~~

~~~java
// com/example/shop/orders/OrderCancelled.java
package com.example.shop.orders;

public record OrderCancelled(String orderId) {}
~~~

Module `orders` công bố event bằng `ApplicationEventPublisher`:

~~~java
package com.example.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(String orderId, OrderPlaced.Priority priority) {
        // Trong hệ thống thật: kiểm tra và lưu đơn hàng theo transaction.
        events.publishEvent(new OrderPlaced(orderId, priority));
    }

    public void cancelOrder(String orderId) {
        // Trong hệ thống thật: kiểm tra nghiệp vụ và lưu thay đổi trạng thái.
        events.publishEvent(new OrderCancelled(orderId));
    }
}
~~~

Ví dụ chỉ nhằm cho thấy **đường tạo và publish domain event**. Nó không triển khai persistence, transaction hay HTTP API hoàn chỉnh; khi xây ứng dụng thật cần quyết định thời điểm publish phù hợp với tính nhất quán dữ liệu.

Nếu module observability đang được cấu hình và event được ghi nhận, ta có thể phân tích:

- Tổng số event do `orders` công bố.
- Số `OrderPlaced` và `OrderCancelled` theo tag `module.event.type` hoặc counter riêng.
- Tần suất `OrderPlaced` trong một cửa sổ thời gian.
- Sau khi tùy biến, phân phối `OrderPlaced` theo `priority`, nếu đó là một nhu cầu vận hành có giá trị.

### 5.1. Một event có nhiều listener: đếm thế nào?

Giả sử `OrderPlaced` được publish **một lần** nhưng có hai listener:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant B as ApplicationEventPublisher
    participant N as notifications
    participant A as analytics
    O->>B: publishEvent(OrderPlaced)
    Note over B: Một lần publish được event metric theo dõi
    B->>N: deliver OrderPlaced
    B->>A: deliver OrderPlaced
~~~

Counter publication không được diễn giải mặc định thành **hai lần xử lý thành công** chỉ vì có hai listener. Với Event Publication Registry, một lần publish có thể sinh **nhiều publication records theo từng listener**; lifecycle của chúng cần được kiểm tra riêng. Metrics do Spring Modulith đăng ký như trên đo khía cạnh **publish**, không thay thế toàn bộ cơ chế theo dõi subscriber.

## 6. Bật Spring Modulith event metrics trong Spring Boot

Phần quan sát module cần Spring Modulith observability và Micrometer metrics infrastructure. Với dự án dùng BOM Spring Boot/Spring Modulith tương thích, cách tiện là thêm Insight starter:

~~~xml
<!-- pom.xml: dùng dependency management phù hợp để quản lý version -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Starter này kết hợp Actuator và hỗ trợ observability của Spring Modulith. Nếu dự án chỉ cần hỗ trợ observability mà không dùng toàn bộ Insight starter, trong Spring Modulith 2.x có thể dùng:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-core</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Với Gradle, ví dụ khi đã cấu hình version management phù hợp:

~~~groovy
dependencies {
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

Để viết Java code sử dụng `ModulithEventMetricsCustomizer` trong Spring Modulith 2.x, có thể cần thêm artifact API trong **compile scope** (không chỉ runtime):

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-api</artifactId>
</dependency>
~~~

Với Spring Modulith 1.x, tên artifact có thể khác. Luôn kiểm tra dependency tree và tài liệu theo **version thực tế**, không trộn tùy tiện artifact từ hai major version.

### 6.1. Cho phép đọc metrics ở môi trường thử nghiệm

Spring Boot Actuator không mặc định expose mọi endpoint qua HTTP. Ví dụ cấu hình cho môi trường phát triển:

~~~yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith"
~~~

Ở đây:

- `/actuator/metrics` dùng để **xem các Micrometer meter**.
- `/actuator/modulith` dùng để xem **module metadata và dependency graph**.
- Hai endpoint trả lời **hai câu hỏi khác nhau**; endpoint `modulith` không phải nơi xem publication counters.

Nếu cần Prometheus, thêm registry phù hợp:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Và expose `prometheus` ở nơi Prometheus server được phép thu thập:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith,prometheus"
~~~

Khi có registry và exposure thích hợp, scrape endpoint là `GET /actuator/prometheus`. Trong production, chỉ mở management endpoints cho hệ thống giám sát hoặc người dùng có quyền; bảo mật có thể được áp dụng bằng Spring Security, network policy, gateway hoặc management port riêng.

**Lưu ý:** Prometheus **không cần tracing exporter** để thu thập counter. Tracing để quan sát span/trace là một pipeline riêng, dù cả hai có thể chia sẻ Micrometer infrastructure.

## 7. Đọc `module.events.published` qua Actuator Metrics

Sau khi chạy ứng dụng và publish một số event thử nghiệm, bắt đầu bằng:

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Response sẽ liệt kê tên metric đang có; các meter đăng ký khi event xuất hiện có thể **chưa có trong danh sách ngay sau startup**. Hãy publish event thật trước khi kết luận rằng cấu hình bị lỗi.

Đọc counter tổng hợp:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published"
~~~

Một response JSON **giả lập để học cách đọc**, sau khi có hai loại event:

~~~json
{
  "name": "module.events.published",
  "description": "Application module event publications",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 15.0
    }
  ],
  "availableTags": [
    {
      "tag": "module.identifier",
      "values": ["orders"]
    },
    {
      "tag": "module.name",
      "values": ["Orders"]
    },
    {
      "tag": "module.event.type",
      "values": ["OrderPlaced", "OrderCancelled"]
    }
  ]
}
~~~

Không coi response này là snapshot của ứng dụng thật. Mô tả text, thứ tự các tag và giá trị `module.event.type` do version/configuration thực tế quyết định.

### 7.1. Lọc theo module identifier

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:orders"
~~~

Kết quả là counter publication tương ứng với meter name và điều kiện tag; nếu nhiều event type cùng thuộc `orders`, endpoint có thể **cộng số đo** của các time series thỏa điều kiện vào một giá trị COUNT.

### 7.2. Lọc theo event type

Giả sử giá trị thực tế trong response là `OrderPlaced`:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published?tag=module.event.type:OrderPlaced"
~~~

Chỉ dùng đúng giá trị tag đã nhìn thấy trong `availableTags`. Nếu runtime trả fully-qualified type name hoặc cách biểu diễn khác, phải thay value tương ứng.

### 7.3. Lọc đồng thời theo module và event type

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:orders&tag=module.event.type:OrderPlaced"
~~~

Hai tham số `tag=...` được Spring Boot Actuator dùng **đồng thời** để thu hẹp những meter trùng tên. Đây là cách trực tiếp để trả lời “module `orders` đã công bố bao nhiêu `OrderPlaced` được ghi nhận?” ở thời điểm hiện tại.

Nếu có nhiều instance, câu trả lời chỉ phản ánh **instance bạn đang gọi**; muốn nhìn tổng hệ thống, dùng backend metrics có cơ chế thu thập từ các instance.

### 7.4. Đọc counter riêng từng loại

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced"
~~~

Tên metric trong URL ở đây vẫn dùng **dấu chấm của Micrometer**, không phải tên Prometheus đã được chuyển đổi. Counter riêng có thể chỉ có `module.identifier` và `module.name` cùng những tag bổ sung do ứng dụng tùy biến.

## 8. Phân tích metric trong Prometheus/Grafana

Spring Boot Actuator với `micrometer-registry-prometheus` cung cấp dữ liệu scrape tại:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Ví dụ cấu hình scrape bên Prometheus:

~~~yaml
scrape_configs:
  - job_name: "shop-modulith"
    metrics_path: "/actuator/prometheus"
    scrape_interval: 15s
    static_configs:
      - targets: ["shop-app:8080"]
~~~

Đây là ví dụ một instance trong mạng thử nghiệm, địa chỉ `shop-app:8080` phải đổi theo môi trường triển khai.

Micrometer/Prometheus chuyển tên metric từ dạng dotted thành dạng phù hợp Prometheus, thường dùng dấu gạch dưới và hậu tố `_total` cho counter. Tên label cũng có thể được chuyển đổi từ dấu chấm sang dấu gạch dưới. **Trước khi viết PromQL, phải kiểm tra tên series và label thực tế trên `/actuator/prometheus`**.

Ví dụ, **nếu** exporter đưa ra series:

~~~text
module_events_published_total{
  module_identifier="orders",
  module_event_type="OrderPlaced",
  module_name="Orders"
} 12
~~~

thì các truy vấn PromQL **minh họa theo tên đã kiểm tra** sẽ là:

~~~promql
# Số lần publish mỗi giây theo module và loại sự kiện (5 phút gần nhất)
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

~~~promql
# Mức tăng số lần publish trong 15 phút theo từng module
sum by (module_identifier) (
  increase(module_events_published_total[15m])
)
~~~

~~~promql
# Tỷ lệ OrderCancelled/OrderPlaced của orders trong 1 giờ;
# clamp_min tránh mẫu số bằng 0.
sum(increase(module_events_published_total{
  module_identifier="orders",module_event_type="OrderCancelled"
}[1h]))
/
clamp_min(
  sum(increase(module_events_published_total{
    module_identifier="orders",module_event_type="OrderPlaced"
  }[1h])), 1
)
~~~

Các truy vấn trên chỉ áp dụng nếu tên metric và label đúng như phần minh họa. Trong hệ thống có tên Prometheus đã đổi theo exporter, phải thay cho phù hợp. Công thức tỷ lệ cần diễn giải cẩn trọng: sử dụng `clamp_min(...,1)` tránh chia cho 0 nhưng khi có ít event có thể làm tỷ lệ kém ý nghĩa; đối với dashboard nghiêm túc nên hiển thị “không đủ dữ liệu” khi mẫu số bằng 0.

### 8.1. Tại sao dùng `rate()` hoặc `increase()`?

Counter không giảm trong vòng đời process, vì thế biểu đồ giá trị tích lũy không trực tiếp phản ánh biến động gần đây. `rate()` và `increase()` giúp quan sát theo cửa sổ thời gian và xử lý reset của counter theo cách Prometheus hỗ trợ.

Khi nhiều instance đồng thời phát event, nên tính `rate()`/`increase()` trên mỗi series **trước khi sum**; đây là quy tắc phổ biến để tránh làm sai lệch việc phát hiện counter reset.

### 8.2. Gợi ý các bảng điều khiển

| Biểu đồ | Nhóm dữ liệu | Câu hỏi vận hành |
| --- | --- | --- |
| Event publications/s | `module.identifier` | Module nào đang phát nhiều event? |
| Event publications/s theo type | `module.identifier` + `module.event.type` | Event nào tăng nhanh bất thường? |
| Tỷ lệ event loại nghiệp vụ | Cùng module, chọn hai event types | Thay đổi trạng thái nghiệp vụ có bất thường không? |
| So sánh trước/sau triển khai | Cùng event type, cùng môi trường | Bản mới có tạo thêm/giảm lần publish không? |

Nếu một event type mới xuất hiện, đồng thời kiểm tra contract, code phát sự kiện và listener tương ứng. Metric tăng không tự chứng minh downstream xử lý tốt; giảm không tự chứng minh ứng dụng hỏng.

## 9. Tùy biến counter riêng bằng `ModulithEventMetricsCustomizer`

Spring Modulith có extension point để bổ sung tag cho counter của **một loại event cụ thể**. Đây là nơi phù hợp để phân loại bằng giá trị hữu hạn trong domain, ví dụ mức ưu tiên STANDARD/EXPRESS.

Theo API hiện hành, `ModulithEventMetricsCustomizer` nằm trong package `org.springframework.modulith.observability`. Với record `OrderPlaced` ở phần 5, có thể viết:

~~~java
package com.example.shop;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderEventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, counter) -> counter.tags(
                "priority",
                event.priority().name()
            )
        );
    }
}
~~~

Đoạn code minh họa sử dụng API `customize(Class<T>, BiConsumer<T, Counter.Builder>)`. Cần import dependency `spring-modulith-observability-api` ở compile scope theo dòng Spring Modulith đang dùng và giữ tên package/class event phù hợp dự án.

Giả sử `priority` là enum có **hai** giá trị, số time series tăng có kiểm soát:

~~~text
module.events.published.orders.OrderPlaced
  module.identifier=orders, priority=STANDARD

module.events.published.orders.OrderPlaced
  module.identifier=orders, priority=EXPRESS
~~~

Không dùng:

~~~java
// Tránh: mỗi orderId mới có thể tạo một time series mới.
counter.tags("orderId", event.orderId());
~~~

**Cardinality** là số tổ hợp các giá trị tag có thể xuất hiện. Nếu có 20 module × 30 event types × 3 mức priority × 5 môi trường, số tổ hợp có thể tăng nhanh; thêm order ID, customer ID hoặc timestamp riêng từng event còn khiến registry và backend quá tải.

### 9.1. Hai cách bổ sung tag không giống nhau

| Cách | Phạm vi | Khi nào dùng? |
| --- | --- | --- |
| `ModulithEventMetricsCustomizer` | Tùy biến counter theo **event type cụ thể**, có thể đọc thuộc tính event | Khi cần phân loại ưu tiên, kênh xử lý hoặc enum domain có ít giá trị |
| `management.metrics.tags.*` / common tags | Áp dụng tag môi trường lên các meter được quản lý | Khi muốn phân biệt environment, region, service |

Việc bổ sung event-specific tags cho **counter riêng** không bảo đảm counter tổng hợp `module.events.published` cũng nhận những tag đó. Hãy kiểm tra cả hai meter sau khi cấu hình.

## 10. Metrics trả lời được gì về kiến trúc mô-đun?

Spring Modulith dùng module graph để biểu diễn quan hệ tĩnh, Actuator để expose metadata module, event metrics để đếm lần publish, tracing để theo dõi execution và context propagation để nối lời gọi qua các ranh giới thread/process.

~~~mermaid
flowchart TB
    Architecture["Module graph<br/>orders → payments, notifications → orders"]
    Actuator["GET /actuator/modulith<br/>metadata kiến trúc"]
    Publisher["orders.publish(OrderPlaced)"]
    Counter["module.events.published<br/>identifier + event type"]
    Listener["notifications listener"]
    Trace["Trace / module entry spans<br/>execution theo thời gian"]
    Registry["Event Publication Registry<br/>trạng thái theo listener"]
    Architecture -.-> Actuator
    Publisher --> Counter
    Publisher --> Listener
    Listener -.-> Trace
    Listener -.-> Registry
~~~

Các nguồn tín hiệu:

| Nguồn | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| Module graph / `/actuator/modulith` | Module và outgoing dependency được nhận diện trong bản ứng dụng | Đã có event cụ thể nào được publish |
| `module.events.published` | Bộ đếm publish theo module và type có tăng | Listener đã nhận hoặc commit thành công |
| Counter riêng theo event type | Số publish của loại event cụ thể, có thể tách theo tag domain giới hạn | Payload, order ID hoặc kết quả mọi listener |
| Module entry spans / distributed tracing | Những đoạn xử lý được instrument và được ghi nhận trong trace | Toàn bộ quan hệ phụ thuộc tĩnh hoặc toàn bộ event không được sample |
| Event Publication Registry | Publication đến transactional listeners và trạng thái xử lý tùy backend/lifecycle | Cùng cách tính với counter aggregate |

Một event type trong module `orders` có thể được listener thuộc `notifications` nhận. Khi đọc metrics, tag `module.identifier=orders` mô tả **module gắn với nguồn event**; không nên mặc định đó là module listener đã hoàn tất xử lý. Muốn phân tích listener, xem event registry, logs và trace span của listener, kết hợp correlation ID.

## 11. Giải thích số liệu trong các tình huống đặc biệt

### 11.1. Có nhiều listener cho cùng một event

Một lần publish có thể khiến nhiều listener được kích hoạt. Counter publish không biến thành counter success của các listener. Nếu cần tính tỷ lệ xử lý thành công, phải lấy mẫu số/mẫu số có cùng **đơn vị đo và semantics**, ví dụ số publication records tới listener so với số publication records hoàn tất, thay vì chia “số listener thành công” cho “số event publish” khi một event có nhiều listener.

### 11.2. Listener chạy bất đồng bộ

Event publication metric có thể đã tăng tại thời điểm publish trong khi listener còn đang đợi executor hoặc transaction commit. Nếu listener chạy sau vài giây/phút, metric không thể tự cung cấp **độ trễ end-to-end**. Cần thêm metric thời gian xử lý, trace span hoặc thời điểm từ publication registry; context propagation giúp giữ correlation khi phù hợp.

### 11.3. Listener lỗi và sự kiện được retry

Một publish ban đầu có thể dẫn tới nhiều lần listener attempt. Việc retry listener từ Event Publication Registry không đồng nghĩa có lần publish domain event mới với cùng semantics. Đừng dùng `module.events.published` làm “số lần retry” nếu chưa kiểm chứng mã instrumentation của version hiện hành. Theo dõi lifecycle publication riêng.

### 11.4. Rollback hoặc publish rồi hủy transaction

Việc gọi `publishEvent(...)` và commit thành công của transaction là hai khái niệm khác nhau. Counter mô tả hoạt động publish mà instrumentation ghi nhận; không tự bảo đảm business transaction commit, database đã lưu hoặc downstream đã xử lý. Việc dispatch/listener thực sự chạy trước hay sau commit phụ thuộc annotation và chính sách transaction.

### 11.5. Trùng class name ở nhiều module

Hai event cùng simple class name `Completed` ở các module khác nhau có thể tạo counter riêng với phần tên giống nhau nhưng tiền tố module khác nhau. Đối với counter tổng hợp, luôn quan sát cả `module.identifier` và giá trị thật của `module.event.type`. Nếu cần tránh nhầm lẫn ở hợp đồng sự kiện, dùng tên sự kiện rõ nghĩa và kiểm tra package/cách biểu diễn type mà version hiện tại cung cấp.

### 11.6. Số counter giảm sau deploy

Counter là giá trị tích lũy theo lifecycle registry/process. Khởi động lại instance có thể làm số đo quay về 0; dashboard nên tính `rate()` hoặc `increase()` và xử lý reset. So sánh giá trị COUNT tuyệt đối giữa hai lần chạy khác thời gian thường vô nghĩa.

## 12. Chẩn đoán khi không thấy metric

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `/actuator/metrics` trả 404 | Endpoint chưa expose, thiếu Actuator hoặc sai port/base path | Kiểm tra dependency, `management.endpoints.web.exposure.include`, management port |
| `/actuator/metrics` trả 401/403 | Management endpoint bị bảo vệ | Dùng danh tính có quyền, giữ security trên môi trường thật |
| Có metrics khác nhưng không thấy `module.events.published` | Chưa publish domain event được instrumentation quan sát, thiếu Modulith observability hoặc runtime module detection khác | Gọi luồng publish thử, kiểm tra dependency, module metadata và log |
| Có counter tổng hợp nhưng query theo type không ra | Giá trị `module.event.type` không giống chuỗi đã đoán | Xem `availableTags`, lọc theo value thực tế |
| Query counter riêng trả 404 | Tên module hoặc simple event type sai, event chưa xuất hiện | Tra danh sách meter names trước, rồi xây lại tên |
| Prometheus không thấy metric | Chưa có Prometheus registry, chưa expose scrape endpoint, scrape lỗi hoặc tên bị đổi | Kiểm tra `/actuator/prometheus` và target health trên Prometheus |
| Count cao hơn kỳ vọng | Event được publish nhiều lần, listener hoặc code khác cũng publish, nhiều instance hoặc đã cộng hai loại metric | Kiểm tra source publish, tag, instance và cách aggregation |
| Count thấp hơn kỳ vọng | Không phải mọi event đi qua đường instrumentation, bị filter/registry disable, instance không được scrape hoặc counter reset | Ghi nhận từng instance và kiểm tra luồng publish, config |
| Type có rất nhiều series | Customizer thêm ID/timestamp hoặc quá nhiều tag tùy biến | Bỏ tag độ biến thiên cao, dùng enum hoặc lưu chi tiết qua log/trace |
| Event metric tăng nhưng không thấy span listener | Tracing chưa cấu hình, sampling, listener async mất context hoặc không được instrument | Kiểm tra tracing/propagation độc lập, event registry nếu có |

Khi xử lý sự cố, hãy kiểm tra theo thứ tự **dependency → event thực sự được publish → meter trong Actuator → exporter/registry → dashboard query**. Cách này giúp phân biệt lỗi tạo số liệu với lỗi truy xuất hoặc hiển thị số liệu.

## 13. Bài thực hành: lọc metrics theo module identifier và event type

**Bối cảnh:** ứng dụng Spring Boot có module `orders` công bố `OrderPlaced` và `OrderCancelled`; module `notifications` lắng nghe `OrderPlaced`. Mục tiêu là chứng minh counters phản ánh **publish**, cho phép tách theo module/type và giữ cardinality hợp lý.

Các bước:

1. Thêm Spring Modulith Insight starter hoặc observability-core và Spring Boot Actuator theo version tương thích.
2. Expose `health,metrics,modulith` ở profile thử nghiệm, cấu hình bảo mật phù hợp.
3. Tạo 10 lần `OrderPlaced`, gồm 6 `STANDARD` và 4 `EXPRESS`, sau đó tạo 2 lần `OrderCancelled`. Giữ số lần publish thực tế có thể kiểm đếm được.
4. Gọi `/actuator/metrics`, xác nhận meter `module.events.published` đã được đăng ký.
5. Lấy `/actuator/metrics/module.events.published`, ghi giá trị trong `availableTags` rồi lọc theo `module.identifier=orders` và tag `module.event.type` thực tế.
6. Đọc từng counter riêng. Đối chiếu số event công bố theo từng loại mà **không cộng thêm** counter tổng hợp.
7. Thêm `ModulithEventMetricsCustomizer` để tách `OrderPlaced` theo `priority`, kiểm tra giá trị STANDARD/EXPRESS trên counter riêng.
8. Nếu có Prometheus, kiểm tra tên series thực tế và vẽ tốc độ tăng trong một cửa sổ thời gian.
9. Cho listener `notifications` thất bại ở môi trường test, rồi giải thích vì sao counter publish vẫn có thể tăng dù listener không hoàn tất; kiểm tra registry/tracing để hiểu sự khác biệt.

Mẫu bảng kết quả **kỳ vọng ở mô hình không publish thêm và không restart**:

| Chỉ số đọc | Số dự kiến | Điều cần chứng minh |
| --- | ---: | --- |
| `module.events.published`, lọc `orders` | 12 | Đếm các event do module được quan sát công bố |
| Cùng meter, lọc `OrderPlaced` | 10 | Có thể chia theo event type |
| Cùng meter, lọc `OrderCancelled` | 2 | Type khác có count riêng |
| Counter riêng của `OrderPlaced`, `priority=STANDARD` | 6 | Custom tag có số giá trị hữu hạn |
| Counter riêng của `OrderPlaced`, `priority=EXPRESS` | 4 | Hai nhánh priority gộp lại bằng 10 |

**Lưu ý:** đây là bảng *dự kiến để tự kiểm chứng*, chỉ đúng nếu luồng chạy đúng số lần publish, instrumentation phù hợp và không có sự kiện thử nghiệm khác cùng type. Với `/actuator/metrics`, giá trị chỉ phản ánh instance được gọi.

**Tiêu chí đạt:** giải thích chính xác chênh lệch giữa metric tổng và riêng, lọc đúng hai chiều module/event, nêu được một truy vấn theo thời gian và chỉ ra vì sao số lần publish không đồng nghĩa số lần xử lý thành công.

## 14. Câu hỏi ôn tập

1. `module.events.published` và `module.events.published.orders.OrderPlaced` có phải hai lần publish khác nhau không?
2. Khi lọc theo `module.identifier=orders`, giá trị `orders` đại diện cho điều gì?
3. Tag nào thể hiện loại event trong counter tổng hợp? Counter riêng có bắt buộc có tag đó không?
4. Một event có hai listener thì giá trị counter publish có nhất thiết tăng hai lần không?
5. Vì sao `orderId` không phải lựa chọn tốt làm metric tag?
6. Vì sao dashboard vận hành nên tính `rate()` hoặc `increase()` thay vì so COUNT tại hai thời điểm không tương đương?
7. Làm thế nào phân biệt lỗi thiếu metric do không có event với lỗi Prometheus chưa scrape được?
8. Nếu listener thất bại nhưng metric publication tăng, cần công cụ nào để biết publication còn xử lý dở hoặc thất bại?

**Gợi ý đáp án:** (1) Không, đây là hai góc nhìn thống kê; (2) module được Spring Modulith gắn với nguồn event, không phải order ID; (3) `module.event.type`, counter riêng phân biệt type qua metric name; (4) không, publish và xử lý theo listener là hai việc khác nhau; (5) cardinality và dữ liệu nhạy cảm; (6) counter reset và thay đổi theo thời gian; (7) đối chiếu meter trực tiếp trong Actuator và scrape/target bên Prometheus; (8) Event Publication Registry, log và tracing.

## 15. Ghi nhớ

Với Spring Modulith, **metric theo module identifier và event type** giúp trả lời câu hỏi *module nào đang công bố loại sự kiện gì, với tần suất bao nhiêu*. Counter tổng hợp `module.events.published` dùng các tag `module.identifier`, `module.name` và `module.event.type`; counter riêng `module.events.published.$moduleIdentifier.$simpleEventTypeName` thuận tiện để thêm một số tag nghiệp vụ có cardinality thấp.

Hãy đọc counters bằng `/actuator/metrics` trước khi viết PromQL; dùng tên và tag thực tế của exporter khi truy vấn Prometheus. Kết hợp với **module graph** và endpoint `/actuator/modulith` để đối chiếu ranh giới kiến trúc, với **traces/context propagation** để lần theo execution, và với **Event Publication Registry** để kiểm tra kết quả xử lý event. Những tín hiệu này bổ trợ nhau nhưng đo **những giai đoạn khác nhau**.

### Tài liệu tham khảo

- [Spring Modulith – Production-ready Features: Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html) — hai counter, các tag và ví dụ `ModulithEventMetricsCustomizer`.
- [Spring Modulith – ModulithEventMetricsCustomizer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html).
- [Spring Modulith – ModulithEventMetrics API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html).
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — meter names, query `tag=KEY:VALUE`, Prometheus và naming conventions.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — HTTP exposure, access và security.
- [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — event listeners và Event Publication Registry.

> **Lưu ý phiên bản:** bài sử dụng tên metrics/tags theo Spring Modulith hiện hành; dependency artifact, hình thức export và một số giá trị tag có thể khác theo Spring Boot, Micrometer và Spring Modulith đang dùng. Khi vận hành, luôn đối chiếu tài liệu đúng với BOM và response thực tế của ứng dụng. Nội dung được soạn cho STEP 4; QA chuyên môn sẽ được xử lý ở bước kế tiếp.
