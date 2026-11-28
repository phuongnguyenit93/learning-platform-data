# `ModulithEventMetricsCustomizer` là gì?

## 1. Bối cảnh: vì sao cần tùy biến metrics cho application event?

Trong ứng dụng Spring Boot thiết kế theo **Spring Modulith**, mỗi *application module* đảm nhiệm một phần nghiệp vụ và có ranh giới rõ ràng. Chẳng hạn, module `ordering` phát sự kiện `OrderPlaced` khi đơn hàng được tạo; module `notification` lắng nghe sự kiện để gửi thông báo; module `reporting` có thể thống kê số đơn hàng.

Trong quá trình vận hành, ta muốn biết một số câu hỏi:

- Module `ordering` đã phát bao nhiêu sự kiện `OrderPlaced`?
- Tần suất phát sự kiện từ kênh `WEB` có khác `MOBILE` không?
- Khi tốc độ phát sự kiện tăng, dashboard có thể phân nhóm theo **loại kênh bán** không?
- Có thể bổ sung nhãn nghiệp vụ mà không phải tự dựng lại toàn bộ bộ đếm do Spring Modulith cung cấp không?

Spring Modulith hỗ trợ metrics cho các domain event được phát. **`ModulithEventMetricsCustomizer`** là interface mở rộng để tùy biến việc xây dựng các **Micrometer Counter** cho từng loại event. Đặc biệt, nó cho phép đọc dữ liệu của event và **thêm tag có ý nghĩa nghiệp vụ** vào counter tương ứng.

Đây là bài học thuộc chương **Event customizer** của module **`SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`**. Mục tiêu rộng hơn của module là sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần của ứng dụng bằng module graph, Actuator, event metrics, tracing và context propagation. Customizer giúp cải thiện góc nhìn metrics trong bức tranh đó.

**Không nhầm vai trò:** customizer thay đổi **cách ghi nhận thông tin trên metric**, chứ không chuyển đổi payload event, không quyết định listener nào nhận event, không bật retry và không bảo đảm event đã được xử lý thành công.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích API `ModulithEventMetricsCustomizer`, biết metric nào được tùy biến, khai báo dependency và bean chính xác, viết ví dụ Java bổ sung tag từ domain event, kiểm tra kết quả qua Actuator, kiểm soát cardinality và phân biệt metric của event với traces, module graph và Event Publication Registry.

## 2. Hai họ event metrics của Spring Modulith

Khi bật hỗ trợ observability, Spring Modulith đăng ký hai họ bộ đếm cho domain event được phát:

| Meter Micrometer | Mục đích | Tag cơ sở theo tài liệu |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp các lần phát domain event. | `module.event.type`, `module.identifier`, `module.name`. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho từng loại event thuộc module. | `module.identifier`, `module.name`; có thể thêm tag nghiệp vụ. |

Ví dụ event `OrderPlaced` của module `ordering` có thể có meter:

~~~text
module.events.published
module.events.published.ordering.OrderPlaced
~~~

Các tên trên là **tên meter trong Micrometer**. Hệ thống như Prometheus có thể biến đổi tên khi xuất dữ liệu (đổi dấu chấm thành dấu gạch dưới, thêm suffix cho counter, v.v.), nên hãy kiểm tra dữ liệu xuất thực tế thay vì suy đoán mọi tên của time series.

### 2.1. Counter tổng hợp: có sẵn chiều phân nhóm

Counter `module.events.published` giúp xem event nào được module nào phát. Những nhãn do Spring Modulith định nghĩa mang ý nghĩa cấu trúc và loại event:

- `module.identifier`: định danh kỹ thuật, ví dụ `ordering`.
- `module.name`: tên hiển thị của module.
- `module.event.type`: loại event được ghi nhận.

Nếu mục tiêu chỉ là đếm tổng số `OrderPlaced` theo module/loại event, các nhãn này thường đã đủ. Customizer không cần thiết cho một câu hỏi mà metrics mặc định đã trả lời.

### 2.2. Counter riêng: nơi cần customizer

Counter riêng `module.events.published.ordering.OrderPlaced` có thể được bổ sung tag `channel=web`, `channel=mobile` hoặc `channel=pos`. Khi đó, dashboard có thể hiển thị ba nhóm lưu lượng thay vì chỉ tổng số sự kiện.

`ModulithEventMetricsCustomizer` được Spring Modulith giới thiệu để tùy biến **individual event metrics** theo loại event. Đây là điểm mở rộng chuyên biệt; không nên hiểu rằng callback này tự thêm tag vào mọi meter do ứng dụng hoặc Spring Boot tạo ra.

## 3. Hợp đồng API của `ModulithEventMetricsCustomizer`

Theo Java API của Spring Modulith 2.2, interface ở package:

~~~java
org.springframework.modulith.observability.ModulithEventMetricsCustomizer
~~~

Nó là một *functional interface* có phương thức về mặt ý tưởng:

~~~java
void customize(ModulithEventMetrics metrics);
~~~

Đối tượng `ModulithEventMetrics` cho phép khai báo quy tắc theo **kiểu Java của domain event**. API hỗ trợ hai dạng:

~~~java
<T> ModulithEventMetrics customize(
    Class<T> type,
    BiConsumer<T, Counter.Builder> consumer
);

<T> ModulithEventMetrics customize(
    Class<T> type,
    Function<T, Counter.Builder> factory
);
~~~

Hai chữ ký trên là **rút gọn để minh họa ý nghĩa API**; khi sử dụng thật, cần các import `java.util.function.*`, `io.micrometer.core.instrument.Counter` tương ứng.

| Thành phần | Vai trò |
| --- | --- |
| `Class<T> type` | Chọn đúng kiểu event mà quy tắc tùy biến áp dụng. |
| `T event` | Object sự kiện cụ thể, cho phép đọc các thuộc tính như `channel`. |
| `Counter.Builder` | Bộ dựng counter Micrometer; có thể bổ sung `tags(...)`. |
| `BiConsumer<T, Counter.Builder>` | Điều chỉnh builder mặc định của metric cho event tương ứng. |
| `Function<T, Counter.Builder>` | Tự cung cấp builder khi cần thay đổi sâu hơn cách tạo counter. |

Trong phần lớn nhu cầu **bổ sung tag**, dạng `BiConsumer` đủ dùng và an toàn hơn vì có thể giữ tên meter và các thiết lập cơ sở do Spring Modulith tạo. Dạng `Function` dành cho nhu cầu thay thế builder và đòi hỏi hiểu rõ naming, tag mặc định, tương thích dashboard và cách triển khai của phiên bản thư viện.

### Callback diễn ra ở đâu?

Sơ đồ sau biểu diễn đường đi logic, không khẳng định mọi phương thức nội bộ được gọi đúng tên như các ô:

~~~mermaid
flowchart LR
    P["ordering phát OrderPlaced"]
    O["Spring Modulith observability"]
    M["Tìm quy tắc cho OrderPlaced"]
    B["Xây Counter.Builder"]
    C["Customizer thêm tag channel"]
    R["Micrometer MeterRegistry"]
    E["/actuator/metrics hoặc backend"]
    P --> O --> M --> B --> C --> R --> E
~~~

Điều quan trọng: các quy tắc được **đăng ký khi Spring cấu hình bean**, còn phần đọc dữ liệu event để tùy biến counter diễn ra trong quá trình ghi nhận sự kiện. Bạn không cần tự gọi `customize(...)` mỗi khi phát event.

## 4. Thiết lập dependency và hạ tầng quan sát

### 4.1. Dependency cho Spring Modulith observability

Với Gradle Kotlin DSL và một dự án đã quản lý phiên bản Spring Boot/Spring Modulith tương thích qua BOM hoặc dependency management:

~~~kotlin
dependencies {
    // Instrumentation và Actuator của Spring Modulith.
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")

    // Cho phép import interface customizer trong source Java.
    implementation("org.springframework.modulith:spring-modulith-observability-api")

    // Chỉ cần nếu muốn xuất metrics cho Prometheus.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

`spring-modulith-starter-insight` cung cấp khả năng Actuator và observability ở runtime. `spring-modulith-observability-api` cần ở **compile scope** vì ứng dụng trực tiếp dùng `ModulithEventMetricsCustomizer` trong Java source. Khi không dùng Insight Starter, có thể khai báo `spring-modulith-observability-core` ở runtime cùng các dependency hạ tầng phù hợp.

Nếu dùng Maven, ý tưởng tương tự: starter insight ở scope `runtime`, còn `spring-modulith-observability-api` ở compile scope mặc định.

**Lưu ý phiên bản:** API customizer được giới thiệu từ Spring Modulith **1.4**. Hãy dùng phiên bản phù hợp với Spring Boot đang chạy và thống nhất phiên bản của các artifact; không tự ghép tùy tiện artifact 1.x với 2.x. Đối chiếu javadoc đúng dòng phiên bản nếu tên package hoặc cách autoconfigure có thay đổi.

### 4.2. Kích hoạt Actuator để kiểm tra

Trong môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
~~~

- `metrics` dùng để xem danh sách và chi tiết meter qua HTTP.
- `prometheus` chỉ có ý nghĩa khi Prometheus registry được thêm và endpoint có quyền truy cập.
- `modulith` công bố cấu trúc application module; nó không trả các giá trị metric.

Việc expose endpoint cần đi kèm cấu hình access và bảo mật phù hợp. Ở production, không công khai metrics và thông tin cấu trúc module nếu không có kiểm soát truy cập.

### 4.3. Có cần tracing để dùng customizer không?

**Không nhất thiết.** Micrometer metrics có thể được ghi nhận qua `MeterRegistry` dù chưa cấu hình tracing backend. Trace/span là nguồn thông tin riêng: nó giúp xem một lần xử lý đã đi qua module nào, còn counter giúp xem số lần event được phát. Khi cần distributed tracing, thêm tracing bridge và exporter theo tài liệu Spring Boot tương ứng; việc đó không phải chức năng của `ModulithEventMetricsCustomizer`.

## 5. Ví dụ hoàn chỉnh: thêm tag `channel` cho `OrderPlaced`

Giả sử ứng dụng có hai module dưới package gốc `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── ObservabilityConfiguration.java
├── ordering
│   ├── OrderPlaced.java
│   └── OrderService.java
└── notification
    └── OrderNotificationListener.java
~~~

Trong ví dụ, `ordering` phát event, `notification` sử dụng event qua listener. Ta muốn phân nhóm lượng event theo kênh bán hàng mà **không** tạo time series riêng cho từng mã đơn hàng.

### 5.1. Tạo kiểu domain event có giá trị phân nhóm hữu hạn

~~~java
package com.example.shop.ordering;

import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(UUID orderId, SalesChannel channel) {

    public OrderPlaced {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(channel, "channel");
    }

    public enum SalesChannel {
        WEB,
        MOBILE,
        POS
    }
}
~~~

`orderId` dùng để liên kết nghiệp vụ; `channel` chỉ có ba giá trị hợp lệ. Vì vậy **`channel` phù hợp làm metric tag hơn `orderId`**.

### 5.2. Phát sự kiện khi có đơn hàng

~~~java
package com.example.shop.ordering;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import com.example.shop.ordering.OrderPlaced.SalesChannel;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public UUID placeOrder(SalesChannel channel) {
        UUID id = UUID.randomUUID();

        // Minh họa điểm phát event. Ứng dụng thật cần lưu đơn hàng
        // và xác định transaction boundary phù hợp.
        events.publishEvent(new OrderPlaced(id, channel));
        return id;
    }
}
~~~

Ví dụ này cố ý ngắn để tập trung vào cơ chế metrics. Khi áp dụng vào nghiệp vụ thực tế, cần xử lý giao dịch, tính nhất quán dữ liệu và cách xử lý event phù hợp. **Gọi `publishEvent(...)` không đồng nghĩa listener đã hoàn tất thành công.**

### 5.3. Đăng ký bean `ModulithEventMetricsCustomizer`

~~~java
package com.example.shop;

import java.util.Locale;
import com.example.shop.ordering.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ModulithEventMetricsCustomizer modulithEventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, builder) -> builder.tags(
                "channel",
                event.channel().name().toLowerCase(Locale.ROOT)
            )
        );
    }
}
~~~

Đây là mẫu sử dụng dạng `BiConsumer<T, Counter.Builder>` theo API chính thức:

1. `@Bean` đưa customizer vào Spring `ApplicationContext`.
2. `metrics.customize(OrderPlaced.class, ...)` chỉ định kiểu event cần tùy biến.
3. `event.channel()` cung cấp dữ liệu nghiệp vụ từ **event hiện tại**.
4. `builder.tags("channel", ...)` bổ sung tag vào counter riêng cho event này.
5. `toLowerCase(Locale.ROOT)` đưa enum thành giá trị thống nhất: `web`, `mobile` hoặc `pos`.

Vì sử dụng một enum đóng, số giá trị của `channel` có giới hạn. Một counter được phân theo tag **không tạo một bản ghi time series mới cho từng order ID**.

### 5.4. Listener minh họa

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    @EventListener
    void on(OrderPlaced event) {
        // Ví dụ: lập lịch gửi email hoặc gửi tới một gateway khác.
        // Phần xử lý cụ thể không ảnh hưởng đến định nghĩa tag channel.
    }
}
~~~

Listener là minh họa cho mối liên hệ giữa module `notification` và event do `ordering` cung cấp. Customizer gắn tag **lúc metrics ghi nhận event được phát**, không cần truy cập vào implementation của listener. Nếu chuyển listener sang `@ApplicationModuleListener` để xử lý sau commit và bất đồng bộ, cần cấu hình transaction/async/context propagation phù hợp; customizer vẫn không thay thế những cấu hình đó.

## 6. Quan sát counter đã được tùy biến

### 6.1. Tạo một vài event khác nhau

Giả sử đã gọi `OrderService.placeOrder(...)` nhiều lần với các kênh:

| Event | `channel` | Kỳ vọng |
| --- | --- | --- |
| `OrderPlaced(id1, WEB)` | `web` | Counter riêng có tag `channel=web` tăng. |
| `OrderPlaced(id2, MOBILE)` | `mobile` | Counter riêng có tag `channel=mobile` tăng. |
| `OrderPlaced(id3, WEB)` | `web` | Cùng nhóm `channel=web` tăng tiếp. |
| `OrderPlaced(id4, POS)` | `pos` | Counter riêng có tag `channel=pos` tăng. |

Với một tiến trình mới chạy và không có event khác, nhóm `web` nhận hai lần increment, `mobile` một lần và `pos` một lần. Đây là **dữ liệu minh họa**, không phải số đo có sẵn của hệ thống.

### 6.2. Xem meter qua Actuator

~~~bash
curl -s http://localhost:8080/actuator/metrics

# Counter tổng hợp mọi domain event được ghi nhận:
curl -s http://localhost:8080/actuator/metrics/module.events.published

# Counter riêng của event OrderPlaced trong module ordering:
curl -s http://localhost:8080/actuator/metrics/module.events.published.ordering.OrderPlaced

# Đọc counter riêng có thêm tag channel:
curl -s "http://localhost:8080/actuator/metrics/module.events.published.ordering.OrderPlaced?tag=channel:web"
~~~

URL trên giả định module được nhận diện với identifier `ordering` và event có simple class name `OrderPlaced`. Tên meter thực tế phải được đối chiếu với dữ liệu Spring Modulith đang chạy. Endpoint `/actuator/metrics` chỉ hiện meter đã được đăng ký; nếu chưa phát event, meter có thể chưa xuất hiện.

Phản hồi `/actuator/metrics/{name}` thường có `name`, các mục `measurements` và `availableTags`. Ví dụ cấu trúc *minh họa*:

~~~json
{
  "name": "module.events.published.ordering.OrderPlaced",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 4.0
    }
  ],
  "availableTags": [
    {
      "tag": "channel",
      "values": ["web", "mobile", "pos"]
    }
  ]
}
~~~

Khi thêm query parameter `tag=channel:web`, response có thể phản ánh giá trị đã lọc thay vì toàn bộ counter. Giá trị thực phụ thuộc những event đã phát và các tag khác hiện diện trong registry.

### 6.3. Xuất qua Prometheus

Nếu thêm `micrometer-registry-prometheus` và expose endpoint:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Bạn có thể tìm chuỗi liên quan đến event `OrderPlaced` và tag `channel`. **Không tự lấy tên trong `/actuator/metrics` để giả định tên PromQL tương ứng**: registry và naming convention có thể thay thế dấu chấm, đổi chữ hoa, chuẩn hóa suffix hoặc nhãn. Sau khi kiểm tra tên time series thực tế, có thể tạo biểu đồ rate trong Prometheus/Grafana theo `channel`.

Một dashboard tốt nên cho thấy **tốc độ phát event theo kênh** trong các khoảng thời gian, thay vì dùng tổng counter tích lũy như tốc độ xử lý. Khi pod restart, counter có thể bắt đầu lại; Prometheus sử dụng các hàm như `rate()` hoặc `increase()` để phân tích counter theo cửa sổ thời gian.

## 7. Thiết kế tag: cardinality là yếu tố quyết định

Micrometer gắn tag vào meter để phân nhóm. Số tổ hợp giá trị tag càng lớn thì số time series cần lưu trữ càng nhiều, làm tăng bộ nhớ, lưu lượng scrape, lưu trữ và độ phức tạp truy vấn.

### 7.1. Chọn nhãn nào?

| Dữ liệu trong event | Nên dùng làm metric tag? | Lý do |
| --- | --- | --- |
| `channel=web/mobile/pos` | **Có** | Tập giá trị nhỏ, ổn định, hữu ích cho dashboard. |
| `paymentMethod=card/bank_transfer/cash` | **Có thể** | Tập giá trị hữu hạn nếu được chuẩn hóa. |
| `priority=normal/urgent` | **Có** | Dễ so sánh các nhóm nghiệp vụ. |
| `orderId=UUID` | **Không** | Gần như mỗi event một giá trị khác, gây high cardinality. |
| `customerId` | **Không** | Nhiều giá trị, có thể là dữ liệu nhạy cảm. |
| `email` hoặc `phone` | **Không** | Dữ liệu cá nhân và cardinality cao. |
| `errorMessage` tự do | **Không** | Có thể chứa thông tin riêng và vô số giá trị. |
| `rawUrl` có ID trong path | **Không** | Mỗi request có thể tạo nhãn khác nhau. |

Ví dụ **không nên làm**:

~~~java
// Tránh: tạo tag giá trị duy nhất gần như cho mỗi đơn hàng.
metrics.customize(OrderPlaced.class, (event, builder) ->
    builder.tags("orderId", event.orderId().toString())
);
~~~

Thay bằng tag `channel` hoặc một nhóm phân loại hữu hạn. Nếu cần truy vết một `orderId` cụ thể, hãy dùng **structured logs**, span attributes theo chính sách dữ liệu hoặc dữ liệu nghiệp vụ; không đưa ID duy nhất vào metric labels.

### 7.2. Số lượng tổ hợp tag

Giả sử counter riêng có thêm hai tag:

- `channel` gồm 3 giá trị.
- `priority` gồm 2 giá trị.

Nếu mọi tổ hợp đều phát sinh, cùng một meter có thể tạo tới **3 × 2 = 6** series riêng, chưa kể những chiều phân tách khác mà hệ thống metrics áp dụng như instance, environment hoặc region. Nếu thay `priority` bằng một `orderId` có 100.000 giá trị, số series có thể tăng rất mạnh.

Thực hành tốt là:

1. Xác định câu hỏi vận hành trước khi thêm tag.
2. Chỉ dùng tập giá trị nhỏ và được chuẩn hóa bằng enum hoặc bảng phân nhóm.
3. Giữ cùng tên tag và cùng miền giá trị trên các bản triển khai.
4. Không đưa dữ liệu cá nhân hoặc payload thô vào metric.
5. Kiểm tra số lượng series thực tế sau khi thêm tag và điều chỉnh dashboard/alert tương ứng.

### 7.3. Không tạo tên metric động theo từng event instance

`module.events.published.$moduleIdentifier.$simpleEventTypeName` dùng định danh module và **kiểu event**, không dùng `orderId` làm một phần tên metric. Customizer nên duy trì sự phân biệt đó: tên meter ổn định, còn các chiều nghiệp vụ hợp lý biểu diễn bằng tag hữu hạn.

## 8. Customizer này khác gì các cơ chế mở rộng khác?

| Cơ chế | Phạm vi chính | Khi nào dùng? |
| --- | --- | --- |
| `ModulithEventMetricsCustomizer` | Cách tạo counter riêng cho một kiểu domain event, đặc biệt là tag nghiệp vụ. | Muốn phân nhóm số lần phát `OrderPlaced` theo `channel`. |
| `ModulithObservationConvention` | Convention của Micrometer Observation đối với module entry, chẳng hạn tên/tag cho observation. | Muốn điều chỉnh convention của module-entry observation/span. |
| Micrometer `MeterFilter` | Chính sách áp dụng rộng trên registry, như lọc hoặc đổi ID meter. | Muốn giới hạn, chặn hoặc chuẩn hóa metrics trên nhiều thành phần. |
| `ApplicationModules.verify()` | Kiểm tra quy tắc phụ thuộc và ranh giới module từ mã nguồn. | Muốn phát hiện module phụ thuộc trái phép hoặc phụ thuộc vòng. |
| `/actuator/modulith` | Công bố cấu trúc module ở runtime. | Muốn xem module graph đang được nhận diện. |
| Event Publication Registry | Theo dõi publication và trạng thái hoàn tất của các transactional listener. | Muốn quản lý việc xử lý event, phát lại publication chưa hoàn tất. |
| Traces và context propagation | Quan sát các chặng thực thi và liên kết trace qua thread/process. | Muốn điều tra một request hoặc listener bất đồng bộ cụ thể. |

Ví dụ tình huống: dashboard thấy `OrderPlaced(channel=web)` tăng bất thường. Customizer giúp **nhìn thấy sự thay đổi theo kênh**. Để biết có bao nhiêu email thực sự gửi thành công, cần metric nghiệp vụ từ listener hoặc trạng thái xử lý event. Để biết vì sao listener chậm, dùng traces và logs; để biết tương tác có vi phạm ranh giới module, dùng graph và kiểm chứng tĩnh.

## 9. Những lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không import được `ModulithEventMetricsCustomizer` | Thiếu `spring-modulith-observability-api` ở compile scope hoặc dùng phiên bản quá cũ. | Kiểm tra artifact/API và BOM Spring Modulith tương thích. |
| Ứng dụng chạy nhưng không có event metric | Thiếu observability runtime, chưa phát domain event phù hợp hoặc module chưa được nhận diện đúng. | Kiểm tra Insight Starter/core, nguồn event, log và `/actuator/metrics`. |
| Có counter mặc định nhưng không thấy `channel` | Bean customizer không được scan/đăng ký, event type đăng ký khác type thực tế, hoặc chưa phát event mới. | Kiểm tra `@Configuration`, `@Bean`, `OrderPlaced.class` và lần phát thử. |
| Tag chỉ xuất hiện ở counter riêng, không có ở `module.events.published` | Customizer được thiết kế để làm giàu **individual event counter**. | Truy vấn đúng meter riêng; không nhầm counter tổng hợp. |
| Counter chỉ có một giá trị `channel` | Lưu lượng thử chỉ phát từ một kênh hoặc các giá trị đã bị chuẩn hóa về một nhóm. | Phát event của nhiều kênh và xem `availableTags`. |
| Số series tăng quá mạnh | Tag `orderId`, `customerId` hoặc payload tùy ý có cardinality cao. | Loại bỏ tag không giới hạn; dùng enum/nhóm cố định; kiểm tra metrics backend. |
| `/actuator/metrics` trả 404 | Endpoint chưa expose, bị hạn chế access hoặc sai URL/port. | Xem cấu hình management và Spring Security. |
| `/actuator/prometheus` không thấy counter | Thiếu registry, endpoint chưa expose hoặc chưa phát event. | Kiểm tra dependency, endpoint và tên meter sau chuyển đổi. |
| Counter tăng nhưng listener lỗi | Metric đếm lần **phát** event chứ không phải số lần listener thành công. | Xem logs/traces và trạng thái Event Publication Registry nếu được dùng. |
| Một deployment có tag khác deployment khác | Thay tên/giá trị tag hoặc config khác nhau giữa phiên bản. | Chuẩn hóa tag và kiểm tra quy ước trong CI/review. |

### Quy trình chẩn đoán ngắn

Khi không thấy custom tag, kiểm tra theo thứ tự:

1. Xác nhận domain event thực sự được phát từ module mà Spring Modulith nhận diện.
2. Xác nhận `spring-modulith-starter-insight` hoặc `spring-modulith-observability-core` đang ở runtime classpath.
3. Xác nhận `spring-modulith-observability-api` có ở compile classpath và bean `ModulithEventMetricsCustomizer` đã được scan.
4. Xác nhận class được dùng trong `metrics.customize(OrderPlaced.class, ...)` đúng kiểu sự kiện xuất hiện trong runtime.
5. Phát một event mới rồi truy vấn **counter riêng**, xem `availableTags` và lọc bằng `tag=channel:web`.
6. Nếu dữ liệu trong `/actuator/metrics` đúng nhưng dashboard vẫn thiếu, kiểm tra registry, exporter, scrape và cách hệ thống đổi tên metric/nhãn.

Không sửa đồng loạt tên metric, tracing configuration và sự kiện khi chưa xác định lỗi nằm ở bước nào.

## 10. Kiểm chứng bằng một trường hợp thực hành

Giả sử ứng dụng mẫu chạy tại `localhost:8080`, thêm cấu hình và class ở mục 4–5. Thực hiện các thao tác:

1. Khởi động ứng dụng và kiểm tra bean customizer đã được tạo (qua log cấu hình hoặc debugger trong môi trường phát triển).
2. Gọi `placeOrder(WEB)` hai lần và `placeOrder(MOBILE)` một lần; đảm bảo event được phát.
3. Truy vấn `/actuator/metrics/module.events.published.ordering.OrderPlaced` và xác nhận có tag `channel`.
4. Truy vấn với `tag=channel:web` và `tag=channel:mobile` để quan sát hai nhóm riêng.
5. Thử thay tag bằng `orderId` trong một nhánh thử nghiệm giới hạn, đánh giá vì sao số meter/series sẽ tăng theo số event; sau đó khôi phục tag `channel`.
6. Đối chiếu với counter tổng hợp `module.events.published`. Giải thích vì sao thông tin module/event type là mặc định, còn `channel` được bổ sung ở counter riêng.

### Bảng kết quả kỳ vọng

| Kiểm tra | Kỳ vọng trong ví dụ |
| --- | --- |
| Bean customizer có mặt | `ModulithEventMetricsCustomizer` được Spring nhận diện. |
| Event `OrderPlaced` được phát | Meter riêng của event xuất hiện sau khi ghi nhận. |
| `availableTags` có `channel` | Các giá trị `web`, `mobile` xuất hiện khi cả hai loại event đã phát. |
| Lọc `channel=web` | Counter của nhóm web phản ánh những lần phát web trong lần chạy đang xét. |
| Lọc `channel=mobile` | Counter của nhóm mobile được tách riêng. |
| Listener có lỗi | Counter phát event vẫn có thể tăng; cần kiểm tra listener bằng nguồn tín hiệu khác. |

Kết quả thực tế còn phụ thuộc những event khác đã phát, thời điểm ứng dụng khởi động, cách registry ghi nhận counter và cấu hình monitoring. Không nên yêu cầu tổng counter luôn bằng một giá trị tuyệt đối nếu môi trường thử nghiệm không được cách ly.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `ModulithEventMetricsCustomizer` là gì?

**Trả lời:** Interface để đăng ký cách tùy biến counter cho từng loại application/domain event được Spring Modulith ghi nhận, thường dùng bổ sung tag nghiệp vụ dựa trên nội dung event.

**Câu 2.** Vì sao ví dụ sử dụng `OrderPlaced.class` khi gọi `metrics.customize(...)`?

**Trả lời:** API ánh xạ quy tắc tùy biến theo **kiểu event cụ thể**. Dữ liệu của event cùng kiểu sẽ được đưa vào callback để điều chỉnh `Counter.Builder`.

**Câu 3.** Tại sao `channel` phù hợp làm tag, còn `orderId` không phù hợp?

**Trả lời:** `channel` có tập giá trị hữu hạn và hữu ích cho dashboard; `orderId` gần như duy nhất ở từng event, gây high cardinality và chi phí lưu trữ cao.

**Câu 4.** Customizer có làm `/actuator/modulith` hiển thị một module mới không?

**Trả lời:** Không. Endpoint `modulith` phản ánh cấu trúc module; customizer chỉ điều chỉnh counter event.

**Câu 5.** Counter `OrderPlaced` tăng có chứng minh listener đã gửi email thành công?

**Trả lời:** Không. Counter đo lần phát event được ghi nhận. Cần metric/log/trace kết quả xử lý hoặc Event Publication Registry để đánh giá listener.

**Câu 6.** Muốn điều chỉnh convention của module-entry spans thay vì counter sự kiện nên tìm API nào?

**Trả lời:** `ModulithObservationConvention` và hạ tầng observation/tracing tương ứng, không phải `ModulithEventMetricsCustomizer`.

## 12. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): mô tả hai nhóm event metrics, tag mặc định và bean `ModulithEventMetricsCustomizer`.
- [Spring Modulith — `ModulithEventMetricsCustomizer` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html): interface và phương thức `customize(ModulithEventMetrics)`.
- [Spring Modulith — `ModulithEventMetrics` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html): hai overload của `customize(Class<T>, ...)`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): application events và cách xử lý event trong kiến trúc module.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `MeterRegistry`, Actuator metrics và cách đọc các meter.
- [Micrometer — Concepts: Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): ý nghĩa counter, rate và cách dùng tags.

**Ghi nhớ:** `ModulithEventMetricsCustomizer` là điểm mở rộng để **làm giàu counter của từng kiểu domain event** bằng các thuộc tính nghiệp vụ có số giá trị nhỏ và ổn định. Hãy dùng nó để biết event nào được phát từ đâu và theo nhóm nào, sau đó kết hợp module graph, logs, traces và trạng thái xử lý event để đánh giá kiến trúc cùng hành vi ứng dụng khi chạy.
