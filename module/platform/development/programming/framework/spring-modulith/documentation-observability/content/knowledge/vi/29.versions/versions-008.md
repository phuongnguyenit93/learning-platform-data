# Kiểm tra thay đổi Micrometer hoặc tracer bridge

## 1. Mục tiêu và bài toán

Trong một ứng dụng Spring Boot dùng **Spring Modulith**, mã nguồn định nghĩa các **application module** và ranh giới phụ thuộc; còn **Micrometer**, **Actuator** và hệ thống tracing cung cấp bằng chứng về tương tác giữa các module trong lúc vận hành. Sau khi nâng cấp Spring Boot, Spring Modulith, Micrometer hoặc chuyển **tracer bridge** từ Brave sang OpenTelemetry (hay ngược lại), nghiệp vụ có thể vẫn thành công nhưng metric biến mất, span đổi tên, listener bất đồng bộ mất trace ID hoặc dashboard không còn nối các thao tác với nhau.

Bài **Kiểm tra thay đổi Micrometer hoặc tracer bridge** thuộc chương **Phiên bản** của **Spring Modulith Documentation & Observability** giúp xác định sự cố thuộc tầng dependency, instrumentation, propagation hay xuất telemetry. Trọng tâm là **đối chiếu trước/sau bằng chứng có thể tái hiện**, gồm module graph, Actuator, event metrics, tracing và context propagation.

Sau bài học, bạn có thể:

1. Ghi lại bộ phiên bản trước và sau nâng cấp bằng dependency tree thực sự được resolve.
2. Phân biệt **MeterRegistry**, **ObservationRegistry**, **Micrometer Tracing**, bridge và exporter.
3. Viết canary test kiểm tra counter, active span và dữ liệu span sau export.
4. Kiểm tra việc truyền context qua HTTP, **@Async**, event sau commit và retry.
5. Đối chiếu module graph của source với runtime evidence mà không nhầm quan hệ phụ thuộc với luồng event.
6. Đề xuất rollout và rollback dựa trên kiểm thử tương thích thay vì chỉ dựa vào việc ứng dụng khởi động được.

Ví dụ minh họa sử dụng hệ sinh thái **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Modulith và Micrometer Tracing**. Số minor/patch của các thư viện thay đổi theo bản Spring Boot/BOM; khi thực hành cần tra **bảng tương thích và release notes đúng phiên bản dự án**, không mặc định một con số là bản mới nhất.

## 2. Đọc đúng kiến trúc observability

Các thành phần liên quan có chức năng khác nhau:

| Thành phần | Vai trò | Dấu hiệu thay đổi phiên bản |
| --- | --- | --- |
| **Spring Modulith core/docs/test** | Phân tích application module, kiểm tra ranh giới, xuất module graph. | Module được phát hiện khác, đồ thị phụ thuộc hoặc kết quả verify đổi. |
| **Spring Modulith observability** | Tích hợp quan sát tương tác module vào hạ tầng Micrometer. | Thiếu hoặc đổi observation/span của tương tác liên module. |
| **Micrometer Observation** | Quản lý observation, lifecycle, context và handler. | Có observation nhưng không được chuyển sang metric/span như trước. |
| **Micrometer Core** | API meter, counter/timer/gauge và **MeterRegistry**. | Tên meter, measurement hoặc tag thay đổi. |
| **Micrometer Tracing** | Abstraction **Tracer**, **Span**, scope và propagation. | Current span, trace ID hoặc parent/link không như kỳ vọng. |
| **Tracer bridge** | **micrometer-tracing-bridge-otel** hoặc **micrometer-tracing-bridge-brave**. | Tracer sử dụng backend/scope/propagator khác. |
| **SDK và exporter** | OpenTelemetry SDK/SpanExporter hoặc Brave reporter; chuyển span đến backend. | Span đã tạo nhưng không đến collector. |
| **Context propagation** | Chụp/khôi phục ngữ cảnh khi đổi thread; inject/extract qua HTTP hoặc message. | Listener có trace độc lập, MDC mất dữ liệu. |
| **Actuator** | Công bố health, metrics và metadata tùy cấu hình/endpoint. | Endpoint, quyền truy cập hoặc cấu hình exposure đổi. |

~~~mermaid
flowchart TD
    M["Module interaction / HTTP / event"] --> O["Micrometer ObservationRegistry"]
    O --> MH["Metrics ObservationHandler"]
    O --> TH["Tracing ObservationHandler"]
    MH --> MR["MeterRegistry"]
    MR --> ME["Metrics exporter / SimpleMeterRegistry"]
    TH --> TR["Micrometer Tracer"]
    TR --> B{"Tracer bridge"}
    B --> OT["OpenTelemetry SDK"]
    B --> BR["Brave"]
    OT --> OE["OTLP / in-memory SpanExporter"]
    BR --> BE["Zipkin/Brave reporter"]
    CP["Context propagation"] --> O
    CP --> TR
~~~

**Điều quan trọng:** bridge chỉ kết nối abstraction Micrometer Tracing với hệ tracing cụ thể. Bridge **không** đồng nghĩa với exporter; việc có bridge trên classpath chưa chứng minh span được xuất. Tương tự, Spring Modulith có thể sinh module graph chính xác nhưng không có runtime trace nếu không instrument hoặc không kết nối tracing pipeline.

Đổi bridge cũng không tự động chuyển đổi reporter của hệ trước: đường truyền span của Brave và **SpanExporter** của OpenTelemetry là các cơ chế riêng. Không nên để cả hai bridge trên runtime classpath như một dạng “dự phòng”.

## 3. Tạo baseline có thể đối chiếu

Trước khi thay dependency, chụp thông tin của đúng **artifact đang chạy**. Cùng một tên service trên dashboard có thể đại diện cho nhiều bản deploy, nhiều profile và nhiều mức sampling.

| Nhóm | Trước khi đổi | Sau khi đổi | Cách xác minh |
| --- | --- | --- | --- |
| Build | Git revision, build ID, Java, Boot, Modulith | Revision và BOM đích | So đúng artifact và thời gian deploy. |
| Classpath | Micrometer Core/Observation/Tracing, bridge, SDK, exporter | Bộ resolved mới | Dependency tree, effective build. |
| Cấu hình | Profile, sampling, propagation, exporter address | Cấu hình thực nhận | Startup logs và bean/property thực. |
| Module source | ApplicationModules.verify() và module graph | Kết quả cùng loại | Đánh giá vi phạm boundary riêng biệt. |
| Metrics | Tên, tags, giá trị counter/timer | Tên/tags/measurement mới | Canh cùng một kịch bản và số lần gọi. |
| Tracing | TraceId, spanId, parentSpanId/link, tên span | Raw span từ bản mới | Đọc exporter/test collector, lưu ý sampling. |
| Event | Event ID, consumer, trạng thái và số lần retry | Tình trạng sau nâng cấp | Đối chiếu event publication và nghiệp vụ. |
| HTTP/message | Headers phát ra và nhận vào | Headers thực tế | Kiểm tra W3C/B3 và carrier. |

Một mẫu ghi nhận dành cho test:

~~~text
scenario: POST /orders -> publish OrderPlaced -> billing listener
source_revision: <commit-thuc-te>
runtime_revision: <commit-thuc-te>
runtime_profile: integration
sampling: 1.0 (chỉ cho test)
bridge: otel
metric: orders.placed{result="success"}
span: orders.place -> billing.on-event
event_outcome: billing đã xử lý xong
trace_evidence: <trace-id-hoac-link-tu-test>
~~~

Các chuỗi trên là ví dụ định dạng, không phải dữ liệu đã thu thập. Nếu dashboard không thấy span do sampling hoặc retention, ghi **chưa có bằng chứng**; không tự kết luận lời gọi giữa các module không tồn tại.

## 4. Quản lý tương thích phiên bản và dependency

### 4.1. Dùng BOM phù hợp

**Spring Boot BOM** thường quản lý các dependency Micrometer và OpenTelemetry liên quan; **Spring Modulith BOM** quản lý hệ artifact Modulith. Chọn Modulith BOM theo **ma trận tương thích với Spring Boot** của dự án, tránh override từng thư viện độc lập mà chưa kiểm tra kết quả.

Ví dụ phần dependency Maven dưới đây giả định dự án đã có Boot parent hoặc đã import Boot BOM, đồng thời khai báo property version cho Modulith trong cấu hình build:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>CHOOSE_COMPATIBLE_MODULITH_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
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
</dependencies>
~~~

**CHOOSE_COMPATIBLE_MODULITH_VERSION** là chỗ cần thay bằng version hợp lệ đã được kiểm chứng, không phải một version có thật để copy chạy nguyên xi. Nếu chọn Brave, thay bằng **micrometer-tracing-bridge-brave** và cấu hình tracing backend tương ứng. Không kéo cả hai bridge vào production để “so sánh tự động”.

### 4.2. Kiểm tra dependency resolved

Trong dự án Maven hoặc Gradle, có thể tự chạy các lệnh thích hợp:

~~~bash
./mvnw dependency:tree -Dverbose
./mvnw help:effective-pom
~~~

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opentelemetry --configuration runtimeClasspath
~~~

Lưu **dependency tree trước/sau** để reviewer kiểm tra các điểm:

- **micrometer-core**, **micrometer-observation** và **micrometer-tracing** được giải quyết theo các bản tương thích; không có override cũ bất ngờ.
- Bridge OTel/Brave phù hợp với **micrometer-tracing** đang dùng.
- OpenTelemetry API, SDK và exporters không bị trộn các nhánh version do dependency truyền tiếp.
- Starter Spring Modulith observability tương thích với Spring Framework/Boot.
- Có **io.micrometer:context-propagation** nếu code cần snapshot/restore context qua executor.
- Không có bridge thừa hoặc hai SDK/reporter sản xuất span vào hai đường không chủ ý.
- Dependency test như **opentelemetry-sdk-testing** không bị đưa vào production classpath.

**Compile PASS chưa đủ**: lỗi **NoSuchMethodError**, thiếu handler hoặc mất parent trace có thể chỉ xuất hiện khi chạy. Nếu chủ động override một version vì bảo mật, ghi lại phạm vi override và chạy toàn bộ test tương thích của đường observability.

## 5. Lỗi điển hình sau khi đổi tracer bridge

| Trường hợp | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Có counter, không có span | Tracing handler không đăng ký, bridge thiếu, sampling hoặc exporter sai. | Canary Observation + currentSpan + exporter in-memory. |
| Span có trong process nhưng dashboard trống | OTLP/Zipkin endpoint, TLS, auth, collector, sampling hoặc retention. | Xem SDK/exporter logs và test collector. |
| Có hai bean Tracer hoặc SDK | Bridge hoặc auto-configuration trùng, custom bean và starter cùng tạo pipeline. | Kiểm tra bean definitions và dependency tree. |
| HTTP service B tạo trace mới | Producer inject W3C nhưng consumer chỉ đọc B3, hoặc thiếu header. | Capture headers và cấu hình propagator hai đầu. |
| @Async listener tạo trace mới | Executor không khôi phục context; task submit ngoài scope. | Ghi current span ở submit/đầu listener, kiểm tra executor. |
| MDC có traceId nhưng span không nối | Chỉ copy MDC string, không chuyển Micrometer/OpenTelemetry context. | Kiểm tra **Tracer.currentSpan()** và span thật. |
| Span/timer đổi tên hoặc tags khác | Observation convention/instrumentation thay phiên bản. | So raw span attributes/meter IDs, kiểm tra migration notes. |
| Event retry tạo nhiều span | At-least-once delivery, listener nhiều attempt hoặc replay. | Theo dõi **eventId + consumer + attempt** và publication status. |

Khi chuyển Brave sang OTel, cần kiểm tra cả **sampler**, **propagator** và **reporter/exporter**. Chỉ thay Maven artifact bridge mà giữ nguyên cấu hình exporter của hệ cũ có thể khiến ứng dụng sinh span nhưng không còn gửi được tới backend.

## 6. Canh một phép đo có tên ổn định để test hồi quy

Trước khi dựa vào các span tự động của Spring Modulith (có thể đổi naming giữa phiên bản), hãy viết một **canary** chủ động tạo observation và counter trong module **orders**.

~~~java
package com.example.shop.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Service;

@Service
public class ObservationProbe {
    private final MeterRegistry meters;
    private final ObservationRegistry observations;
    private final Tracer tracer;

    public ObservationProbe(MeterRegistry meters,
                            ObservationRegistry observations,
                            Tracer tracer) {
        this.meters = meters;
        this.observations = observations;
        this.tracer = tracer;
    }

    public String record() {
        AtomicReference<String> traceId = new AtomicReference<>();

        Observation.createNotStarted("orders.probe", observations)
                .lowCardinalityKeyValue("module", "orders")
                .observe(() -> {
                    meters.counter("orders.probe.calls",
                            "module", "orders",
                            "result", "success").increment();

                    Span current = tracer.currentSpan();
                    traceId.set(current == null
                            ? null
                            : current.context().traceId());
                });

        return traceId.get();
    }
}
~~~

**orders.probe.calls** là counter tăng bằng code. **orders.probe** là observation được Micrometer xử lý bằng các handler đã đăng ký. Nếu tracing handler và bridge hoạt động, observation có thể tạo span; **currentSpan()** trong observation phải cho thấy context span hoạt động. Nếu counter tăng nhưng **traceId == null**, trước tiên xem lại tracing handler và bridge, chưa vội sửa Spring Modulith.

Một observation cũng có thể được metrics handler ghi timer theo convention. **Counter thủ công** và **timer observation** là hai measurement khác nhau; đừng áp đặt giả định rằng mỗi observation tự động tạo một counter cùng tên.

Đặc biệt, tránh đưa **orderId**, **traceId**, email hoặc eventId vào metric tags: chúng có cardinality cao. Dùng các tag hữu hạn như **module**, **operation** và **result**; định danh tương quan nên đặt trong trace/log được bảo vệ.

## 7. Integration test với exporter giả của OpenTelemetry

Với phương án **micrometer-tracing-bridge-otel**, test có thể dùng **InMemorySpanExporter** để xác nhận span thực được kết thúc và xuất trong bộ nhớ, không phụ thuộc collector ngoài. Với Brave, cần dùng test span handler phù hợp của Brave; **InMemorySpanExporter** không tự nhận span từ một pipeline Brave.

Trong test classpath, cần **spring-boot-starter-test**, **opentelemetry-sdk-testing**, và **opentelemetry-sdk** phiên bản tương thích. Ví dụ cấu hình test:

~~~java
package com.example.shop;

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
class InMemoryTracingConfig {

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
    OpenTelemetry openTelemetry(SdkTracerProvider provider) {
        return OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build();
    }
}
~~~

Một bài kiểm thử gọi probe:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.orders.ObservationProbe;
import io.micrometer.core.instrument.MeterRegistry;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@Import(InMemoryTracingConfig.class)
class TracerBridgeRegressionTest {

    @Autowired ObservationProbe probe;
    @Autowired MeterRegistry metrics;
    @Autowired InMemorySpanExporter spans;

    @Test
    void recordsMetricAndFinishedSpan() {
        spans.reset();

        var previous = metrics.find("orders.probe.calls")
                .tags("module", "orders", "result", "success")
                .counter();
        double before = previous == null ? 0.0 : previous.count();

        String traceId = probe.record();

        assertThat(metrics.get("orders.probe.calls")
                .tags("module", "orders", "result", "success")
                .counter().count()).isEqualTo(before + 1.0);
        assertThat(traceId).isNotBlank();

        assertThat(spans.getFinishedSpanItems())
                .anySatisfy(span -> {
                    assertThat(span.getName()).isEqualTo("orders.probe");
                    assertThat(span.getTraceId()).isEqualTo(traceId);
                });
    }
}
~~~

Trong **src/test/resources/application-test.yml**, có thể cho phép sampling 100%:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

**Điều kiện bắt buộc của test:** **ObservationRegistry** phải có tracing observation handler; Micrometer bridge phải dùng **chính OpenTelemetry SDK** đã nối với exporter giả. **@Primary** chỉ giúp ưu tiên bean lúc inject, không tự tắt exporter mạng hoặc sửa mọi auto-configuration khi tồn tại nhiều SDK. Hãy kiểm tra bean thực tế và vô hiệu hóa exporter thật trong profile test theo đúng property của phiên bản Boot đang dùng.

**SimpleSpanProcessor** xuất ngay khi span kết thúc, phù hợp với canary đồng bộ. Với listener bất đồng bộ, đợi task hoàn tất bằng condition và timeout rõ ràng. Không chạy song song các test cùng reset một exporter in-memory vì có thể xóa span của test khác.

Canary này xác minh đường **Observation → Tracer/bridge → exporter**, chưa chứng minh các span tự sinh liên module của Spring Modulith hay giao thức OTLP qua HTTP. Cần các bài test riêng cho những điểm đó.

## 8. Kiểm tra context propagation khi nâng cấp

### 8.1. Qua HTTP và messaging

Hai đầu giao tiếp phải hiểu định dạng propagation thực tế. Các định dạng phổ biến:

| Định dạng | Header quan trọng | Lỗi cần thử |
| --- | --- | --- |
| **W3C Trace Context** | **traceparent**, có thể **tracestate** | Producer gửi nhưng consumer không extract hoặc proxy làm mất header. |
| **B3 single** | **b3** | Consumer chỉ đọc B3 multi hoặc W3C. |
| **B3 multi** | **X-B3-TraceId**, **X-B3-SpanId** và các header liên quan | Một số header bị chặn hoặc không đồng bộ. |
| **Baggage** | Theo convention của tracing stack | Giá trị cần truyền bị mất hoặc truyền quá nhiều dữ liệu nhạy cảm. |

Ví dụ request W3C hợp lệ về mặt cấu trúc:

~~~http
POST /api/orders HTTP/1.1
Host: shop.example.test
Content-Type: application/json
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

{"orderId":"ORD-TEST-001"}
~~~

Sau đổi bridge, kiểm tra header **đã phát** trên HTTP/message và **header đã nhận** ở consumer. Không suy ra định dạng mặc định từ tên bridge: cấu hình propagator, phiên bản Spring Boot, instrumentation và các client/server library cùng quyết định. Nếu cần hỗ trợ W3C và B3 trong thời gian chuyển đổi, xác minh khả năng nhận/ghi của cả hai đầu bằng integration test.

### 8.2. Qua executor và event async

Với cùng một process, context hiện hành thường gắn với scope/thread. Khi **@Async** chạy trên thread khác, **ThreadLocal không tự sao chép**. Spring Framework 6.1+ và **io.micrometer:context-propagation** hỗ trợ **ContextPropagatingTaskDecorator**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class ModuleAsyncConfig {
    @Bean("moduleEventExecutor")
    ThreadPoolTaskExecutor moduleEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setThreadNamePrefix("module-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Listener minh họa:

~~~java
@Async("moduleEventExecutor")
@EventListener
public void on(OrderPlaced event) {
    // Tạo observation trong listener; so traceId với publisher.
}
~~~

Phải đặt method listener trong bean Spring và import các annotation tương ứng. **Decorator chỉ áp dụng cho task đi qua executor này**. Nếu Spring Modulith **@ApplicationModuleListener** dùng executor khác, khai báo bean trên chưa khắc phục được gì.

Sự kiện xử lý **sau transaction commit** cũng cần đánh giá khác: context của observation publisher có thể đã rời scope trước khi callback submit task. Decorator chỉ chuyển context còn hiện hành lúc submit; nó không thể tái tạo parent đã mất. Với event qua broker, retry/replay sau restart, cần truyền context bằng message headers hoặc dùng span link/correlation ID theo chính sách.

Khi kịch bản đơn giản submit task lúc span publisher còn active, assert:

~~~text
publisher.traceId == listener.traceId
listener.parentSpanId == publisher.spanId
~~~

Nếu có span trung gian, after-commit callback hoặc messaging, parent trực tiếp có thể khác. Có thể kiểm chứng **ancestor, span links hoặc correlation ID** phù hợp thay vì ép mọi event thành child trực tiếp của HTTP request.

**Lưu ý:** sao chép **MDC** có thể làm traceId hiện trong log nhưng không khôi phục span scope. Kiểm tra **Tracer.currentSpan()** và span đã export để xác nhận propagation thực.

## 9. Spring Modulith module graph và event metrics sau thay đổi

Đồ thị module source và dữ liệu runtime không mang cùng ý nghĩa:

~~~text
Source:  billing --(tham chiếu OrderPlaced)--> orders
Runtime: orders --(publish OrderPlaced)--> billing
Tracing: orders.place --> billing.on-event (nếu có context/link)
~~~

Hai mũi tên source/runtime có thể ngược chiều vì một bên biểu diễn **dependency kiểu Java**, một bên biểu diễn **luồng event**. Đừng coi đó là architecture drift.

Kiểm tra source bằng **ApplicationModules**:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {
    @Test
    void checksDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nếu dự án dùng **Documenter** để sinh module graph hoặc Actuator để hiển thị metadata module, hãy tạo bản chụp **cùng revision đang chạy**. **ApplicationModules.verify()** PASS chỉ nói các quy tắc ranh giới source được thỏa mãn, chưa chứng minh span runtime có được tạo/export.

Để kiểm tra event sau nâng cấp, so dữ liệu nghiệp vụ và event publication registry (khi dự án cấu hình), đối chiếu **eventId + consumer + attempt + status**. Một event có thể đến nhiều consumer, một consumer có thể retry, nên số lượng publication không đương nhiên bằng số span/timer của listener. Thiếu span cũng không chứng minh event không được giao.

Nếu tên observation/span nội bộ của Spring Modulith đổi giữa phiên bản, nên xác minh contract của bản mới trước khi cập nhật dashboard hoặc test. Không khóa ứng dụng vào tên implementation detail nếu tên đó không được cam kết ổn định; ưu tiên evidence về module identity, trace linkage, outcome và lượng event phù hợp.

## 10. Triage theo triệu chứng

| Triệu chứng | Cần kiểm tra đầu tiên |
| --- | --- |
| **NoClassDefFoundError** hoặc **NoSuchMethodError** | Dependency resolved/BOM; trộn version Micrometer hoặc SDK. |
| Counter vẫn có, timer observation mất | Metrics observation handler và meter convention. |
| Metric vẫn có, span trống | Tracing handler, bridge, sampler, SDK và exporter. |
| Canary có span, collector không nhận | URL/protocol/auth/TLS, OTLP/Zipkin reporter, network, sampling/retention. |
| HTTP client và server có hai traceId | Trace headers, W3C/B3 propagator và instrumentation của cả hai đầu. |
| Listener @Async có traceId mới | Executor thực tế, ContextPropagatingTaskDecorator và thời điểm submit. |
| Listener sau commit có root span mới | Scope publisher hết trước callback; chọn linkage phù hợp với lifecycle. |
| Log có traceId nhưng span không có | MDC được copy độc lập, sampling hoặc bridge chưa nối. |
| Dashboard mất metric sau nâng version | Tên/tag/đơn vị meter đổi, dashboard filter hoặc exporter. |
| Graph module khác nhưng nghiệp vụ không đổi | So source revision, quy tắc phát hiện module và named interfaces. |
| Event metrics có nhưng thiếu span | Listener có chạy không, instrumentation có tạo span không, exporter/sampling ra sao. |

Quy trình điều tra từ trong ra ngoài:

1. **Nghiệp vụ:** request và event có thực sự chạy? Listener xử lý thành công, retry hay còn pending?
2. **Instrumentation:** observation và span có được tạo/kết thúc ở process không?
3. **Registry/bridge:** **MeterRegistry**, **ObservationRegistry**, **Tracer** và SDK nào đang được inject?
4. **Propagation:** context có sẵn khi submit/extract qua thread/HTTP/message không?
5. **Export:** exporter có gửi đúng và collector nhận được không?
6. **Hiển thị:** dashboard query, filter, sampling, tag, retention và quyền truy cập có còn phù hợp không?

Không sửa bằng cách bỏ assertion span hoặc bật sampling production 100% vô thời hạn. Mỗi thay đổi cần chứng minh chính xác tầng nào đã được khôi phục.

## 11. Ma trận nghiệm thu và kế hoạch rollback

| Kịch bản | Bằng chứng trước/sau | Kỳ vọng |
| --- | --- | --- |
| Canary đồng bộ | Counter, current traceId, in-memory finished span | Cả metric và tracing pipeline hoạt động. |
| HTTP inbound/outbound | Captured propagation headers, server trace | Hai đầu liên kết đúng theo chuẩn đã chọn. |
| Event giữa module | Publication/handler status, observation/span | Event xử lý đúng và có evidence runtime. |
| Async executor | Thread, trace ID, parent/link | Context được bảo toàn ở task thực sự chạy. |
| After-commit/replay | Event ID, attempt, span links/correlation | Liên kết nhân quả đúng với lifecycle. |
| Module source | ApplicationModules.verify(), Documenter graph | Ranh giới được kiểm chứng trên cùng revision. |
| Collector thật | Exporter logs, span/metric ở test collector | Giao thức, TLS/auth và endpoint hoạt động. |

Thực hiện thay đổi có kiểm soát:

1. Lưu **baseline** dependency tree, active profile, cấu hình, module graph, metric/span và trạng thái event.
2. Chọn version Spring Boot/Modulith/Micrometer theo BOM và release/migration notes đúng bản đích.
3. Chỉ thay đổi **một nhóm lớn mỗi lượt** (ví dụ nâng BOM trước, đổi bridge sau) để xác định nguyên nhân nếu regression xuất hiện.
4. Loại bridge/exporter cũ không còn dùng, kiểm tra resolved classpath.
5. Chạy canary, architecture test, async/event test và integration test đến collector test.
6. So raw metrics/spans, tên/tag, propagation headers, kết quả xử lý event và chi phí/cardinality.
7. Deploy ở staging hoặc canary với sampling, retention và giới hạn an toàn.
8. Nếu fail, rollback **artifact và cấu hình tương thích đã được xác nhận**, không chỉ hạ version một thư viện bất kỳ.

Mẫu báo cáo review:

~~~text
Application revision: <git-commit>
Before Boot/Modulith/Micrometer BOMs: <versions>
After Boot/Modulith/Micrometer BOMs: <versions>
Before tracer bridge: <otel|brave>
After tracer bridge: <otel|brave>
Sampling and propagation: <settings>
Canary metric/span: PASS|FAIL, <evidence>
Async and HTTP context: PASS|FAIL, <trace/header evidence>
Module graph verification: PASS|FAIL, <test report>
Event delivery: PASS|FAIL, <publication evidence>
Collector integration: PASS|FAIL, <test collector evidence>
Remaining gaps: <not instrumented|not observed|not yet verified>
Rollback artifact/config: <known-good reference>
~~~

Khi thu thập bằng chứng, che dữ liệu người dùng và bí mật trong header/log; kiểm soát quyền truy cập trace và thời gian lưu. Không đưa traceId/eventId/orderId vào metric tags làm tăng cardinality.

## 12. Bài tập và câu hỏi tự kiểm tra

### Thực hành

1. Lấy resolved dependency tree của một dự án Spring Boot + Spring Modulith. Ghi rõ phiên bản **micrometer-core**, **micrometer-observation**, **micrometer-tracing**, bridge và SDK/exporter.
2. Viết **ObservationProbe** trong module orders. Dùng profile **test**, **SimpleMeterRegistry** và **InMemorySpanExporter** để kiểm tra counter và span.
3. Trong một nhánh test cô lập, thử làm thiếu tracing handler/bridge và quan sát counter vẫn có nhưng span fail. Khôi phục cấu hình đúng.
4. Dùng **@Async** listener, ghi trace ID trước/sau khi gắn context decorator vào đúng executor; so parent/link.
5. Thử một HTTP client gửi **traceparent** cho consumer và xác minh khả năng extract; sau đó kiểm tra tình huống consumer dùng định dạng propagation khác.
6. Cho listener xử lý sau commit hoặc thử lại event; phân biệt event delivery và trace linkage, ghi lại event ID và attempt.
7. Sinh module graph, chạy **ApplicationModules.verify()**, đối chiếu graph source với evidence runtime của đúng revision.
8. Lập bảng nghiệm thu và rollback nếu đổi từ Brave sang OpenTelemetry bridge.

### Tự kiểm tra

- **Micrometer Observation**, **MeterRegistry** và **Micrometer Tracing** khác nhau ở đâu?
- Bridge có thay thế cho SDK/exporter không? Làm sao biết tracer nào thực sự được dùng?
- Vì sao counter tăng nhưng không có span sau nâng cấp?
- Khi đổi từ B3 sang W3C Trace Context, phải kiểm tra điều gì ở producer và consumer?
- Vì sao chỉ sao chép MDC chưa đủ để nối trace qua executor?
- Vì sao event xử lý sau commit hoặc replay không nhất thiết là child trực tiếp của HTTP span?
- Tại sao module graph đúng không chứng minh exporter đang hoạt động?
- Vì sao dependency tree và runtime artifact quan trọng hơn chỉ xem version khai báo?

**Kết quả cần nộp:** bảng phiên bản và dependency trước/sau, canary metric/span, kiểm thử context qua HTTP và async event, module graph và kiểm tra boundary, bằng chứng xuất tới collector test, cùng quyết định rollout/rollback. Cách tiếp cận này giúp **Spring Modulith Documentation & Observability** tiếp tục phản ánh đúng ranh giới application module và các tương tác thực tế khi Micrometer hoặc tracer bridge thay đổi.
