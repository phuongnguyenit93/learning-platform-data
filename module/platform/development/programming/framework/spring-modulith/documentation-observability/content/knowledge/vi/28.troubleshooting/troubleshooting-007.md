# Event async không nối được trace

## 1. Triệu chứng và phạm vi chẩn đoán

Ứng dụng Spring Boot dùng **Spring Modulith** để tách các **application module** theo ranh giới nghiệp vụ. Module **orders** phát sự kiện **OrderPlaced**; module **billing** xử lý sự kiện bằng listener bất đồng bộ. Nghiệp vụ vẫn chạy đúng, nhưng trên hệ thống tracing xuất hiện hai trace độc lập:

~~~text
Trace A — HTTP POST /orders
└── orders.place
    └── publish OrderPlaced

Trace B — không có parent từ Trace A
└── billing.onOrderPlaced
~~~

Khi điều tra từ request đặt hàng, người vận hành không tìm thấy bước xử lý của **billing**, dù listener đã hoàn tất. Log có thể cũng mất **traceId** sau khi chuyển sang thread khác. Đây là tình huống **“Event async không nối được trace”** của chương **Chẩn đoán lỗi**.

Trong **Spring Modulith Documentation & Observability**, cần phân biệt ba vấn đề:

1. **Kiến trúc module:** module nào phát, nhận sự kiện và được phép phụ thuộc module nào. **ApplicationModules** và tài liệu module graph trả lời câu hỏi này từ source.
2. **Event delivery:** sự kiện có được phát, giao tới listener, hoàn thành, thất bại hoặc được phát lại không. Cơ chế sự kiện của Spring/Spring Modulith, event publication registry và dữ liệu nghiệp vụ giúp kiểm chứng.
3. **Tracing:** observation/span của lời gọi phát và xử lý event có nằm trong cùng trace hoặc được liên kết bằng **span link/correlation ID** hay không. Micrometer Observation, Micrometer Tracing, OpenTelemetry và context propagation giải quyết phần này.

**Mất liên kết trace không đồng nghĩa mất event**; ngược lại, thấy hai span trong một trace cũng chưa chứng minh giao dịch nghiệp vụ thành công. Bài học hướng dẫn xác minh từng tầng, xác định lúc context bị mất, sửa đường truyền context phù hợp và viết test có thể tái hiện.

Sau bài này, bạn có thể xác định liệu lỗi nằm ở sampling/exporter, thiếu instrumentation, đổi thread, callback sau commit, retry sau khi khởi động lại hay ranh giới messaging; cấu hình executor có context propagation; đọc trace tree đúng và kiểm thử kết quả trước/sau khi sửa.

**Phạm vi ví dụ:** Java 17+, Spring Boot 3.x, Spring Framework 6.1+ khi dùng **ContextPropagatingTaskDecorator**, Spring Modulith và Micrometer Tracing tích hợp OpenTelemetry. API và tên property có thể thay đổi theo BOM và phiên bản cụ thể của dự án.

## 2. Trace, span và context khác nhau thế nào?

Một **trace** mô tả quan hệ nhân quả giữa các thao tác. Mỗi **span** có **traceId**, **spanId** và có thể có **parentSpanId**. **Trace context** chứa thông tin về span hiện hành, sampling và các trường truyền liên quan. Trong OpenTelemetry, context có thể được gắn vào một scope để các thao tác kế tiếp trở thành span con hoặc span được liên kết thích hợp.

| Dữ liệu | Vai trò | Điều thường gây nhầm lẫn |
| --- | --- | --- |
| **traceId** | Nhận diện một trace. | Hai span cùng traceId chưa chắc có quan hệ parent-child trực tiếp. |
| **spanId** | Nhận diện một span. | Khác traceId; không dùng spanId thay cho correlation ID nghiệp vụ. |
| **parentSpanId** | Cho biết span cha trực tiếp, nếu có. | Qua messaging bất đồng bộ, hệ thống có thể dùng span link thay cho parent. |
| **ObservationRegistry** | Quản lý observation và các handler trong Micrometer. | Tạo observation không tự bảo đảm có span nếu thiếu tracing handler/bridge. |
| **MeterRegistry** | Lưu và xuất counter, timer, gauge. | Metric có giá trị không có nghĩa trace được tạo hoặc nối thành công. |
| **Trace context propagation** | Chuyển context sang thread/process/message khác. | Chỉ copy MDC/log variables không tự truyền OpenTelemetry context. |
| **Event publication registry** | Theo dõi publication và xử lý sự kiện theo cơ chế Spring Modulith được cấu hình. | Không phải một tracing exporter và không tự phục hồi ThreadLocal context sau restart. |

Micrometer Tracing thường quản lý span hiện hành qua một cơ chế scope gắn với luồng xử lý; đồng thời hệ quan sát có thể liên kết với OpenTelemetry context. **ThreadLocal ở thread gửi không tự xuất hiện trong thread listener**. Khi công việc được đưa vào executor, thông tin cần được chụp tại **thời điểm submit** và khôi phục khi task chạy, hoặc cần được truyền tường minh bằng carrier (message headers/event metadata) nếu qua hàng đợi hay xử lý lại sau này.

### Sơ đồ hai đường đi

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP client
    participant O as orders
    participant X as Executor
    participant B as billing listener
    participant T as Tracing SDK
    C->>O: POST /orders
    O->>T: Bắt đầu span orders.place (Trace A)
    O->>X: Submit task xử lý OrderPlaced
    Note over O,X: Chụp observation/trace context khi submit
    X->>B: Thực thi task trên thread khác
    B->>T: Bắt đầu span billing.onEvent
    Note over B,T: Có context: cùng Trace A<br/>Thiếu context: trace root mới
    B-->>X: Xử lý xong
    O-->>C: Kết quả đặt hàng
~~~

Trong bài test listener đồng bộ, việc không đổi thread có thể khiến mọi thứ đúng, rồi lỗi chỉ xuất hiện khi triển khai **@Async**, **@ApplicationModuleListener**, executor pool hoặc broker. Vì vậy phải tái hiện đúng đường dispatch đang dùng ở runtime.

## 3. Nhận diện điểm đứt qua một ví dụ Spring Modulith

Giả sử package gốc là **com.example.shop**, có hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderService.java
│   └── OrderPlaced.java
└── billing/
    └── BillingEventListener.java
~~~

Event contract nên được công bố ở API hợp lệ của module **orders**, ví dụ:

~~~java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {}
~~~

Đoạn minh họa sau tạo observation có tên ổn định ở publisher:

~~~java
package com.example.shop.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;
    private final ObservationRegistry observations;

    public OrderService(ApplicationEventPublisher events,
                        ObservationRegistry observations) {
        this.events = events;
        this.observations = observations;
    }

    public void place(String orderId) {
        Observation.createNotStarted("orders.place", observations)
                .lowCardinalityKeyValue("module", "orders")
                .observe(() -> events.publishEvent(new OrderPlaced(orderId)));
    }
}
~~~

Đây là ví dụ không dùng giao dịch để cô lập lỗi đổi thread. Bài production có lưu đơn hàng và giao dịch cần điều chỉnh điểm phát event/transaction cho phù hợp.

Listener có observation riêng để đo được thao tác thực hiện:

~~~java
package com.example.shop.billing;

import com.example.shop.orders.OrderPlaced;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class BillingEventListener {

    private final ObservationRegistry observations;

    public BillingEventListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @Async("moduleEventExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        Observation.createNotStarted("billing.on-order-placed", observations)
                .lowCardinalityKeyValue("module", "billing")
                .observe(() -> {
                    // Xử lý thanh toán, ghi dữ liệu, phát event tiếp theo...
                });
    }
}
~~~

**Hai observation này chỉ tạo span khi tracing handler được kết nối đúng với ObservationRegistry.** Tên **orders.place** và **billing.on-order-placed** là tên bài thực hành tự đặt, không phải tên span cố định của mọi phiên bản Spring Modulith.

Trong ví dụ trên, điểm quan trọng là đoạn **submit task** nằm bên trong observation **orders.place**. Nếu task được thực thi bởi executor chưa truyền context, listener vẫn xử lý event nhưng span mới có thể trở thành root của trace B.

Với **@ApplicationModuleListener** của Spring Modulith, ngữ nghĩa có thể bao gồm xử lý sau khi transaction commit và bất đồng bộ, thường kết hợp với cơ chế event publication. Đừng suy luận rằng thay **@EventListener** bằng annotation đó vẫn giữ nguyên thời điểm submit: **callback sau commit có thể được kích hoạt khi observation gốc đã kết thúc**. Cần chẩn đoán riêng trường hợp này ở mục 7.

## 4. Triage trước khi sửa code

Trước khi thay executor, kiểm tra xem dữ liệu trace đã được tạo và xuất thành công chưa. Một checklist chẩn đoán:

| Triệu chứng quan sát | Khả năng chính | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| **Không có span ở cả orders lẫn billing** | Chưa bật tracing, thiếu Micrometer bridge/handler, sampler bỏ trace hoặc exporter sai. | Classpath, ObservationRegistry, sampling, exporter và log tự cấu hình. |
| **Có span orders, không có span billing** | Listener chưa chạy, thiếu instrumentation, span chưa kết thúc hoặc sampling/export lỗi. | Event publication, log vào listener, observation lifecycle, exporter. |
| **Có hai traceId khác nhau** | Mất context khi chuyển thread, sau commit, qua broker hoặc retry/replay. | Executor thực tế, thời điểm submit, transaction/event metadata. |
| **Cùng traceId nhưng parentSpanId không như mong đợi** | Có span trung gian hoặc mô hình async dùng link thay cho parent. | Trace tree đầy đủ, span links, thời điểm bắt đầu và SpanKind. |
| **Log mất traceId nhưng trace vẫn nối được** | MDC/log correlation cấu hình thiếu hoặc log ở ngoài active scope. | MDC bridge, log pattern và scope của logging. |
| **Metrics có, spans trống** | MeterRegistry hoạt động nhưng tracing handler/exporter chưa hoạt động. | Đường Observation → Tracer → SpanProcessor → Exporter. |
| **Chỉ mất trace sau restart/retry** | Context gốc ở memory không còn; event được xử lý lại trong lượt chạy mới. | Publication ID, attempt, thời gian event, persisted headers. |

Một quy trình 10 phút trong môi trường kiểm thử:

1. Chọn **một** sự kiện có mã tương quan (event ID hoặc order ID dùng riêng trong log/trace, không gắn vào metric tags).
2. Xác nhận publisher đã thực sự phát event; ghi thời điểm, active thread và traceId nếu có.
3. Kiểm tra listener được gọi **mấy lần**, ở thread nào, vào thời điểm nào, có đang retry hay không.
4. Tìm span và traceId tại **đầu** và **cuối** listener, rồi đối chiếu với publisher.
5. Kiểm tra **sampler/exporter** trước khi kết luận span không được tạo.
6. Nếu context mất, tìm ranh giới chính xác: submit executor, transaction commit, message hop, replay hoặc khởi động lại.

Nên ghi **application version/commit**, active profile, trace sampling và khoảng thời gian kiểm tra. Một trace export của phiên bản cũ không nên được đối chiếu với module graph của bản source mới rồi kết luận kiến trúc thay đổi.

## 5. Kiểm tra cấu hình observability cơ bản

Ứng dụng cần thành phần Spring Modulith và Micrometer tương thích với BOM. Các dependency thường gặp trong dự án Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-observability</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>context-propagation</artifactId>
</dependency>
~~~

Tracing còn cần một SDK và exporter/collector phù hợp (ví dụ OpenTelemetry SDK cùng OTLP exporter). **spring-modulith-starter-observability** giúp instrument tương tác module; riêng starter không bảo đảm trace đến backend nếu thiếu tracing bridge, exporter hoặc cấu hình bắt buộc.

Trong profile kiểm thử, có thể bật sampling 100%:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Thiết lập này giúp giảm khả năng không thấy span do sampling. Tuy nhiên, sampling 100% **không tự tạo span** nếu thiếu observation/tracing handler. Không xem sampling 100% là mặc định nên giữ trong production: khối lượng telemetry và chi phí có thể tăng lớn.

**Actuator** hữu ích để xác minh health, metrics và metadata module tùy cấu hình. **Endpoint cung cấp module graph không phải đồ thị các lời gọi đã chạy**; muốn nhìn cạnh runtime cần spans, observation hoặc event evidence. Việc không thấy module **billing** trong dashboard trace chưa đủ chứng minh module đó không nhận event.

### Log điều tra không làm tăng cardinality metric

Khi tái hiện, thêm log ở điểm phát và điểm nhận với các trường **eventId, threadName, traceId, spanId, timestamp**. Định danh nghiệp vụ và traceId chỉ nên nằm trong log/trace có kiểm soát quyền truy cập và thời gian lưu; **không đưa orderId, eventId, traceId vào metric tag**. Tag metric nên dùng giá trị hữu hạn như **module=orders**, **operation=place**, **result=success**.

MDC từ SLF4J có thể rỗng khi chưa cấu hình logging correlation; có thể đọc trace/span hiện hành qua Micrometer Tracer khi cần xác minh gốc:

~~~java
// Chỉ là đoạn kiểm tra chẩn đoán; Tracer đến từ Micrometer Tracing.
Span current = tracer.currentSpan();
if (current != null) {
    log.info("traceId={}, spanId={}, thread={}",
            current.context().traceId(),
            current.context().spanId(),
            Thread.currentThread().getName());
} else {
    log.info("No current span, thread={}", Thread.currentThread().getName());
}
~~~

Import tương ứng: **io.micrometer.tracing.Tracer** và **io.micrometer.tracing.Span**. Log có **traceId** bằng cách copy một chuỗi thủ công vẫn không chứng minh span hiện hành đã được truyền; phải kiểm tra **tracer.currentSpan()** hoặc dữ liệu exporter.

## 6. Khắc phục khi điểm đứt là chuyển thread bằng @Async

Với Spring Framework 6.1+, **ContextPropagatingTaskDecorator** có thể chụp và khôi phục ngữ cảnh Micrometer trên task được submit qua **ThreadPoolTaskExecutor**. Tạo executor dành cho đường async event:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncEventConfig {

    @Bean("moduleEventExecutor")
    public ThreadPoolTaskExecutor moduleEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("module-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Listener ví dụ ở mục 3 dùng **@Async("moduleEventExecutor")**, vì vậy task sẽ đi qua đúng executor này. Khi **orders.place** còn active tại thời điểm submit, decorator chụp context và khôi phục trong thread listener; observation **billing.on-order-placed** có thể nối về span cha phù hợp.

**Điểm kiểm tra quan trọng:** thêm bean executor mới **không** tự động làm tất cả listener dùng nó. Cần kiểm tra annotation **@Async** có qualifier nào, Spring async infrastructure chọn executor nào, có custom **AsyncConfigurer** hay không, và task thực sự được dispatch qua **ThreadPoolTaskExecutor** này. Nếu có nhiều executor, ghi nhận thread name ở listener để đối chiếu.

Trong Spring Modulith, **@ApplicationModuleListener** có thể sử dụng async executor mặc định khi annotation không chỉ định executor. Nếu ứng dụng dùng annotation này, hãy xác minh default executor theo **AsyncConfigurer** hoặc cấu hình async Spring thực tế. Có thể định nghĩa **AsyncConfigurer#getAsyncExecutor()** để trả về executor có decorator; chỉ làm vậy khi đã xem xét ảnh hưởng tới các tác vụ **@Async** khác trong cùng ứng dụng.

Chẳng hạn cấu hình dùng chung executor làm mặc định cho async:

~~~java
// Đặt hai method sau trong @Configuration @EnableAsync ở trên;
// thêm "implements AsyncConfigurer" vào khai báo class.

@Override
public java.util.concurrent.Executor getAsyncExecutor() {
    return moduleEventExecutor();
}
~~~

Import thêm **org.springframework.scheduling.annotation.AsyncConfigurer**. Với **@Configuration** mặc định **proxyBeanMethods=true**, lời gọi tới **@Bean** method trong cùng class trả về bean được Spring quản lý. Nếu chuyển sang **proxyBeanMethods=false** thì không nên gọi trực tiếp bean factory method từ **getAsyncExecutor()**, vì dễ tạo executor thứ hai không được quản lý; hãy inject bean hiện có theo một cấu hình phù hợp.

Khi decorator hoạt động, vẫn cần phân biệt **span là parent-child** hay **span được liên kết qua link**. Tác vụ được thực thi muộn không có nghĩa nó phải đóng trước HTTP request. Một span được xuất sau span cha vẫn có thể có cùng traceId; quan hệ nhân quả phải được đọc từ context/links, không suy từ thứ tự timestamp.

### Đừng xem sao chép MDC là sửa tracing

Có ứng dụng dùng **TaskDecorator** tùy chỉnh để copy **MDC.getCopyOfContextMap()** từ thread nguồn sang thread đích. Cách này có thể làm log hiện lại **traceId** dạng chuỗi, nhưng chưa chắc khôi phục scope của Micrometer Tracer/OpenTelemetry. Sau khi sửa phải kiểm tra **span trong exporter** thực sự cùng trace hoặc có span link; chỉ nhìn log pattern là chưa đủ.

## 7. Trường hợp khó: listener sau commit, phát lại và khởi động lại

Spring Modulith thường dùng listener nghiệp vụ có ngữ nghĩa **xử lý sau khi transaction commit**. Ví dụ:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    // Xử lý event sau commit theo cơ chế của Spring Modulith.
}
~~~

Code trên minh họa cách dùng annotation trong một bean listener; cần import **org.springframework.modulith.events.ApplicationModuleListener** và đảm bảo cấu hình transaction, event publication theo phiên bản đang dùng.

Với listener sau commit, trình tự có thể như sau:

~~~mermaid
sequenceDiagram
    participant H as HTTP request
    participant S as Service/Transaction
    participant A as Async listener
    participant R as Event publication registry
    H->>S: begin transaction
    S->>S: publish OrderPlaced
    S->>S: kết thúc đoạn observation ban đầu
    S->>S: commit transaction
    S->>R: publication được theo dõi nếu bật registry
    S-->>A: dispatch callback sau commit
    Note over S,A: Parent context có thể không còn active
    A->>A: xử lý event/retry
~~~

Trong tình huống này, **decorator chỉ chuyển được context thực sự hiện hành tại lúc task được submit**. Nếu observation gốc đã đóng trước khi callback sau commit submit task, decorator không thể tái tạo một parent span đã bị mất khỏi scope.

Các lựa chọn thiết kế:

1. **Muốn thấy quan hệ nhân quả trong cùng lần chạy:** giữ một observation bao quanh thời điểm dispatch sau commit nếu hợp lý với lifecycle, hoặc truyền context tường minh theo cơ chế hỗ trợ của hệ event. Không kéo dài transaction hay span vô hạn chỉ để dashboard đẹp.
2. **Có message broker, queue hoặc event replay:** ghi context trong **message headers/event envelope** tại điểm phát; ở consumer, extract context và tạo span xử lý. Dùng **W3C Trace Context** (ví dụ **traceparent**, có thể thêm **tracestate**) nếu tracing stack hỗ trợ. Cần xác minh giá trị header đúng tại cả producer và consumer.
3. **Consumer được chạy lại sau một giờ hoặc sau restart:** không còn ThreadLocal của publisher. Có thể tạo trace mới và liên kết về trace trước bằng **span link** hoặc **event/correlation ID**, tùy chính sách tracing. Không bắt buộc mọi retry phải có parent-child trực tiếp với HTTP span cũ.
4. **Dùng event publication registry:** theo dõi publication ID, trạng thái hoàn thành/chưa hoàn thành, số lần thử lại và lỗi listener để điều tra delivery. Registry không tự bảo đảm context propagation qua thời gian hoặc qua process.

**Không lưu vô điều kiện toàn bộ tracing baggage** vào payload sự kiện: có thể chứa dữ liệu nhạy cảm và khiến message phình to. Chọn một tập thông tin truyền tối thiểu, ràng buộc kích thước, làm sạch dữ liệu không đáng tin và tuân thủ chuẩn/header mà các hệ thống liên quan chấp nhận.

Một ví dụ cấp khái niệm về carrier khi tích hợp OpenTelemetry trực tiếp:

~~~java
// Producer: inject W3C context khi span gốc còn current.
Map<String, String> headers = new HashMap<>();
openTelemetry.getPropagators()
        .getTextMapPropagator()
        .inject(
                io.opentelemetry.context.Context.current(),
                headers,
                (carrier, key, value) -> carrier.put(key, value)
        );
// Gửi headers cùng message/event envelope.

// Consumer: extract vào scope trước khi tạo span xử lý.
io.opentelemetry.context.Context extracted =
        openTelemetry.getPropagators().getTextMapPropagator()
                .extract(
                        io.opentelemetry.context.Context.root(),
                        receivedHeaders,
                        (carrier, key) -> carrier.get(key)
                );
try (io.opentelemetry.context.Scope scope = extracted.makeCurrent()) {
    // Bắt đầu span xử lý event bằng SDK/bridge tương thích.
}
~~~

Đoạn này minh họa nguyên tắc inject/extract, **không phải mẫu thay thế hoàn chỉnh cho Spring Modulith event infrastructure**. Nó cần một **OpenTelemetry** đã cấu hình W3C propagator, import **Map/HashMap**, loại message/header hợp lệ, và quy tắc tạo observation/span nhất quán với Micrometer Tracing đang dùng. Nếu dùng framework messaging có built-in instrumentation, ưu tiên cấu hình propagation của framework và kiểm thử headers thay vì viết một cơ chế song song gây double-span.

## 8. Kiểm thử tự động bằng exporter trong bộ nhớ

Một bài test tracing nên xác nhận chính **traceId/parentSpanId/span links** của các span đã hoàn thành, thay vì chỉ kiểm tra **@EventListener** được gọi. Với OpenTelemetry bridge có thể dùng **InMemorySpanExporter** từ **opentelemetry-sdk-testing**, nối vào **SdkTracerProvider** và cấu hình Micrometer Tracing sử dụng đúng provider đó.

Cấu hình test dành riêng cho profile **test**:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class TraceTestConfiguration {

    @Bean
    InMemorySpanExporter spanExporter() {
        return InMemorySpanExporter.create();
    }

    @Bean(destroyMethod = "close")
    SdkTracerProvider tracerProvider(InMemorySpanExporter exporter) {
        return SdkTracerProvider.builder()
                .setSampler(Sampler.alwaysOn())
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
    }

    @Bean
    @Primary
    OpenTelemetry testOpenTelemetry(SdkTracerProvider provider) {
        return OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build();
    }
}
~~~

Các class đến từ **org.springframework.boot.test.context.TestConfiguration**, **org.springframework.context.annotation.Bean/Primary**, **io.opentelemetry.api.OpenTelemetry**, **io.opentelemetry.sdk.OpenTelemetrySdk**, **io.opentelemetry.sdk.trace.SdkTracerProvider**, **io.opentelemetry.sdk.trace.export.SimpleSpanProcessor**, **io.opentelemetry.sdk.trace.samplers.Sampler** và **io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter**.

Trong cấu hình thực tế, phải bảo đảm **ObservationRegistry → Micrometer Tracing bridge → chính SdkTracerProvider của test**. Chỉ đăng ký exporter nhưng vẫn dùng tracer/provider production có thể làm test rỗng hoặc gửi dữ liệu ra collector thật. Tắt các exporter mạng khác trong profile test theo đúng phiên bản Boot; **@Primary** không tự vô hiệu hóa mọi export pipeline.

Một bài test dùng **Awaitility** để chờ listener hoàn thành, với timeout hữu hạn:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@Import(TraceTestConfiguration.class)
class AsyncEventTraceTest {

    @Autowired OrderService orders;
    @Autowired InMemorySpanExporter exporter;

    @Test
    void listenerSpanKeepsTraceContext() {
        exporter.reset();
        orders.place("ORD-TEST-1");

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            var finished = exporter.getFinishedSpanItems();
            assertThat(finished).anyMatch(s -> s.getName().equals("orders.place"));
            assertThat(finished).anyMatch(
                    s -> s.getName().equals("billing.on-order-placed"));
        });

        var spans = exporter.getFinishedSpanItems();
        var parent = spans.stream()
                .filter(s -> s.getName().equals("orders.place"))
                .findFirst().orElseThrow();
        var child = spans.stream()
                .filter(s -> s.getName().equals("billing.on-order-placed"))
                .findFirst().orElseThrow();

        assertThat(child.getTraceId()).isEqualTo(parent.getTraceId());
        // Trong topology đơn giản này, kỳ vọng parent trực tiếp:
        assertThat(child.getParentSpanId()).isEqualTo(parent.getSpanId());
    }
}
~~~

Các import chính gồm **@SpringBootTest**, **@ActiveProfiles**, **@Import**, **@Autowired**, **@Test**, **Duration**, AssertJ **assertThat** và static **org.awaitility.Awaitility.await**. Nếu chưa có, thêm dependency test **org.awaitility:awaitility** (Spring Boot starter test thường cung cấp thư viện này theo nhánh phiên bản). Mẫu dự kiến dùng **@EventListener + @Async("moduleEventExecutor")**, event được submit trong scope publisher và tracing bridge đã bật.

**Không áp dụng nguyên xi assertion parent trực tiếp** khi listener thực thi qua **@TransactionalEventListener AFTER_COMMIT**, broker, retry sau restart hoặc có span trung gian; trong các hệ đó, kiểm tra cùng traceId hoặc **span links/correlation ID** đúng thiết kế. Khi nhiều event chạy song song, gắn mã tương quan có kiểm soát hoặc cô lập test, tránh chọn nhầm hai span cùng tên thuộc những request khác nhau.

### Kiểm thử trước/sau để chứng minh sửa đúng lỗi

Một phép thử có giá trị là:

1. Dùng executor **không có** context decorator trong profile test cô lập. Kiểm tra listener vẫn chạy nhưng hai span có trace khác nhau, nếu môi trường tracer tạo root mới đúng như kỳ vọng.
2. Bật **ContextPropagatingTaskDecorator** cho chính executor listener sử dụng.
3. Chạy lại **cùng một kịch bản**, cùng sampling và cùng exporter, xác nhận span được nối đúng.
4. Thử trường hợp sau commit hoặc replay và ghi nhận kỳ vọng riêng (parent, link hoặc correlation). Không lẫn điều kiện của test thread-hop đơn giản với event delivery bền vững.

Nếu lỗi chỉ xuất hiện trong production, bổ sung integration test trên hạ tầng async/messaging tương đương. Test dùng in-memory exporter không chứng minh collector OTLP qua mạng đã hoạt động, nhưng kiểm chứng tốt phần instrumentation và nối context trong tiến trình.

## 9. Phân biệt lỗi event delivery và lỗi quan sát

Không có span không đủ để kết luận listener chưa xử lý. Trong Spring Modulith, một sự kiện có thể đi qua transaction, publication registry, listener bất đồng bộ, retry và replay. Cần đối chiếu với kết quả nghiệp vụ:

| Bằng chứng | Có ý nghĩa gì? | Chưa thể kết luận |
| --- | --- | --- |
| Đơn hàng được tạo | Publisher xử lý lưu dữ liệu ban đầu. | Listener đã nhận event hay chưa. |
| Publication được ghi nhận | Cơ chế publication theo dõi sự kiện (nếu được bật). | Handler đã hoàn thành thành công hay chưa. |
| Publication còn outstanding | Có thể chưa được xử lý xong hoặc lỗi cần retry, tùy cơ chế. | Trace mất liên kết là nguyên nhân duy nhất. |
| Listener log “done” | Code listener đi qua một điểm đã log. | Transaction downstream đã commit hay span đã export. |
| Exporter có span | Instrumentation có đo một thao tác. | Business outcome đúng hoặc event chỉ xử lý đúng một lần. |
| Counter event tăng | Metric được ghi với tag tương ứng. | Số event duy nhất; retry/fan-out có thể làm số lần xử lý lớn hơn số publication. |

Ở hệ thống **at-least-once delivery**, listener cần cơ chế **idempotency** theo eventId/nghiệp vụ. Việc “nối trace” không được dùng để che giấu xử lý trùng, rollback hoặc publication còn pending.

## 10. Khi cả trace và module graph không khớp

**Spring Modulith** có thể sinh tài liệu về package/module boundaries và dependency từ mã nguồn; thông tin quan sát runtime cho thấy đường tương tác được thực thi. Khi module **billing** lắng nghe **OrderPlaced** do **orders** công bố, đồ thị dependency kiểu có thể thể hiện **billing → orders**, trong khi luồng sự kiện runtime là **orders → billing**. Đây là hai quan hệ khác loại, không mặc nhiên có lỗi.

Ví dụ:

~~~text
Source dependency: billing --(import OrderPlaced)--> orders
Runtime event flow: orders --(publish OrderPlaced)--> billing
Runtime trace:      orders.place --> billing.on-order-placed  [nếu có context]
~~~

Nếu Runtime trace là hai cây độc lập, chỉ có thể kết luận **trong tập dữ liệu đang xem, liên kết tracing chưa thể hiện hoặc chưa được thu thập**. Kiểm tra sampling, event execution, span links và nguồn dữ liệu trước khi gọi đó là architecture drift.

Chạy kiểm tra module boundaries để tách lỗi cấu trúc source khỏi lỗi quan sát:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {
    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ApplicationModules.verify()** có thể phát hiện các dạng vi phạm dependency được Spring Modulith hỗ trợ kiểm tra, nhưng không kiểm tra trace/span của một event đã thực thi. Ngược lại, test exporter chỉ kiểm tra luồng thực tế được chạy và instrument; không thay thế module graph hoặc quy tắc source.

## 11. Checklist khắc phục trong môi trường vận hành

| Bước | Việc cần làm | Tiêu chí xác nhận |
| --- | --- | --- |
| 1. Chọn sự kiện | Xác định eventId, commit/build, thời gian, profile và listener. | Có thể truy vết đúng một lượt xử lý, kể cả retry. |
| 2. Xác minh delivery | So publisher, listener, event publication status và kết quả nghiệp vụ. | Biết rõ event chạy hay chưa và chạy ở đâu. |
| 3. Xác minh spans | Kiểm tra sampling, instrumentation, Micrometer bridge, exporter, retention. | Biết span thiếu do không tạo hay không được export. |
| 4. Xác định ranh giới | So thread/executor, transaction commit, broker hoặc replay. | Tìm được thời điểm current context biến mất. |
| 5. Sửa propagation | Decorate đúng executor hoặc truyền carrier qua message; giữ span links khi cần. | Listener thấy context mong đợi trong kịch bản tái hiện. |
| 6. Kiểm thử | Bắt event, chờ completion, so traceId/parent/link và kết quả nghiệp vụ. | Test có thể phát hiện lỗi cũ và pass sau sửa. |
| 7. Đối chiếu kiến trúc | Dùng module graph và module boundary test. | Luồng đã quan sát tuân thủ hợp đồng module. |
| 8. Quan sát sau triển khai | Theo dõi lỗi listener, retry/pending, span export và trace correlation. | Có bằng chứng ở cùng bản triển khai, không tăng lộ dữ liệu nhạy cảm. |

**Các lỗi cần tránh khi sửa:**

- Cố bật tracing bằng cách chỉ thêm prefix **traceId** vào log, mà không truyền span context.
- Thêm một **ContextPropagatingTaskDecorator** nhưng listener lại chạy trên executor khác.
- Cho rằng callback **sau commit** vẫn giữ nguyên current span tại thời điểm service phát sự kiện.
- Đòi parent-child trực tiếp cho mọi event đã qua message broker hoặc xử lý lại sau restart; có trường hợp span link/correlation phù hợp hơn.
- Tăng sampling production lên 100% vô thời hạn để “chữa” mất trace.
- Đưa eventId/orderId/traceId vào metric tags làm tăng cardinality và chi phí.
- Tắt event publication registry hoặc bỏ retry khi thấy trace tách, khiến độ tin cậy nghiệp vụ suy giảm.

## 12. Bài tập thực hành

Thực hiện lần lượt, lưu kết quả test hoặc log/trace đã che dữ liệu nhạy cảm:

1. Tạo module **orders** phát **OrderPlaced** và module **billing** có **@EventListener + @Async**. Thêm observation **orders.place** và **billing.on-order-placed**. Với exporter trong bộ nhớ, ghi lại traceId/spanId của hai span.
2. Dùng executor chưa cấu hình propagation và chụp bằng chứng hai trace bị tách (nếu tracing SDK tạo span riêng). Xác minh nghiệp vụ vẫn hoàn thành.
3. Gắn **ContextPropagatingTaskDecorator** cho executor đang dùng; so sánh trace tree và assertion của test trước/sau.
4. Đổi sang listener có xử lý sau commit bằng Spring Modulith. Tìm thời điểm transaction callback được dispatch; quan sát xem decorator có còn context để chụp hay không.
5. Mô phỏng listener xử lý lại sau khi producer hoàn thành hoặc sau restart. Đề xuất một cách liên kết bằng message headers, span link hoặc correlation ID mà không dựa vào ThreadLocal cũ.
6. Tạo tình huống listener thất bại một lần rồi retry; kiểm tra trạng thái publication, số lượt xử lý và cơ chế idempotency. Đánh giá trace giữa các attempt.
7. Sinh module graph và chạy **ApplicationModules.verify()**. Chỉ ra khác biệt giữa cạnh **billing → orders** (dependency kiểu) và cạnh **orders → billing** (event flow).

### Câu hỏi tự kiểm tra

1. Vì sao listener chạy thành công nhưng span xuất hiện trong trace khác?
2. **MDC**, **ObservationRegistry**, **Tracer** và **SpanExporter** khác vai trò như thế nào?
3. Context decorator phải được gắn vào executor nào, và vì sao thời điểm **submit** quan trọng?
4. Vì sao listener sau commit có thể mất context dù dùng decorator đúng?
5. Trường hợp retry/replay sau restart nên xem xét **span link** hoặc correlation ID khi nào?
6. Cách phân biệt **span chưa export**, **span không được tạo** và **event chưa được giao**?
7. Một module graph đúng có chứng minh trace runtime đã nối thành công không?

**Kết quả cần nộp:** sơ đồ publisher/listener và ranh giới async, bảng bằng chứng delivery và trace trước/sau, cấu hình executor thực sự được sử dụng, bài test kiểm tra traceId/parent hoặc links theo đúng ngữ nghĩa, cùng ghi chú về after-commit/retry/replay. Khi đó, **Spring Modulith Documentation & Observability** giúp đối chiếu kiến trúc mô-đun với hành vi quan sát được, còn **context propagation** giúp những tương tác async được kết nối đúng về mặt tracing mà không đánh đồng telemetry với độ tin cậy xử lý sự kiện.
