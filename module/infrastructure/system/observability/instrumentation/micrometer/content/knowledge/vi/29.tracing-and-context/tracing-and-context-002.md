# Bridge cho OpenTelemetry hoặc Brave và quản lý phiên bản tương thích

Micrometer Tracing cung cấp API thống nhất để ứng dụng tạo và quản lý trace, span, baggage và context. API này không tự quyết định thư viện tracing cụ thể hoặc nơi lưu span. Một bridge kết nối API Micrometer với tracer implementation như Brave hoặc OpenTelemetry; exporter/reporter chịu trách nhiệm gửi span đến hệ thống nhận.

Khi tích hợp, cần chọn đúng một bridge làm implementation chính, chọn exporter tương ứng và để dependency management quản lý các phiên bản tương thích. Trộn nhiều bridge hoặc tự override từng thư viện tracing dễ gây xung đột bean, lỗi nạp class và lỗi runtime như NoSuchMethodError.

## 1. Ba lớp trong kiến trúc Micrometer Tracing

Ba thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Micrometer Tracing API | API mà code ứng dụng dùng để tạo span, lấy current span, thêm tag và quản lý baggage | Tracer, Span, BaggageManager |
| Bridge | Chuyển API Micrometer sang tracer implementation | micrometer-tracing-bridge-brave, micrometer-tracing-bridge-otel |
| Exporter/reporter | Đưa span đã kết thúc đến backend hoặc collector | Zipkin reporter, OpenTelemetry OTLP exporter |

Luồng dữ liệu:

~~~mermaid
flowchart LR
    A["Application code / Observation"] --> B["Micrometer Tracing API"]
    B --> C{"Bridge được chọn"}
    C --> D["Brave tracer"]
    C --> E["OpenTelemetry tracer"]
    D --> F["Zipkin reporter"]
    E --> G["OTLP exporter"]
    F --> H["Zipkin / Collector"]
    G --> H
    H --> I["Tracing backend"]
~~~

Bridge không đồng nghĩa với exporter. Thêm bridge giúp Micrometer nói chuyện với tracer implementation; ứng dụng vẫn cần reporter/exporter hoặc cấu hình auto-configuration để span đến được backend.

Tương tự, exporter không thay thế bridge. Exporter biết cách gửi span theo giao thức của backend, còn bridge cung cấp implementation cho API tracing mà Micrometer sử dụng.

## 2. Chọn Brave hay OpenTelemetry

Micrometer Tracing hỗ trợ nhiều tracer implementation. Hai lựa chọn phổ biến là Brave và OpenTelemetry.

| Tiêu chí | Brave bridge | OpenTelemetry bridge |
| --- | --- | --- |
| Artifact bridge | micrometer-tracing-bridge-brave | micrometer-tracing-bridge-otel |
| Tracer implementation | Brave | OpenTelemetry SDK |
| Hệ sinh thái thường gặp | Zipkin, B3 propagation và các tích hợp Brave | OpenTelemetry API/SDK, OTLP, Collector và nhiều exporter |
| Reporter/exporter phổ biến | Zipkin Reporter | OTLP exporter |
| Phù hợp khi | Hệ thống đang dùng Brave/Zipkin và muốn tiếp tục tương thích | Hệ thống chuẩn hóa theo OpenTelemetry hoặc gửi qua OTel Collector |
| API nghiệp vụ | Vẫn có thể dùng Micrometer Tracing/Observation | Vẫn có thể dùng Micrometer Tracing/Observation |

Chọn theo hạ tầng tracing đang có, giao thức propagation giữa các service, exporter mà backend hỗ trợ và yêu cầu vận hành. Không có bridge nào tự động làm cho toàn bộ hệ thống phân tán tương thích nếu các service đang dùng propagation format khác nhau.

### Khi nào chọn Brave?

Brave phù hợp khi hệ thống hiện có Zipkin hoặc các thư viện đã phụ thuộc Brave. Bridge cho phép code ứng dụng sử dụng API Micrometer trong khi Brave quản lý span và context ở bên dưới.

Nếu backend nhận Zipkin, cần reporter phù hợp. Ví dụ, artifact Zipkin Reporter dành cho Brave là:

~~~text
io.zipkin.reporter2:zipkin-reporter-brave
~~~

### Khi nào chọn OpenTelemetry?

OpenTelemetry phù hợp khi tổ chức muốn dùng API/SDK và ecosystem OpenTelemetry, gửi telemetry đến OpenTelemetry Collector hoặc cần lựa chọn nhiều exporter.

Với OTLP, exporter thường dùng là:

~~~text
io.opentelemetry:opentelemetry-exporter-otlp
~~~

Collector có thể nhận OTLP rồi chuyển tiếp span đến một hoặc nhiều backend. Cách này giúp ứng dụng phụ thuộc vào endpoint collector thay vì từng backend lưu trữ cụ thể.

## 3. Không thêm đồng thời hai bridge như hai implementation mặc định

Một ứng dụng Spring Boot thông thường nên chọn một tracer implementation chính. Nếu thêm cả Brave bridge và OpenTelemetry bridge, auto-configuration có thể tạo nhiều bean cùng loại hoặc nhiều thành phần tracing cạnh tranh nhau.

Hậu quả có thể gồm:

- Không xác định được Tracer bean nào được inject.
- Auto-configuration không match theo điều kiện missing-bean.
- Span được tạo bởi implementation khác với exporter đang cấu hình.
- Propagation hoặc sampling có hành vi không nhất quán.
- Dependency graph chứa hai bộ thư viện tracing và nhiều phiên bản transitive.

Chỉ tích hợp cả hai khi có thiết kế rõ ràng cho việc chuyển tiếp hoặc tương thích đặc biệt, và đã kiểm thử cách quản lý context, exporter và bean. Đây không phải cấu hình mặc định cho một ứng dụng chỉ cần tracing.

Nếu cần di chuyển từ Brave sang OpenTelemetry, hãy thay bridge cùng exporter theo một kế hoạch có kiểm soát. Đừng thêm bridge mới vào trước khi loại bỏ hoặc cô lập implementation cũ mà không xác minh auto-configuration.

## 4. Dependency cho Spring Boot với Brave

Với Spring Boot 3 trở lên, một cấu hình điển hình dùng Actuator, Brave bridge và Zipkin reporter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-brave")
    runtimeOnly("io.zipkin.reporter2:zipkin-reporter-brave")
}
~~~

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
    </dependency>
    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Khi dùng Spring Boot dependency management, thường không ghi version riêng cho các dependency đã được BOM quản lý. Boot auto-configuration có thể tạo tracer, observation handler và reporter tương ứng khi dependency cùng property cần thiết hiện diện.

Ví dụ cấu hình sampling và Zipkin endpoint:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

Đây là cấu hình tham khảo cho các phiên bản Spring Boot có property tương ứng. Hãy kiểm tra configuration metadata của đúng Boot version để xác nhận prefix và property được hỗ trợ. Nếu dùng agent hoặc collector làm điểm nhận Zipkin, thay endpoint theo network và đường dẫn thực tế.

## 5. Dependency cho Spring Boot với OpenTelemetry

Một cấu hình điển hình dùng Micrometer OpenTelemetry bridge và OTLP exporter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Với OTLP/HTTP, endpoint traces thường có dạng:

~~~text
http://otel-collector:4318/v1/traces
~~~

Với OTLP/gRPC, collector thường lắng nghe cổng 4317. Giao thức và endpoint phải khớp với exporter được cấu hình. Không đưa URL HTTP path vào cấu hình gRPC hoặc ngược lại.

Property cấu hình endpoint tracing trong Spring Boot thay đổi theo thế hệ Boot và exporter integration. Dùng configuration metadata của đúng phiên bản đang chạy để xác định property chính xác; đừng suy ra property tracing từ property metrics vì hai exporter có thể có prefix và cấu hình khác nhau.

## 6. Quản lý phiên bản bằng BOM

Micrometer Tracing phụ thuộc vào nhiều thành phần có phiên bản liên quan:

- Micrometer Observation và Micrometer Tracing API.
- Bridge Brave hoặc OpenTelemetry.
- Brave core và các module reporter liên quan, hoặc OpenTelemetry API/SDK.
- Exporter/reporter và các thư viện transport.
- Spring Boot auto-configuration và Actuator.

Các thư viện này có thể biên dịch được với một tổ hợp version nhưng không tương thích ở runtime nếu một dependency transitive bị override.

### Khi dùng Spring Boot

Ưu tiên Spring Boot dependency management/BOM. BOM chọn các phiên bản Micrometer, bridge và thư viện liên quan đã được kiểm thử cùng dòng Boot đó.

~~~kotlin
plugins {
    id("org.springframework.boot") version "<boot-version>"
    id("io.spring.dependency-management") version "<plugin-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Các placeholder version chỉ được đặt ở plugin Boot trong ví dụ. Không thêm version riêng vào từng module Micrometer/OTel nếu BOM đang quản lý chúng, trừ khi có lý do nâng cấp và đã kiểm tra tương thích.

### Khi không dùng Spring Boot

Ứng dụng tự quản lý dependency cần giữ các module Micrometer cùng một dòng phát hành và chọn các phiên bản Brave hoặc OpenTelemetry phù hợp với bridge. Dùng BOM hoặc version catalog chính thức của các dự án tương ứng thay vì khai báo mỗi module một version.

Không lấy version mới nhất của OpenTelemetry SDK rồi ghép tùy ý với bridge cũ. Bridge được biên dịch và kiểm thử với một dải API/SDK nhất định; thay đổi major/minor có thể làm thay đổi method signature hoặc hành vi.

## 7. Ma trận tương thích cần kiểm tra

Không có một con số version duy nhất áp dụng cho mọi ứng dụng. Căn cứ phải là bộ dependency thực tế của dự án:

| Lớp | Điều cần đồng bộ |
| --- | --- |
| Spring Boot | Dòng Boot và BOM đang quản lý |
| Micrometer | Observation, Tracing API và bridge phải thuộc tổ hợp tương thích |
| Brave | Brave core và Zipkin reporter phải tương thích với Brave bridge |
| OpenTelemetry | OTel API, SDK và exporter phải tương thích với OTel bridge |
| Java | Bytecode/runtime target phải được các dependency hỗ trợ |
| Framework integration | Spring Cloud, messaging, HTTP client và instrumentation module phải hỗ trợ cùng dòng framework |

### Mốc chuyển từ Sleuth sang Micrometer Tracing

Spring Cloud Sleuth thuộc thế hệ Spring Boot 2.x. Với Spring Boot 3.x, tracing được tích hợp theo hướng Micrometer Tracing và Observation; không nên mang nguyên dependency Sleuth cũ sang Boot 3.

Khi nâng Boot major:

1. Kiểm tra hướng dẫn migration của Spring Boot và Spring Cloud release train.
2. Loại bỏ Sleuth starter/module không còn tương thích.
3. Chọn một Micrometer tracing bridge.
4. Thêm exporter/reporter tương ứng.
5. Chuyển code dùng API Sleuth cũ sang Micrometer Observation/Tracing API hoặc API phù hợp.
6. Kiểm tra propagation header và trace continuity qua các service.

Với Spring Boot major mới hơn, hãy để BOM của dòng đó quyết định Micrometer major version. Không giả định mọi Boot major đều dùng cùng một Micrometer Tracing version.

## 8. Kiểm tra dependency graph để tìm xung đột

Khai báo trong build file chỉ cho biết dependency trực tiếp. Thư viện khác có thể kéo một phiên bản Brave hoặc OpenTelemetry khác vào runtime classpath.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-observation --configuration runtimeClasspath
./gradlew dependencyInsight --dependency brave --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opentelemetry --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=io.micrometer,io.zipkin.brave,io.zipkin.reporter2,io.opentelemetry
~~~

Kiểm tra:

- Chỉ có bridge implementation mà ứng dụng chủ định sử dụng.
- Micrometer Observation và Tracing không bị lệch version ngoài BOM.
- Brave bridge không kéo nhiều phiên bản Brave core hoặc reporter.
- OTel bridge, API, SDK và exporter có phiên bản tương thích.
- Không có Sleuth cũ còn tồn tại trong ứng dụng Boot 3.
- Không có dependency exclude làm mất exporter hoặc SDK cần thiết.

Các lỗi như ClassNotFoundException, NoClassDefFoundError, NoSuchMethodError, ClassCastException hoặc NoUniqueBeanDefinitionException thường gợi ý classpath hoặc auto-configuration không đồng nhất.

## 9. Dùng Observation để giữ code độc lập với bridge

Trong phần lớn instrumentation nghiệp vụ, nên dùng Micrometer Observation thay vì gọi trực tiếp API Brave hoặc OpenTelemetry. Khi đổi bridge, code tạo Observation có thể được giữ nguyên.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public CheckoutResult checkout(CheckoutCommand command) {
        return Observation.createNotStarted(
                "business.checkout",
                observationRegistry
            )
            .lowCardinalityKeyValue("channel", command.channel())
            .observe(() -> performCheckout(command));
    }

    private CheckoutResult performCheckout(CheckoutCommand command) {
        // Xử lý nghiệp vụ.
        return new CheckoutResult();
    }
}
~~~

Observation có thể được xử lý đồng thời bởi metrics handler và tracing handler. Metrics handler tạo meter; tracing bridge tạo span tương ứng. Không cần tạo Counter/Timer riêng nếu Observation convention đã tạo đúng phép đo cần thiết.

Chỉ dùng API Tracer trực tiếp khi cần thao tác tracing đặc thù mà Observation không biểu đạt phù hợp, chẳng hạn tạo span thủ công quanh một đoạn tích hợp hoặc quản lý baggage cụ thể.

## 10. Dùng Tracer API khi cần tạo Span thủ công

Micrometer Tracing cung cấp abstraction Tracer và Span. Ví dụ:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

public class PartnerClient {

    private final Tracer tracer;

    public PartnerClient(Tracer tracer) {
        this.tracer = tracer;
    }

    public PartnerResult callPartner() {
        Span span = tracer.nextSpan()
            .name("partner.call")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            return invokeRemoteService();
        } catch (RuntimeException error) {
            span.error(error);
            throw error;
        } finally {
            span.end();
        }
    }
}
~~~

Span biểu diễn một operation trong trace. withSpan() đưa span thành current span trong scope; khi SpanInScope đóng, current span trước đó được khôi phục. span.end() kết thúc span. Tương tự Observation/Scope, hai thao tác này có lifecycle riêng.

Không giữ SpanInScope mở xuyên qua thời gian chờ asynchronous trên thread pool. Với async, hãy truyền context theo cơ chế được framework hỗ trợ và mở scope trên thread thực thi callback khi cần.

## 11. Propagation giữa các service

Trace chỉ có ích xuyên dịch vụ nếu context được truyền qua ranh giới process. Các định dạng thường gặp:

| Format | Header thường gặp | Ghi chú |
| --- | --- | --- |
| W3C Trace Context | traceparent, tracestate | Chuẩn phổ biến trong OpenTelemetry và hệ sinh thái hiện đại |
| B3 | b3 hoặc các header X-B3-* | Phổ biến trong hệ sinh thái Zipkin/Brave |
| Baggage | baggage | Truyền các thuộc tính context được phép qua service boundary |

Brave và OpenTelemetry có thể hỗ trợ nhiều propagation format tùy cấu hình. Không giả định bridge tự chọn format phù hợp với mọi service. Hãy cấu hình format mà các service trong hệ thống cùng hiểu.

Khi một service nhận traceparent hoặc B3, nó cần tiếp tục trace hiện có thay vì tạo trace root mới ngoài ý muốn. Kiểm tra trace ID ở hai phía của một lời gọi để xác nhận propagation hoạt động.

Không đưa dữ liệu nhạy cảm vào baggage. Baggage có thể được truyền qua nhiều service và có thể xuất hiện trong log hoặc telemetry tùy cấu hình. Chỉ truyền key-value có mục đích rõ ràng, kích thước nhỏ và chính sách bảo mật phù hợp.

## 12. Sampling và chi phí tracing

Sampling quyết định trace nào được ghi lại và export. Nếu sampling probability quá thấp, trace của request thử nghiệm có thể không xuất hiện dù instrumentation hoạt động. Nếu luôn lấy mẫu toàn bộ traffic ở tải lớn, chi phí CPU, network, storage và backend có thể tăng đáng kể.

Ví dụ cấu hình Spring Boot:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Giá trị 0.10 chỉ là ví dụ tương ứng khoảng 10% sampling cho cấu hình hỗ trợ xác suất. Property và semantics có thể phụ thuộc Boot version và sampler implementation.

Khi điều tra:

- Xác nhận sampling probability không bằng 0.
- Kiểm tra sampler có bị cấu hình khác ghi đè không.
- Kiểm tra backend nhận span và không loại bỏ theo policy.
- Với distributed trace, hiểu parent-based sampling để service con tuân theo quyết định của trace cha.
- Không tăng sampling toàn production chỉ để kiểm tra một request nếu có thể dùng môi trường test hoặc cơ chế sampling có kiểm soát.

Sampling ảnh hưởng trace export, không đồng nghĩa metrics instrumentation bị tắt. Metrics vẫn có thể được ghi nhận ngay cả khi trace tương ứng không được sample.

## 13. Exporter và backend phải khớp với bridge

| Bridge | Reporter/exporter | Endpoint ví dụ | Backend/receiver |
| --- | --- | --- | --- |
| Brave | Zipkin Reporter | http://zipkin:9411/api/v2/spans | Zipkin hoặc receiver tương thích Zipkin |
| OpenTelemetry | OTLP exporter | http://otel-collector:4318/v1/traces | OpenTelemetry Collector |

Đây là ví dụ endpoint phổ biến, không phải URL bắt buộc. Môi trường triển khai có thể dùng HTTPS, authentication, gateway hoặc cổng khác.

Với OpenTelemetry, Collector có thể nhận OTLP rồi export sang nhiều backend. Với Brave/Zipkin, reporter thường gửi span theo định dạng Zipkin. Nếu backend chỉ nhận OTLP, cần exporter tương ứng hoặc Collector chuyển đổi; không thể chỉ đổi URL của Zipkin reporter thành endpoint OTLP.

Kiểm tra cả đường đi:

1. Span được tạo và kết thúc trong ứng dụng.
2. Reporter/exporter được khởi tạo.
3. Request export đến đúng receiver.
4. Receiver chấp nhận payload và authentication.
5. Pipeline chuyển span đến backend.
6. Backend truy vấn được trace theo service name hoặc trace ID.

## 14. Kiểm tra auto-configuration và bean

Với Spring Boot, bridge và exporter thường kích hoạt auto-configuration theo classpath và property. Khi Tracer bean không xuất hiện hoặc có nhiều candidate:

- Bật condition evaluation report bằng debug.
- Kiểm tra bridge artifact có trong runtime classpath không.
- Kiểm tra có đồng thời Brave và OTel bridge không.
- Kiểm tra exporter/reporter dependency tương ứng.
- Kiểm tra bean tùy chỉnh có làm auto-configuration mặc định back off không.
- Kiểm tra dependency exclusion hoặc version conflict.

Có thể kiểm tra các bean chính trong integration test:

~~~java
@SpringBootTest
class TracingConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void hasOneTracerImplementation() {
        assertThat(context.getBeansOfType(Tracer.class))
            .hasSize(1);
    }
}
~~~

Đoạn test dùng Micrometer Tracer abstraction. Trong dự án thực tế cần import JUnit, Spring Boot Test và AssertJ, đồng thời cấu hình đúng bridge trong test runtime.

## 15. Kiểm thử propagation và export end-to-end

Unit test tạo Span thành công chưa chứng minh trace đi qua mạng. Cần kiểm thử integration:

1. Khởi động ứng dụng với đúng bridge và exporter.
2. Gọi một endpoint tạo Observation.
3. Gửi request qua service boundary nếu cần kiểm tra propagation.
4. Ghi lại trace ID ở service đầu và service nhận.
5. Xác nhận trace ID được giữ nguyên theo cùng distributed trace.
6. Kiểm tra backend/collector nhận span và parent-child relationship.
7. Kiểm tra sampling và service/resource attributes.

Với W3C propagation, xác minh header traceparent được inject và extract. Với B3, xác minh header B3 phù hợp được gửi và đọc. Tránh chỉ kiểm tra log của ứng dụng vì log có thể chứa trace ID ngay cả khi exporter không gửi được span.

Nếu dùng exporter bất đồng bộ, chờ theo cơ chế test/flush/shutdown phù hợp để tránh test kết thúc trước khi batch được gửi. Không dùng sleep tùy tiện làm bằng chứng duy nhất.

## 16. Các lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| NoSuchMethodError | Micrometer/Brave/OTel module lệch version | Dependency insight/tree và BOM |
| NoClassDefFoundError | Thiếu SDK, bridge hoặc exporter ở runtime | Runtime classpath và dependency scope |
| NoUniqueBeanDefinitionException cho Tracer | Có nhiều tracer implementation hoặc bean tùy chỉnh trùng | Chỉ chọn một bridge mặc định |
| Tracer bean không có | Bridge thiếu hoặc auto-configuration không match | Conditions report và classpath |
| Có trace trong log nhưng backend không có span | Exporter chưa cấu hình hoặc request export thất bại | Exporter log, endpoint và receiver |
| Mỗi service tạo trace ID mới | Propagation header không được inject/extract | W3C/B3 config và HTTP instrumentation |
| Trace không xuất hiện ngẫu nhiên | Sampling hoặc backend filtering | Probability, parent sampling và receiver policy |
| Span bị mất khi async | Context không được propagate hoặc Observation/Span bị kết thúc sai thời điểm | Async instrumentation và terminal lifecycle |
| Duplicate spans | Instrumentation chồng lấn hoặc tạo span thủ công trùng với auto instrumentation | Kiểm tra Observation, client instrumentation và custom spans |

## 17. Checklist chọn bridge và quản lý version

- [ ] Đã chọn một tracer implementation chính: Brave hoặc OpenTelemetry.
- [ ] Đã thêm đúng Micrometer tracing bridge.
- [ ] Đã thêm reporter/exporter phù hợp với backend.
- [ ] Để Spring Boot BOM hoặc dependency management quản lý version khi có thể.
- [ ] Micrometer Observation, Tracing API và bridge cùng tổ hợp tương thích.
- [ ] Brave core/reporter hoặc OTel API/SDK/exporter được đồng bộ.
- [ ] Không có Sleuth cũ trong ứng dụng Spring Boot 3.
- [ ] Đã kiểm tra runtime dependency graph.
- [ ] Auto-configuration tạo đúng một Tracer bean.
- [ ] Propagation format tương thích giữa các service.
- [ ] Sampling probability phù hợp với yêu cầu và tải.
- [ ] Exporter gửi được span đến receiver.
- [ ] Integration test xác nhận trace ID và span đến backend.

Micrometer Tracing cho ứng dụng một API thống nhất; bridge chọn tracer implementation và exporter/reporter đưa span đến backend. Hãy chọn Brave khi cần tương thích hệ sinh thái Brave/Zipkin, hoặc OpenTelemetry khi muốn chuẩn hóa theo OTel/OTLP. Để BOM quản lý các phiên bản liên quan, chỉ dùng một bridge mặc định, xác minh propagation giữa các service và kiểm thử toàn bộ đường export. Cách tổ chức này giúp đổi backend hoặc tracer implementation mà không phải gắn chặt logic nghiệp vụ vào một thư viện tracing cụ thể.
