# Đăng ký customizer bằng Spring bean

> **Chương:** Event customizer  
> **Phạm vi:** Đăng ký `ModulithEventMetricsCustomizer` trong Spring Boot để bổ sung metadata có kiểm soát vào metrics công bố domain event của Spring Modulith.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `ModulithEventMetricsCustomizer` dùng để làm gì và tại sao nên đăng ký bằng `@Bean` trong Spring ApplicationContext.
2. Phân biệt bộ đếm tổng hợp `module.events.published` với bộ đếm riêng `module.events.published.$moduleIdentifier.$simpleEventTypeName`.
3. Tạo một Spring `@Configuration` đăng ký customizer cho event type cụ thể, sử dụng `metrics.customize(EventType.class, (event, builder) -> ...)`.
4. Chọn giá trị tag có **cardinality thấp**, tránh đưa ID đơn hàng, thông tin khách hàng hoặc dữ liệu nhạy cảm vào metrics.
5. Kiểm tra bean đã được Spring quản lý, kiểm tra meter và tag qua Actuator, nhận diện tên metric thực tế khi xuất Prometheus.
6. Phân biệt tùy biến event metrics với tùy biến module spans, module graph và cơ chế xử lý hoặc phát lại event.

## 2. Vấn đề thực tế: cần thêm chiều phân tích cho một loại event

Giả sử ứng dụng Spring Boot được chia thành các application module `orders`, `payments` và `notifications`. Module `orders` công bố hai sự kiện nghiệp vụ:

- `OrderPlaced`: khách hàng tạo đơn hàng.
- `OrderCancelled`: đơn hàng bị hủy.

Spring Modulith observability có thể ghi nhận số lượng event publications theo module và event type. Tuy nhiên, đội vận hành còn muốn trả lời:

> Trong những sự kiện `OrderPlaced` do module `orders` công bố, bao nhiêu sự kiện thuộc mức giao hàng `STANDARD` và bao nhiêu thuộc `EXPRESS`?

Thông tin `STANDARD/EXPRESS` không nằm trong bộ tag module mặc định. Đây là trường hợp phù hợp để tạo **event metrics customizer**, bổ sung một tag `delivery.priority` với tập giá trị hữu hạn.

~~~mermaid
flowchart LR
    Order["orders module"] -->|"publish OrderPlaced"| Spring["Spring event infrastructure"]
    Spring --> Modulith["Spring Modulith event metrics"]
    Bean["@Bean ModulithEventMetricsCustomizer"] -.->|"cấu hình Counter.Builder"| Modulith
    Modulith --> Summary["module.events.published"]
    Modulith --> Specific["module.events.published.orders.OrderPlaced<br/>delivery.priority=STANDARD/EXPRESS"]
    Summary --> Registry["Micrometer MeterRegistry"]
    Specific --> Registry
    Registry --> Actuator["Actuator /metrics"]
    Registry --> Prom["Prometheus nếu có registry"]
~~~

Sơ đồ mô tả quan hệ **khái niệm**: customizer khai báo cách làm giàu counter riêng cho event type đã chọn; Micrometer quản lý meter và Actuator/Prometheus cho phép kiểm tra chúng. Nó không quyết định listener nào được chạy hoặc transaction nào được commit.

## 3. Phân biệt hai nhóm event metric trước khi tùy biến

Theo phần observability metrics của Spring Modulith, có hai loại counter:

| Nhóm | Tên Micrometer | Metadata mặc định |
| --- | --- | --- |
| Tổng hợp các event | `module.events.published` | `module.identifier`, `module.name`, `module.event.type` |
| Riêng một event type | `module.events.published.$moduleIdentifier.$simpleEventTypeName` | `module.identifier`, `module.name`; cho phép thêm tag của domain event |

Ví dụ một lần công bố `OrderPlaced` từ module `orders` có thể làm cả hai góc nhìn thống kê tăng. **Không cộng chúng lại** để tính tổng event, vì đó có thể là hai meter quan sát cùng một lần publish.

Khi customizer làm giàu counter của `OrderPlaced`, cần đọc kết quả từ counter riêng, chẳng hạn:

~~~text
module.events.published.orders.OrderPlaced
  module.identifier = orders
  module.name       = Orders
  delivery.priority = EXPRESS
~~~

Đây là ví dụ giá trị tag để học cách đọc, **không phải output cố định**. Tên module và tên hiển thị phụ thuộc cấu hình module detection; tên metric ở Prometheus sẽ chịu naming convention của registry. Counter tổng hợp không mặc nhiên nhận tag mới của customizer dành cho counter riêng.

**Ý nghĩa số đếm:** event publication counter theo dõi thao tác **publish event** mà Spring Modulith nhận diện; không tương đương số listener xử lý thành công, số notification đã gửi hay số publication records trong Event Publication Registry.

## 4. Hợp đồng API của `ModulithEventMetricsCustomizer`

Trong Spring Modulith hiện hành, interface cần dùng nằm tại:

~~~java
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;
~~~

Nó là functional interface có một phương thức khái niệm:

~~~java
void customize(ModulithEventMetrics metrics);
~~~

Đối tượng `ModulithEventMetrics` cho phép đăng ký cách tùy biến theo **Java event class**:

~~~java
// Định dạng chữ ký API, không phải class cần tự viết lại.
<T> ModulithEventMetrics customize(
    Class<T> type,
    BiConsumer<T, Counter.Builder> consumer
);
~~~

Diễn giải lần lượt:

1. `Class<T> type` là loại event bạn muốn tùy biến, ví dụ `OrderPlaced.class`.
2. `T event` là instance thực tế của sự kiện khi tạo meter tương ứng; bạn có thể đọc thuộc tính có tập giá trị nhỏ từ instance.
3. `Counter.Builder builder` là builder do Spring Modulith cấp để cấu hình counter; thêm tag bằng `builder.tags(key, value)`.
4. Phương thức customizer **đăng ký quy tắc**, còn framework chịu trách nhiệm áp dụng quy tắc khi tạo counter tương ứng.

Không tự tạo một `Counter` mới bằng `Counter.builder(...).register(registry)` chỉ để làm cùng công việc: làm vậy có thể dẫn tới meter khác với meter do Spring Modulith quản lý, gây trùng số đếm hoặc dữ liệu khó đối chiếu.

API còn cung cấp overload:

~~~java
<T> ModulithEventMetrics customize(
    Class<T> type,
    Function<T, Counter.Builder> factory
);
~~~

Overload dùng `Function` cho phép tùy chỉnh cách **khởi tạo builder** ở mức sâu hơn. Với nhu cầu chỉ **thêm tag**, ưu tiên overload `BiConsumer<T, Counter.Builder>` vì nó giữ các thiết lập mặc định của counter. Hai overload có thể kết hợp theo API; hãy kiểm tra hành vi và tên metric thực tế nếu dùng factory thay thế.

## 5. Ví dụ event có thuộc tính phù hợp làm tag

Ta định nghĩa mức ưu tiên giao hàng bằng enum thay vì chuỗi tự do:

~~~java
// src/main/java/com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId, DeliveryPriority priority) {

    public enum DeliveryPriority {
        STANDARD,
        EXPRESS
    }
}
~~~

Một event khác của cùng module:

~~~java
// src/main/java/com/example/shop/orders/OrderCancelled.java
package com.example.shop.orders;

public record OrderCancelled(String orderId, CancelReason reason) {

    public enum CancelReason {
        CUSTOMER_REQUEST,
        OUT_OF_STOCK,
        PAYMENT_FAILED
    }
}
~~~

`orderId` có thể khác nhau theo từng đơn; không dùng nó làm tag. Ngược lại, `priority` chỉ có **hai** giá trị và `reason` có **ba** giá trị, phù hợp cho việc tổng hợp metrics theo các nhóm đã định nghĩa.

Với mã nghiệp vụ minh họa, module `orders` có thể publish event như sau:

~~~java
package com.example.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final ApplicationEventPublisher events;

    public OrderApplicationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(String orderId, OrderPlaced.DeliveryPriority priority) {
        // Trong ứng dụng thật: validate và lưu trạng thái theo giao dịch phù hợp.
        events.publishEvent(new OrderPlaced(orderId, priority));
    }

    public void cancelOrder(String orderId, OrderCancelled.CancelReason reason) {
        // Trong ứng dụng thật: xác thực quyền hủy và cập nhật đơn hàng.
        events.publishEvent(new OrderCancelled(orderId, reason));
    }
}
~~~

Ví dụ tập trung vào việc publish và đo event; không minh họa đầy đủ persistence, transaction, xác nhận thanh toán hay external message broker. Một event được publish từ ứng dụng **chưa chắc** đồng nghĩa business transaction đã commit.

## 6. Đăng ký customizer bằng Spring `@Bean`

Đây là trọng tâm bài học. Tạo class cấu hình trong **package được component scan của Spring Boot quét**, ví dụ `com.example.shop.observability` dưới root package `com.example.shop`.

~~~java
// src/main/java/com/example/shop/observability/EventMetricsConfiguration.java
package com.example.shop.observability;

import com.example.shop.orders.OrderCancelled;
import com.example.shop.orders.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer modulithEventMetricsCustomizer() {
        return metrics -> {
            metrics.customize(OrderPlaced.class, (event, builder) -> {
                builder.tags("delivery.priority", event.priority().name());
            });

            metrics.customize(OrderCancelled.class, (event, builder) -> {
                builder.tags("cancel.reason", event.reason().name());
            });
        };
    }
}
~~~

Ở đây:

- `@Configuration` giúp Spring phát hiện cấu hình khi class thuộc phạm vi component scan.
- `@Bean` đưa một object có type `ModulithEventMetricsCustomizer` vào ApplicationContext.
- `metrics.customize(OrderPlaced.class, ...)` áp dụng rule cho loại `OrderPlaced`, sử dụng giá trị của chính event instance để thêm tag.
- `metrics.customize(OrderCancelled.class, ...)` là rule thứ hai của **cùng một bean**; không bắt buộc tạo một bean cho mỗi event type.
- `builder.tags(...)` thay đổi cấu hình counter trước khi meter được đăng ký; **không gọi** `increment()` hay tự ghi số đếm ở callback.
- `proxyBeanMethods = false` phù hợp với class cấu hình chứa factory methods không gọi chéo nhau; không phải điều kiện đặc biệt của Spring Modulith.

### 6.1. Vì sao chỉ khai báo interface, không tự gọi `customize(...)`?

Spring Boot tạo ApplicationContext và phát hiện bean. Tích hợp observability của Spring Modulith lấy các bean kiểu `ModulithEventMetricsCustomizer` rồi áp dụng vào factory tạo event metric. Vì vậy bạn đăng ký **quy tắc** ở giai đoạn cấu hình; việc publish event về sau là thứ kích hoạt metric được ghi nhận.

~~~mermaid
sequenceDiagram
    participant Boot as Spring Boot context
    participant Config as EventMetricsConfiguration
    participant Mod as Spring Modulith observability
    participant Publisher as ApplicationEventPublisher
    participant Registry as MeterRegistry
    Boot->>Config: Khởi tạo bean @Configuration
    Config-->>Boot: @Bean ModulithEventMetricsCustomizer
    Boot->>Mod: Cung cấp customizer bean
    Mod->>Mod: Đăng ký customize(OrderPlaced.class, ...)
    Publisher->>Mod: Publish OrderPlaced
    Mod->>Mod: Áp dụng tag của event vào Counter.Builder
    Mod->>Registry: Tạo/lấy Counter và ghi nhận publication
~~~

Thứ tự nội bộ được mô tả **ở mức khái niệm**; chi tiết các bean post-processors và thời điểm tạo meter có thể khác theo phiên bản.

### 6.2. Đảm bảo bean nằm trong ApplicationContext thật

Một số nguyên nhân làm code hợp lệ nhưng customizer không được sử dụng:

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Class `EventMetricsConfiguration` nằm ngoài vùng component scan | Spring không đăng ký bean | Đặt trong package con của root `@SpringBootApplication` hoặc import cấu hình tường minh |
| Method thiếu `@Bean` | Chỉ còn một method Java bình thường | Khai báo `@Bean` hoặc dùng cách đăng ký bean phù hợp |
| Code cấu hình chỉ nằm trong `src/test/java` | Bản deploy production không có bean | Đặt cấu hình cần thiết trong `src/main/java` |
| Thiếu dependency `observability-api` lúc compile | Compiler không tìm thấy interface | Khai báo API đúng scope và BOM |
| Chưa có runtime observability của Spring Modulith | Bean có thể tồn tại nhưng không được tích hợp event metrics tiêu thụ | Thêm core observability hoặc Insight starter tương thích |
| Bean chỉ được tạo dưới profile không kích hoạt | Không có rule tại runtime | Kiểm tra `@Profile`, `@Conditional...` và profile đang chạy |

Không nên khắc phục bằng cách gọi thủ công `new EventMetricsConfiguration().modulithEventMetricsCustomizer()`: object đó không tự trở thành bean được Spring quản lý.

## 7. Khai báo dependency ở đúng scope

Với **Spring Modulith 2.x** và Spring Boot tương thích, bạn có thể chọn Insight starter để bật observability và Actuator:

~~~xml
<!-- pom.xml, version do BOM Spring Modulith và Spring Boot quản lý -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Để **biên dịch code Java** có import `ModulithEventMetricsCustomizer`, thêm observability API vào compile scope:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-api</artifactId>
</dependency>
~~~

Nếu chỉ cần phần observability thay vì cả Insight starter, có thể sử dụng `spring-modulith-observability-core` ở runtime cùng Spring Boot Actuator/metrics phù hợp:

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

Tương đương ví dụ Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.modulith:spring-modulith-observability-api"
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

**Chọn một đường runtime observability**, tránh khai báo core thêm vào khi Insight starter đã cung cấp. Không tự lấy version ngẫu nhiên cho từng artifact. Dùng BOM phù hợp với Spring Boot và dòng Spring Modulith của dự án.

Ở **Spring Modulith 1.x**, cách tách artifact có thể khác; trước khi copy cấu hình dependency, đối chiếu tài liệu/Java API theo version đang dùng. `ModulithEventMetricsCustomizer` được tài liệu ghi nhận từ dòng **1.4**.

## 8. Đặt tag sao cho metrics có ích và vận hành được

Trong Micrometer, **tag** là chiều phân loại của một time series. Một meter được phân biệt qua tên và tập tag; mỗi tổ hợp giá trị mới có thể tạo thêm time series.

| Tag đề xuất | Giá trị mẫu | Đánh giá |
| --- | --- | --- |
| `delivery.priority` | `STANDARD`, `EXPRESS` | Tốt: enum có hai giá trị |
| `cancel.reason` | Ba loại lý do hủy cố định | Tốt: nhóm có số lượng nhỏ |
| `channel` | `WEB`, `MOBILE`, `API` | Có thể dùng khi danh sách được quản lý |
| `order.id` | `ORD-001`, `ORD-002`, ... | Tránh: cardinality tăng theo từng order |
| `customer.email` | Địa chỉ email khách hàng | Không dùng: nhạy cảm, cardinality cao |
| `timestamp` | Mỗi lần publish một thời điểm khác | Tránh: gần như mỗi event tạo một series |
| `error.message` | Thông báo lỗi tự do | Tránh: số biến thể không kiểm soát |

Giả sử có 4 module × 8 loại event × 3 kênh × 3 mức priority × 6 instances. Chỉ riêng những chiều đó đã có tối đa **1.728 tổ hợp** trước khi xét thêm tag hoặc environment. Trong hệ thống lớn, số series có thể tăng nhanh hơn tưởng tượng.

**Quy tắc:** thêm tag khi có câu hỏi vận hành cụ thể, có tập giá trị hữu hạn, và có cách kiểm soát thay đổi tập giá trị. Dữ liệu dùng để truy lại một event cụ thể nên thuộc log có correlation ID, trace hoặc event publication record với quyền truy cập phù hợp.

### 8.1. Tránh null trong giá trị tag

Giả sử một số event cũ không có `priority`. Đừng gọi `event.priority().name()` khi giá trị có thể null. Trong code production, có thể chuẩn hóa về enum `UNKNOWN`:

~~~java
metrics.customize(OrderPlaced.class, (event, builder) -> {
    String priority = event.priority() == null
        ? "UNKNOWN"
        : event.priority().name();

    builder.tags("delivery.priority", priority);
});
~~~

Không sử dụng ngoại lệ từ callback để báo lỗi nghiệp vụ: quy tắc tạo metrics không nên khiến việc publish event thất bại do thiếu metadata quan sát. Nếu field event cần bắt buộc không null, kiểm tra ở biên nghiệp vụ và trong constructor/event contract.

### 8.2. Hạn chế ghi nhầm tags sang nhóm metric khác

Customizer này **chỉ nhắm tới counter event type được chọn**. Nếu cần thêm metadata môi trường như `environment=staging` cho tất cả meters, Spring Boot có cơ chế **common tags**:

~~~yaml
management:
  metrics:
    tags:
      environment: staging
      service: shop-modulith
~~~

Common tags áp dụng rộng hơn cho các meter được quản lý. Không nên dùng event customizer để sao chép tag môi trường giống nhau cho mọi event type nếu có thể cấu hình chung một lần.

## 9. Kiểm tra customizer bằng Actuator

Trong môi trường học tập, expose `metrics` (và `health`) qua Actuator:

~~~yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

Management endpoint có thể được bảo vệ bằng Spring Security hoặc network policy; dùng đúng cổng/base path thực tế. Trên môi trường production, chỉ expose cho người/công cụ có quyền.

Khởi động ứng dụng, gọi code thực sự publish `OrderPlaced` và `OrderCancelled`, sau đó truy vấn:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/module.events.published
curl -i http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced
~~~

Các meter có thể được đăng ký **sau khi event lần đầu xuất hiện**, vì thế đừng kết luận thiếu customizer chỉ dựa vào danh sách metrics ngay sau startup.

### 9.1. Đọc thông tin từ meter riêng

Ví dụ response **minh họa** cho counter `module.events.published.orders.OrderPlaced` sau khi publish 6 event:

~~~json
{
  "name": "module.events.published.orders.OrderPlaced",
  "measurements": [
    { "statistic": "COUNT", "value": 6.0 }
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
      "tag": "delivery.priority",
      "values": ["STANDARD", "EXPRESS"]
    }
  ]
}
~~~

Đây **không phải response lấy từ một ứng dụng thật**. Nội dung `availableTags` và giá trị COUNT tùy code đã chạy; kiểm tra dữ liệu thực tế để xác nhận version và customizer đang được áp dụng.

Lọc số lượt publish riêng loại `EXPRESS`:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced?tag=delivery.priority:EXPRESS"
~~~

Lọc đồng thời theo module và priority:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderPlaced?tag=module.identifier:orders&tag=delivery.priority:STANDARD"
~~~

Spring Boot Actuator cho phép lặp nhiều tham số `tag=KEY:VALUE` để lọc; response sẽ tổng hợp các meter cùng tên thỏa các điều kiện đó. Nếu môi trường chạy nhiều instances, request HTTP tới một instance phản ánh meter của **instance ấy**.

### 9.2. So sánh với counter tổng hợp

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:orders"
~~~

Counter tổng hợp thường cho phép chọn `module.event.type` nhưng **không bắt buộc** chứa `delivery.priority`. Kiểm tra `availableTags` ở từng meter trước khi lọc. Nếu lọc `delivery.priority` trên meter tổng hợp và nhận lỗi/không thấy dữ liệu, đó có thể là **đúng thiết kế**: tag này chỉ được thêm cho counter riêng.

## 10. Khi dùng Prometheus hoặc Grafana

Muốn dùng Prometheus, thêm `micrometer-registry-prometheus` và expose `/actuator/prometheus` ở management server:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Kiểm tra dữ liệu scrape:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Tên Micrometer như `module.events.published.orders.OrderPlaced` có thể được Prometheus registry **đổi tên và gắn hậu tố counter**, đồng thời các dấu chấm trong tag được chuẩn hóa. Hãy lấy tên series và label thật từ scrape output hoặc Prometheus UI rồi mới viết PromQL; tránh dựa vào tên tự đoán.

Ví dụ **giả sử** scrape output chứa series đã chuẩn hóa dạng:

~~~text
module_events_published_orders_OrderPlaced_total{
  module_identifier="orders",
  delivery_priority="EXPRESS"
} 4
~~~

thì truy vấn tốc độ publish `EXPRESS` trong năm phút có thể viết theo tên **đã kiểm tra**:

~~~promql
sum(
  rate(module_events_published_orders_OrderPlaced_total{
    module_identifier="orders",
    delivery_priority="EXPRESS"
  }[5m])
)
~~~

Đừng dùng chuỗi ví dụ này như bảo đảm về cách Prometheus exporter đổi tên. Với một số naming convention, chữ hoa có thể được chuẩn hóa khác. Hãy nhìn đúng output thực tế.

**Vì sao `rate()`?** Counter được tích lũy trong vòng đời instance và có thể reset khi khởi động lại; `rate()`/`increase()` trên từng time series giúp đọc tốc độ hoặc số tăng theo cửa sổ, sau đó mới `sum` nếu có nhiều instances.

## 11. Phân biệt event metrics customizer với các extension point khác

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `ModulithEventMetricsCustomizer` | Tùy biến counter riêng cho một event type | Thêm `delivery.priority=EXPRESS` khi publish `OrderPlaced` |
| `ModulithObservationConvention` | Tùy biến convention của module observations/spans | Đổi tên observation hoặc bổ sung metadata cho module entry |
| Spring Boot common tags / `MeterFilter` | Tùy biến metadata/đặc tính meter trong phạm vi registry | Thêm `environment` cho mọi metrics, đổi tên tag |
| Event Publication Registry | Theo dõi trạng thái publication hướng tới transactional listeners, hỗ trợ quản lý publication | Phát hiện publication chưa hoàn tất |
| Module graph / `/actuator/modulith` | Biểu diễn module và dependency tĩnh trong ứng dụng | `notifications → orders` do listener phụ thuộc event type |
| Distributed tracing | Quan sát operation được instrument và mối liên hệ giữa các spans | Lần theo HTTP request, module entry span, listener |

Không dùng `ModulithEventMetricsCustomizer` để tự thêm span, điều khiển retry, sửa transaction, thay đổi listener order hoặc chặn event publish. Đây là **extension point của metric**, không phải event interceptor nghiệp vụ.

## 12. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| IDE báo không tìm thấy `ModulithEventMetricsCustomizer` | Thiếu `spring-modulith-observability-api` ở compile scope hoặc version không phù hợp | Kiểm tra BOM, dependency tree, import đúng package |
| Có bean nhưng counter không có tag mới | Bean không được runtime observability tích hợp; event type không khớp; rule không được chạy | Kiểm tra runtime artifact, ApplicationContext, loại event thực tế |
| Metric tổng hợp không có `delivery.priority` | Customizer chỉ làm giàu counter riêng | Query đúng meter riêng theo module và event |
| `/actuator/metrics` 404 | Chưa expose endpoint, thiếu Actuator, sai management port/base path | Kiểm tra Actuator config và địa chỉ |
| `/actuator/metrics` 401/403 | Security chặn management endpoint | Dùng danh tính được cấp quyền, không tắt bảo mật trên production |
| Meter riêng chưa xuất hiện sau startup | Chưa có publish được instrumentation ghi nhận | Chạy use case tạo event rồi truy vấn lại |
| Tạo rất nhiều time series | Tag dùng order ID, text tự do, timestamp hoặc quá nhiều chiều | Đổi sang enum/nhóm giá trị hữu hạn; bỏ tag có cardinality cao |
| Tag value gây exception | Field event null hoặc mapping không bao phủ tất cả trường hợp | Chuẩn hóa sang giá trị ổn định như `UNKNOWN` |
| Đổi sang `Function<T, Counter.Builder>` làm metric name lạ | Factory tùy chỉnh thay cấu hình builder gốc | Ưu tiên overload `BiConsumer` khi chỉ thêm tag |
| Số lần publish khác số listener hoàn tất | Một event có nhiều listeners, listener async/after-commit/retry | Đối chiếu Event Publication Registry, logs, traces |
| Không thấy Prometheus series | Chưa có registry, scrape không truy cập được, sai tên series | Kiểm tra `/actuator/prometheus` và target trong Prometheus |
| Sau deploy tổng COUNT giảm | Counter reset do restart | Dùng `rate()`/`increase()` theo cửa sổ thay vì so giá trị tuyệt đối |

Khi điều tra, đi lần lượt từ **bean registration → observability runtime → event thực sự được publish → meter trong Actuator → exporter → dashboard**. Cách này giúp xác định lỗi nằm ở khâu tích hợp hay khâu trình bày dữ liệu.

## 13. Bài thực hành: từ Spring bean đến dashboard

**Bối cảnh:** module `orders` phát `OrderPlaced` có `DeliveryPriority.STANDARD/EXPRESS` và `OrderCancelled` có `CancelReason`. Muốn tạo báo cáo phân bố mức ưu tiên khi đặt hàng và lý do hủy.

Thực hiện:

1. Tạo hai record event như phần 5 trong module `orders`, viết một Spring service publish chúng thông qua `ApplicationEventPublisher`.
2. Cấu hình dependency observability runtime và observability API compile theo version dự án.
3. Tạo `EventMetricsConfiguration` trong vùng component scan, đăng ký **một bean** `ModulithEventMetricsCustomizer` với hai quy tắc theo class event.
4. Trong môi trường dev, expose endpoint `/actuator/metrics` và giữ quyền truy cập phù hợp.
5. Publish tổng cộng **8 `OrderPlaced`** (5 STANDARD, 3 EXPRESS) và **4 `OrderCancelled`** (ví dụ 2 CUSTOMER_REQUEST, 1 OUT_OF_STOCK, 1 PAYMENT_FAILED). Đảm bảo không có lần publish phát sinh ngoài kịch bản.
6. Truy vấn counter riêng của `OrderPlaced`, dùng `availableTags` để xác nhận `delivery.priority` rồi lọc hai giá trị.
7. Truy vấn counter riêng của `OrderCancelled`, dùng `cancel.reason` để thấy ba nhóm nguyên nhân hủy.
8. So sánh với `module.events.published` theo `module.identifier` và `module.event.type`, giải thích vì sao không cộng counter riêng vào counter tổng hợp.
9. Nếu có Prometheus, kiểm tra output scrape và tạo truy vấn tốc độ publish của `EXPRESS` theo cửa sổ năm phút.
10. Thử thêm tag `order.id` trong một nhánh thử nghiệm, kiểm tra vì sao số series tăng mạnh, rồi khôi phục cấu hình an toàn trước khi dùng ở môi trường thật.

Mẫu **kết quả dự kiến trong một instance mới, không có publish khác**:

| Meter | Điều kiện lọc | Số lượt kỳ vọng |
| --- | --- | ---: |
| Counter riêng của `OrderPlaced` | `delivery.priority=STANDARD` | 5 |
| Counter riêng của `OrderPlaced` | `delivery.priority=EXPRESS` | 3 |
| Counter riêng của `OrderCancelled` | `cancel.reason=CUSTOMER_REQUEST` | 2 |
| Counter riêng của `OrderCancelled` | `cancel.reason=OUT_OF_STOCK` | 1 |
| Counter riêng của `OrderCancelled` | `cancel.reason=PAYMENT_FAILED` | 1 |
| `module.events.published` | Module `orders`, nếu mọi event được nhận diện | 12 |

Trong bảng này, các counter riêng cho `OrderPlaced` có tổng 8 và cho `OrderCancelled` có tổng 4. Counter tổng hợp 12 là **góc nhìn khác** của cùng 12 lượt publish, không cộng thêm thành 24.

**Tiêu chí đạt:** bạn giải thích được cách Spring tìm bean customizer; viết được lambda có event type và `Counter.Builder`; chỉ ra meter nào nhận tag; đọc kết quả qua Actuator; giải thích được nguy cơ cardinality và giới hạn “publish ≠ listener success”.

## 14. Câu hỏi tự kiểm tra

1. Vì sao method trả về `ModulithEventMetricsCustomizer` cần được đăng ký bằng `@Bean`?
2. Với `metrics.customize(OrderPlaced.class, (event, builder) -> ...)`, hai tham số `event` và `builder` đại diện cho những gì?
3. Đưa `orderId` vào tag có tốt hơn đưa `DeliveryPriority` vào tag không? Vì sao?
4. Customizer của counter riêng có bắt buộc bổ sung tag vào `module.events.published` tổng hợp không?
5. Vì sao cần `spring-modulith-observability-api` ở compile scope khi source code import customizer?
6. Một event có hai listener, trong đó một listener thất bại: counter publish có trả lời được số listener thành công không?
7. Bạn kiểm tra điều gì trước khi viết PromQL dựa vào tên meter dotted trong Micrometer?
8. Khi event type mới được tạo nhưng chưa publish lần nào, vì sao không thấy metric trong Actuator chưa đủ kết luận bean lỗi?

**Gợi ý trả lời:** (1) để Spring đưa customizer vào ApplicationContext và tích hợp framework tìm thấy; (2) instance domain event và Micrometer Counter.Builder của meter đang được cấu hình; (3) `DeliveryPriority` có số giá trị hữu hạn, `orderId` có cardinality cao; (4) không, phần tùy biến theo event type hướng tới counter riêng; (5) import type cần có trong compile classpath; (6) không, cần trạng thái listener/event publication; (7) kiểm tra scrape output, naming convention và label được exporter chuẩn hóa; (8) nhiều meter được tạo khi sự kiện thực sự được ghi nhận.

## 15. Tổng kết và liên hệ kiến trúc module

Đăng ký `ModulithEventMetricsCustomizer` dưới dạng **Spring bean** là cách Spring Modulith cung cấp để làm giàu event publication metrics bằng thông tin nghiệp vụ được giới hạn chặt chẽ. Pattern chính:

~~~java
@Bean
ModulithEventMetricsCustomizer customizer() {
    return metrics -> metrics.customize(
        OrderPlaced.class,
        (event, builder) ->
            builder.tags("delivery.priority", event.priority().name())
    );
}
~~~

Luôn đối chiếu kết quả ở counter riêng theo event type, chọn tags có **cardinality thấp** và không đưa dữ liệu nhạy cảm vào metric labels. Để kiểm chứng kiến trúc trong Spring Boot, kết hợp **module graph** và Actuator module metadata (quan hệ tĩnh), **event metrics** (tần suất publish), **tracing/module entry spans** (hành vi được instrument), **context propagation** (giữ tương quan khi đổi thread) và **Event Publication Registry** (trạng thái publication/listener).

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html) — tên counter, tag và cách đăng ký `@Bean`.
- [Spring Modulith — ModulithEventMetricsCustomizer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html) — method `customize(ModulithEventMetrics)`.
- [Spring Modulith — ModulithEventMetrics API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html) — hai overload `customize(...)` cho một event class.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — event publication, listener và publication registry.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — cách truy vấn metrics và lọc tag.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure, access và bảo mật management endpoints.

> **Ghi chú về phiên bản:** ví dụ dựa trên API Spring Modulith hiện hành (2.x); các artifact và cấu hình tích hợp có thể khác ở những dòng Spring Modulith/Spring Boot cũ. Dùng BOM tương thích và đối chiếu API theo phiên bản thực tế. Bài được soạn trong STEP 4; vòng QA chuyên môn dành cho bước riêng.
