# Trace asynchronous qua application event

## 1. Vì sao application event bất đồng bộ khó theo dõi bằng trace?

Trong ứng dụng Spring Boot thiết kế theo **Spring Modulith**, các *application module* nên giao tiếp qua API được công bố hoặc qua domain event. Cách dùng `ApplicationEventPublisher` giúp module phát sự kiện không cần biết trực tiếp những module nào sẽ phản ứng. Chẳng hạn `ordering` phát `OrderPlaced`; `notification` nhận sự kiện và gửi email sau khi đơn hàng được lưu.

Vấn đề phát sinh khi listener chạy **bất đồng bộ (asynchronous)**: request HTTP đã đi qua một thread, trong khi listener được thực thi trên thread của executor, có thể sau khi request đã kết thúc. Nếu chỉ dựa vào trace mặc định của HTTP, người vận hành có thể thấy “đặt hàng thành công” nhưng không thấy bước “gửi thông báo” trong cùng trace.

Đây là bài học về **module spans**, nằm trong phạm vi `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`: dùng Spring Modulith để quan sát tương tác qua ranh giới application module, đọc traces và event metrics, đồng thời hiểu **context propagation** để kiểm chứng hành vi khi hệ thống vận hành.

Ba câu hỏi cần tách biệt ngay từ đầu:

1. **Event có được phát không?** Có thể theo dõi bằng log hoặc counter `module.events.published` khi observability được cấu hình.
2. **Listener có được thực thi và hoàn tất không?** Cần tín hiệu từ chính listener, log, trace và/hoặc Event Publication Registry.
3. **Span listener có nối với trace gốc không?** Phụ thuộc vào instrumentation, tracing backend, sampling và việc truyền trace context qua ranh giới thread.

Counter tăng không đồng nghĩa listener thành công; listener chạy xong cũng không đồng nghĩa span được gắn đúng vào trace của request phát sự kiện.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa event đồng bộ, `@Async` và `@ApplicationModuleListener`.
- Đọc quan hệ module-entry spans, trace ID và parent span khi xử lý event bất đồng bộ.
- Cấu hình executor truyền Micrometer observation/trace context bằng `ContextPropagatingTaskDecorator`.
- Phân biệt “thiếu span vì mất context” với “listener không chạy” hoặc “span bị sampling loại bỏ”.
- Đối chiếu tracing với metrics, module graph và Event Publication Registry mà không suy luận sai về bảo đảm giao dịch.

## 2. Một luồng đặt hàng xuyên hai module

Xét hai module trực tiếp dưới package gốc `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering
│   ├── OrderService.java
│   ├── OrderPlaced.java
│   └── internal
│       └── OrderRepository.java
└── notification
    ├── OrderNotificationListener.java
    └── internal
        └── EmailGateway.java
~~~

`OrderService` lưu đơn hàng và phát sự kiện. `OrderNotificationListener` nhận sự kiện để gửi thông báo. Sơ đồ mô tả **quy trình nghiệp vụ**, không phải chiều phụ thuộc tĩnh:

~~~mermaid
sequenceDiagram
    autonumber
    actor C as HTTP client
    participant O as ordering / HTTP thread
    participant TX as Transaction manager
    participant X as Async executor
    participant N as notification / worker thread
    C->>O: POST /orders
    O->>TX: lưu đơn hàng trong transaction
    O->>TX: publishEvent(OrderPlaced)
    Note over TX: Transaction commit thành công
    TX->>X: lên lịch listener sau commit
    O-->>C: HTTP response
    X-->>N: on(OrderPlaced)
    N->>N: gửi email / ghi nhận kết quả
~~~

Sơ đồ minh họa thứ tự logic: listener được lên lịch khi transaction gốc commit, còn thời điểm thread thực sự xử lý tùy executor. HTTP response và listener có thể chồng lấn; không suy diễn một thứ tự thời gian tuyệt đối từ hình vẽ.

### 2.1. Domain event và publisher

Một event công khai có thể dùng Java record:

~~~java
package com.example.shop.ordering;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

Service phát event trong transaction:

~~~java
package com.example.shop.ordering;

import com.example.shop.ordering.internal.OrderRepository;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;
    private final OrderRepository orders;

    public OrderService(ApplicationEventPublisher events, OrderRepository orders) {
        this.events = events;
        this.orders = orders;
    }

    @Transactional
    public UUID placeOrder(Order order) {
        orders.save(order);
        events.publishEvent(new OrderPlaced(order.getId()));
        return order.getId();
    }
}
~~~

`Order` và `OrderRepository` là các thành phần miền minh họa cần được cài đặt trong ứng dụng thực tế. Điểm cần hiểu là lời gọi `publishEvent(…)` xảy ra **trong transaction**, để listener dạng `@TransactionalEventListener` có thể được kích hoạt ở phase thích hợp. Khi dùng phase mặc định `AFTER_COMMIT`, nếu không có transaction tương ứng, listener thông thường sẽ không chạy, trừ khi bạn cấu hình `fallbackExecution` thích hợp.

### 2.2. Listener bất đồng bộ theo Spring Modulith

Spring Modulith cung cấp `@ApplicationModuleListener`:

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import com.example.shop.notification.internal.EmailGateway;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    private final EmailGateway emailGateway;

    public OrderNotificationListener(EmailGateway emailGateway) {
        this.emailGateway = emailGateway;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        emailGateway.sendOrderConfirmation(event.orderId());
    }
}
~~~

Trong ví dụ, `EmailGateway` là cổng tích hợp do module `notification` triển khai. Annotation `@ApplicationModuleListener` là cách viết gọn cho tổ hợp **`@Async` + `@TransactionalEventListener` + `@Transactional(propagation = REQUIRES_NEW)`**. Vì vậy:

- Listener phản ứng **sau khi transaction phát event commit thành công** theo phase mặc định của `@TransactionalEventListener`.
- Listener được lên lịch chạy bất đồng bộ khi cơ chế `@Async` được kích hoạt và có executor phù hợp.
- Listener có thể chạy trong **transaction riêng**, tách khỏi transaction đặt hàng.

Để áp dụng `@Async` trong ứng dụng Spring thông thường, cần bật async processing, ví dụ dùng `@EnableAsync` trong một lớp cấu hình. Đừng đánh đồng “phương thức có annotation” với “đang thực sự chạy trên thread khác”; hãy kiểm tra cấu hình và quan sát thread trong runtime.

## 3. Trace, span và bối cảnh hiện hành

Trong hệ sinh thái Spring Boot, **Micrometer Observation** là mô hình ghi nhận một vùng thực thi. Khi kết hợp `ObservationRegistry` với tracing bridge và exporter, các observation được instrument có thể tạo **span** hiển thị trong Zipkin, Jaeger, Grafana Tempo hoặc backend tương ứng.

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Trace** | Tập span được liên kết để mô tả một luồng xử lý logic. |
| **Trace ID** | Định danh liên kết các span thuộc cùng trace. |
| **Span ID** | Định danh của một span cụ thể. |
| **Parent span ID** | Quan hệ cha/con giúp biểu diễn vùng xử lý nào đã tạo hoặc kích hoạt vùng khác. |
| **Current span/observation** | Span/observation đang hoạt động trong ngữ cảnh thực thi hiện tại. |
| **Context propagation** | Mang thông tin trace/observation sang vùng thực thi khác, ví dụ từ HTTP thread sang executor thread. |
| **Sampling** | Quyết định trace/span nào được ghi hoặc xuất; có thể làm thiếu một số dữ liệu khi quan sát. |

Trong lời gọi đồng bộ, code thường thực thi cùng thread, nên các giá trị ngữ cảnh dạng `ThreadLocal` có thể được giữ trong call stack. Khi `@Async` gửi task sang một thread khác, `ThreadLocal` từ thread phát sự kiện **không tự động xuất hiện** ở thread nhận. Nếu không có propagation, listener có thể bắt đầu trace khác, mất thông tin trace hiện hành hoặc không tạo span như mong đợi.

## 4. Spring Modulith tạo module-entry spans như thế nào?

Spring Modulith có hỗ trợ observability để chặn các lời gọi đi vào Spring component thuộc **API của application module** và tạo Micrometer Observation/span cho tương tác qua ranh giới. Với event listener nằm trong phạm vi được instrument, trace có thể cho thấy điểm vào module `notification`.

Các tag được tài liệu Spring Modulith mô tả cho *module entry span*:

| Tag | Mục đích |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của module, ví dụ `notification`. |
| `module.name` | Tên hiển thị của application module. |
| `module.method` | Phương thức được thực thi ở điểm vào module. |
| `module.invocation-type` | Kiểu lời gọi, theo tài liệu là **`event listener`** hoặc **`bean`**. |

Ở đây, `module.invocation-type` là loại tương tác để phân tích dấu vết, **không phải** kết quả xử lý. Không nên suy ra một span có tag `event listener` là sự kiện đã được gửi lại, đã được commit hoặc đã thành công.

### Trace mong muốn khi truyền context đúng

Một hình dạng **minh họa**:

~~~text
Trace T-123 (trace ID giống nhau trên các vùng được liên kết)
├── HTTP POST /orders
│   └── module-entry: ordering / placeOrder(...)
└── module-entry: notification / on(OrderPlaced)
    module.identifier = notification
    module.invocation-type = event listener
~~~

Điểm quan trọng là **có thể liên hệ span của listener với luồng phát event bằng trace context**. Vị trí span trên cây, quan hệ cha/con và thời gian bắt đầu/kết thúc phụ thuộc thời điểm capture context, tracing bridge, các observation đang mở và cách listener được instrument; listener bất đồng bộ có thể bắt đầu sau khi span HTTP kết thúc. Vì vậy sơ đồ trên **không cam kết** rằng mọi backend sẽ hiển thị đúng một cây có hai nhánh như vậy.

### Trace có thể bị tách khi không truyền context

~~~text
Trace T-123:
  HTTP POST /orders
    module-entry: ordering / placeOrder(...)

Trace T-987 hoặc span không được xuất:
  module-entry: notification / on(OrderPlaced)
~~~

Nếu có dấu hiệu này, chưa thể kết luận listener không chạy. Trước hết cần xác minh thread và context được truyền sang executor, tracer/exporter hoạt động và cả hai nhánh đã được lấy mẫu.

## 5. Điểm dễ nhầm: event đồng bộ khác listener bất đồng bộ

Mặc định, khi không cấu hình bất đồng bộ, Spring `ApplicationEventPublisher` phát event tới listener đồng bộ trên thread hiện hành. Listener `@EventListener` thông thường có thể chạy ngay trong call stack của publisher.

Với `@ApplicationModuleListener`, việc xử lý được thiết kế theo cách **transactional sau commit + async**:

| Tiêu chí | `@EventListener` mặc định | `@ApplicationModuleListener` |
| --- | --- | --- |
| Thread xử lý | Thường cùng thread với publisher. | Có thể là thread executor khác do `@Async`. |
| Thời điểm xử lý | Khi publish event, theo cơ chế sync. | Sau commit thành công của transaction gốc. |
| Transaction riêng | Không tự tạo chỉ vì là listener. | Dùng transaction riêng với `REQUIRES_NEW`. |
| Quan hệ với latency HTTP | Thời gian listener đồng bộ có thể kéo dài request. | Thường tách công việc nền ra khỏi thời gian chờ response. |
| Nhu cầu truyền trace context | Ít ranh giới thread hơn. | Cần đặc biệt chú ý propagation qua executor. |
| Đảm bảo không mất event | Không tự được bảo đảm cho mọi lỗi. | Cũng cần cơ chế reliability, ví dụ Event Publication Registry, nếu nghiệp vụ yêu cầu. |

Nếu chỉ viết `@Async` mà không kích hoạt async processing, phương thức có thể không được đưa qua executor. Nếu dùng `@TransactionalEventListener` mà event được phát **ngoài transaction**, listener có thể không được gọi theo mặc định. Hai trường hợp này phải kiểm tra trước khi đổ lỗi cho tracing.

## 6. Cấu hình khả năng quan sát Spring Modulith

### 6.1. Dependency của module observability

Với dự án sử dụng BOM tương thích giữa Spring Boot và Spring Modulith, có thể dùng Insight Starter để bật Actuator cùng observability:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Nếu chỉ cần instrumentation module mà không cần endpoint `/actuator/modulith`, Spring Modulith 2.x cũng cung cấp:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-observability-core")
}
~~~

Các ví dụ sử dụng Gradle Kotlin DSL và giả định phiên bản dependency được quản lý bởi BOM/plugin. **Tên artifact và phương thức cấu hình tracer có thể thay đổi giữa Spring Modulith 1.x, 2.x cũng như Spring Boot 3.x, 4.x**; hãy đối chiếu tài liệu phiên bản đang dùng.

Insight Starter hỗ trợ instrumentation, nhưng để xem trace cần có **Micrometer Tracing bridge, exporter và tracing backend** phù hợp. Trong Spring Boot 4.x, một cấu hình ví dụ khi xuất OpenTelemetry/OTLP có thể sử dụng:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
}
~~~

Với Spring Boot 3.x, lựa chọn phổ biến là Micrometer Tracing bridge cho OpenTelemetry hoặc Brave cùng exporter phù hợp. Không sao chép nguyên starter/tracing property từ Boot 4.x vào dự án Boot 3.x.

Trong môi trường thử nghiệm, có thể cấu hình:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0  # dễ quan sát mọi request trong bài thực hành nhỏ
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith"
~~~

Sampling 100% là lựa chọn cho **dev/test**, không mặc định thích hợp ở production do chi phí ghi và lưu dữ liệu. Việc expose Actuator qua HTTP không tạo ra trace exporter, và `/actuator/modulith` là endpoint **cấu trúc module**, không phải endpoint trả về các trace.

## 7. Truyền context khi đổi thread với `ContextPropagatingTaskDecorator`

Đây là bước quan trọng nhất khi muốn nối trace của event listener bất đồng bộ với trace gốc. Spring Framework cung cấp `ContextPropagatingTaskDecorator` để **capture** các giá trị ngữ cảnh hiện hành khi task được lập lịch và **restore** chúng trong lúc task chạy trên executor thread.

Với `@Async` dùng một `ThreadPoolTaskExecutor` do ứng dụng định nghĩa, ví dụ:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncExecutionConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("modulith-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Điểm cần ghi nhớ:

1. `@EnableAsync` bật cơ chế xử lý `@Async`.
2. `ThreadPoolTaskExecutor` là nơi listener được lập lịch; tên bean `taskExecutor` giúp ứng dụng sử dụng đúng executor mặc định cho `@Async` khi không chỉ định tên khác.
3. `setTaskDecorator(new ContextPropagatingTaskDecorator())` chụp và khôi phục context qua thread boundary.
4. Thư viện `io.micrometer:context-propagation` phải có trên classpath (có thể đã được dependency observability/tracing kéo theo). Nếu class không có, bổ sung dependency và đối chiếu BOM.
5. Nếu ứng dụng cấu hình **nhiều executor** hoặc `@Async("executorKhac")`, cần gắn decorator vào **executor thực sự được listener sử dụng**, không chỉ vào một executor bất kỳ.

`ContextPropagatingTaskDecorator` giúp chuyển context, nhưng tự nó **không tạo một span nghiệp vụ mới**, không bảo đảm export trace và không giải quyết tính tin cậy của event. Nếu muốn quan sát thời gian chờ trong queue, phải thêm instrumentation hoặc metric thích hợp: module-entry span của listener thường đo **thời gian thực thi của listener**, không mặc nhiên bao gồm toàn bộ thời gian chờ.

### 7.1. Khi dùng Spring Boot tự cấu hình executor

Spring Boot có thể tự cấu hình `AsyncTaskExecutor` và tự liên kết các `TaskDecorator` bean tùy phiên bản/cấu hình. Tài liệu Spring Boot 3.5 hướng dẫn khai báo bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
class TraceContextConfiguration {
    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

**Đây là phương án khác với việc tự khai báo executor ở trên.** Nếu ứng dụng đã tự tạo executor, hãy kiểm tra nó thực sự sử dụng bean decorator hay gắn trực tiếp `setTaskDecorator(…)`. Một số bản Spring Boot mới còn có thuộc tính `spring.task.execution.propagate-context` cho auto-configured executor. Không dựa vào thuộc tính ấy khi dùng phiên bản Spring Boot chưa hỗ trợ.

### 7.2. Vì sao decorator hoạt động?

~~~mermaid
flowchart LR
    HTTP["HTTP thread: current observation T-123"]
    Capture["TaskDecorator: capture context"]
    Queue["Executor queue"]
    Restore["Worker thread: restore context"]
    Listener["notification.on(OrderPlaced)"]
    Span["Module entry observation / span"]
    HTTP --> Capture --> Queue --> Restore --> Listener --> Span
~~~

Khi listener chạy, context đã được đưa sang thread mới; instrumentation có thể dùng context đó để liên hệ span với trace đang có. Điều kiện tiên quyết là **có context hợp lệ tại thời điểm capture** và các thành phần observation/tracing đã được kích hoạt.

## 8. Cách kiểm chứng trace qua application event

### 8.1. Thực hiện một luồng có thể tái hiện

Trong môi trường dev:

1. Khởi động ứng dụng có Spring Modulith observability, tracing bridge và exporter.
2. Cấu hình listener `@ApplicationModuleListener`, bật `@EnableAsync` và executor có context propagation.
3. Gửi một yêu cầu tạo đơn hàng, bảo đảm `OrderService` chạy trong transaction rồi commit.
4. Đọc log để xác nhận publisher và listener đều chạy; ghi thêm `orderId` làm correlation key của nghiệp vụ.
5. Mở backend tracing, tìm trace HTTP tương ứng, quan sát module-entry span của `ordering` và `notification` nếu được instrument.
6. Đối chiếu trace ID, thời gian bắt đầu/kết thúc và loại span; nếu vắng listener span, điều tra theo mục 10.

Ví dụ request chỉ mang tính minh họa:

~~~bash
curl -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"BOOK-1","quantity":1}'
~~~

URL, payload và controller của ứng dụng thật sẽ khác. Nếu backend tracing hoặc exporter chưa cấu hình, `curl` thành công không chứng minh trace đã được thu thập.

### 8.2. Log correlation để kiểm tra khi thiếu span

Khi có Micrometer `Tracer` trong classpath, có thể log `traceId` và `orderId` tại điểm xử lý:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Đặt phần này trong listener đã có Tracer được inject.
private static final Logger log =
    LoggerFactory.getLogger(OrderNotificationListener.class);

private final Tracer tracer;

private void logTrace(OrderPlaced event) {
    Span span = tracer.currentSpan();
    String traceId = span == null ? "none" : span.context().traceId();
    log.info("stage=notification orderId={} traceId={}",
        event.orderId(), traceId);
}
~~~

Đây là **đoạn bổ sung minh họa**, không phải một class hoàn chỉnh: hãy thêm constructor injection `Tracer` và gọi `logTrace(event)` trong listener nếu muốn thực hành. `Tracer` chỉ tồn tại khi dự án có hạ tầng tracing tương ứng; Insight Starter một mình chưa đủ.

Khi so hai dòng log, hãy hỏi:

- `orderId` có giống nhau? Nó liên kết các bước về mặt nghiệp vụ.
- `traceId` có giống nhau? Nó liên kết các span theo ngữ cảnh tracing.
- Thread name có khác nhau? Điều đó giúp xác định listener thực sự async.
- Có lỗi trong listener hoặc exporter không? Việc log được trace ID không đảm bảo span đã được backend lưu.

**Không dùng giá trị `orderId` hoặc thông tin cá nhân làm tag metric low-cardinality**: số giá trị tăng vô hạn sẽ gây áp lực lên hệ thống metrics. Dùng correlation ID trong log/trace theo chính sách bảo vệ dữ liệu của ứng dụng.

### 8.3. Nhìn trace đúng cách

Mô tả timeline **minh họa**, không phải trace thực tế:

~~~text
Time →
HTTP request       [-----------]
  ordering entry     [-------]
  commit                       |
async task queue               ........
notification entry                  [--------]

Vùng [---] = span được instrument, "........" = thời gian đợi có thể chưa có span.
~~~

Vì listener chạy ở task riêng, `notification` có thể bắt đầu **sau** khi span của `ordering` đã kết thúc. Quan hệ thời gian chồng lấn hay không không tự quyết định span có cùng trace ID. Và một span có `module.invocation-type=event listener` chỉ xác nhận đoạn code tương ứng được ghi nhận, không chứng minh event đã được xử lý duy nhất đúng một lần.

## 9. Metrics, module graph và Event Publication Registry bổ sung gì?

Trace phục vụ điều tra một lần xử lý, nhưng để kiểm chứng đầy đủ hệ thống nên kết hợp các nguồn:

| Nguồn | Trả lời câu hỏi | Điều không chứng minh được |
| --- | --- | --- |
| `/actuator/modulith` / module graph | Module nào được nhận diện và quan hệ dependency nào tồn tại? | Event cụ thể đã chạy hay không. |
| `module.events.published` | Số lượt phát domain event đã được instrument là bao nhiêu? | Listener đã xử lý thành công hay chưa. |
| Module-entry spans | Điểm vào module nào đã được ghi, mất bao lâu và liên kết trace như thế nào? | Bảo đảm giao event exactly-once hoặc trạng thái giao dịch toàn cục. |
| Logs với correlation key | Kết nối thông tin nghiệp vụ và lỗi ở các bước. | Tự động thay thế cơ chế phục hồi event. |
| Event Publication Registry | Theo dõi các publication cho transactional listeners và hỗ trợ xử lý sự kiện chưa hoàn tất. | Tự động bảo đảm span của retry nằm cùng trace với request ban đầu. |
| `ApplicationModules.verify()` | Kiểm tra một số luật ranh giới/quan hệ phụ thuộc tĩnh. | Độ trễ listener ở thời gian chạy. |

### 9.1. Event Publication Registry không phải tracing

Spring Modulith có **Event Publication Registry** để ghi nhận việc công bố sự kiện tới các transactional event listener và đánh dấu khi listener hoàn thành. Tùy phiên bản/cấu hình, các publication chưa hoàn tất hoặc lỗi có thể được phát lại theo cơ chế phục hồi.

Giả sử một listener gửi email bị lỗi, việc xử lý lại sự kiện sau vài phút có thể chạy trong **một lần thực thi mới**, khi HTTP request gốc đã kết thúc từ lâu. Khi đó, không nên giả định rằng span của lần retry phải là con trực tiếp của span HTTP cũ. Nên dùng **correlation ID nghiệp vụ** hoặc metadata được bảo vệ phù hợp để liên hệ lịch sử gốc và các lần thử xử lý, đồng thời đọc trạng thái publication riêng.

**Trace continuity** và **reliability** là hai vấn đề khác nhau: truyền context giúp nối span trong các bước có liên quan; registry giúp theo dõi và phục hồi event được giao cho listener. Một hệ thống có thể làm tốt một việc mà vẫn thiếu việc kia.

### 9.2. Khi event vượt khỏi tiến trình

`ApplicationEventPublisher` và `@ApplicationModuleListener` trong ví dụ này là cơ chế event **nội bộ tiến trình Spring Boot**. Nếu event được chuyển qua Kafka, RabbitMQ hoặc một dịch vụ khác, cần cơ chế **inject/extract trace context vào message headers** theo chuẩn được tracing stack hỗ trợ (ví dụ W3C Trace Context) và instrumentation của producer/consumer. `ContextPropagatingTaskDecorator` chỉ giải quyết ranh giới **task/thread trong tiến trình**; không tự đưa context qua broker hay mạng.

## 10. Xử lý sự cố theo dấu hiệu quan sát

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| Counter event tăng nhưng listener không chạy | Transaction rollback; publish ngoài transaction; listener không đăng ký; bean không được scan. | Xem `@TransactionalEventListener`, transaction boundary, component scan, exception và cấu hình async. |
| Listener chạy trên thread HTTP | `@EnableAsync` chưa được bật; proxy async không áp dụng; cấu hình sai. | Kiểm tra `@EnableAsync`, `@ApplicationModuleListener`, bean proxy và thread name. |
| Listener chạy nhưng `traceId=none` | Không có tracing bridge/context; executor không truyền context; span không đang active. | Kiểm tra tracer, `TaskDecorator` trên executor thực, thời điểm capture và logging. |
| Publisher và listener có trace ID khác nhau | Context mất khi chuyển thread; listener khởi tạo trace mới; replay về sau. | Xem context propagation, executor hoặc nguồn event có phải lần retry khác. |
| Có cùng trace ID nhưng không thấy span listener | Module listener không thuộc phạm vi instrumentation; observation bị lọc hoặc span không được xuất. | Kiểm tra observability dependency, module boundary, sampling, exporter và backend. |
| Có span listener nhưng không có HTTP span | HTTP server instrumentation hoặc sampling khác, truy vấn trace chưa đủ, hoặc event phát ngoài HTTP request. | Kiểm tra nguồn phát, trace ID và cấu hình HTTP tracing. |
| Listener span chậm nhưng không thấy thời gian trong queue | Module-entry span thường chỉ đo vùng listener thực thi. | Thêm metric queue depth/wait time hoặc observation riêng nếu cần đo thời gian chờ. |
| Listener bị gọi lại và tạo span trùng nghiệp vụ | Event retry/republication, ít nhất một lần xử lý hoặc logic publish trùng. | Xem Event Publication Registry, attempt, idempotency key và kết quả nghiệp vụ. |
| Không thấy trace trong Zipkin/Tempo | Thiếu exporter, sai URL, lỗi collector, sampling loại bỏ hoặc backend chưa nhận dữ liệu. | Kiểm tra dependency tracing, endpoint exporter, log exporter và cấu hình sampling. |

### Quy trình kiểm tra ưu tiên

Khi không thấy span của `notification`, đừng chỉnh tracing ngay lập tức. Lần lượt xác minh **listener thật sự chạy**, **nó chạy ở thread nào**, **có current trace context lúc task được lập lịch**, **decorator có nằm trên executor thực tế**, **module instrumentation có tạo observation**, rồi mới kiểm tra **sampling và exporter**. Cách này giúp tránh nhầm lỗi business, async và observability với nhau.

## 11. Hạn chế và các nguyên tắc thiết kế

1. **Span là bằng chứng của vùng đã được instrument.** Không có span không có nghĩa không có thực thi; có thể do sampling, cấu hình, proxy hoặc ranh giới thread.
2. **Một trace có thể chứa công việc bất đồng bộ sau HTTP response.** Đừng dựa vào thời điểm kết thúc request để loại bỏ phần xử lý sau commit.
3. **Chỉ dùng sampling 100% khi cần kiểm chứng nhỏ.** Ở production, chọn xác suất dựa vào tải, chi phí, chính sách lưu trữ và nhu cầu phân tích sự cố.
4. **Không nhầm queue latency với listener duration.** Muốn đo từ lúc publish đến lúc listener bắt đầu, cần ghi nhận thời gian enqueue/dequeue có chủ đích.
5. **Truyền context có chi phí.** `ContextPropagatingTaskDecorator` hữu ích qua thread boundary nhưng có overhead, nhất là với lượng task rất nhỏ và dày đặc; đo hiệu năng khi áp dụng trên workload nhạy cảm.
6. **Tránh tag cardinality cao và dữ liệu nhạy cảm.** Không đưa địa chỉ email, thông tin khách hàng hoặc order ID vào metric tags có lượng giá trị vô hạn.
7. **Đảm bảo listener idempotent khi có retry.** Tracing giúp điều tra hành vi, không thay thế logic tránh gửi email hoặc thanh toán lặp.
8. **Kiểm chứng ranh giới module bằng mã nguồn.** Dùng `ApplicationModules.verify()` và `Documenter` bên cạnh Actuator graph, metrics và traces để đối chiếu kiến trúc.

## 12. Bài tập thực hành

**Bài tập 1 — Xác định khác biệt:** Tạo hai listener xử lý cùng một event, một listener `@EventListener` đồng bộ và một listener `@ApplicationModuleListener`. Ghi thread name và thời điểm chạy. Giải thích vì sao kết quả khác nhau khi transaction commit.

**Bài tập 2 — Tái hiện mất context:** Trong môi trường test, cấu hình async executor chưa có `ContextPropagatingTaskDecorator` và quan sát trace/log khi phát `OrderPlaced`. Sau đó bật decorator trên đúng executor và so sánh trace ID. Ghi rõ tracing bridge và sampling đang được sử dụng.

**Bài tập 3 — Đọc span:** Trong tracing backend, tìm span có `module.identifier=notification` và `module.invocation-type=event listener` (nếu được instrument). So sánh thời lượng span với thời gian gửi email; giải thích giới hạn của dữ liệu.

**Bài tập 4 — Transaction rollback:** Buộc transaction đặt hàng rollback sau khi publish event. Kiểm tra listener `@ApplicationModuleListener` có được gọi hay không và lý giải theo phase `AFTER_COMMIT`. Thực hiện chỉ ở môi trường thử nghiệm.

**Bài tập 5 — Retry:** Giả lập một listener xử lý lỗi trong môi trường có Event Publication Registry. Theo dõi trạng thái publication và thử cơ chế resubmit được cấu hình. Kiểm tra tại sao trace của lần thử lại có thể khác trace ban đầu, đồng thời phải duy trì correlation key nghiệp vụ.

### Câu hỏi tự kiểm tra

**Câu 1.** `@ApplicationModuleListener` thay thế những annotation nào trong cách cấu hình thường gặp?

**Trả lời:** Nó là shortcut của `@Async`, `@TransactionalEventListener` và `@Transactional(propagation = REQUIRES_NEW)`.

**Câu 2.** Vì sao listener có thể chạy thành công nhưng xuất hiện trong trace khác?

**Trả lời:** Vì context dạng `ThreadLocal` không tự truyền qua executor thread; thiếu propagation, listener có thể bắt đầu một trace mới hoặc không xuất span như mong đợi.

**Câu 3.** `ContextPropagatingTaskDecorator` có tự bảo đảm event không bị mất không?

**Trả lời:** Không. Nó truyền observation/trace context khi task đổi thread; Event Publication Registry và cơ chế retry/idempotency phục vụ bài toán reliability khác.

**Câu 4.** Có thể khẳng định listener thành công nếu `module.events.published` tăng không?

**Trả lời:** Không. Counter phản ánh publication được ghi nhận; cần tín hiệu kết quả listener hoặc trạng thái publication để kết luận xử lý.

**Câu 5.** Nếu listener được resubmit sau khi ứng dụng khởi động lại, có nhất thiết cùng trace ID với request HTTP gốc không?

**Trả lời:** Không. Đó là lần thực thi mới; dùng correlation key nghiệp vụ để nối các lần thử, không phụ thuộc hoàn toàn vào parent span ban đầu.

## 13. Tài liệu tham khảo

- [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `ApplicationEventPublisher`, `@ApplicationModuleListener`, transaction phase và Event Publication Registry.
- [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): `spring-modulith-starter-insight`, module-entry spans, event metrics và nhãn spans.
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation và context propagation qua async executor.
- [Spring Boot 3.5 – Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): hướng dẫn `ContextPropagatingTaskDecorator` cho Boot 3.x.
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, sampling, exporter và trace context.
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): phạm vi instrumentation, event handling và truyền context.
- [Spring Framework – ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): cách decorator bọc task và chi phí thực thi.

**Ghi nhớ:** để trace một application event bất đồng bộ trong Spring Modulith, phải kiểm tra **cả ba mắt xích**: event được phát và listener thực thi đúng phase; context của request được truyền qua executor thread; instrumentation/tracer/exporter tạo và lưu span. Graph mô-đun, event metrics, traces và Event Publication Registry cung cấp những bằng chứng khác nhau, cần được đối chiếu thay vì xem một tín hiệu là kết luận cho toàn bộ hệ thống.
