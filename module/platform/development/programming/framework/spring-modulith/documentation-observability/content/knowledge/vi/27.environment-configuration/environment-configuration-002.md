# Profile test với registry và exporter giả

## 1. Mục tiêu của profile kiểm thử observability

**Spring Modulith Documentation & Observability** giúp nhận diện ranh giới **application module** từ mã nguồn và theo dõi các tương tác giữa module khi ứng dụng Spring Boot vận hành. Khi kiểm thử, ta cần biết một luồng nghiệp vụ có tạo đúng **metric**, **observation**, **trace/span** và có truyền ngữ cảnh qua các ranh giới mong đợi hay không. Chỉ kiểm tra nghiệp vụ trả kết quả đúng sẽ bỏ sót các lỗi như không ghi metric, mất trace context khi đổi thread hoặc vô tình gửi telemetry từ máy chạy test đến hệ thống thật.

Bài **Profile test với registry và exporter giả**, thuộc chương **Cấu hình môi trường**, hướng dẫn tạo môi trường kiểm thử mà:

- **Spring profile** tên **test** chọn cấu hình observability dành riêng cho bài test.
- **SimpleMeterRegistry** giữ metric trong bộ nhớ để kiểm tra counter/timer và nhãn (tag) bằng assertion.
- **InMemorySpanExporter** tiếp nhận span ngay trong tiến trình test, thay cho việc xuất trace ra collector bên ngoài.
- **ObservationRegistry** tiếp tục hoạt động với handler của Micrometer và tracing bridge để test phát hiện được span thật.
- Kiểm thử module, sự kiện và context propagation có dữ liệu quan sát được, không phụ thuộc Prometheus, Grafana, Jaeger hay OpenTelemetry Collector đang chạy.

**Đầu ra cần đạt:** chạy một bài integration test với **@ActiveProfiles("test")**, gọi nghiệp vụ liên module, đọc được metric từ registry và span từ exporter giả; chứng minh có thể chạy test lặp lại, không gửi telemetry ra mạng và phân biệt lỗi của instrumentation với lỗi nghiệp vụ.

Các ví dụ dưới đây minh họa **Java 17+, Spring Boot 3.x, Spring Modulith và Micrometer Tracing dùng OpenTelemetry bridge**. Tên cấu hình export/auto-configuration có thể khác giữa các nhánh Spring Boot; luôn dùng phiên bản Spring Modulith, Micrometer và OpenTelemetry tương thích với BOM của dự án.

## 2. Phân biệt registry, observation, exporter và event publication

Khi nói đến “registry” trong hệ quan sát, cần xác định đang kiểm thử đúng thành phần.

| Thành phần | Trách nhiệm | Cách kiểm thử trong bài |
| --- | --- | --- |
| **MeterRegistry** (Micrometer Metrics) | Lưu hoặc chuyển tiếp counter, timer, gauge và các measurement. | Dùng **SimpleMeterRegistry**, đọc meter trực tiếp, không cần metrics backend. |
| **ObservationRegistry** (Micrometer Observation) | Điều phối lifecycle và handler cho observation, có thể chuyển thành metric và trace. | Giữ registry do Boot cấu hình và bảo đảm có tracing/metrics handler phù hợp. |
| **Tracer** (Micrometer Tracing) | Tạo span, quản lý span hiện hành và liên hệ ngữ cảnh truy vết. | Dùng bridge OpenTelemetry của Micrometer và SDK chạy trong test. |
| **SpanExporter** (OpenTelemetry SDK) | Nhận span đã kết thúc để xuất đến một đích. | Dùng **InMemorySpanExporter** lưu span vào bộ nhớ. |
| **Event Publication Registry** (Spring Modulith) | Ghi nhận tình trạng phát/xử lý sự kiện của application module để hỗ trợ reliability. | Kiểm thử riêng theo cấu hình lưu trữ sự kiện; **không đồng nghĩa** với MeterRegistry. |

Registry và exporter giả **không phải stub toàn bộ ứng dụng**. Logic nghiệp vụ, Spring application context, module boundaries và Micrometer API vẫn chạy; chỉ có nơi tiếp nhận dữ liệu observability được thay bằng bộ nhớ cục bộ.

~~~mermaid
flowchart LR
    T["JUnit với profile test"] --> S["OrderService"]
    S --> O["ObservationRegistry"]
    S --> M["MeterRegistry"]
    S --> E["ApplicationEventPublisher"]
    E --> L["Listener của module khác"]
    O --> B["Observation handlers / tracing bridge"]
    B --> P["SDK TracerProvider"]
    P --> X["InMemorySpanExporter"]
    M --> R["SimpleMeterRegistry"]
    X --> A["Assertion với spans"]
    R --> C["Assertion với counters/timers"]
~~~

Sơ đồ trên thể hiện trường hợp có **handler tracing được đăng ký**. Chỉ tạo **InMemorySpanExporter** mà không nối exporter vào **SdkTracerProvider** và tracing bridge sẽ cho ra danh sách span rỗng dù nghiệp vụ chạy thành công.

## 3. Kịch bản mẫu: ứng dụng có hai application module

Giả sử ứng dụng Spring Boot có package gốc **com.example.shop**, hai module logic và một phép gọi nghiệp vụ:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderService.java
│   └── OrderPlaced.java
└── fulfillment/
    └── FulfillmentListener.java
~~~

**orders** tiếp nhận lệnh đặt hàng, tăng counter và phát sự kiện **OrderPlaced**. **fulfillment** lắng nghe sự kiện đó. Trong Spring Modulith, việc đặt lớp vào package/module và công bố kiểu sự kiện qua API của module giúp công cụ nhận diện quan hệ phụ thuộc. Trong ví dụ, record **OrderPlaced** được khai báo public ở package gốc của **orders**, tức là phần API có thể được module khác sử dụng theo quy ước mặc định.

~~~java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {}
~~~

Code nghiệp vụ sẽ tự tạo một observation tên **orders.place** và một counter **orders.placed**. Hai tên này do bài thực hành đặt ra để assertion ổn định; **đây không phải tên metric/span mặc định do Spring Modulith cam kết cung cấp**.

~~~java
package com.example.shop.orders;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final MeterRegistry meters;
    private final ObservationRegistry observations;
    private final ApplicationEventPublisher events;

    public OrderService(
            MeterRegistry meters,
            ObservationRegistry observations,
            ApplicationEventPublisher events) {
        this.meters = meters;
        this.observations = observations;
        this.events = events;
    }

    public void place(String orderId) {
        Observation.createNotStarted("orders.place", observations)
                .lowCardinalityKeyValue("module", "orders")
                .observe(() -> {
                    // Trong ứng dụng thật: kiểm tra tồn kho, lưu đơn và quản lý giao dịch.
                    events.publishEvent(new OrderPlaced(orderId));

                    Counter.builder("orders.placed")
                            .tag("result", "success")
                            .register(meters)
                            .increment();
                });
    }
}
~~~

Một listener đồng bộ đơn giản để quan sát đường tương tác giữa hai module:

~~~java
package com.example.shop.fulfillment;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class FulfillmentListener {

    @EventListener
    void on(OrderPlaced event) {
        // Ví dụ: ghi nhận yêu cầu xử lý đơn event.orderId().
    }
}
~~~

**Vì sao dùng @EventListener đồng bộ trong ví dụ nền?** Bài test metric/span này tập trung vào một đường chạy có thể lặp lại, hoàn thành trước khi lời gọi **place()** trả về. Khi chuyển sang **@ApplicationModuleListener** của Spring Modulith, cần bổ sung giao dịch và cấu hình event publication phù hợp; listener thường được xử lý bất đồng bộ sau commit. Khi đó phải chờ có giới hạn và kiểm tra trạng thái event riêng, không giả định span của listener đã hoàn thành tức thì.

## 4. Chọn dependencies và phiên bản nhất quán

Ứng dụng mẫu cần Spring Boot, Spring Modulith observability, Actuator, Micrometer Tracing bridge và SDK. Trong Maven, bổ sung các dependency sau vào mục **dependencies** của dự án đã quản lý version bằng Spring Boot BOM và Spring Modulith BOM tương thích:

~~~xml
<!-- Runtime: thiết kế module, instrumentation và Actuator -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-core</artifactId>
</dependency>
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

<!-- Test: kiểm tra context, module và các span trong bộ nhớ -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-sdk-testing</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu mã test cần tham chiếu trực tiếp **SdkTracerProvider**, hãy bảo đảm **opentelemetry-sdk** có trên test classpath (có thể được kéo vào gián tiếp; khai báo trực tiếp với scope **test** nếu chưa có). **SimpleMeterRegistry** có trong **micrometer-core**, thường được Actuator/Micrometer đưa vào. Không ghim tùy tiện phiên bản OpenTelemetry SDK khác BOM chỉ để biên dịch ví dụ.

Trong môi trường production, hệ thống có thể dùng thêm **micrometer-registry-prometheus**, **micrometer-registry-otlp**, OTLP trace exporter hoặc Zipkin exporter. Các exporter mạng không cần thiết cho bài test và phải được vô hiệu hóa hoặc thay thế trong profile test. **spring-modulith-starter-observability** bổ sung khả năng quan sát tương tác module nhưng không tự biến một đơn vị test thành hệ thống tracing hoàn chỉnh nếu thiếu registry, bridge và handler.

## 5. Tách cấu hình test khỏi môi trường thật

Tạo file **src/test/resources/application-test.yml** (nằm trên test classpath):

~~~yaml
spring:
  application:
    name: modulith-shop-test

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    metrics:
      export:
        enabled: false
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Ý nghĩa của các thiết lập:

1. **@ActiveProfiles("test")** kích hoạt các thiết lập của **application-test.yml** trong bài test; profile không tự kích hoạt chỉ vì file tồn tại.
2. Sampling 100% giúp test có thể kiểm tra các span đã tạo. Đây là thiết lập **cho test**, không phải khuyến nghị sampling production.
3. Tắt xuất metrics qua OTLP theo cấu hình Spring Boot 3.x, nếu runtime có Micrometer OTLP registry. Nếu dự án có Prometheus, Zipkin hoặc trace exporter khác, cần tắt/thay đúng exporter tương ứng theo phiên bản Boot đang dùng.
4. Giới hạn endpoint Actuator được công bố qua HTTP trong test. Bài test đọc **MeterRegistry** và **InMemorySpanExporter** trực tiếp nên không cần mở endpoint **/actuator/metrics** cho Internet.

Đừng hiểu nhầm **management.tracing.enabled=false** là cách chuẩn bị bài test có span: cấu hình đó có thể loại bỏ tracing handler, khiến exporter giả luôn trống. Hãy giữ tracing được kích hoạt và thay đường xuất dữ liệu bằng giả lập.

**Lưu ý về thuộc tính theo phiên bản:** Spring Boot có những thay đổi tên property cho exporter qua các phiên bản. Nếu cấu hình của dự án dùng tên khác **management.otlp.metrics.export.enabled**, tra metadata cấu hình đúng phiên bản và xác nhận thực tế không còn exporter mạng. Test profile không phải bằng chứng rằng không có request telemetry đi ra ngoài.

## 6. Tạo test registry và in-memory span exporter

Trong **src/test/java/com/example/shop/TelemetryTestConfiguration.java**, định nghĩa các bean chỉ dành cho test. Mục đích là dùng **SimpleMeterRegistry** cho metric và nối **InMemorySpanExporter** vào **SdkTracerProvider**. Bean **OpenTelemetry** sau đó được tracing bridge sử dụng khi ứng dụng cấu hình tương thích.

~~~java
package com.example.shop;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class TelemetryTestConfiguration {

    @Bean
    @Primary
    SimpleMeterRegistry testMeterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    InMemorySpanExporter testSpanExporter() {
        return InMemorySpanExporter.create();
    }

    @Bean(destroyMethod = "close")
    SdkTracerProvider testTracerProvider(InMemorySpanExporter exporter) {
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

**SimpleMeterRegistry** lưu measurement để truy vấn bằng **registry.get(...)**, không gửi chúng đi đâu. **InMemorySpanExporter** lưu dữ liệu span đã kết thúc, có API **getFinishedSpanItems()** và **reset()**. **SimpleSpanProcessor** xuất span đồng bộ ngay khi span kết thúc; phù hợp với test nhỏ, tránh độ trễ của batch exporter. **SdkTracerProvider** được đóng khi ApplicationContext đóng.

**Điều kiện quan trọng:** cần xác minh tracing bridge thực sự sử dụng bean **OpenTelemetry** của test và **ObservationRegistry** có handler tạo span. Việc này phụ thuộc auto-configuration và classpath của phiên bản Boot đang dùng. Nếu dự án tự cấu hình **Tracer**, **OpenTelemetrySdk**, **SpanProcessor** hoặc một auto-configuration khác vẫn tạo exporter thật, phải điều chỉnh bean hoặc test configuration để chỉ giữ đường đi test mong muốn. **@Primary** chỉ quyết định ưu tiên chọn bean khi inject, không bảo đảm một exporter khác đã ngừng chạy.

Không đặt **TelemetryTestConfiguration** vào **src/main/java**: một bean giả vô tình được nạp trong production sẽ khiến trace không được chuyển đến collector thật.

## 7. Viết integration test kiểm tra metric và span thật

Tạo **src/test/java/com/example/shop/TelemetryProfileTest.java**:

~~~java
package com.example.shop;

import com.example.shop.orders.OrderService;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
@Import(TelemetryTestConfiguration.class)
class TelemetryProfileTest {

    @Autowired OrderService orders;
    @Autowired SimpleMeterRegistry metrics;
    @Autowired InMemorySpanExporter spans;

    @Test
    void capturesMetricAndSpanWithoutRemoteCollector() {
        spans.reset();

        Counter existing = metrics.find("orders.placed")
                .tag("result", "success")
                .counter();
        double before = existing == null ? 0.0 : existing.count();

        orders.place("ORD-TEST-001");

        Counter counter = metrics.get("orders.placed")
                .tag("result", "success")
                .counter();
        assertThat(counter.count()).isEqualTo(before + 1.0);

        assertThat(spans.getFinishedSpanItems())
                .anySatisfy(span ->
                        assertThat(span.getName()).isEqualTo("orders.place"));
    }
}
~~~

**Vì sao test kiểm tra cả hai?** Metric assertion chứng minh **OrderService** đã ghi số lần đặt hàng. Span assertion chứng minh **Observation** đã chạy qua tracing handler/bridge tới SDK và exporter giả. Nếu bỏ tracing bridge khỏi classpath hoặc vô tình tắt tracing bằng property, nghiệp vụ và counter có thể vẫn thành công nhưng **span assertion sẽ thất bại**. Đó là tín hiệu hữu ích để phát hiện cấu hình sai.

Test dùng **delta** thay vì bắt counter bằng 1 tuyệt đối vì cùng một ApplicationContext có thể được sử dụng cho nhiều bài test. Còn **spans.reset()** xóa dữ liệu trước lần gọi này. Nếu nhiều test chạy song song và chia sẻ context/exporter, cần tách context, dùng khóa đồng bộ hoặc gắn correlation riêng để tránh đọc chéo dữ liệu. Không chạy đồng thời các test có thao tác **reset()** trên cùng exporter.

Nếu test chỉ tạo **orders.place** bằng instrumentation thủ công, điều đó xác minh **tracing pipeline**, chưa đủ chứng minh **module-to-module spans** do Spring Modulith sinh tự động. Muốn kiểm thử span module, kích hoạt Modulith observability và đưa thêm assertion cho span tương tác **orders → fulfillment** sau khi xác minh đúng ngữ nghĩa/naming từ phiên bản đang dùng.

## 8. Kiểm thử lỗi và các tín hiệu không được giả mạo

Trong nghiệp vụ thật, nên phân biệt thành công và thất bại bằng tag hữu hạn:

~~~java
Counter.builder("orders.placed")
        .tag("result", "failure")
        .register(meters)
        .increment();
~~~

Đoạn trên chỉ dùng ở nhánh lỗi thực sự; không ghi counter thất bại khi request thành công. Một bài test bổ sung có thể truyền **orderId** không hợp lệ và assert counter **result=failure** tăng đúng một lần, exception hoặc response giữ nguyên ngữ nghĩa nghiệp vụ và span phản ánh lỗi nếu handler hỗ trợ record exception.

Các điều kiện cần phân biệt:

| Tình huống | Metric | Span | Diễn giải |
| --- | --- | --- | --- |
| Nghiệp vụ chạy đúng; registry và bridge hoạt động | Có | Có | Đường đo mẫu hoạt động. |
| Bridge tracing chưa được nạp | Có thể có | Không có | Cần kiểm tra **Tracer**, **ObservationRegistry** handler và classpath. |
| Sampling bằng 0 | Có thể có | Không được ghi/export | Test span không có giá trị; đổi sampling test về 1.0. |
| Không tạo observation trong luồng kiểm thử | Counter thủ công vẫn có thể tăng | Có thể không | Test không đi qua đoạn code có instrumentation. |
| Span chạy bất đồng bộ chưa kết thúc | Có thể có | Chưa xuất | Chờ completion có giới hạn; không kết luận mất span ngay. |
| Exporter giả được tạo nhưng không nối vào provider thực | Có | Danh sách rỗng | Kiểm tra cách Spring Boot dựng **OpenTelemetry** và span processor. |
| Có exporter thật cùng chạy | Có | Có thể có | Dù test pass, telemetry vẫn có thể bị gửi ra ngoài; kiểm tra cấu hình nguồn exporter. |

**Không mock toàn bộ MeterRegistry hoặc Tracer bằng Mockito** nếu mục tiêu là xác nhận việc đăng ký meter, tăng counter, tạo span và liên kết trace thực. Mock đơn thuần chỉ chứng minh một hàm được gọi; test với registry/exporter bộ nhớ còn xác minh dữ liệu được hệ instrumentation tạo ra.

## 9. Context propagation qua ranh giới module và thread

Với một lời gọi đồng bộ trong cùng thread, context hiện hành thường được Micrometer truy cập qua scope/thread-local. Khi event được xử lý bất đồng bộ, context không tự động chuyển sang thread khác. Nếu bỏ qua bước này, ta có thể thấy:

~~~text
HTTP request -> orders.place [trace A]
                        |
                        +-- async listener -> fulfillment [trace B độc lập]
~~~

Nếu muốn kiểm chứng đường nhân quả, cần chủ động cấu hình và test **context propagation**, hoặc dùng **eventId/correlationId** khi không thể bảo đảm trace liên tục. Với Spring Framework 6.1+ và dependency **io.micrometer:context-propagation**, có thể tạo executor mang theo ngữ cảnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncObservationConfig {

    @Bean("observedExecutor")
    TaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Bean executor chỉ có hiệu lực cho các tác vụ **thực sự chạy trên executor đó**. Với **@Async** hoặc **@ApplicationModuleListener**, phải kiểm tra executor được framework lựa chọn, transaction commit, lifecycle listener và cơ chế publication/retry. Chỉ thêm một bean mới không làm mọi listener tự động chuyển sang executor này.

Một bài test propagation có thể thực hiện các bước:

1. Mở một observation root trong **orders** và ghi lại trace ID/span ID hiện hành.
2. Gửi một tác vụ qua executor đã cấu hình, trong đó tạo observation cho **fulfillment** rồi kết thúc.
3. Chờ **Future** hoàn thành hoặc dùng **Awaitility** với timeout hữu hạn; kiểm tra exporter giả đã nhận đủ span.
4. Kiểm tra quan hệ **traceId** và **parentSpanId** hoặc span link đúng với thiết kế. Không mặc định mọi async consumer phải là child span: event qua broker/replay có thể dùng span link hay correlation ID.
5. Chạy lại với executor không propagation để xác nhận bài test thực sự có khả năng phát hiện mất context; hoàn nguyên cấu hình trước khi hoàn tất.

**Cảnh báo về kiểm thử:** thiết lập một test dùng **SimpleSpanProcessor** không bảo đảm toàn bộ pipeline production giữ context qua HTTP, messaging, transaction hoặc broker. Cần có test riêng ở ranh giới vận chuyển và kiểm tra propagation headers (chẳng hạn **traceparent**) khi đó là một phần yêu cầu hệ thống.

## 10. Quan sát module qua Spring Modulith trong profile test

**Spring Modulith** phân tích cấu trúc module từ source; quan sát runtime cho biết tương tác nào đã diễn ra trong các kịch bản kiểm thử. Hai loại dữ liệu bổ sung cho nhau:

| Loại kiểm chứng | Dụng cụ | Điều được xác nhận |
| --- | --- | --- |
| Kiến trúc module tĩnh | **ApplicationModules.of(ShopApplication.class).verify()** | Kiểm tra ranh giới và dependency được framework hỗ trợ phát hiện. |
| Sự kiện và nghiệp vụ | Test **OrderService** và listener | Event được phát và xử lý đúng cho tình huống cụ thể. |
| Counter/timer | **SimpleMeterRegistry** | Measurement được ghi với tên và tag mong đợi. |
| Trace/span | **InMemorySpanExporter** | Observation tạo span, có tên/context phù hợp và được SDK kết thúc. |
| Tương tác module runtime | Modulith observability + span/log có ngữ cảnh | Tìm bằng chứng về đường tương tác **đã thực sự chạy**; tên span phụ thuộc bản framework. |

Có thể viết một bài test kiểm tra cấu trúc source độc lập:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {
    @Test
    void respectsDeclaredModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**Documenter** của Spring Modulith có thể sinh module graph để reviewer hiểu dependency, nhưng đồ thị này là **đồ thị source**, không phải danh sách span runtime. Một dependency xuất hiện trong source mà chưa có span trong bài test có thể chỉ vì nhánh code tương ứng chưa được chạy. Ngược lại, exporter trống không có nghĩa module không tồn tại.

Với **@ApplicationModuleTest** có thể thu hẹp ApplicationContext vào một module cùng dependency được chọn, giúp test nhanh hơn. Tuy nhiên, nếu mục tiêu là kiểm tra **end-to-end** cả exporter, bridge và sự kiện liên module, một **@SpringBootTest** có cấu hình test rõ ràng thường dễ đối chiếu hơn. Có thể dùng cả hai cấp độ kiểm thử với mục tiêu khác nhau.

## 11. Tính ổn định và cô lập của test telemetry

### 11.1. Không phụ thuộc network và thời gian thực

Khi mục tiêu chỉ là kiểm tra telemetry, đừng khởi chạy collector giả bằng một cổng HTTP ngẫu nhiên nếu **InMemorySpanExporter** đã đáp ứng. Network test nên dành cho kiểm thử riêng của giao thức OTLP, retry, TLS hoặc hệ thống thu thập. In-memory exporter giúp giảm yếu tố ngẫu nhiên: timeout, cổng bị chiếm, DNS, proxy, batch flush.

Khi cần kiểm tra **khả năng gửi OTLP qua HTTP**, mock endpoint thực (ví dụ stub server) mới là công cụ thích hợp; **InMemorySpanExporter** không chứng minh payload HTTP/protobuf hay xác thực collector tương thích.

### 11.2. Giữ test cách ly

- Dùng **@ActiveProfiles("test")** và **@Import(TelemetryTestConfiguration.class)** tại test. Không kích hoạt **test** bằng biến môi trường production.
- Reset exporter trước phép đo, hoặc tạo context riêng nếu nhiều bài test dùng chung tracer.
- Khi đo counter/timer, assert **delta** hoặc dùng registry mới, không giả định thứ tự chạy test.
- Tránh sleep cố định cho listener bất đồng bộ; dùng điều kiện hoàn thành với timeout đủ rõ.
- Tránh gắn **orderId**, email, userId, traceId hay giá trị tùy ý vào metric tag vì sẽ làm tăng cardinality. Những định danh này có thể xuất hiện trong log/trace được bảo vệ và che dữ liệu khi cần.
- Đóng **SdkTracerProvider**, registry và executor khi kết thúc context để tránh thread sống nền hay tài nguyên bị giữ.

### 11.3. Kiểm tra cấu hình được chọn

Khi test bất ngờ gửi telemetry ra một endpoint thật, kiểm tra theo thứ tự:

1. Log khởi động có active profile **test** đúng không?
2. **TelemetryTestConfiguration** đã được import và các bean giả thực sự nằm trong context chưa?
3. Classpath có OTLP/Zipkin exporter khác đang tự cấu hình hay không?
4. **OpenTelemetry**, **Tracer**, **ObservationRegistry**, **MeterRegistry** đang được inject từ bean nào?
5. Tracing sampler, auto-configuration conditions và các property exporter có khớp với **phiên bản Boot đang chạy** không?

Không dựa vào mỗi việc test pass để khẳng định telemetry hoàn toàn không ra mạng. Có thể xác thực thêm bằng kiểm tra bean exporter thực được đăng ký hoặc chạy test trong môi trường chặn outbound network theo chính sách CI.

## 12. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Khả năng nguyên nhân | Cách xác minh |
| --- | --- | --- |
| **NoSuchBeanDefinitionException: MeterRegistry** | Thiếu Micrometer/Actuator hoặc test config không được import. | Kiểm tra dependency, bean **SimpleMeterRegistry** và active profile. |
| Counter luôn bằng 0 | Nghiệp vụ không chạy tới đoạn tăng counter; test truy vấn sai tên/tag hoặc registry khác. | Đối chiếu **orders.placed**, **result=success** và registry inject trong service. |
| **getFinishedSpanItems()** rỗng | Thiếu tracing bridge, handler, sampling bằng 0, exporter chưa nối provider hoặc span chưa kết thúc. | Kiểm tra **Tracer**, **ObservationRegistry**, **SdkTracerProvider** và thứ tự hoàn thành. |
| Có span nhưng sai trace ID | Đổi thread không truyền context; có nhiều root trace; retry/replay. | Kiểm tra executor, propagation, span link và correlation ID. |
| Test chậm, có timeout kết nối | Exporter mạng vẫn được cấu hình; listener chưa hoàn thành; backend chưa sẵn sàng. | Kiểm tra auto-config của exporter, mạng outbound và trạng thái listener. |
| Test qua lớp này ảnh hưởng lớp khác | Cùng context chứa registry/exporter đã lưu kết quả từ test trước. | Reset có kiểm soát, dùng delta, cô lập test chạy song song. |
| **@ApplicationModuleListener** không được gọi như dự kiến | Thiếu commit transaction, thiếu event infrastructure, handler chưa đăng ký hoặc async chưa kết thúc. | Kiểm tra transaction boundary, event publication và log/event ID. |
| Actuator có số liệu, assertion đọc sai | Có nhiều MeterRegistry/CompositeMeterRegistry hoặc tag khác nhau. | Xác định registry được service dùng và meter identity thực tế. |
| Compile lỗi trên test exporter | Lệch phiên bản OpenTelemetry hoặc thiếu **opentelemetry-sdk-testing**. | Đối chiếu dependency tree và BOM, import **InMemorySpanExporter** đúng package. |

Không nên “sửa” bài test span rỗng bằng cách bỏ assertion. Nếu mục tiêu học tập là kiểm chứng tracing, sự thất bại đó cho biết một mắt xích trong pipeline chưa được cấu hình hoặc chưa được thực thi.

## 13. Quy trình thực hành và tiêu chí hoàn thành

Thực hiện theo trình tự:

1. **Đặt baseline:** tạo hai module **orders** và **fulfillment**; cấu hình **OrderService** tạo observation **orders.place**, counter **orders.placed** và event **OrderPlaced**.
2. **Lắp observability:** thêm Actuator, Spring Modulith observability, Micrometer Tracing bridge và các test dependencies tương thích phiên bản.
3. **Tách môi trường:** đặt cấu hình trong **src/test/resources/application-test.yml**, kích hoạt bằng **@ActiveProfiles("test")**, bảo đảm exporter mạng không hoạt động trong test.
4. **Đăng ký giả lập:** tạo **SimpleMeterRegistry** và **InMemorySpanExporter**, nối exporter vào SDK tracer provider và xác minh bridge lấy đúng SDK.
5. **Chạy test:** gọi **orders.place("ORD-TEST-001")** rồi assert counter tăng đúng một đơn vị và exporter có span **orders.place**.
6. **Thử thất bại có chủ ý:** tạm ngắt tracing bridge trong môi trường test riêng để thấy test span thất bại; khôi phục và kiểm tra PASS.
7. **Mở rộng:** thay listener đồng bộ bằng async có transaction thích hợp; kiểm tra context propagation bằng trace/span IDs và theo dõi event publication tới completion.
8. **Xác nhận module boundary:** dùng **ApplicationModules.verify()** và, nếu cần, Documenter để so quan hệ source với đường tương tác đã được đo trong test.

### Mẫu bảng bằng chứng

| Nội dung | Bằng chứng minh họa | Kỳ vọng |
| --- | --- | --- |
| Active profile | **test** | Đúng |
| Metric | **orders.placed{result="success"}** | Tăng 1 sau mỗi lần gọi thành công |
| Observation | **orders.place** | Bắt đầu và kết thúc trong lời gọi mẫu |
| Trace exporter | **InMemorySpanExporter** | Có span đã kết thúc, không đòi collector ngoài |
| Module interaction | **orders → fulfillment** | Có bằng chứng sau khi listener thực sự chạy |
| Source boundary | **ApplicationModules.verify()** | Không có vi phạm theo quy tắc đã khai báo |
| Network telemetry | Không đăng ký exporter mạng trong test | Không có đường xuất ra collector thật |

Các dòng trên là **kỳ vọng của bài thực hành**, không phải kết quả từ một ứng dụng đã chạy. Khi nộp bài, điền số liệu assertion/test output thực tế và mô tả nếu một span không được ghi do thiếu instrumentation hoặc sampling.

### Câu hỏi tự kiểm tra

1. Vì sao **SimpleMeterRegistry** kiểm được số counter nhưng không tự ghi lại span?
2. Tại sao tạo bean **InMemorySpanExporter** vẫn có thể không thu được span?
3. Sự khác nhau giữa **ObservationRegistry**, **MeterRegistry** và **Event Publication Registry** của Spring Modulith là gì?
4. Vì sao **management.tracing.enabled=false** có thể khiến test kiểm tra tracing thất bại?
5. Vì sao **@ActiveProfiles("test")** và **@TestConfiguration** đều cần được cấu hình rõ?
6. Khi dùng **@ApplicationModuleListener**, tại sao phải cân nhắc transaction commit, async completion và propagation?
7. Test với exporter trong bộ nhớ chứng minh điều gì, và còn thiếu kiểm thử nào trước khi kết luận hệ thống OTLP production hoạt động?

**Kết quả cần nộp:** profile **test** độc lập, cấu hình registry và exporter giả, test assertion có metric/span thực được lưu trong bộ nhớ, minh chứng kiểm tra ranh giới module, và ghi chú xử lý async/context propagation. Qua đó, Spring Modulith Documentation & Observability có thể được kiểm chứng lặp lại từ môi trường test mà vẫn giữ được ý nghĩa của module graph, Actuator, event metrics và tracing trong ứng dụng Spring Boot.
