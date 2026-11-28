# Bridge từ Observation sang tracer

## 1. Tại sao cần bridge giữa Observation và tracer?

Trong ứng dụng Spring Boot, **Micrometer Observation** cung cấp một API chung để ghi nhận hoạt động của chương trình. Một observation có thể được dùng để tạo metrics, traces hoặc các tín hiệu quan sát khác thông qua những handler được đăng ký trong `ObservationRegistry`.

Khi ứng dụng sử dụng **Spring Modulith**, framework có thể tạo observation tại điểm đi vào API của application module. Ví dụ, request đặt hàng đi từ module `ordering` sang API của `payment`. Observation giúp ghi nhận thời gian và metadata của lời gọi này. Nhưng để nhìn thấy nó thành một **span** trong Zipkin, Grafana Tempo hoặc Jaeger, ứng dụng còn cần một tracer và một đường xuất trace.

**Bridge từ Observation sang tracer** chính là lớp tích hợp biến vòng đời observation thành thao tác tracing. Nó cho phép instrumentation tạo observation mà không cần phụ thuộc trực tiếp vào Brave hoặc OpenTelemetry. Một tracing handler nhận các sự kiện start/stop của observation, sử dụng API Micrometer Tracing để tạo và hoàn tất span; bridge implementation kết nối API đó với tracer nền.

Bài này thuộc chương **Micrometer tracing** của module **`SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`**. Mục tiêu của module là dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác trong ứng dụng Spring Boot, bao gồm module graph, Actuator, event metrics, tracing và context propagation.

Sau bài học, bạn có thể:

1. Phân biệt Observation API, Micrometer Tracing API, bridge implementation, exporter và tracing backend.
2. Mô tả đường đi từ `ObservationRegistry` đến span.
3. Chọn một bridge Brave hoặc OpenTelemetry phù hợp với dự án.
4. Cấu hình dependency và sampling theo phiên bản Spring Boot.
5. Hiểu vai trò của `Tracer`, `Propagator` và tracing observation handlers.
6. Tạo một observation nghiệp vụ và xác minh nó được chuyển thành span.
7. Đọc module-entry spans của Spring Modulith và kiểm tra context propagation.
8. Chẩn đoán trường hợp metrics vẫn hoạt động nhưng không thấy trace.

## 2. Bức tranh kiến trúc: từ observation đến span

Một pipeline tracing dựa trên Micrometer thường gồm các thành phần:

~~~mermaid
flowchart LR
    A["Instrumentation<br/>Spring Modulith / Spring Boot / code ứng dụng"]
    B["ObservationRegistry"]
    C["Tracing ObservationHandler"]
    D["Micrometer Tracing API<br/>Tracer / Span / Propagator"]
    E["Bridge implementation<br/>Brave hoặc OpenTelemetry"]
    F["Exporter / Reporter"]
    G["Tracing backend<br/>Zipkin / Tempo / Jaeger"]
    A --> B --> C --> D --> E --> F --> G
~~~

Sơ đồ thể hiện các trách nhiệm logic. Trong Spring Boot, một số bean được tự cấu hình dựa trên dependency có trong classpath; không nhất thiết ứng dụng phải tự tạo từng lớp theo đúng thứ tự trong hình.

| Thành phần | Vai trò |
| --- | --- |
| **Instrumentation** | Tạo observation quanh hoạt động cần đo, ví dụ HTTP request, database call hoặc điểm vào application module. |
| **`ObservationRegistry`** | Quản lý observation hiện hành, convention, filter và các handler. |
| **Tracing ObservationHandler** | Nhận vòng đời observation và ánh xạ nó sang span. |
| **Micrometer Tracing API** | Cung cấp abstraction như `Tracer`, `Span` và `Propagator`. |
| **Bridge implementation** | Nối API Micrometer Tracing với thư viện tracing nền như Brave hoặc OpenTelemetry. |
| **Exporter/Reporter** | Gửi span đã kết thúc tới collector hoặc backend. |
| **Tracing backend** | Lưu, tìm kiếm, hiển thị trace và các span liên quan. |

### 2.1. Ba lớp thường bị nhầm

- **Observation** mô tả một vùng thực thi và vòng đời của nó.
- **Span** là đơn vị trong distributed trace, có trace ID, span ID, thời gian, quan hệ cha/con, attributes và trạng thái lỗi.
- **Exporter** chuyển dữ liệu span ra khỏi tiến trình để backend thu thập.

Vì vậy, có `ObservationRegistry` chưa có nghĩa là ứng dụng đã có tracer; có tracer chưa chắc đã có exporter; có exporter chưa có nghĩa collector/backend đang nhận dữ liệu. Cần kiểm tra từng mắt xích.

## 3. Observation API và Micrometer Tracing API

### 3.1. Observation API

Micrometer Observation định nghĩa cách instrument mà không gắn chặt vào một vendor tracing cụ thể. Những khái niệm chính:

| API | Chức năng |
| --- | --- |
| `Observation` | Đối tượng đại diện một hoạt động có start, stop, error, event và scope. |
| `ObservationRegistry` | Registry điều phối observation và handler. |
| `Observation.Context` | Giữ dữ liệu của observation cụ thể. |
| `ObservationConvention` | Quy định tên, contextual name và key/value metadata. |
| `ObservationHandler` | Nhận các callback trong vòng đời observation để xuất tín hiệu. |

Instrumentation có thể dùng `Observation.createNotStarted(...)` rồi `observe(...)` để quản lý vòng đời. Spring Boot và Spring Modulith cũng có thể tạo observation tự động cho các điểm đã được instrument.

### 3.2. Micrometer Tracing API

Micrometer Tracing cung cấp abstraction tracing để ứng dụng và instrumentation không phải gọi trực tiếp API riêng của Brave hoặc OpenTelemetry.

| API | Vai trò |
| --- | --- |
| `Tracer` | Tạo span mới, lấy span hiện tại và đưa span vào scope hiện hành. |
| `Span` | Đại diện một vùng trong trace, có thể đặt tên, tag, ghi lỗi, start và end. |
| `TraceContext` | Chứa trace ID, span ID, thông tin sampled và các trường context liên quan. |
| `Propagator` | Inject context vào carrier khi gửi đi và extract context khi nhận. |
| `Baggage` | Mang một số giá trị context xuyên qua các ranh giới nếu được cấu hình. |

### 3.3. Bridge implementation

Micrometer Tracing cung cấp các bridge phổ biến:

| Artifact | Kết nối tới |
| --- | --- |
| `io.micrometer:micrometer-tracing-bridge-brave` | Brave tracer. |
| `io.micrometer:micrometer-tracing-bridge-otel` | OpenTelemetry tracer. |

Bridge cung cấp implementation cho các abstraction Micrometer Tracing. Ví dụ, khi code gọi `Tracer.nextSpan()`, bridge chuyển thao tác đó thành hành động tương ứng trên Brave hoặc OpenTelemetry.

**Chọn một implementation phù hợp cho một pipeline tracing.** Không thêm cả Brave bridge và OpenTelemetry bridge chỉ vì muốn “có nhiều lựa chọn”; chúng có cách cấu hình, exporter và propagation khác nhau. Nếu cần chuyển đổi backend, hãy thay đổi bridge và cấu hình theo kế hoạch, rồi xác minh dữ liệu trace.

## 4. Tracing ObservationHandler làm gì?

ObservationRegistry có thể có nhiều handler cùng nhận một observation. Ví dụ:

- Metrics handler tạo timer/counter hoặc cập nhật meter.
- Tracing handler tạo span khi observation bắt đầu và hoàn tất span khi observation kết thúc.
- Các handler khác có thể ghi log hoặc tích hợp hệ thống giám sát riêng.

Vì vậy, **một observation có thể đồng thời tạo metric và span** nếu cả hai handler đều được đăng ký. Tracing không thay thế metrics; hai handler xử lý cùng một nguồn instrument nhưng tạo loại tín hiệu khác nhau.

Trong Micrometer Tracing, những handler có vai trò phổ biến gồm:

| Handler | Vai trò |
| --- | --- |
| `DefaultTracingObservationHandler` | Tạo span từ observation thông thường và quản lý vòng đời span. |
| `PropagatingSenderTracingObservationHandler` | Xử lý observation thuộc ngữ cảnh gửi, inject trace context vào carrier trước khi gửi. |
| `PropagatingReceiverTracingObservationHandler` | Xử lý observation thuộc ngữ cảnh nhận, extract trace context từ carrier. |

Các sender/receiver handler chỉ hoạt động khi instrumentation sử dụng context tương ứng (ví dụ `SenderContext` hoặc `ReceiverContext`) và được cấu hình đúng. Không phải mọi observation đều là một lần gửi/nhận qua mạng.

### 4.1. Vòng đời ánh xạ observation sang span

~~~mermaid
sequenceDiagram
    participant I as Instrumentation
    participant R as ObservationRegistry
    participant H as Tracing ObservationHandler
    participant T as Micrometer Tracer
    participant B as Brave / OpenTelemetry
    I->>R: tạo và start Observation
    R->>H: onStart(context)
    H->>T: tạo hoặc tiếp tục Span
    T->>B: thao tác qua bridge
    B-->>H: span context
    I->>I: thực thi nghiệp vụ
    I->>R: stop Observation
    R->>H: onStop(context)
    H->>T: kết thúc Span
    T->>B: end/export pipeline
~~~

Đây là sơ đồ khái niệm. Trình tự callback cụ thể còn phụ thuộc loại observation, handler và phiên bản Micrometer. Span có thể được tạo trước khi code nghiệp vụ chạy và được hoàn tất khi observation dừng; exporter thường gửi dữ liệu khi span kết thúc hoặc theo cơ chế batching.

### 4.2. Scope và parent-child relationship

Khi observation mở scope, span tương ứng có thể trở thành span hiện hành. Một observation được tạo trong scope đó có thể tạo **span con**, nhờ vậy trace thể hiện một hoạt động lớn gồm các bước nhỏ hơn.

Ví dụ:

~~~text
HTTP POST /orders
└── module-entry: ordering / placeOrder
    ├── module-entry: payment / authorize
    │   └── observation: payment.gateway.request
    └── observation: order.repository.save
~~~

Sơ đồ chỉ xuất hiện nếu từng bước có instrumentation tương ứng. Một lời gọi Java thông thường không tự động thành span chỉ vì nó nằm dưới một span khác.

## 5. Spring Boot tự cấu hình pipeline tracing ra sao?

Spring Boot tích hợp Micrometer Observation và Micrometer Tracing. Khi các dependency cần thiết có mặt, auto-configuration có thể tạo tracer, propagator và observation handlers phù hợp với bridge đã chọn.

### 5.1. Dependency cho Brave + Zipkin

Ví dụ Gradle Kotlin DSL cho một ứng dụng Spring Boot 3.x sử dụng Brave và Zipkin:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Bridge Micrometer Tracing sang Brave.
    implementation("io.micrometer:micrometer-tracing-bridge-brave")

    // Reporter gửi span tới Zipkin.
    runtimeOnly("io.zipkin.reporter2:zipkin-reporter-brave")
}
~~~

Phiên bản các dependency nên do Spring Boot dependency management/BOM quản lý; không ghim các phiên bản Micrometer hoặc Zipkin tùy ý nếu BOM đã cung cấp phiên bản tương thích.

### 5.2. Dependency cho OpenTelemetry + OTLP

Một lựa chọn khác:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Bridge Micrometer Tracing sang OpenTelemetry.
    implementation("io.micrometer:micrometer-tracing-bridge-otel")

    // Exporter dùng giao thức OTLP.
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Đây là cách khai báo theo mô hình Spring Boot 3.x/Micrometer Tracing. Với các thế hệ Spring Boot mới hơn, starter và cơ chế auto-configuration có thể thay đổi; hãy dùng dependency management và hướng dẫn tracing đúng dòng Boot đang chạy. **Không thêm cả hai bridge vào cùng một cấu hình chỉ để dự phòng.**

### 5.3. Spring Modulith Insight Starter

Khi muốn thêm instrumentation của Spring Modulith, có thể dùng:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Insight Starter cung cấp hỗ trợ Actuator và observability của Spring Modulith. Nó không đồng nghĩa với việc đã chọn exporter hoặc backend. Cần bridge/tracer và exporter phù hợp nếu muốn xem module-entry observations dưới dạng spans bên ngoài ứng dụng.

Nếu chỉ cần module-entry instrumentation, Spring Modulith 2.x cũng có artifact `spring-modulith-observability-core`; nếu source Java cần import API tùy biến như `ModulithObservationConvention`, thêm `spring-modulith-observability-api` ở compile scope.

### 5.4. Sơ đồ lựa chọn dependency

~~~mermaid
flowchart TB
    A["Cần module-entry observations của Spring Modulith?"]
    A -->|"Có"| M["spring-modulith-starter-insight<br/>hoặc observability-core"]
    A -->|"Không"| B["Spring Boot Observation instrumentation"]
    M --> C["Chọn một Micrometer Tracing bridge"]
    B --> C
    C --> D{"Tracer backend"}
    D -->|"Brave"| E["micrometer-tracing-bridge-brave"]
    D -->|"OpenTelemetry"| F["micrometer-tracing-bridge-otel"]
    E --> G["Zipkin reporter / exporter tương ứng"]
    F --> H["OTLP exporter"]
    G --> I["Tracing backend"]
    H --> I
~~~

## 6. Cấu hình endpoint và sampling

### 6.1. Sampling trong môi trường phát triển

Ví dụ `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
  tracing:
    sampling:
      probability: 1.0
~~~

`management.tracing.sampling.probability` là tỷ lệ lấy mẫu trace trong cấu hình Spring Boot tương ứng. Giá trị `1.0` giúp quan sát mọi request trong một bài thực hành nhỏ. Trong production, cần cân nhắc lưu lượng, chi phí, thời hạn lưu dữ liệu và yêu cầu điều tra sự cố; không mặc định dùng 100% sampling cho hệ thống tải lớn.

Các endpoint có ý nghĩa:

- `/actuator/health`: trạng thái sức khỏe theo các health contributor.
- `/actuator/metrics`: meter đã được đăng ký.
- `/actuator/prometheus`: chỉ khi có Prometheus registry và được expose.
- `/actuator/modulith`: cấu trúc application module, không phải trace endpoint.

### 6.2. Cấu hình Zipkin

Nếu sử dụng Zipkin reporter và Spring Boot có cấu hình tương ứng, endpoint thường được đặt bằng thuộc tính:

~~~yaml
management:
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Tên thuộc tính và auto-configuration cần được đối chiếu với phiên bản Spring Boot cụ thể. Backend Zipkin phải đang chạy và có thể nhận request từ ứng dụng.

### 6.3. Cấu hình OTLP

Với OpenTelemetry exporter, cấu hình endpoint phụ thuộc giao thức và phiên bản Spring Boot/OTel exporter. Với OTLP/HTTP, collector thường có endpoint nhận traces như `http://localhost:4318/v1/traces`; với OTLP/gRPC, cổng và endpoint có thể khác.

Không nhầm **collector endpoint** với giao diện truy vấn của backend. Ví dụ, Tempo có thể nhận OTLP ở collector/gateway nhưng người dùng xem trace qua Grafana. Cần cấu hình đúng endpoint gửi span, protocol, TLS và authentication theo môi trường.

## 7. Ví dụ: tạo Observation và để bridge chuyển thành span

Spring Modulith có thể tự tạo observation ở điểm vào module. Với một bước nghiệp vụ riêng bên trong module, ứng dụng cũng có thể tạo observation thủ công bằng `ObservationRegistry`. Khi tracing handlers được đăng ký, observation này có thể được chuyển thành span mà không cần gọi trực tiếp API Brave/OpenTelemetry.

Ví dụ trong module `payment`:

~~~java
package com.example.shop.payment;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentCaptureService {

    private final ObservationRegistry registry;
    private final PaymentGateway gateway;

    public PaymentCaptureService(
            ObservationRegistry registry,
            PaymentGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void capture(String orderId, String channel) {
        Observation.createNotStarted("payment.capture", registry)
            .contextualName("capture payment")
            .lowCardinalityKeyValue("payment.channel", channel)
            .observe(() -> gateway.capture(orderId));
    }
}
~~~

`PaymentGateway` là interface minh họa cần được định nghĩa trong ứng dụng. `channel` nên được chuẩn hóa thành một tập giá trị hữu hạn, ví dụ `web`, `mobile`, `pos`. Không dùng order ID hoặc customer ID làm low-cardinality metric tag.

Khi bridge/tracing handler đã được cấu hình:

1. `Observation.createNotStarted(...)` tạo observation gắn với registry.
2. `observe(...)` start observation, mở scope, chạy callback và stop observation.
3. Tracing handler nhận callback vòng đời và tạo span qua `Tracer`.
4. Bridge chuyển thao tác Micrometer Tracing sang Brave hoặc OpenTelemetry.
5. Span được kết thúc và chuyển đến exporter/backend theo pipeline đã cấu hình.

Nếu chỉ có metrics handler, observation có thể tạo timer/metric nhưng không có span. Nếu có tracing handler nhưng thiếu exporter, span có thể được tạo trong tiến trình nhưng không nhìn thấy trên backend ngoài.

### 7.1. Lấy tracer hiện hành để kiểm tra

Ứng dụng có thể inject `io.micrometer.tracing.Tracer`:

~~~java
package com.example.shop.payment;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
class TraceContextInspector {

    private final Tracer tracer;

    TraceContextInspector(Tracer tracer) {
        this.tracer = tracer;
    }

    void logCurrentTrace() {
        Span current = tracer.currentSpan();
        if (current == null) {
            // Không có span hiện hành trong scope này.
            return;
        }

        String traceId = current.context().traceId();
        String spanId = current.context().spanId();
        // Ghi vào log theo chính sách dữ liệu của ứng dụng.
    }
}
~~~

`currentSpan()` có thể trả `null` nếu không có span đang hoạt động. Điều đó không nhất thiết chứng minh tracing chưa được cấu hình: code có thể đang chạy ngoài observation scope hoặc context đã mất khi chuyển thread.

### 7.2. Khi nào nên gọi trực tiếp `Tracer`?

Phần lớn instrumentation nghiệp vụ nên ưu tiên **Observation API** vì nó độc lập với backend và có thể đồng thời phục vụ metrics lẫn traces. Gọi trực tiếp `Tracer` hữu ích trong một số trường hợp đặc thù cần quản lý span thủ công hoặc thao tác với trace context. Tuy nhiên, code phụ thuộc trực tiếp `Tracer` thường gắn chặt hơn với tracing stack và phải quản lý scope, error, start/end cẩn thận.

## 8. Propagator: đưa trace context qua ranh giới

Tạo span trong một tiến trình chỉ là một phần của distributed tracing. Khi request đi qua HTTP client, message broker hoặc executor thread, các bước ở đầu nhận cần biết **trace context của đầu gửi** để nối đúng trace.

`Propagator` cung cấp hai thao tác khái niệm:

- **Inject:** ghi trace context hiện tại vào carrier, ví dụ HTTP headers hoặc message headers.
- **Extract:** đọc context từ carrier ở đầu nhận và khôi phục ngữ cảnh cho span tiếp theo.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant P as Propagator
    participant H as HTTP / message headers
    participant B as Service B
    A->>P: inject current TraceContext
    P->>H: ghi traceparent / baggage nếu cấu hình
    A->>B: gửi request/message
    B->>P: extract headers
    P->>B: tạo context nhận
    B->>B: tạo span con / tiếp nối trace
~~~

Trong hệ thống hỗ trợ W3C Trace Context, header `traceparent` mang thông tin trace ID, parent span ID và flags; `tracestate` có thể mang thông tin vendor-specific. Baggage là cơ chế riêng để truyền các key/value được cho phép.

**Không tự viết header theo định dạng riêng nếu thư viện đã có Propagator.** Dùng instrumentation HTTP client/server hoặc messaging tích hợp với Micrometer Tracing để tránh sai chuẩn, mất parent context và lỗi tương thích.

### 8.1. Context propagation qua executor thread

Một application event có thể được xử lý bất đồng bộ trên thread khác. `ThreadLocal` không tự sao chép từ thread phát event sang worker thread. Với Spring Framework, có thể dùng `ContextPropagatingTaskDecorator` trên executor thực tế:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator chụp context khi task được lập lịch và khôi phục khi task chạy. Nếu có nhiều executor hoặc listener chỉ định `@Async("otherExecutor")`, phải gắn decorator vào executor **thực sự được dùng**. Với message broker sang tiến trình khác, task decorator không đủ; cần inject/extract qua headers.

`ContextPropagatingTaskDecorator` cần Spring Framework có hỗ trợ API này và Micrometer Context Propagation (`io.micrometer:context-propagation`) trên classpath để capture/restore các accessor đã đăng ký. Spring Boot có thể quản lý dependency tương ứng trong một số cấu hình; nếu tự khai báo executor hoặc dependency tối giản, hãy kiểm tra dependency tree và tài liệu đúng phiên bản.

## 9. Spring Modulith và module-entry spans

Khi observability của Spring Modulith được bật, framework tạo observation tại điểm vào Spring component thuộc API module được instrument. Observation này có thể được tracing handler chuyển thành span thông qua bridge.

Một module-entry span có thể mang các tag:

| Tag | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của module. |
| `module.name` | Tên hiển thị của module. |
| `module.method` | Phương thức tại điểm vào module. |
| `module.invocation-type` | Kiểu lời gọi, ví dụ `bean` hoặc `event listener`. |

Ví dụ trace:

~~~text
Trace: POST /orders
└── HTTP server span
    └── module-entry: ordering / placeOrder
        └── module-entry: payment / authorize
            └── observation: payment.capture
~~~

Các span xuất hiện tùy thuộc đường đi thực thi và phạm vi instrumentation. Graph có cạnh `ordering → payment` không đảm bảo mọi request đều đi qua `payment`; chỉ trace của một lần gọi được ghi nhận mới cho biết lần đó đã đi qua những điểm instrument nào.

### 9.1. Event metrics không thay thế spans

Spring Modulith ghi nhận domain event publication bằng các meter như:

- `module.events.published`: counter tổng hợp, có tag module và event type.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`: counter riêng cho một kiểu event, có thể tùy biến tag qua `ModulithEventMetricsCustomizer`.

Counter cho biết số lần phát event đã được instrument. Module-entry span cho biết một vùng thực thi được quan sát và thời gian của nó. Counter tăng không chứng minh listener thành công; span không thay thế cơ chế đảm bảo event được xử lý đáng tin cậy.

### 9.2. Quan hệ với Event Publication Registry

Event Publication Registry của Spring Modulith theo dõi publication tới transactional listeners và trạng thái hoàn tất của listener theo cơ chế được cấu hình. Nó giải quyết khía cạnh **theo dõi và phục hồi xử lý event**. Tracing bridge giải quyết khía cạnh **biến observation thành span**. Context propagation giải quyết **liên kết ngữ cảnh khi thực thi qua thread/process**.

Một lần retry sau khi ứng dụng khởi động lại có thể là một execution mới, không nhất thiết tiếp tục trace ID của HTTP request ban đầu. Khi cần liên kết lịch sử nghiệp vụ, dùng correlation ID có kiểm soát bên cạnh trace ID.

## 10. Kiểm chứng pipeline end-to-end

### 10.1. Tạo một luồng có thể tái hiện

Trong môi trường development:

1. Khởi động ứng dụng với Spring Modulith Insight Starter.
2. Chọn một tracing bridge: Brave hoặc OpenTelemetry.
3. Cấu hình exporter tới Zipkin hoặc OTLP collector.
4. Đặt sampling ở mức cao cho bài thực hành nhỏ.
5. Gửi request tạo đơn hàng có gọi qua API module `payment`.
6. Tìm trace tương ứng trên backend.
7. Xác nhận có HTTP span, module-entry span và observation nghiệp vụ nếu đã instrument.

Ví dụ gọi API minh họa:

~~~bash
curl -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"BOOK-1","quantity":1}'
~~~

Đường dẫn và payload cần điều chỉnh theo controller thực tế. Request thành công **không chứng minh** exporter đã gửi trace; hãy tìm trace trên backend hoặc kiểm tra log exporter/collector.

### 10.2. Checklist xác minh từng mắt xích

| Kiểm tra | Cách xác nhận |
| --- | --- |
| Observation được tạo | Instrumentation đã chạy; có thể kiểm tra metric hoặc custom handler trong môi trường test. |
| Tracing handler được đăng ký | Auto-configuration nhận diện tracing bridge và tạo handler phù hợp. |
| Micrometer Tracer tồn tại | Bean `Tracer` có thể inject; `currentSpan()` có giá trị trong scope thích hợp. |
| Bridge được chọn đúng | Classpath có một implementation tương ứng Brave hoặc OpenTelemetry. |
| Span được kết thúc | Observation dừng; tracing handler nhận callback stop. |
| Exporter hoạt động | Collector nhận dữ liệu, không có lỗi kết nối/xác thực. |
| Backend hiển thị trace | Tìm theo service name, trace ID hoặc thời điểm request. |
| Context được truyền | HTTP/message headers hoặc executor context được inject/extract đúng. |

### 10.3. Đối chiếu Actuator

~~~bash
# Sức khỏe ứng dụng
curl -s http://localhost:8080/actuator/health

# Cấu trúc module
curl -s http://localhost:8080/actuator/modulith

# Các meter đã đăng ký
curl -s http://localhost:8080/actuator/metrics

# Dữ liệu Prometheus nếu có registry
curl -s http://localhost:8080/actuator/prometheus
~~~

Không có endpoint mặc định `/actuator/traces` chỉ vì bridge đã được thêm. Traces được truy vấn trên backend đã cấu hình. Các endpoint Actuator cần được expose và bảo vệ đúng cách.

## 11. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Có metrics nhưng không có trace | Chỉ có metrics handler; chưa có bridge hoặc tracing handler. | Kiểm tra bridge dependency và auto-configuration. |
| Inject được `Tracer` nhưng backend trống | Thiếu exporter/reporter, sai endpoint hoặc collector không nhận. | Kiểm tra exporter dependency, URL, protocol, TLS và log exporter. |
| Trace chỉ có HTTP span | Module instrumentation chưa bật hoặc request không đi qua điểm vào API module được instrument. | Kiểm tra Insight Starter/observability-core, module boundary và đường thực thi. |
| Có module graph nhưng không có module span | Graph là cấu trúc tĩnh; trace chỉ ghi nhận lời gọi thực sự được instrument. | Gửi request qua API module và kiểm tra tracing handler. |
| Span con thành trace riêng | Parent context không được giữ hoặc không được extract đúng. | Kiểm tra scope, executor decorator, HTTP/messaging propagation. |
| Listener async chạy nhưng không cùng trace | Context không được truyền sang executor thread hoặc là lần retry khác. | Gắn ContextPropagatingTaskDecorator vào executor thực tế; dùng correlation ID cho retry. |
| Traces xuất hiện không đều | Sampling loại một phần request hoặc exporter/backend có giới hạn. | Kiểm tra sampling và chính sách thu thập. |
| Trace bị thiếu span kết thúc | Exception hoặc lifecycle quản lý span không đúng trong code thủ công. | Ưu tiên Observation API; bảo đảm scope/span luôn được đóng trong finally/try-with-resources. |
| Hai bộ bridge cùng xuất hiện | Dependency tree chứa cả Brave và OpenTelemetry bridge. | Chọn một implementation cho pipeline, loại dependency không dùng. |
| Span name/tag khác dự kiến | Convention hoặc instrumentation thay đổi, version khác nhau. | Kiểm tra ObservationConvention và schema metadata theo phiên bản. |
| Trace ID không có trong log | Logging correlation không được bật hoặc log pattern không chứa MDC key. | Kiểm tra logging integration và pattern; không tự suy luận trace không tồn tại. |

### Quy trình chẩn đoán theo thứ tự

Khi không thấy trace, kiểm tra theo chuỗi:

1. **Instrumentation:** observation có thật sự được tạo?
2. **Registry:** observation dùng đúng `ObservationRegistry` đang được cấu hình?
3. **Handler:** tracing observation handler có nhận observation?
4. **Tracer/bridge:** Micrometer Tracer và bridge implementation có được tạo?
5. **Span lifecycle:** span có được start/stop?
6. **Exporter:** span có được gửi ra collector?
7. **Backend:** backend có nhận và lưu?
8. **Propagation:** nếu trace đứt ở ranh giới, context có được inject/extract hoặc truyền qua executor?

Không thay đồng thời sampling, bridge, exporter và module instrumentation trước khi xác định mắt xích đang lỗi.

## 12. Các nguyên tắc khi triển khai production

1. **Dùng dependency management thống nhất:** để Spring Boot quản lý phiên bản Micrometer, bridge và exporter tương thích.
2. **Chọn một tracing implementation:** Brave hoặc OpenTelemetry theo hệ sinh thái backend, tránh đăng ký hai bridge cạnh tranh.
3. **Giữ instrumentation độc lập backend:** ưu tiên Observation API trong code nghiệp vụ; hạn chế gọi API vendor trực tiếp nếu không cần.
4. **Chọn sampling phù hợp:** 100% chỉ dành cho môi trường nhỏ hoặc giai đoạn điều tra có kiểm soát.
5. **Bảo vệ dữ liệu:** không đưa thông tin thanh toán, email hoặc dữ liệu cá nhân vào span attributes/baggage nếu không được phép.
6. **Quản lý cardinality:** tag metrics phải có tập giá trị nhỏ; ID duy nhất nên nằm trong traces/logs có kiểm soát.
7. **Truyền context có chủ đích:** cấu hình executor, HTTP client/server và messaging propagation ở đúng ranh giới.
8. **Không đồng nhất trace với reliability:** dùng Event Publication Registry, transaction và idempotency cho độ tin cậy xử lý event.
9. **Đối chiếu với kiến trúc:** dùng module graph và `ApplicationModules.verify()` để kiểm tra phụ thuộc, không dùng traces làm phép xác minh cấu trúc duy nhất.
10. **Đặt tên ổn định:** observation name và convention nên có quy ước để dashboard không bị vỡ khi refactor.

## 13. Bài tập thực hành

### Bài 1 — Quan sát cùng một Observation bằng metrics và tracing

Tạo observation `payment.capture` bằng `ObservationRegistry`. Chạy ứng dụng chỉ có metrics handler rồi ghi lại dữ liệu. Sau đó thêm tracing bridge và exporter, chạy lại và so sánh: observation có thể tạo timer ở lần đầu và thêm span ở lần sau. Giải thích vì sao API instrumentation không cần đổi.

### Bài 2 — So sánh Brave và OpenTelemetry bridge

Tạo hai cấu hình riêng biệt trong nhánh thử nghiệm: một dùng `micrometer-tracing-bridge-brave`, một dùng `micrometer-tracing-bridge-otel`. So sánh dependency, exporter, cách kết nối collector và trace hiển thị. Không đăng ký đồng thời cả hai bridge trong cùng một cấu hình.

### Bài 3 — Tạo trace qua ranh giới module

Gửi request `ordering → payment`, xác nhận module-entry span có `module.identifier=payment`. Đối chiếu với `/actuator/modulith` để hiểu graph tĩnh và span động khác nhau ra sao.

### Bài 4 — Tái hiện mất context

Cho `notification` xử lý `OrderPlaced` qua executor. Tạm thời bỏ task decorator trong môi trường dev, quan sát trace listener. Sau đó cấu hình `ContextPropagatingTaskDecorator` trên executor thực tế và so sánh trace ID. Ghi rõ điều kiện sampling/exporter để kết quả có thể tái hiện.

### Bài 5 — Kiểm tra exporter

Giữ instrumentation và bridge không đổi, thay endpoint collector trong một môi trường thử nghiệm. Quan sát khác biệt giữa span được tạo trong tiến trình và span backend nhận được. Mục tiêu là xác định vai trò riêng của exporter.

### Câu hỏi tự kiểm tra

**Câu 1.** Bridge từ Observation sang tracer thực hiện nhiệm vụ gì?

**Đáp án:** Tracing observation handler dùng Micrometer Tracing API để chuyển vòng đời Observation thành span; bridge implementation nối API Micrometer Tracing với Brave hoặc OpenTelemetry.

**Câu 2.** Có `ObservationRegistry` là đã có trace backend chưa?

**Đáp án:** Chưa. Cần tracing handler, tracer/bridge, exporter và backend nhận dữ liệu.

**Câu 3.** Vì sao một Observation có thể tạo metric nhưng không tạo span?

**Đáp án:** Registry có thể có metrics handler nhưng không có tracing handler/bridge phù hợp; hai loại handler độc lập.

**Câu 4.** `Propagator` có vai trò gì?

**Đáp án:** Inject trace context vào carrier ở đầu gửi và extract context ở đầu nhận để liên kết span qua ranh giới.

**Câu 5.** Spring Modulith Insight Starter có tự cung cấp Zipkin hoặc Tempo không?

**Đáp án:** Không. Starter cung cấp khả năng observability/Actuator của Spring Modulith; cần tracing bridge, exporter và backend riêng.

**Câu 6.** Khi listener async không có cùng trace ID với request gốc, nên kiểm tra điều gì?

**Đáp án:** Context propagation trên executor, task decorator, instrumentation listener, sampling và khả năng đây là lần retry mới.

## 14. Tài liệu tham khảo

- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/): Micrometer Tracing API, Brave/OpenTelemetry bridge, propagator và exporter.
- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation, ObservationRegistry, convention và handlers.
- [Micrometer Tracing — Tracer API](https://docs.micrometer.io/tracing/reference/api.html): `Tracer`, `Span`, `TraceContext` và scope.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): dependency bridge, sampling, propagation và exporter.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry và handler integration.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight Starter, module-entry spans và event metrics.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): inject/extract trace context qua ranh giới dịch vụ.

**Ghi nhớ:** Observation mô tả vùng thực thi; tracing handler chuyển vòng đời observation thành span qua Micrometer Tracing API; bridge kết nối API đó với Brave hoặc OpenTelemetry; exporter gửi span đến backend. Spring Modulith cung cấp module-entry observations, còn context propagation giúp nối chúng qua thread/process. Muốn trace hoạt động end-to-end, phải xác minh đủ **instrumentation → registry/handler → tracer/bridge → exporter → backend**.
