# Observation không sinh dữ liệu do thiếu handler, predicate hoặc cấu hình tương ứng

Micrometer Observation cung cấp một vòng đời chung để mô tả thao tác: bắt đầu, mở scope, phát event, ghi nhận lỗi và kết thúc. Bản thân việc tạo một Observation chưa đồng nghĩa với việc metrics hoặc trace sẽ xuất hiện. Các tín hiệu chỉ được tạo khi có ObservationHandler phù hợp đăng ký trong đúng ObservationRegistry, handler chấp nhận loại context đó và cấu hình cho phép Observation chạy.

Khi Observation không sinh dữ liệu, cần tách ba tầng để chẩn đoán: **instrumentation có tạo Observation không**, **handler có xử lý Observation đó không**, và **registry/exporter có đưa meter ra hệ thống giám sát không**. Một Observation có thể chạy bình thường nhưng không có handler tạo Timer; một Timer có thể đã được ghi trong MeterRegistry nhưng endpoint export không được bật; hoặc predicate có thể biến Observation thành no-op trước khi handler nhận được lifecycle.

Bài này thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, tập trung vào các nguyên nhân thường gặp khiến Observation không sinh metrics hoặc tracing: thiếu handler, đăng ký sai registry, supportsContext không khớp, ObservationPredicate từ chối, thiếu MeterRegistry/exporter, cấu hình Spring Boot không được áp dụng và instrumentation bằng annotation không có AOP aspect.

## 1. Phân biệt Observation với dữ liệu được xuất

Observation là abstraction mô tả một thao tác. ObservationRegistry điều phối vòng đời; ObservationHandler nhận các callback và chuyển thông tin thành tín hiệu cụ thể.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Instrumentation | Tạo và điều khiển Observation | Observation API, @Observed, HTTP client instrumentation |
| ObservationRegistry | Giữ cấu hình và danh sách handler | Registry được inject vào service |
| ObservationPredicate | Quyết định Observation có được tạo đầy đủ hay trở thành no-op | Bỏ qua một nhóm Observation |
| ObservationConvention | Đặt tên và tạo low/high-cardinality key-value | Tên checkout.authorize |
| ObservationFilter | Chỉnh context trước khi handler xử lý stop | Thêm deployment.environment |
| ObservationHandler | Tạo tín hiệu từ lifecycle | Timer, Counter event, span |
| MeterRegistry | Lưu và xuất meter | SimpleMeterRegistry, PrometheusMeterRegistry |
| Exporter/endpoint | Đưa dữ liệu đến nơi thu thập | /actuator/prometheus, OTLP exporter |

Luồng metrics điển hình:

~~~text
Instrumentation
      |
      v
ObservationRegistry
      |
      +--> ObservationPredicate
      |       |
      |       +--> reject: Observation no-op
      |
      v
Observation lifecycle
      |
      +--> ObservationFilter trước stop
      |
      v
ObservationHandler
      |
      v
MeterRegistry
      |
      v
Registry exporter / Actuator endpoint
      |
      v
Prometheus / monitoring backend
~~~

Nếu bất kỳ tầng nào thiếu hoặc không được cấu hình đúng, dữ liệu có thể không xuất hiện ở nơi bạn đang kiểm tra. Không nên kết luận rằng Observation không chạy chỉ vì Prometheus chưa hiển thị metric.

## 2. ObservationRegistry không tự tạo metrics

Đoạn code sau tạo một registry nhưng chưa đăng ký handler tạo meter:

~~~java
ObservationRegistry observationRegistry =
        ObservationRegistry.create();

Observation.createNotStarted(
        "checkout.authorize",
        observationRegistry
).observe(() -> gateway.authorize());
~~~

Observation lifecycle vẫn được gọi, nhưng registry không có handler chuyển nó thành Timer hoặc Counter. Vì vậy, không có metrics tương ứng được ghi vào MeterRegistry.

Với Micrometer 1.18, có thể đăng ký DefaultMeterObservationHandler như sau:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
        .observationHandler(
                DefaultMeterObservationHandler.builder(meterRegistry).build()
        );
~~~

Trong các phiên bản Micrometer cũ hơn, API đăng ký có thể dùng constructor thay cho builder. Hãy kiểm tra Javadoc của phiên bản thực tế được dependency management resolve; không sao chép builder hoặc constructor từ một phiên bản khác mà chưa compile.

Handler phải được đăng ký trên đúng registry mà instrumentation sử dụng. Tạo một registry riêng trong service, trong khi handler lại được gắn vào registry do Spring Boot quản lý, sẽ khiến Observation đi qua registry không có handler.

## 3. Kiểm tra instrumentation đang dùng registry nào

Một ứng dụng Spring Boot thường có ObservationRegistry được auto-configure. Nếu code tự gọi ObservationRegistry.create() ở một nơi khác, nó tạo một registry độc lập và không tự kế thừa handler từ registry của Spring.

Ví dụ dễ mắc lỗi:

~~~java
@Service
public class CheckoutService {

    private final ObservationRegistry registry =
            ObservationRegistry.create();

    public void authorize(Payment payment) {
        Observation.createNotStarted("checkout.authorize", registry)
                .observe(() -> gateway.authorize(payment));
    }
}
~~~

Trong trường hợp này, service tự tạo registry và không dùng bean mà Spring Boot đã cấu hình. Nếu handler metrics được gắn vào bean registry của Spring, Observation trong service sẽ không đi qua handler đó.

Hãy inject registry:

~~~java
@Service
public class CheckoutService {

    private final ObservationRegistry registry;
    private final PaymentGateway gateway;

    public CheckoutService(
            ObservationRegistry registry,
            PaymentGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void authorize(Payment payment) {
        Observation.createNotStarted("checkout.authorize", registry)
                .observe(() -> gateway.authorize(payment));
    }
}
~~~

Trong test Spring context, kiểm tra bean thực tế được inject thay vì tự tạo registry phụ. Nếu ứng dụng có nhiều registry do nhiều context hoặc module tạo ra, xác nhận rõ registry nào đang nhận Observation và registry nào đang được exporter sử dụng.

## 4. Kiểm tra ObservationHandler đã được đăng ký

Một registry có thể có nhiều handler. Handler metrics và handler tracing đảm nhiệm các đầu ra khác nhau:

- DefaultMeterObservationHandler chuyển Observation thành Timer và event Counter.
- Tracing handler chuyển Observation thành span hoặc event trên span.
- Handler tùy chỉnh có thể ghi audit, log hoặc cập nhật hệ thống riêng.

Có handler tracing không đồng nghĩa đã có handler metrics. Tương tự, có MeterRegistry không có nghĩa Observation tự động được nối vào registry đó.

Với Micrometer 1.18, có thể kiểm tra cấu hình trong một test bằng cách tự tạo registry và gắn meter handler:

~~~java
SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

observations.observationConfig()
        .observationHandler(
                DefaultMeterObservationHandler.builder(meters).build()
        );
~~~

Sau đó chạy một Observation và xác nhận Timer xuất hiện trong SimpleMeterRegistry. Cách này cô lập được việc mapping từ Observation sang meter mà không phụ thuộc exporter hoặc ứng dụng Spring Boot.

Trong production, tránh đăng ký thêm một DefaultMeterObservationHandler nếu Spring Boot đã tự cấu hình handler tương ứng. Đăng ký trùng có thể khiến callback được xử lý nhiều lần hoặc tạo số đo bị nhân đôi tùy loại handler.

## 5. supportsContext không khớp khiến handler bỏ qua Observation

Mỗi ObservationHandler có thể giới hạn loại context mà nó hỗ trợ. Registry hỏi handler thông qua supportsContext(context); nếu handler trả về false, handler đó không nhận lifecycle của Observation.

Ví dụ handler chỉ hỗ trợ PaymentContext:

~~~java
public class PaymentMetricsHandler
        implements ObservationHandler<PaymentContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentContext;
    }

    @Override
    public void onStart(PaymentContext context) {
        // Bắt đầu theo dõi thao tác thanh toán.
    }

    @Override
    public void onStop(PaymentContext context) {
        // Kết thúc phép đo.
    }
}
~~~

Nếu instrumentation tạo Observation.Context mặc định thay vì PaymentContext, handler trên không được gọi. Handler vẫn đã đăng ký; vấn đề nằm ở loại context không tương thích.

Khi dùng custom context:

- Đảm bảo instrumentation tạo đúng subclass.
- Đảm bảo supportsContext kiểm tra đúng loại context.
- Không trả true cho mọi context nếu handler giả định các field riêng đã tồn tại.
- Kiểm tra handler nhận được onStart và onStop bằng test.
- Nếu dùng composite handler, xác nhận handler cụ thể nằm trong composite đang được registry sử dụng.

Không nhầm việc supportsContext trả false với ObservationPredicate từ chối Observation. Predicate quyết định Observation có chạy hay không; supportsContext quyết định handler nào được tham gia.

## 6. ObservationPredicate có thể biến Observation thành no-op

ObservationPredicate được gọi khi Observation được tạo. Nếu predicate trả false, Observation tương ứng trở thành no-op và các handler không nhận lifecycle như một Observation bình thường.

Ví dụ:

~~~java
observationRegistry.observationConfig()
        .observationPredicate((name, context) ->
                !name.startsWith("internal.")
        );
~~~

Cấu hình này bỏ qua mọi Observation có tên bắt đầu bằng internal. Nếu tên metric thực tế được tạo từ convention hoặc instrumentation khác với tên bạn dự kiến, predicate có thể vô tình từ chối một nhóm Observation quan trọng.

Khi điều tra:

1. Ghi nhận tên Observation thực tế tại điểm tạo.
2. Kiểm tra tất cả predicate đã đăng ký.
3. Tạm thời loại predicate trong test cô lập.
4. Xác nhận predicate trả true cho tên/context cần đo.
5. Kiểm tra cấu hình theo tên hoặc pattern có bị quá rộng không.

Predicate không phải MeterFilter. Predicate có thể ngăn Observation được thực thi; MeterFilter tác động đến việc đăng ký meter trong MeterRegistry. Nếu predicate trả false, sửa MeterFilter sẽ không làm Observation hoạt động trở lại.

Không dùng predicate để loại bỏ tất cả request lỗi hoặc request chậm nhằm làm dashboard đẹp hơn. Việc lọc như vậy có thể che mất tín hiệu cần phát hiện.

## 7. ObservationFilter không thay thế ObservationHandler

ObservationFilter chỉnh sửa Observation.Context trước khi handler nhận callback onStop. Filter thường được dùng để bổ sung hoặc chuẩn hóa key-value.

Ví dụ:

~~~java
observationRegistry.observationConfig()
        .observationFilter(context ->
                context.addLowCardinalityKeyValue(
                        KeyValue.of("deployment.environment", "production")
                )
        );
~~~

Filter không tự tạo Timer, Counter hoặc span. Nếu registry không có handler phù hợp, việc thêm key-value qua filter vẫn không tạo metrics.

Filter cũng chạy ở giai đoạn stop, vì vậy nó không thể thay đổi tag của event Counter đã được ghi trước đó hoặc meter active được tạo tại thời điểm start. Nếu một tag cần có trên mọi meter, hãy thêm nó qua convention hoặc tại thời điểm tạo Observation.

## 8. Kiểm tra Observation có thực sự được stop

DefaultMeterObservationHandler thường ghi Timer khi Observation kết thúc. Nếu code chỉ gọi start() nhưng không gọi stop(), Timer hoàn tất sẽ không được ghi.

Đoạn code thiếu stop:

~~~java
Observation observation =
        Observation.start("checkout.authorize", registry);

try (Observation.Scope scope = observation.openScope()) {
    gateway.authorize(payment);
}
// Không có observation.stop()
~~~

Cách an toàn cho thao tác đồng bộ:

~~~java
Observation.createNotStarted("checkout.authorize", registry)
        .observe(() -> gateway.authorize(payment));
~~~

Hoặc điều khiển lifecycle rõ ràng:

~~~java
Observation observation =
        Observation.start("checkout.authorize", registry);

try (Observation.Scope scope = observation.openScope()) {
    gateway.authorize(payment);
}
catch (RuntimeException error) {
    observation.error(error);
    throw error;
}
finally {
    observation.stop();
}
~~~

Timer được ghi khi stop. Trong lúc Observation đang chạy, LongTaskTimer có thể giúp quan sát thao tác đang hoạt động nếu handler và phiên bản được cấu hình hỗ trợ nó. Hành vi LongTaskTimer đã thay đổi giữa các phiên bản Micrometer; kiểm tra cấu hình đúng version trước khi dùng sự vắng mặt của active meter để kết luận.

Với CompletableFuture hoặc CompletionStage, đảm bảo Observation được giữ đến completion nếu mục tiêu là đo toàn bộ tác vụ. Nếu stop ngay sau submit, Timer chỉ đo thời gian tạo và submit tác vụ.

## 9. Event, error và Timer có thời điểm xuất hiện khác nhau

Không phải mọi tín hiệu đều xuất hiện tại cùng một thời điểm:

| Tín hiệu | Thời điểm thường được ghi |
|---|---|
| Timer của Observation | Khi Observation stop |
| Counter từ Observation event | Khi event được phát, nếu handler hỗ trợ mapping |
| LongTaskTimer active | Khi Observation start, nếu được bật |
| Span tracing | Theo lifecycle và cấu hình tracing handler |
| Custom audit/log | Theo callback mà handler triển khai |

Nếu dashboard chỉ tìm Timer ngay sau start, có thể chưa có Timer vì Observation chưa kết thúc. Nếu event Counter không xuất hiện, kiểm tra handler có mapping event và event có thực sự được phát hay không.

Gọi error(exception) đánh dấu lỗi trong context nhưng không tự tạo một error Counter riêng trong DefaultMeterObservationHandler. Thông thường lỗi được biểu diễn qua tag error của Timer khi Observation stop. Nếu cần Counter riêng cho một loại lỗi nghiệp vụ, tạo meter rõ ràng hoặc phát event với tên ổn định.

## 10. Kiểm tra MeterRegistry có tồn tại và đúng loại

Observation handler tạo metrics cần một MeterRegistry hoạt động. Trong test, có thể dùng SimpleMeterRegistry. Trong production, Spring Boot thường cấu hình registry dựa trên dependency exporter có mặt.

Các vấn đề thường gặp:

- Không có dependency registry/exporter tương ứng.
- MeterRegistry được tạo nhưng không phải registry mà handler đang sử dụng.
- Ứng dụng có nhiều registry và kiểm tra nhầm registry.
- MeterFilter từ chối meter hoặc đổi tên/tag.
- Registry đã bị đóng trong test hoặc lifecycle ứng dụng.
- Exporter bị disable bởi cấu hình.

Để tách lỗi mapping khỏi lỗi export, kiểm tra trực tiếp MeterRegistry trước:

~~~java
Timer timer = meters.find("checkout.authorize")
        .tag("payment.method", "card")
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
~~~

Nếu Timer tồn tại trong SimpleMeterRegistry nhưng không xuất hiện ở endpoint, vấn đề nằm ở exporter, endpoint exposure, security hoặc scrape configuration, không còn ở ObservationHandler.

## 11. MeterFilter có thể từ chối hoặc biến đổi meter

MeterFilter được áp dụng trong MeterRegistry khi meter được đăng ký. Một filter có thể deny meter, đổi tên, đổi tag hoặc cấu hình distribution.

Ví dụ filter từ chối tên meter:

~~~java
registry.config().meterFilter(
        MeterFilter.denyNameStartsWith("checkout.")
);
~~~

Nếu có filter như vậy, Observation có thể chạy và handler có thể cố tạo Timer nhưng registry không lưu meter mong muốn.

Kiểm tra:

- Có denyNameStartsWith hoặc deny() nào đang áp dụng không?
- Có maximumAllowableMetrics hoặc maximumAllowableTags đã chạm giới hạn không?
- Có filter đổi tên meter khiến dashboard tìm sai tên không?
- Có filter loại tag khiến truy vấn dùng tag cũ không còn match?
- Filter được đăng ký trước khi meter được tạo chưa?

MeterFilter là lớp bảo vệ registry, nhưng một filter deny quá rộng có thể làm mất metrics quan trọng. Test nên xác nhận cả meter được chấp nhận và meter bị từ chối theo chủ đích.

## 12. Spring Boot auto-configuration và registry tự tạo

Trong Spring Boot, Actuator cùng registry dependency phù hợp thường cung cấp MeterRegistry, ObservationRegistry và các handler cần thiết thông qua auto-configuration. Tuy nhiên, điều này phụ thuộc dependency, phiên bản và điều kiện cấu hình.

Các nguyên nhân khiến auto-configuration không tạo dữ liệu:

- Không có Spring Boot Actuator hoặc dependency cần thiết.
- Không có registry implementation cho backend mong muốn.
- Tự khai báo ObservationRegistry khiến cấu hình mặc định lùi lại hoặc code dùng nhầm registry.
- Custom ObservationHandler không được thêm vào registry chính.
- Exporter bị disable hoặc endpoint chưa được expose.
- Các điều kiện profile/property khiến bean không được tạo.
- Dùng registry khác trong test so với registry ở runtime.

Trong ứng dụng Spring Boot, ưu tiên inject ObservationRegistry và MeterRegistry từ application context. Không tạo registry thủ công trong mỗi service.

Với ứng dụng Maven, dependency thường cần có gồm Spring Boot Actuator và registry implementation tương ứng với backend. Ví dụ khi xuất Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Phiên bản Micrometer nên được quản lý bởi Spring Boot dependency management/BOM tương thích. Tránh ép một phiên bản Micrometer riêng lẻ nếu chưa kiểm tra compatibility matrix.

Nếu cần custom handler, hãy bổ sung vào registry đang được Boot quản lý theo cơ chế cấu hình của phiên bản Spring Boot đang dùng. Trước khi thêm DefaultMeterObservationHandler, kiểm tra xem Boot đã đăng ký handler đó chưa để tránh duplicate instrumentation.

## 13. Annotation không chạy nếu thiếu AOP aspect

Nếu Observation được tạo bằng annotation @Observed nhưng không có Observation, kiểm tra AOP riêng biệt. Annotation không tự tạo handler và cũng không tự kích hoạt proxy.

Các nguyên nhân phổ biến:

- Thiếu dependency Spring AOP.
- ObservedAspect chưa được đăng ký.
- Annotation scanning chưa được bật theo cấu hình của phiên bản Spring Boot.
- Object không do Spring quản lý.
- Method được gọi nội bộ trong cùng object (self-invocation), bỏ qua proxy.
- Proxy không intercept được method theo visibility/final constraints.
- Code đang dùng một instance khác với bean đã được proxy.

Ví dụ cấu hình aspect tường minh:

~~~java
@Configuration
class ObservationAspectConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Đây là cấu hình theo API Micrometer; nếu Spring Boot đã auto-configure annotation scanning hoặc aspect, không đăng ký trùng. Kiểm tra tài liệu phiên bản Spring Boot đang dùng để chọn một cơ chế cấu hình phù hợp.

Với instrumentation programmatic bằng Observation API, không cần AOP. Vì vậy, hãy thử một test programmatic trước để tách lỗi registry/handler khỏi lỗi proxy annotation.

## 14. Meter có thể tồn tại nhưng endpoint không xuất dữ liệu

Nếu SimpleMeterRegistry có Timer nhưng Prometheus không thấy, kiểm tra chuỗi export:

1. Có Prometheus registry dependency phù hợp không?
2. Registry có được Spring Boot auto-configure không?
3. Endpoint prometheus có được expose không?
4. Security chain có cho phép scraper truy cập không?
5. Scrape target có đúng host, port và path không?
6. Scrape có lỗi timeout hoặc authentication không?
7. Tên meter có được chuẩn hóa sang Prometheus naming convention không?
8. Tag có bị filter hoặc đổi tên không?

Ví dụ expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Exposure không tự mở quyền truy cập. Endpoint vẫn cần security và network policy phù hợp. Nếu endpoint bị bảo vệ đúng cách, hãy xác nhận Prometheus scraper có credential hoặc network route cần thiết.

Không dùng việc curl endpoint thất bại từ máy cá nhân để kết luận registry không tạo meter. Có thể endpoint đang chặn truy cập từ nguồn không được phép.

## 15. Convention có thể làm thay đổi tên và key-value

ObservationConvention có thể đặt tên Observation và tạo low/high-cardinality key-value. Nếu dashboard tìm tên mặc định nhưng convention thay đổi tên, dữ liệu có thể đã tồn tại dưới một tên khác.

Ví dụ convention:

~~~java
class CheckoutObservationConvention
        implements ObservationConvention<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public String getName() {
        return "checkout.payment";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            CheckoutContext context) {
        return KeyValues.of(
                KeyValue.of("payment.method", context.paymentMethod())
        );
    }
}
~~~

Nếu tên thực tế là checkout.payment, tìm checkout.authorize sẽ không có kết quả. Tương tự, convention có thể đổi tag key hoặc value khiến query dashboard không match.

Khi chẩn đoán, xem meter names và tags thực tế trong registry hoặc endpoint export. Không chỉ dựa vào tên dự kiến trong code gọi Observation.

## 16. Phân biệt lỗi metrics và lỗi tracing

Một Observation có thể được xử lý bởi nhiều handler độc lập:

- Metrics handler tạo Timer và Counter.
- Tracing handler tạo span và event.
- Logging handler hoặc handler tùy chỉnh tạo log/audit.

Nếu không thấy trace, chưa chắc metrics cũng bị mất. Tracing có thể có sampling hoặc exporter riêng; metrics có registry và pipeline export riêng. Ngược lại, có Timer không chứng minh tracing đã hoạt động.

Dùng bảng sau để khoanh vùng:

| Quan sát | Khu vực cần kiểm tra đầu tiên |
|---|---|
| Không có Timer, không có span | Instrumentation, registry, predicate, handler registration |
| Có span, không có Timer | Meter handler, MeterRegistry, MeterFilter |
| Có Timer, không có span | Tracing handler, tracer, sampling, span exporter |
| Có Timer trong registry, không có ở backend | Exporter, endpoint, scrape/push, naming |
| Có event span, không có event Counter | Meter handler mapping event và phiên bản |
| Có metric nhưng tag khác dự kiến | Convention, filter, key-value timing |

Không dùng trạng thái của một backend để suy luận trạng thái của backend còn lại.

## 17. Kiểm thử tối thiểu: handler tạo Timer

Dùng SimpleMeterRegistry để xác nhận Observation được chuyển thành Timer. Ví dụ dùng builder API của Micrometer 1.18:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationHandlerTest {

    @Test
    void recordsTimerWhenObservationStops() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build()
        );

        try {
            Observation.createNotStarted(
                    "checkout.authorize", observations
            )
            .lowCardinalityKeyValue("payment.method", "card")
            .observe(() -> {
                // Thao tác nghiệp vụ được thực hiện trong Observation.
            });

            Timer timer = meters.find("checkout.authorize")
                    .tag("payment.method", "card")
                    .timer();

            assertThat(timer).isNotNull();
            assertThat(timer.count()).isEqualTo(1);
        }
        finally {
            meters.close();
        }
    }
}
~~~

Test này xác nhận ba điều: registry có handler, Observation được chạy và stop, MeterRegistry nhận Timer. Nó không kiểm tra exporter hoặc endpoint.

Với Micrometer phiên bản cũ hơn, thay builder bằng API constructor tương ứng trong Javadoc của version đó. Không để ví dụ test trôi theo version mà không kiểm tra dependency thực tế.

## 18. Kiểm thử khi thiếu handler và khi predicate từ chối

Test không có handler giúp xác nhận Observation lifecycle không tự sinh meter:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class MissingObservationHandlerTest {

@Test
void doesNotCreateMetersWithoutMeterHandler() {
    SimpleMeterRegistry meters = new SimpleMeterRegistry();
    ObservationRegistry observations = ObservationRegistry.create();

    try {
        Observation.createNotStarted(
                "checkout.authorize", observations
        ).observe(() -> {
            // Observation chạy nhưng không có meter handler.
        });

        assertThat(meters.getMeters()).isEmpty();
    }
    finally {
        meters.close();
    }
}
}
~~~

Trong test trên, MeterRegistry chưa được nối với ObservationRegistry. Đây là cách mô phỏng lỗi thiếu handler.

Test predicate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationPredicateTest {

@Test
void predicateCanRejectObservation() {
    SimpleMeterRegistry meters = new SimpleMeterRegistry();
    ObservationRegistry observations = ObservationRegistry.create();

    observations.observationConfig()
            .observationHandler(
                    DefaultMeterObservationHandler.builder(meters).build()
            )
            .observationPredicate((name, context) ->
                    !name.equals("checkout.authorize")
            );

    try {
        Observation.createNotStarted(
                "checkout.authorize", observations
        ).observe(() -> {
            // Predicate từ chối Observation này.
        });

        assertThat(meters.find("checkout.authorize").timer()).isNull();
    }
    finally {
        meters.close();
    }
}
}
~~~

Hai test tách biệt hai nguyên nhân: thiếu meter handler và predicate loại Observation. Khi điều tra production, có thể dùng cách cô lập tương tự trong test để xác nhận hành vi cấu hình.

## 19. Kiểm thử custom handler và supportsContext

Với handler tùy chỉnh, test trực tiếp context mà handler hỗ trợ:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

class CheckoutContext extends Observation.Context {
}

class CheckoutHandler implements ObservationHandler<CheckoutContext> {

    private final AtomicInteger starts = new AtomicInteger();
    private final AtomicInteger stops = new AtomicInteger();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        starts.incrementAndGet();
    }

    @Override
    public void onStop(CheckoutContext context) {
        stops.incrementAndGet();
    }

    int starts() {
        return starts.get();
    }

    int stops() {
        return stops.get();
    }
}
~~~

Để kiểm tra dispatch, dùng factory/instrumentation tạo Observation với CheckoutContext và đăng ký CheckoutHandler vào cùng registry. Xác nhận starts/stops bằng 1; sau đó tạo Observation.Context mặc định và xác nhận handler không được gọi. Cách tạo Observation với custom context phụ thuộc API convention/factory của phiên bản Micrometer đang dùng, vì vậy nên kiểm tra signature trong Javadoc tương ứng thay vì ép context bằng cast.

Nếu handler không nhận callback, kiểm tra context type và supportsContext trước khi điều tra exporter. Với composite handler, kiểm tra cả handler con và cách composite lựa chọn handler: first-matching chỉ chọn handler phù hợp đầu tiên, trong khi all-matching có thể gọi tất cả handler phù hợp.

## 20. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hành động |
|---|---|---|
| Observation chạy nhưng không có Timer | Thiếu DefaultMeterObservationHandler | Đăng ký handler vào đúng registry |
| Handler có đăng ký nhưng không được gọi | supportsContext trả false | Sửa context type hoặc điều kiện hỗ trợ |
| Không có callback nào | Predicate từ chối hoặc dùng no-op registry | Kiểm tra predicate và registry thực tế |
| Timer chỉ xuất hiện sau khi method kết thúc | Hành vi bình thường của Timer | Kiểm tra sau stop; dùng LongTaskTimer nếu cần active state |
| Không có Timer dù tác vụ đã chạy | Không gọi stop hoặc lifecycle async chưa hoàn tất | Bảo đảm stop ở completion/error/cancel |
| Có Timer trong SimpleMeterRegistry nhưng không có trên Prometheus | Exporter/endpoint/scrape sai | Kiểm tra registry, exposure, security và scrape |
| Metrics có tên khác | ObservationConvention hoặc MeterFilter đổi tên | Xem tên meter thực tế |
| @Observed không tạo Observation | Thiếu aspect/AOP hoặc self-invocation | Kiểm tra proxy và ObservedAspect |
| Có span nhưng không có metrics | Thiếu meter handler hoặc MeterFilter deny | Kiểm tra metrics handler |
| Có metrics nhưng không có span | Tracing handler/exporter/sampling | Kiểm tra tracing pipeline |
| Event không có Counter | Handler không map event hoặc event chưa được phát | Kiểm tra event handler/version |
| Error không có Counter riêng | Default handler gắn error vào Timer tag | Tạo Counter/event riêng nếu cần |

## 21. Quy trình chẩn đoán theo thứ tự

Khi Observation không sinh dữ liệu, thực hiện theo thứ tự sau để thu hẹp phạm vi:

1. Xác nhận instrumentation thực sự được gọi; nếu dùng annotation, xác nhận AOP proxy intercept method.
2. Ghi lại Observation name và context type tại thời điểm tạo.
3. Xác nhận registry được inject là registry đang được cấu hình.
4. Kiểm tra ObservationPredicate có trả true không.
5. Kiểm tra handler phù hợp đã đăng ký trong registry.
6. Kiểm tra supportsContext của từng handler.
7. Xác nhận Observation đi qua start và stop; với async, chờ completion đúng lifecycle.
8. Kiểm tra MeterRegistry có Timer/Counter trực tiếp bằng SimpleMeterRegistry hoặc registry test.
9. Kiểm tra MeterFilter có deny hoặc đổi tên/tag không.
10. Nếu meter đã tồn tại, kiểm tra exporter, endpoint exposure, security và scrape/push.
11. Nếu tracing thiếu nhưng metrics có, điều tra tracing handler/exporter riêng.
12. Thêm test hồi quy cho đúng nguyên nhân đã tìm thấy.

Không thay đổi nhiều lớp cùng lúc. Nếu đồng thời thêm handler, bỏ predicate và đổi exporter, sẽ khó xác định nguyên nhân thực sự và có thể tạo duplicate metrics.

## 22. Checklist cấu hình trước production

- Instrumentation sử dụng đúng ObservationRegistry do ứng dụng quản lý.
- ObservationRegistry có handler metrics và/hoặc tracing phù hợp với mục tiêu.
- Handler supportsContext chấp nhận loại context thực tế.
- ObservationPredicate không vô tình từ chối Observation cần đo.
- ObservationFilter chỉ bổ sung/chuẩn hóa dữ liệu, không được kỳ vọng tạo meter.
- Observation luôn stop ở success, error và async completion.
- MeterRegistry được kết nối với handler metrics.
- MeterFilter không deny meter cần thiết.
- Convention và filter không làm thay đổi tên/tag ngoài dự kiến.
- Spring Boot Actuator và registry exporter được cấu hình theo version.
- Endpoint metrics được expose và bảo vệ đúng mô hình truy cập.
- Annotation instrumentation có AOP/aspect nếu cần.
- Không đăng ký handler trùng với auto-configuration.
- Test xác nhận Timer, event Counter, error tag và predicate behavior.
- Integration test xác nhận endpoint export có sample mong đợi.

Observation không sinh dữ liệu thường là lỗi ở một mắt xích giữa instrumentation, registry, predicate, handler và exporter. Hãy xác nhận Observation có được tạo, handler có nhận đúng context và MeterRegistry có ghi meter trước khi điều tra backend. Khi kiểm tra từng tầng độc lập và có test tái hiện cho thiếu handler, predicate từ chối, context không khớp và export bị tắt, nguyên nhân sẽ rõ ràng và dễ ngăn tái diễn.

## Tài liệu tham khảo

- [Micrometer - Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer - Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot - Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
