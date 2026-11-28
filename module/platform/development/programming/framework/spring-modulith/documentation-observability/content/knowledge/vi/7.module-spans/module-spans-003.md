# Span được tạo cho event listener

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot tổ chức bằng **Spring Modulith**, một module có thể phát sự kiện miền (domain event) để module khác phản ứng mà không gọi trực tiếp vào phần triển khai của nó. Ví dụ, module **order** phát **OrderPlaced**, module **notification** tiếp nhận rồi gửi thông báo. Khi hệ thống chạy thật, câu hỏi quan trọng không chỉ là **“sự kiện đã được phát chưa?”**, mà còn là **“listener nào đã chạy, mất bao lâu, có lỗi không, và xử lý đó liên hệ thế nào với yêu cầu ban đầu?”**

Bài thuộc chương **Module spans** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Phạm vi chung của module học là dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác trong Spring Boot, bao gồm module graph, Actuator, event metrics, tracing và context propagation. Riêng bài này đi sâu vào **span được tạo khi event listener xử lý sự kiện**: cơ chế phát sinh, các thuộc tính module, ranh giới transaction/async, đọc trace, xử lý mất context và kiểm chứng với metrics/logs.

Sau bài học, bạn có thể:

1. Phân biệt **event publication**, **listener invocation**, **Observation**, **span** và **trace**.
2. Nhận diện **module entry span** có loại invocation là **event listener** cùng các thuộc tính do Spring Modulith công bố.
3. Giải thích vì sao listener sau commit hoặc bất đồng bộ có thể không nằm trong cùng trace với yêu cầu HTTP.
4. Cấu hình tối thiểu instrumentation và trace exporter, rồi tìm span của listener trong backend quan sát.
5. Phân biệt **listener span không xuất hiện** với **listener không chạy**, cũng như **listener span thành công** với **tác vụ ngoài hệ thống đã thành công**.

## 2. Event listener span thực sự biểu diễn điều gì?

Một **span** mô tả khoảng thời gian thực hiện một thao tác đã được instrument; nó có các thông tin như **traceId**, **spanId**, tên, thời gian bắt đầu/kết thúc, thuộc tính (attributes) và thông tin lỗi nếu có. Nhiều spans liên hệ nhau tạo thành một **trace**.

Trong Spring Modulith, hỗ trợ observability có thể chặn lời gọi đi qua các thành phần Spring thuộc API application module và tạo **module entry observation/span**. Tài liệu Spring Modulith còn mô tả một loại **module invocation** là **event listener**. Do đó, khi listener được nhận diện và đi qua điểm instrumentation, trace có thể xuất hiện span cho việc **module nhận bắt đầu xử lý một sự kiện**.

Điểm cần phân biệt: Spring Framework **không tự tạo Observation cho mọi phương thức gắn @EventListener**. Span mang thông tin module xuất hiện nhờ **Spring Modulith observability và cấu hình Micrometer Tracing**, không phải cứ thêm annotation xử lý sự kiện là bảo đảm có span. Phạm vi cụ thể còn phụ thuộc module detection, cấu trúc Spring bean, phiên bản và điểm gọi được instrument.

| Khái niệm | Điều ghi nhận | Không thể suy ra |
| --- | --- | --- |
| **ApplicationEventPublisher.publishEvent(...)** | Publisher phát một application event trong tiến trình Spring. | Listener đã chạy xong, có trace được export, hay event đã tới message broker. |
| **Metric module.events.published** | Số event được công bố theo instrumentation Spring Modulith. | Từng listener đã thành công. |
| **Module entry span loại event listener** | Một lần lời gọi listener được observability bắt và ghi nhận. | Event chỉ được xử lý đúng một lần, mọi side effect bên ngoài đều thành công. |
| **Trace** | Tập spans có quan hệ và được lấy mẫu/xuất thành công. | Toàn bộ event phát sinh đều được lưu giữ; các span async luôn chung trace. |
| **Event Publication Registry** | Theo dõi trạng thái xử lý publication tới các transactional listeners khi được cấu hình. | Tự thay thế tracing hoặc bảo đảm exactly-once cho API bên ngoài. |

Một event có thể được nhiều listener tiếp nhận. **Không có quy tắc “một sự kiện bằng một listener span”**: nếu hai listener được instrument và cùng xử lý event, có thể có các spans khác nhau; nếu sampling tắt hoặc một listener không qua điểm instrumentation, backend có thể không nhận span tương ứng.

## 3. Các thuộc tính nhận diện module listener span

Tài liệu Spring Modulith liệt kê bốn khóa quan trọng của **Module Entry Span**:

| Attribute | Giá trị/ý nghĩa |
| --- | --- |
| **module.identifier** | Định danh kỹ thuật của application module. |
| **module.name** | Tên module. |
| **module.method** | Phương thức được thực thi tại điểm vào module. |
| **module.invocation-type** | Kiểu lời gọi: **event listener** hoặc **bean**. |

Khi điều tra luồng event-driven, **module.invocation-type** cho biết đây là lời gọi qua listener thay vì một bean invocation thông thường. **module.identifier** giúp lọc theo ranh giới kiến trúc, còn **module.method** giúp xác định vị trí xử lý. Chuỗi tên span do exporter/backend hiển thị có thể phụ thuộc ObservationConvention và phiên bản, vì vậy **ưu tiên kiểm tra attributes** thay vì chỉ so tên span chính xác.

Ví dụ biểu diễn **dữ liệu minh họa** của một span:

~~~text
Trace:    7e1ba34d11f54a57989bfa9471242b21
Span:     c9f218647e32d95a
Name:     module entry / notification listener  (minh họa)
Duration: 83 ms
Attributes:
  module.identifier = notification
  module.name = Notification
  module.method = on(OrderPlaced)
  module.invocation-type = event listener
~~~

**Không xem các chuỗi giả định ở ví dụ là output bảo đảm từ một phiên bản cụ thể.** Giá trị của **module.method**, định dạng tên span và chữ hoa/thường phải lấy từ trace thực tế. Các khóa attribute trong bảng mới là điểm tham chiếu từ tài liệu Spring Modulith.

### Span, tag và cardinality

Số module và loại phương thức thường hữu hạn, nên những thuộc tính module tương đối hữu ích cho tìm kiếm hoặc phân tổ. Tuy nhiên, **eventId**, **orderId**, địa chỉ email, request payload và thông tin bí mật không phù hợp làm **nhãn metric** có cardinality cao. Khi cần đối chiếu từng nghiệp vụ, sử dụng **structured logs** chứa eventId, và cân nhắc custom span attributes theo chính sách bảo mật và chi phí của hệ thống.

## 4. Ba cách listener chạy và hình dạng trace tương ứng

Spring cho phép nhiều cơ chế lắng nghe sự kiện. Chúng khác nhau đáng kể về **thời điểm thực thi, thread và transaction**, từ đó ảnh hưởng tới span được tạo.

| Listener | Khi nào xử lý? | Ranh giới luồng/giao dịch | Điều cần hiểu khi đọc trace |
| --- | --- | --- | --- |
| **@EventListener** | Thường ngay lúc publishEvent được gọi. | Mặc định đồng bộ trên cùng luồng; có thể đang trong transaction của publisher. | Nếu được instrument, listener span có thể lồng trong thời gian xử lý của publisher. |
| **@TransactionalEventListener** | Mặc định ở pha **AFTER_COMMIT**. | Annotation tự nó **không làm xử lý bất đồng bộ**. | Listener chỉ được gọi khi transaction phù hợp commit; không giả định callback có span cùng cấu trúc với đồng bộ. |
| **@Async** trên listener | Theo TaskExecutor được cấu hình. | Chuyển sang thread khác; context theo thread cần được truyền. | Trace có thể bị tách; cần kiểm tra propagation và thời điểm span bắt đầu. |
| **@ApplicationModuleListener** | Xử lý sau commit theo cơ chế listener của Spring Modulith. | Kết hợp bất đồng bộ với transaction riêng cho listener. | HTTP/publisher có thể hoàn tất trước listener; span của listener phải được diễn giải độc lập. |

Đối với **@TransactionalEventListener**, nếu không có transaction hoạt động, listener mặc định không chạy, trừ khi dùng chế độ fallback phù hợp. Nếu transaction rollback, callback **AFTER_COMMIT** không được gọi. Khi không có lời gọi listener, sẽ không có listener invocation span, dù publisher có thể đã tạo log trước rollback.

**@ApplicationModuleListener** là annotation rút gọn của Spring Modulith cho listener bất đồng bộ, chạy sau commit và có transaction riêng. Điều này phù hợp với tác vụ bổ sung như thông báo, nhưng cũng làm xuất hiện khoảng cách giữa **giao dịch nghiệp vụ đã thành công** và **listener đã xử lý xong**.

## 5. Ví dụ xuyên module: OrderPlaced đến Notification

Giả sử cấu trúc:

~~~text
com.example.shop
  ShopApplication
  order
    OrderPlaced.java
    OrderService.java
  notification
    internal
      OrderPlacedListener.java
~~~

**OrderPlaced** là hợp đồng sự kiện công khai của module **order**, tránh truyền JPA entity sang module nhận:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Module order phát sự kiện trong nghiệp vụ tạo đơn:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final ApplicationEventPublisher publisher;
    private final OrderRepository orders;

    OrderService(ApplicationEventPublisher publisher, OrderRepository orders) {
        this.publisher = publisher;
        this.orders = orders;
    }

    @Transactional
    public UUID placeOrder(CreateOrderRequest request) {
        var order = orders.save(Order.from(request));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), order.getId(), Instant.now()));

        return order.getId();
    }
}
~~~

**OrderRepository**, **Order**, **CreateOrderRequest** là các kiểu minh họa nghiệp vụ; cần bổ sung trong một dự án thực tế. Ví dụ nhấn mạnh rằng publisher **không gọi trực tiếp NotificationService**. Nó chỉ công bố một sự kiện có mã **eventId** ổn định.

Module notification định nghĩa listener:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.order.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final NotificationRequestRepository notifications;

    OrderPlacedListener(NotificationRequestRepository notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        // Dùng eventId làm khóa chống xử lý trùng.
        notifications.createIfAbsent(event.eventId(), event.orderId());
    }
}
~~~

**NotificationRequestRepository** và phương thức **createIfAbsent** là hợp đồng giả định. Trong ứng dụng thật, cần ràng buộc duy nhất ở DB hoặc cơ chế idempotency khác; chỉ kiểm tra tồn tại trong Java trước khi insert là chưa an toàn khi có xử lý đồng thời.

Nếu listener được Spring Modulith instrument và tracing được bật, có thể tìm một **module entry span** với **module.identifier=notification**, **module.invocation-type=event listener** khi method **on(...)** được gọi. Việc gọi **publishEvent** không tự có nghĩa span này đã được tạo tại đúng thời điểm publisher gọi.

### Trục thời gian của listener sau commit

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client
    participant O as Order module
    participant DB as Database
    participant E as Event dispatcher
    participant N as Notification listener
    participant B as Trace backend
    C->>O: POST /orders
    activate O
    O->>DB: Lưu order trong transaction
    O->>E: publish OrderPlaced
    Note over O,E: Publisher vẫn ở transaction chính
    O->>DB: Commit thành công
    O-->>C: HTTP 201
    deactivate O
    E-->>N: Gọi listener sau commit, async
    activate N
    Note right of N: Module entry span bắt đầu khi listener được instrument và gọi
    N->>DB: Ghi yêu cầu thông báo (transaction riêng)
    N-->>E: Hoàn tất hoặc ném lỗi
    deactivate N
    N-->>B: Span export theo pipeline tracing
~~~

Sơ đồ thể hiện **trật tự logic**, không cố định thứ tự thực tế giữa việc trả HTTP response và worker bắt đầu chạy: lịch executor có thể khiến listener bắt đầu trước hoặc sau khi client nhận phản hồi. Span thường chỉ đo **khoảng thời gian lời gọi được instrument**; nó **không tự đo toàn bộ độ trễ từ lúc publish đến khi worker nhận nhiệm vụ**.

## 6. Phân biệt quan hệ trace và ranh giới transaction

Với xử lý đồng bộ, parent observation đang hoạt động trong HTTP request thường còn hiện diện khi method listener được gọi. Vì vậy, nếu instrumentation thu thập cả hai, **listener span có thể là child span trong cùng trace**.

Ở ranh giới **sau commit và bất đồng bộ**, thread xử lý listener khác thread request. Thông tin theo thread như current observation, trace context và MDC **không được mặc định bảo đảm truyền qua mọi executor**. Khi không có propagation, listener có thể:

- Tạo **trace mới** với root span riêng.
- Có logs thiếu **traceId** hoặc không cùng traceId với publisher.
- Bị mất liên hệ cha-con trên backend, dù nghiệp vụ listener vẫn chạy thành công.

Khi có propagation thích hợp, span của listener có thể tiếp tục liên hệ với context upstream. Nhưng **không nên mặc định mọi listener sau commit nằm dưới HTTP span cũ**, đặc biệt khi xử lý bị trì hoãn, retry sau restart hoặc qua broker khác tiến trình.

~~~mermaid
flowchart TD
    H["HTTP span / order"] --> P["publish OrderPlaced"]
    P --> S{"Listener đồng bộ hay async?"}
    S -->|"Đồng bộ + context hiện diện"| Child["Có thể tạo listener child span cùng trace"]
    S -->|"Async + propagated context"| Prop["Span liên hệ upstream nếu instrumentation phù hợp"]
    S -->|"Async thiếu context / retry muộn"| Root["Span có thể thuộc trace mới"]
    Child --> Corr["eventId vẫn là khóa tương quan nghiệp vụ"]
    Prop --> Corr
    Root --> Corr
~~~

Đặc biệt, **trace context không phải transaction context**. Việc copy context để nối traces không mang JDBC transaction hay EntityManager của publisher sang luồng listener. Với **@ApplicationModuleListener**, giao dịch xử lý riêng phải được quản lý theo hành vi của listener, độc lập với đường nối trace.

### EventId: mối liên hệ bền hơn thread-local

Nên đưa **eventId** vào hợp đồng sự kiện và ghi cùng thông tin nghiệp vụ trong logs của publisher/consumer:

~~~text
2026-11-27T09:00:00Z INFO module=order
  action=event_published eventType=OrderPlaced
  eventId=e-102 orderId=o-300 traceId=4bf92f...

2026-11-27T09:00:01Z INFO module=notification
  action=listener_started eventType=OrderPlaced
  eventId=e-102 traceId=7c82...

2026-11-27T09:00:02Z INFO module=notification
  action=listener_completed eventId=e-102 durationMs=103
~~~

Các ID trên là dữ liệu minh họa; **hai traceId khác nhau vẫn có thể là cùng nghiệp vụ**. Muốn nối qua một lần retry sau khi ứng dụng khởi động lại, eventId trong payload/registry/log thường đáng tin cậy hơn việc trông chờ thread-local context còn tồn tại.

## 7. Bật module span instrumentation và exporter

### 7.1. Spring Modulith observability

Spring Modulith hiện hành cung cấp **spring-modulith-starter-insight** để bổ sung cả Actuator và observability. Nếu chỉ cần observability có thể dùng module **spring-modulith-observability-core** cùng các dependency Actuator/tracing phù hợp:

~~~groovy
dependencies {
    // Cách tiện lợi cho ứng dụng muốn cả Actuator và observability:
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

**Cần BOM/release train tương thích** giữa Spring Boot và Spring Modulith. Tên artifact observability riêng đã thay đổi giữa các dòng cũ và mới, nên kiểm tra đúng tài liệu phiên bản trước khi sao chép dependency. **Starter Insight không tự lựa chọn, cấu hình hoặc triển khai một tracing backend**.

### 7.2. Ví dụ Spring Boot 4.x: OpenTelemetry/OTLP

Ở dòng Spring Boot 4.x, cấu hình theo starter và namespace property hiện hành:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics
~~~

Ví dụ dùng **OTLP/HTTP** đến OpenTelemetry Collector hoặc backend có receiver tương thích. Cổng **4318** thường nhận OTLP/HTTP và đường dẫn **/v1/traces**; cổng **4317** thường dùng OTLP/gRPC và không có đường dẫn HTTP tương tự. **localhost** phải được đánh giá từ bên trong runtime của ứng dụng; khi chạy Docker/Kubernetes, thường cần hostname nội bộ thay cho localhost.

### 7.3. Ví dụ Spring Boot 3.x: Micrometer Tracing bridge

Với dự án sử dụng Spring Boot 3.x và release Spring Modulith tương thích, cách khai báo tracer/exporter có thể là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Khác biệt quan trọng: **Spring Boot 3.x** thường dùng **management.otlp.tracing.endpoint**, còn ví dụ **Boot 4.x** dùng **management.opentelemetry.tracing.export.otlp.endpoint**. Không chép lẫn property giữa hai dòng; dùng BOM và tài liệu của phiên bản được triển khai.

**Sampling probability 1.0** chỉ nên dùng trong lab để dễ tìm trace. Ở production, cần điều chỉnh theo lưu lượng, thời gian lưu và chi phí. **Không thấy một span trong backend không đồng nghĩa listener chưa chạy**: có thể trace không được sampled hoặc export bị lỗi.

## 8. Context propagation cho listener bất đồng bộ

Nếu listener dùng **@Async**, executor sẽ quyết định thread xử lý. Spring Framework mô tả khả năng dùng **Micrometer Context Propagation** và **ContextPropagatingTaskDecorator** để mang ngữ cảnh quan sát vào task.

Ví dụ cấu hình một executor **do ứng dụng chủ động chọn**:

~~~java
package com.example.shop.infrastructure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncObservabilityConfiguration {

    @Bean("observedEventExecutor")
    ThreadPoolTaskExecutor observedEventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("event-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Để minh họa việc **chọn đúng executor**, với Spring Framework listener theo transaction tự khai báo:

~~~java
@Component
class AlternativeNotificationListener {

    @Async("observedEventExecutor")
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    @TransactionalEventListener
    public void on(OrderPlaced event) {
        // Xử lý event trong transaction mới, ngoài luồng publisher.
    }
}
~~~

Các imports cần thiết trong ví dụ: **Async**, **Transactional**, **Propagation**, **TransactionalEventListener**, **Component**. Cần thư viện **io.micrometer:context-propagation** phù hợp trên classpath; một số starter có thể cung cấp gián tiếp, nên kiểm tra dependency tree của bản chạy.

**Không tự động suy ra @ApplicationModuleListener sẽ dùng observedEventExecutor chỉ vì bean tồn tại.** Annotation tiện ích này có cấu hình và lựa chọn executor riêng theo cơ chế async của ứng dụng. Muốn xác nhận context propagation cho listener thật, phải biết **chính xác TaskExecutor nào thực thi listener** và test traceId/MDC trên thread đó. Đổi global **ApplicationEventMulticaster** cũng có thể tác động các listener khác; không nên làm chỉ để sửa một trace nếu chưa đánh giá hành vi transaction.

### Phạm vi và giới hạn context propagation

- **Trace context** giúp nối quan hệ quan sát, không thay thế **độ tin cậy giao event**.
- **Security context** và **transaction context** có cơ chế riêng; không xem việc truyền tracing context là truyền mọi ThreadLocal.
- Nếu event được retry từ registry sau restart hoặc chuyển qua broker, cần cơ chế truyền trace context rõ ràng qua boundary tương ứng; nối lại **eventId** là lựa chọn thực dụng khi parent span cũ không còn.
- Sự kiện và baggage/header không nên chứa email, token, dữ liệu cá nhân hoặc payload nhạy cảm chỉ để tiện tra cứu trace.

## 9. Cách đọc span của listener trong một trace

Khi đã có exporter và backend như Zipkin, Grafana Tempo hoặc Jaeger, tiến hành:

1. Gửi một yêu cầu tạo đơn và ghi lại **orderId/eventId**.
2. Trên backend, lọc service theo **spring.application.name** (ví dụ **shop-modulith**) và thời gian thử nghiệm.
3. Mở trace có request hoặc module entry span và tìm các spans có **module.identifier=notification**.
4. Kiểm tra **module.invocation-type=event listener**, **module.method**, thời gian bắt đầu/kết thúc và thông tin lỗi.
5. Nếu listener span không nằm trong cùng trace, tra logs theo **eventId** để lấy traceId khác rồi mở trace đó.
6. Đối chiếu kết quả với **event publication status** và trạng thái nghiệp vụ thực tế; không kết luận chỉ từ màu xanh/đỏ trên một span.

### Cách diễn giải thời lượng

Giả sử ở môi trường lab:

| Mốc | Thời gian tương đối |
| --- | ---: |
| Publisher gọi publishEvent | 0 ms |
| Transaction đặt hàng commit | 25 ms |
| Listener được executor bắt đầu gọi | 120 ms |
| Listener xử lý xong | 205 ms |

Khi đó:

- **Khoảng chờ từ publish đến listener start** khoảng 120 ms (cần đo bằng log/metric/sự kiện thời gian phù hợp).
- **Khoảng listener thực thi** khoảng 85 ms (là ứng viên cho span duration nếu span bao đúng lời gọi).
- **Tổng thời gian từ publish đến hoàn tất listener** khoảng 205 ms.

Đây là số liệu giả định để học cách đọc timeline; **module listener span không tự đo toàn bộ 205 ms**. Nếu listener thực hiện thao tác email bên ngoài và chỉ đưa task vào queue, span thành công ở mốc 205 ms chưa chứng minh email đã tới người nhận.

### Trường hợp có nhiều listener

~~~mermaid
flowchart TD
    P["OrderPlaced published"] --> L1["Notification listener span"]
    P --> L2["Reporting listener span"]
    L1 --> O1["Tạo yêu cầu gửi email"]
    L2 --> O2["Cập nhật báo cáo"]
    O1 --> R["Outcomes riêng từng listener"]
    O2 --> R
~~~

Từng listener có thể bắt đầu, kết thúc hoặc lỗi ở thời điểm khác nhau. Nếu có registry bền vững, publication status thường được theo dõi theo **listener đích**, không nên gom chung thành trạng thái thành công duy nhất chỉ vì event đã được phát.

## 10. Lỗi listener, retry và ý nghĩa của spans

**Mốc “listener bắt đầu” khác “listener thành công”**. Spring Modulith có Event Publication Registry để ghi nhận việc giao event đến transactional listeners khi được cấu hình với backend phù hợp. Registry hỗ trợ điều tra khi listener thất bại; version và cấu hình quyết định trạng thái lifecycle, cơ chế retry và cách phát lại.

### Các trường hợp cần phân biệt

| Tình huống | Dấu vết quan sát có thể có | Cần kiểm tra tiếp |
| --- | --- | --- |
| Publisher gọi publishEvent, transaction rollback | Log publisher hoặc span liên quan có thể tồn tại; listener AFTER_COMMIT không chạy. | Transaction outcome; đừng tìm listener span sau commit nếu event không đủ điều kiện phát. |
| Transaction commit, worker chưa bắt đầu | Có event/registry entry, chưa có listener invocation span. | Executor, backlog, trạng thái publication, startup/restart. |
| Listener bắt đầu và ném exception | Module span có thể có error metadata nếu instrumentation ghi nhận; log stack trace. | Publication status, retry policy, idempotency. |
| Listener chạy thành công nhưng exporter lỗi | Listener hoàn tất, backend không thấy span. | Exporter/collector/trace sampling/logs. |
| Listener chạy lại cùng eventId | Có thể thấy nhiều listener spans ở nhiều thời điểm/traces. | Retry và unique constraint; không mặc định đó là phát event mới. |
| Listener ghi DB thành công nhưng external API gửi email thất bại sau đó | Span của listener có thể “thành công” theo phạm vi mã listener. | Trạng thái yêu cầu thông báo, API đích, outbox/queue, đối soát. |

**Span lỗi không tự thực hiện retry.** Tracing giúp điều tra; tính đúng đắn cần transaction, registry, chính sách phục hồi và **idempotency**. Khi listener đã gọi API ngoài nhưng chưa kịp đánh dấu publication hoàn tất, retry có thể gây side effect trùng. Dùng eventId làm khóa chống trùng ở DB/consumer; với API ngoài, cân nhắc idempotency key hoặc outbox.

### Không nhầm các trạng thái Spring Modulith với span status

Trong Spring Modulith 2.x, Event Publication Registry có lifecycle riêng cho publication như **PUBLISHED**, **PROCESSING**, **COMPLETED**, **FAILED** và các trạng thái phát lại theo phiên bản. Đây là **trạng thái xử lý sự kiện** trong tầng publication. Trái lại, **span status** phản ánh cách instrumentation ghi nhận một đoạn thực thi. Hai dữ liệu liên quan nhưng không thay thế nhau; có thể có publication FAILED nhưng không có trace được export.

## 11. Phối hợp spans với metrics, logs và module graph

| Nguồn | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- |
| **Module graph** | Có những module nào, API và dependencies ra sao? | Là góc nhìn cấu trúc, không xác nhận một lần xử lý runtime. |
| **/actuator/modulith** | Bản ứng dụng đang chạy nhận diện các module, dependency nào? | Không phải danh sách listener invocations đã hoàn tất. |
| **module.events.published** | Có bao nhiêu lần công bố domain event? | Không phải counter “listener thành công”. |
| **Listener module span** | Một lời gọi listener được instrument diễn ra bao lâu, liên hệ với trace nào? | Không bao gồm mọi thời gian chờ, không bảo đảm mọi lần gọi đều được sampled/export. |
| **Structured logs** | eventId nào chạy/lỗi ở đâu, với thông tin nghiệp vụ nào? | Cần thiết kế định dạng và correlation nhất quán. |
| **Event Publication Registry** | Publication nào chưa hoàn tất hoặc đã xử lý tùy backend/version? | Không thay thế thống kê latency/correlation trong tracing. |
| **Executor/queue metrics** | Hàng đợi, số worker và thời gian chờ của tác vụ async. | Thường phải instrument riêng theo executor đang dùng. |

Spring Modulith có metric công bố domain event **module.events.published**, cùng các counter theo loại event/module. Nếu metric tăng nhưng listener span không xuất hiện, đừng vội kết luận listener bị bỏ qua: hãy kiểm tra **transaction phase**, **sampling**, **observability module**, **executor**, **trace exporter** và **backend**.

### Những metric listener nên cân nhắc tự bổ sung

Các tên sau là **gợi ý metric nghiệp vụ**, không phải cam kết Spring Modulith tự tạo chúng:

| Metric gợi ý | Kiểu | Mục tiêu |
| --- | --- | --- |
| **domain_event_listener_completed_total** | Counter | Số lần listener hoàn tất theo eventType, listener, outcome. |
| **domain_event_listener_failed_total** | Counter | Số lần lỗi để cảnh báo và so tỷ lệ lỗi. |
| **domain_event_listener_duration_seconds** | Timer/Histogram | Thời gian xử lý listener, theo p95/p99. |
| **domain_event_pending_publications** | Gauge | Số publication còn chờ xử lý từ registry phù hợp. |
| **domain_event_oldest_pending_age_seconds** | Gauge | Tuổi của publication chờ lâu nhất. |
| **domain_event_executor_queued** | Gauge | Độ sâu hàng đợi executor đã instrument. |

Đặt nhãn có cardinality hữu hạn (**module**, **eventType**, **listener**, **outcome**). Không dùng **eventId/orderId** làm labels của metrics. Các định danh này phù hợp để tra logs hoặc tìm kiếm span chi tiết khi chính sách dữ liệu cho phép.

## 12. Thực hành kiểm chứng listener spans end-to-end

Một bài lab có thể triển khai hai module **order** và **notification** ở trên cùng một ứng dụng Spring Boot. Khi tạo đơn, publisher phát **OrderPlaced**; listener nhận sau commit và ghi yêu cầu thông báo vào DB.

### Chuẩn bị

1. Chọn phiên bản Spring Boot và Spring Modulith tương thích; thêm Insight starter và tracer/exporter theo mục 7.
2. Khởi động Zipkin hoặc Collector với backend trace thực sự. Nếu dùng OTLP/HTTP, xác nhận receiver nghe cổng **4318**; Collector chỉ có debug exporter thì trace chỉ hiện trong log Collector.
3. Bật sampling **1.0** tạm thời trong lab và cấu hình **spring.application.name=shop-modulith**.
4. Bật log có **traceId/spanId** và thêm **eventId** cho publisher/consumer.
5. Xác nhận module order và notification được nhận diện bằng module graph hoặc **/actuator/modulith** khi endpoint đã expose.

### Thử nghiệm A — Xử lý thành công

**Thao tác:** Gọi API tạo đơn một lần và kiểm tra kết quả lưu DB/notification request.

**Bằng chứng mong đợi:** Có log **OrderPlaced published**, log listener bắt đầu/kết thúc, một hoặc nhiều trace tìm được trên backend. Nếu instrumentation nhận diện listener, kiểm tra span có **module.identifier=notification** và **module.invocation-type=event listener**. Nếu chỉ có HTTP span, kiểm tra điều kiện instrumentation và sampling trước khi kết luận listener không chạy.

### Thử nghiệm B — Rollback trước commit

**Thao tác:** Trong integration test, tạo giao dịch rồi ném exception để rollback sau khi phát event.

**Bằng chứng mong đợi:** Với listener **AFTER_COMMIT** không có side effect của notification. Việc không xuất hiện listener span trong tình huống này là **đúng thiết kế**; event publication log chỉ nên phản ánh trạng thái theo quy tắc transaction/registry đã cấu hình.

### Thử nghiệm C — Lỗi ở listener

**Thao tác:** Trong môi trường test, cho dependency của listener ném exception.

**Bằng chứng mong đợi:** Publisher đã commit nhưng listener thất bại; log lỗi chứa eventId. Nếu trace được thu thập, xem module listener span và lỗi. Nếu registry bền vững được bật, kiểm tra publication chưa hoàn tất/trạng thái FAILED theo phiên bản, rồi xử lý retry an toàn.

### Thử nghiệm D — Mất context khi async

**Thao tác:** So sánh traceId trong log publisher và listener khi dùng executor hiện tại. Nếu thiếu propagation, cấu hình TaskDecorator/Context Propagation trên **đúng executor** và thử lại.

**Bằng chứng mong đợi:** Trace correlation cải thiện khi cấu hình đúng. Tuy vậy, vẫn giữ **eventId** để nối nghiệp vụ trong retry hoặc trường hợp không có một trace liên tục.

### Thử nghiệm E — Chẩn đoán pipeline telemetry

**Thao tác:** Xác nhận listener xử lý được event nhưng tạm thời đặt sai endpoint OTLP trong lab.

**Bằng chứng mong đợi:** Logs/trạng thái DB cho thấy listener đã chạy, nhưng trace không đến backend; lỗi ở exporter/collector chứ không phải ở listener. Khôi phục endpoint và thử lại để phân biệt rõ **mất telemetry** với **mất xử lý nghiệp vụ**.

### Checklist kết quả

| Kiểm tra | Đạt khi |
| --- | --- |
| Có đúng publisher/consumer | OrderPlaced phát từ order, listener thuộc notification. |
| Có module instrumentation | Dependency và module detection đúng; trace có module entry spans khi được sample. |
| Metadata span | Có module.identifier, module.name, module.method, module.invocation-type khi instrumentation ghi nhận. |
| Đúng thời điểm | AFTER_COMMIT listener không tạo side effect nếu giao dịch rollback. |
| Đúng transaction | Listener async xử lý riêng, không làm rollback đơn hàng đã commit. |
| Correlation | Có eventId ở cả publisher và listener; traceId đúng kỳ vọng theo propagation. |
| Phân biệt lỗi | Khi listener lỗi, registry/log/tracing phản ánh tình trạng theo vai trò riêng. |
| Không xử lý trùng | Retry cùng eventId không tạo dữ liệu nghiệp vụ lặp. |

## 13. Chẩn đoán khi không có hoặc có “span lạ”

| Triệu chứng | Nguyên nhân cần phân biệt | Cách xác minh |
| --- | --- | --- |
| Không thấy span cho listener | Listener chưa chạy hoặc không được instrument; sampling/exporter cũng có thể làm span biến mất. | Kiểm tra logs eventId, side effect, registry, module detection, tracer và exporter. |
| Có event-published counter nhưng thiếu listener span | Metric đếm publisher, khác listener invocation; cũng có thể async chưa chạy. | Kiểm tra transaction phase, queue, listener logs và trace sampling. |
| Có span HTTP, không có module span | Thiếu Spring Modulith observability hoặc tương tác không qua điểm API được instrument. | Kiểm tra Insight/observability core, Spring bean, module API, version. |
| Listener span là root span khác trace HTTP | Context không qua executor, retry sau restart hoặc không có parent lúc xử lý. | Kiểm tra TaskExecutor, Context Propagation, logs eventId. |
| Hai span listener cho cùng eventId | Có thể nhiều lần retry hoặc có nhiều listener. | Kiểm tra listener identity, publication status và thời điểm gọi. |
| Listener span duration thấp nhưng email tới chậm | Listener có thể chỉ đưa yêu cầu vào queue hoặc đo một phần workflow. | Theo dõi trạng thái email gateway, outbox, downstream latency. |
| Listener span success nhưng registry chưa hoàn tất | Registry completion/transaction có thể lỗi sau khi method thực hiện side effect. | Kiểm tra transaction, registry logs, retry và idempotency. |
| Thiếu span ở tỷ lệ request thấp | Sampling < 100%, collector/backend drop, lọc sai service/time range. | Thử sampling 100% trong lab, kiểm tra exporter và service name. |
| Module method tag khác kỳ vọng | Naming convention/phiên bản hoặc method interception khác. | So module.identifier, invocation-type và stack phiên bản thực tế. |
| Trace chứa dữ liệu cá nhân | Custom span attributes/logging đã ghi payload nhạy cảm. | Kiểm tra semantic conventions, giới hạn dữ liệu và policy retention. |

Quy trình điều tra nên theo thứ tự: **nghiệp vụ có chạy không → listener có được gọi không → instrumentation có tạo Observation không → tracer có sample không → exporter/collector có nhận không → backend có hiển thị đúng time range/service không**. Không sửa mã listener trước khi phân biệt được đây là lỗi nghiệp vụ hay lỗi telemetry.

## 14. Những nguyên tắc thiết kế để span có giá trị

**Ưu tiên các ranh giới ổn định.** Module entry span nên đại diện cho tương tác giữa các application module hoặc lần listener tiếp nhận sự kiện, chứ không phải mọi private method. Cần chi tiết hơn thì tự instrument những bước nghiệp vụ quan trọng bằng Micrometer Observation, tránh tạo hàng nghìn spans cho từng thao tác nhỏ.

**Không để tracing thay thế tính đúng đắn.** Sampling và exporter có thể làm mất dữ liệu trace; transaction, idempotency và registry mới giúp xác nhận/khôi phục xử lý event. Không viết logic nghiệp vụ phụ thuộc vào việc có trace hay không.

**Tôn trọng bất đồng bộ.** Listener sau commit có thời điểm và transaction khác publisher. Khi so duration, phải tách **queue wait**, **execution time** và **external side effect completion**. Một span bắt đầu khi listener được gọi không thể tự đo thời gian trước khi listener được schedule.

**Giữ đường điều tra bền vững.** Event payload có **eventId**, logs có correlation ID, dashboard có metrics theo module/eventType, tracing có module attributes. Không bắt buộc mọi sự kiện đi trong cùng traceId với HTTP request để kết luận luồng xử lý đúng.

**Tách metadata ổn định và dữ liệu cá nhân.** module.identifier/module.method hữu ích để lọc; tuyệt đối không dùng token, email hay payload nhạy cảm làm metric labels và cần kiểm soát span attributes cùng lưu trữ tracing.

## 15. Nguồn tham khảo

Các tài liệu chính thức để kiểm tra API và hành vi theo phiên bản dự án:

- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — Module Entry Span, bộ attribute module, Insight starter, event publication metrics.
- **Spring Modulith — Working with Application Events:** https://docs.spring.io/spring-modulith/reference/events.html — ApplicationEventPublisher, @TransactionalEventListener, @ApplicationModuleListener và Event Publication Registry.
- **Spring Framework — Observability Support:** https://docs.spring.io/spring-framework/reference/integration/observability.html — Micrometer Observation, phạm vi instrumentation, @EventListener và context propagation.
- **Spring Boot — Tracing:** https://docs.spring.io/spring-boot/reference/actuator/tracing.html — Micrometer Tracing, sampler, OTLP/Zipkin exporter và truyền trace giữa các thành phần.
- **Spring Boot 3.5 — Tracing:** https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html — dependency và property khi ứng dụng sử dụng Spring Boot 3.x.

## 16. Tổng kết

**Span của event listener** trong Spring Modulith là bằng chứng quan sát về **một lời gọi listener đã được instrument**, thường được nhận diện qua **module.invocation-type=event listener** cùng **module.identifier**, **module.name** và **module.method**. Span có thể cho thấy thời gian và lỗi của phần xử lý được bao bởi instrumentation, nhưng không tự đại diện cho toàn bộ thời gian từ lúc phát event đến khi tác vụ ngoài hệ thống hoàn tất.

Khi listener chạy sau commit và bất đồng bộ, transaction của publisher đã độc lập với listener, còn trace context có thể mất tại ranh giới executor hoặc retry. Muốn kiểm chứng hành vi runtime, hãy phối hợp **module spans**, **module graph/Actuator**, **event metrics**, **structured logs với eventId**, **context propagation** và **Event Publication Registry khi được cấu hình**. Nhờ đó, bạn có thể phân biệt chính xác một event chưa được xử lý, một listener đã lỗi, hay đơn giản là một trace không được xuất đến backend.
