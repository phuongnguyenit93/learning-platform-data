# Phối hợp nhiều handler cho phép đo, trace hoặc xử lý tùy biến

Micrometer Observation cho phép instrument một thao tác một lần rồi gắn nhiều hành vi quan sát vào vòng đời của thao tác đó. Một handler có thể tạo Timer, handler khác tạo span, còn handler tùy biến có thể ghi log sự kiện, bổ sung thông tin chẩn đoán hoặc cập nhật bộ đếm riêng. Các handler cùng nhận một Observation.Context nên có thể phối hợp mà không cần mã nghiệp vụ gọi trực tiếp từng hệ thống quan sát.

Khi cấu hình nhiều handler, cần phân biệt hai nhu cầu: một Observation có thể cần chạy đồng thời nhiều handler, hoặc chỉ cần chọn đúng một handler trong một nhóm handler thay thế nhau. Micrometer cung cấp hai composite tương ứng là AllMatchingCompositeObservationHandler và FirstMatchingCompositeObservationHandler.

## 1. Một Observation, nhiều hành vi quan sát

Giả sử ứng dụng xử lý thanh toán. Khi một Observation bắt đầu, ứng dụng có thể muốn:

- Đo thời gian xử lý và số lần xảy ra bằng Micrometer metrics.
- Tạo span để theo dõi luồng gọi qua nhiều service.
- Ghi nhận sự kiện nghiệp vụ hoặc thông tin chẩn đoán bằng handler tùy biến.
- Đưa Observation hiện tại vào scope để tracing và logging có thể lấy ngữ cảnh phù hợp.

Nếu từng service tự gọi MeterRegistry, Tracer và logger, mã nghiệp vụ sẽ phụ thuộc trực tiếp vào nhiều API quan sát. Observation tách việc đó ra: code chỉ tạo và điều khiển Observation; các handler đã đăng ký quyết định hành vi nào chạy.

~~~mermaid
flowchart TD
    A[Mã nghiệp vụ tạo Observation] --> B[ObservationRegistry]
    B --> C{supportsContext?}
    C -->|Phù hợp| D[DefaultMeterObservationHandler]
    C -->|Phù hợp| E[Tracing handler]
    C -->|Phù hợp| F[Custom handler]
    D --> G[Timer / Counter]
    E --> H[Span / propagation]
    F --> I[Log / audit / diagnostics]
~~~

Một handler chỉ nhận các Observation có context mà nó hỗ trợ. Vì thế, cùng một registry có thể quản lý handler cho HTTP server, HTTP client, database, message consumer và context nghiệp vụ riêng.

## 2. ObservationHandler nhận những callback nào?

ObservationHandler phản ứng với các sự kiện trong vòng đời Observation và Scope:

| Callback | Thời điểm | Công việc thường làm |
| --- | --- | --- |
| onStart(context) | Observation bắt đầu. | Tạo span, bắt đầu bộ đo thời gian hoặc lưu trạng thái cần dùng về sau. |
| onError(context) | Observation nhận lỗi qua error(exception). | Đánh dấu lỗi trên span, ghi thông tin lỗi hoặc cập nhật trạng thái chẩn đoán. |
| onEvent(event, context) | Code phát một Observation.Event. | Ghi annotation vào span, đếm sự kiện hoặc ghi log có cấu trúc. |
| onScopeOpened(context) | Observation được đưa vào scope hiện tại. | Đưa span hoặc context vào cơ chế truy cập theo luồng. |
| onScopeClosed(context) | Scope được đóng. | Khôi phục hoặc dọn ngữ cảnh theo luồng. |
| onStop(context) | Observation kết thúc. | Dừng Timer, kết thúc span hoặc hoàn tất xử lý tùy biến. |

Các phương thức callback ngoại trừ supportsContext có triển khai mặc định rỗng. Handler chỉ cần override những callback mà nó thực sự sử dụng.

onScopeOpened và onScopeClosed thuộc vòng đời Scope, không đồng nghĩa với onStart và onStop. Một Observation có thể mở scope nhiều lần trong quá trình thực thi. Nếu handler dùng ThreadLocal hoặc gắn thông tin vào ngữ cảnh hiện tại, phải dọn đúng lúc scope đóng.

## 3. supportsContext quyết định handler nào được gọi

Mỗi handler phải triển khai supportsContext. Phương thức này nhận Observation.Context và trả về true nếu handler có thể xử lý loại context đó.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class CheckoutAuditHandler
        implements ObservationHandler<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        // Handle checkout observations.
    }
}
~~~

CheckoutContext là context chuyên biệt do instrumentation tạo ra. Handler chỉ nhận loại context đó, vì vậy nó không vô tình xử lý Observation của JDBC hoặc HTTP client.

Có thể dùng ObservationHandler<Observation.Context> nếu handler thật sự áp dụng cho mọi loại context. Trong trường hợp đó, supportsContext có thể trả về true cho tất cả. Hãy tránh trả true một cách máy móc nếu handler chỉ hiểu một tập dữ liệu cụ thể.

Khi đăng ký nhiều handler riêng biệt vào ObservationRegistry, mỗi handler có supportsContext trả về true đều nhận callback tương ứng. Không cần composite nếu chỉ muốn đăng ký một số handler độc lập.

## 4. Đăng ký metrics, tracing và handler tùy biến

Với Micrometer metrics, DefaultMeterObservationHandler chuyển Observation thành meter. Với tracing, Micrometer Tracing cung cấp các handler tạo span và xử lý propagation. Handler tùy biến có thể xử lý cùng Observation.Context để ghi thông tin chẩn đoán.

Ví dụ cấu hình độc lập:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public final class ObservationHandlersConfiguration {

    public void configure(
            ObservationRegistry observationRegistry,
            MeterRegistry meterRegistry,
            CheckoutAuditHandler auditHandler) {

        observationRegistry.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meterRegistry))
                .observationHandler(auditHandler);
    }
}
~~~

Trong cấu hình này, meter handler và audit handler được đăng ký độc lập. Nếu cả hai hỗ trợ context của một Observation, cả hai cùng nhận lifecycle callbacks. Một handler không thay thế handler còn lại.

Tracing handler cũng có thể được đăng ký độc lập nếu ứng dụng chỉ có một handler tracing phù hợp cho mọi loại context. Khi cần chọn một trong nhiều handler tracing theo loại context, dùng FirstMatchingCompositeObservationHandler như phần sau.

## 5. DefaultMeterObservationHandler tạo những meter nào?

DefaultMeterObservationHandler là handler dựng sẵn để chuyển Observation thành metrics:

| Meter | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| Timer có tên bằng Observation name | onStop | Đo thời lượng từ lúc start đến stop; có low-cardinality tags và tag error. |
| Counter có tên dạng observation-name.event-name | onEvent | Tăng khi Observation phát một event. |
| LongTaskTimer có hậu tố .active | onStart | Theo dõi Observation đang chạy; phải bật tùy chọn includeActiveObservationLongTaskTimer. |

Chỉ low-cardinality key-values được dùng làm meter tags. High-cardinality key-values không được đưa vào meter để tránh tạo quá nhiều time series.

Ví dụ đăng ký handler:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();
MeterRegistry meterRegistry = new SimpleMeterRegistry();

registry.observationConfig().observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry).build());
~~~

Nếu cần theo dõi các Observation đang chạy, bật LongTaskTimer:

~~~java
registry.observationConfig().observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry)
                .includeActiveObservationLongTaskTimer(true)
                .build());
~~~

LongTaskTimer được tạo ở onStart nên chỉ nhận low-cardinality tags có sẵn tại thời điểm Observation bắt đầu. Các tag được thêm sau start có thể xuất hiện trong Timer cuối cùng nhưng không có trong LongTaskTimer đang chạy.

Không đăng ký đồng thời hai DefaultMeterObservationHandler vào cùng registry nếu chúng cùng đo cùng Observation. Điều đó có thể dẫn đến ghi nhận trùng hoặc cấu hình meter xung đột.

## 6. Phân biệt AllMatching và FirstMatching

Micrometer có hai composite handler:

| Composite | Cách chọn handler con | Trường hợp phù hợp |
| --- | --- | --- |
| AllMatchingCompositeObservationHandler | Gọi tất cả handler con có supportsContext trả về true. | Một Observation cần chạy nhiều xử lý tùy biến cùng lúc. |
| FirstMatchingCompositeObservationHandler | Chọn handler đầu tiên trong danh sách có supportsContext trả về true. | Một nhóm handler thay thế nhau, chỉ một handler được xử lý Observation đó. |

Hai composite đều được đăng ký như một ObservationHandler bình thường. Chúng giúp gom các handler có quan hệ cấu hình vào một nhóm.

Thứ tự các handler con trong constructor có ý nghĩa với FirstMatchingCompositeObservationHandler: handler phù hợp đầu tiên thắng. Với AllMatchingCompositeObservationHandler, các handler phù hợp được gọi theo thứ tự trong danh sách.

## 7. Dùng AllMatchingCompositeObservationHandler khi cần chạy tất cả

Giả sử checkout cần hai xử lý tùy biến: một handler ghi audit event và một handler đo thời lượng phục vụ chẩn đoán. Cả hai cần nhận cùng CheckoutContext:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

ObservationHandler<Observation.Context> checkoutHandlers =
        new ObservationHandler.AllMatchingCompositeObservationHandler(
                new CheckoutAuditHandler(),
                new CheckoutTimingHandler());

observationRegistry.observationConfig()
        .observationHandler(checkoutHandlers);
~~~

CheckoutAuditHandler và CheckoutTimingHandler đều cần triển khai supportsContext để nhận CheckoutContext. Khi context phù hợp, composite gọi callback của cả hai handler.

Có thể dùng AllMatchingCompositeObservationHandler cho nhiều handler cùng loại hoặc khác mục đích, miễn là tất cả đều cần chạy trên cùng Observation. Không dùng nó nếu chỉ một handler trong danh sách được phép tạo span hoặc thực hiện một tác vụ loại trừ lẫn nhau.

## 8. Dùng FirstMatchingCompositeObservationHandler cho tracing

Tracing thường có các handler chuyên biệt:

- PropagatingSenderTracingObservationHandler xử lý Observation phía gửi.
- PropagatingReceiverTracingObservationHandler xử lý Observation phía nhận.
- DefaultTracingObservationHandler xử lý các Observation tracing thông thường.

Một context gửi dữ liệu có thể phù hợp với sender handler; context nhận dữ liệu có thể phù hợp với receiver handler. Các context khác dùng handler mặc định.

~~~java
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingReceiverTracingObservationHandler;
import io.micrometer.tracing.handler.PropagatingSenderTracingObservationHandler;

// Inject the real Tracer and Propagator from the selected tracing bridge.
ObservationHandler<Observation.Context> tracingHandlers =
        new ObservationHandler.FirstMatchingCompositeObservationHandler(
                new PropagatingSenderTracingObservationHandler<>(
                        tracer, propagator),
                new PropagatingReceiverTracingObservationHandler<>(
                        tracer, propagator),
                new DefaultTracingObservationHandler(tracer));

observationRegistry.observationConfig()
        .observationHandler(tracingHandlers);
~~~

Các lớp tracing đến từ Micrometer Tracing; ứng dụng cần bridge tương ứng như Brave hoặc OpenTelemetry và dependency tương thích. Thứ tự sender, receiver, default là có chủ đích: handler chuyên biệt được xét trước, handler mặc định là phương án cuối.

FirstMatchingCompositeObservationHandler chỉ gọi handler đầu tiên phù hợp. Vì vậy, không đặt DefaultMeterObservationHandler vào cùng composite tracing này nếu muốn metrics và tracing cùng chạy. Meter handler phải được đăng ký riêng trên ObservationRegistry.

## 9. Kết hợp metrics, tracing và xử lý tùy biến

Một cấu hình kết hợp có thể đăng ký ba nhánh:

~~~java
observationRegistry.observationConfig()
        // Always create metrics for supported observations.
        .observationHandler(
                new DefaultMeterObservationHandler(meterRegistry))
        // Select one tracing handler for each context.
        .observationHandler(tracingHandlers)
        // Run every matching custom handler.
        .observationHandler(
                new ObservationHandler.AllMatchingCompositeObservationHandler(
                        new CheckoutAuditHandler(),
                        new CheckoutTimingHandler()));
~~~

Với một CheckoutContext được hỗ trợ bởi cả ba nhánh:

1. DefaultMeterObservationHandler ghi nhận metrics.
2. Composite tracing chọn đúng một tracing handler.
3. Composite tùy biến gọi mọi handler con hỗ trợ CheckoutContext.

Đây là cấu trúc phổ biến khi cùng một instrumentation cần phát ra metrics, trace và thông tin chẩn đoán. Mỗi nhánh có trách nhiệm riêng và được chọn theo chính sách supportsContext.

## 10. Viết custom handler cho một loại context

Ví dụ context checkout:

~~~java
import io.micrometer.observation.Observation;

public final class CheckoutContext extends Observation.Context {

    private final String channel;
    private final String checkoutType;

    public CheckoutContext(String channel, String checkoutType) {
        this.channel = channel;
        this.checkoutType = checkoutType;
    }

    public String getChannel() {
        return channel;
    }

    public String getCheckoutType() {
        return checkoutType;
    }
}
~~~

Custom handler có thể ghi log các callback mà nó cần:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class CheckoutAuditHandler
        implements ObservationHandler<CheckoutContext> {

    private static final Logger log =
            LoggerFactory.getLogger(CheckoutAuditHandler.class);

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        log.debug("Checkout started: channel={}, type={}",
                context.getChannel(), context.getCheckoutType());
    }

    @Override
    public void onError(CheckoutContext context) {
        Throwable error = context.getError();
        String errorType = error == null
                ? "unknown"
                : error.getClass().getSimpleName();

        log.warn("Checkout failed: channel={}, type={}, errorType={}",
                context.getChannel(), context.getCheckoutType(), errorType);
    }

    @Override
    public void onEvent(
            Observation.Event event,
            CheckoutContext context) {
        log.debug("Checkout event: name={}, channel={}",
                event.getName(), context.getChannel());
    }

    @Override
    public void onStop(CheckoutContext context) {
        log.debug("Checkout observation stopped: channel={}, type={}",
                context.getChannel(), context.getCheckoutType());
    }
}
~~~

Handler này chỉ nhận CheckoutContext. Nó không ghi lại order ID, email, token hoặc nội dung request. Khi xử lý log hoặc audit, chỉ đưa dữ liệu đã được cho phép vào log và tuân thủ chính sách lưu trữ của ứng dụng.

Nếu cần theo dõi scope, có thể override onScopeOpened và onScopeClosed. Hãy giữ logic cleanup trong onScopeClosed để tránh rò rỉ ThreadLocal hoặc ngữ cảnh theo luồng.

## 11. Chia sẻ trạng thái giữa các handler qua Context

Observation.Context là vùng dữ liệu chung được truyền giữa instrumentation và các handler. Handler có thể lưu trạng thái ở onStart rồi đọc lại ở onStop. Cách này phù hợp để giữ timestamp, correlation data hoặc một kết quả tính toán tạm thời.

Ví dụ lưu thời điểm bắt đầu:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class CheckoutTimingHandler
        implements ObservationHandler<CheckoutContext> {

    private static final String START_NANOS =
            CheckoutTimingHandler.class.getName() + ".startNanos";

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public void onStart(CheckoutContext context) {
        context.put(START_NANOS, System.nanoTime());
    }

    @Override
    public void onStop(CheckoutContext context) {
        Object value = context.get(START_NANOS);
        if (value instanceof Long startedAt) {
            long elapsedNanos = System.nanoTime() - startedAt;
            // Use the duration for bounded diagnostics if needed.
        }
    }
}
~~~

Nếu chỉ cần thời gian thực thi, ưu tiên Timer có sẵn của DefaultMeterObservationHandler thay vì tự đo lại. Ví dụ trên minh họa cách chia sẻ state giữa callbacks hoặc hỗ trợ một xử lý chẩn đoán đặc biệt.

Dùng key riêng có namespace để tránh xung đột với dữ liệu của handler khác. Không lưu đối tượng lớn hoặc dữ liệu nhạy cảm vào Context nếu không cần thiết. Context được chia sẻ trong vòng đời Observation; không xem nó là kho lưu trữ lâu dài.

## 12. Ghi nhận error và event

Error và event là hai tín hiệu khác nhau:

- error(exception) báo rằng thao tác gặp lỗi. Handler nhận onError và có thể đọc context.getError().
- event(event) báo một mốc tùy ý trong thao tác. Handler nhận onEvent và có thể tạo annotation, log hoặc Counter.

Ví dụ:

~~~java
import io.micrometer.observation.Observation;

Observation observation =
        Observation.createNotStarted("checkout.process", registry)
                .lowCardinalityKeyValue("channel", "web");

observation.observe(() -> {
    paymentService.authorize();
    observation.event(Observation.Event.of("payment.authorized"));
});
~~~

Nếu paymentService.authorize ném exception, observe tự động báo lỗi cho Observation rồi kết thúc Observation. Không cần tự gọi error và stop thêm lần nữa trong trường hợp dùng observe.

Với lifecycle điều khiển thủ công:

~~~java
import io.micrometer.observation.Observation;

Observation observation = Observation.start("checkout.process", registry);

try (Observation.Scope scope = observation.openScope()) {
    paymentService.authorize();
}
catch (RuntimeException exception) {
    observation.error(exception);
    throw exception;
}
finally {
    observation.stop();
}
~~~

Khi dùng cách thủ công, phải bảo đảm scope được đóng và Observation được stop kể cả khi có exception. Không gọi error chỉ để đánh dấu một outcome nghiệp vụ bình thường như declined nếu nó không phải lỗi kỹ thuật; hãy dùng event hoặc tag outcome có ngữ nghĩa rõ ràng.

## 13. Scope và tracing context

Tracing handler thường đưa span hiện tại vào scope khi Observation mở scope. Nhờ vậy, code chạy bên trong scope có thể lấy span hiện tại hoặc ghi log với trace context phù hợp.

~~~java
Observation observation = Observation.start("checkout.process", registry);

try (Observation.Scope scope = observation.openScope()) {
    checkoutService.process();
}
catch (RuntimeException exception) {
    observation.error(exception);
    throw exception;
}
finally {
    observation.stop();
}
~~~

Scope phải được đóng đúng thứ tự. Với code đồng bộ, try-with-resources là cách rõ ràng. Với async hoặc reactive pipeline, ThreadLocal không tự động đi theo mọi thread; cần cấu hình context propagation phù hợp với framework.

Không tự đặt span vào ThreadLocal rồi quên khôi phục giá trị cũ. Nếu custom handler quản lý ThreadLocal, phải dọn ở onScopeClosed và xử lý đúng trường hợp scope lồng nhau.

## 14. Phối hợp handler với Spring Boot

Spring Boot cấu hình ObservationRegistry và tự động đăng ký các bean thuộc những loại sau:

- ObservationHandler.
- ObservationPredicate.
- GlobalObservationConvention.
- ObservationFilter.

Có thể khai báo custom handler như bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CheckoutObservationConfiguration {

    @Bean
    CheckoutAuditHandler checkoutAuditHandler() {
        return new CheckoutAuditHandler();
    }

    @Bean
    CheckoutTimingHandler checkoutTimingHandler() {
        return new CheckoutTimingHandler();
    }
}
~~~

Spring Boot tự đăng ký các handler bean vào ObservationRegistry do Boot quản lý. Inject ObservationRegistry từ container khi tạo Observation. Không tạo registry riêng trong mỗi service vì registry mới có thể thiếu meter handler, tracing handler hoặc filter đã được Boot cấu hình.

Nếu cần cấu hình phức tạp hơn, có thể dùng ObservationRegistryCustomizer. Khi đó, kiểm tra các handler đã được Boot auto-configure để tránh đăng ký trùng DefaultMeterObservationHandler hoặc tracing handler. Chọn một nơi sở hữu việc đăng ký cho mỗi handler.

## 15. Khi nào dùng handler trực tiếp, AllMatching hay FirstMatching?

| Nhu cầu | Cách cấu hình |
| --- | --- |
| Metrics và audit đều cần chạy trên cùng context. | Đăng ký riêng hai handler hoặc gom vào AllMatchingCompositeObservationHandler. |
| Nhiều custom handler cùng xử lý checkout. | AllMatchingCompositeObservationHandler. |
| Chọn sender, receiver hoặc default tracing handler. | FirstMatchingCompositeObservationHandler. |
| Chỉ có một custom handler. | Đăng ký trực tiếp vào ObservationRegistry. |
| Một handler xử lý mọi context. | Dùng supportsContext phù hợp, thường trả true sau khi xác định thật sự áp dụng toàn cục. |

Composite không bắt buộc cho mọi trường hợp nhiều handler. Đăng ký trực tiếp thường đơn giản nhất khi các handler độc lập. Composite hữu ích khi cần gom các handler thành một nhóm có chính sách chọn rõ ràng.

## 16. Tránh phụ thuộc thứ tự giữa các handler độc lập

Một Observation có thể được xử lý bởi nhiều handler. Không nên thiết kế các handler độc lập theo kiểu handler A phải ghi dữ liệu vào Context trước thì handler B mới chạy được, trừ khi thứ tự đó được điều phối rõ ràng.

Nếu các handler cần cùng một dữ liệu:

- Đưa dữ liệu đó vào Context trước khi Observation bắt đầu.
- Dùng một convention hoặc instrumentation component để chuẩn hóa dữ liệu.
- Nếu handler phải thay thế lẫn nhau, dùng FirstMatchingCompositeObservationHandler.
- Nếu mọi handler phải cùng chạy, dùng AllMatchingCompositeObservationHandler.

AllMatchingCompositeObservationHandler gọi các handler phù hợp theo thứ tự trong danh sách. Tuy vậy, hãy giữ chúng độc lập và không dùng thứ tự đó như một giao thức truyền dữ liệu giữa các thành phần.

## 17. Giữ handler nhẹ và an toàn

Handler được gọi khi Observation phát sinh lifecycle callback. Công việc trong callback có thể nằm trực tiếp trên đường thực thi của thao tác được đo, vì vậy cần giữ chi phí nhỏ và dễ dự đoán.

Nên:

- Ghi nhận dữ liệu cục bộ hoặc cập nhật meter nhanh.
- Dùng logger có mức log phù hợp.
- Đưa công việc gửi audit hoặc telemetry từ xa vào cơ chế queue/buffer có giới hạn nếu thật sự cần.
- Bắt và xử lý lỗi nội bộ của phần tùy biến để không che mất exception nghiệp vụ ban đầu.
- Tránh tag hoặc log chứa token, thông tin cá nhân hay payload nhạy cảm.

Tránh:

- Gọi HTTP hoặc database đồng bộ từ onStart/onStop.
- Chờ queue không giới hạn.
- Tạo meter mới theo từng request hoặc từng ID.
- Dùng cùng một handler cho context mà nó không hiểu.
- Để handler giữ reference lâu dài đến Observation.Context sau khi Observation kết thúc.

Handler không nên trở thành một đường xử lý nghiệp vụ thứ hai. Nếu cần gửi sự kiện bền vững, dùng event pipeline hoặc outbox chuyên biệt; Observation chỉ nên cung cấp tín hiệu quan sát.

## 18. Kiểm thử nhiều handler bằng SimpleMeterRegistry

Có thể kiểm tra metrics và custom handler cùng nhận một Observation:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ObservationHandlersTest {

    @Test
    void runsMetricsAndEveryMatchingCustomHandler() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        AtomicInteger auditStops = new AtomicInteger();
        AtomicInteger diagnosticStops = new AtomicInteger();

        ObservationHandler<Observation.Context> auditHandler =
                new ObservationHandler<>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        auditStops.incrementAndGet();
                    }
                };

        ObservationHandler<Observation.Context> diagnosticHandler =
                new ObservationHandler<>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        diagnosticStops.incrementAndGet();
                    }
                };

        observations.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meters))
                .observationHandler(
                        new ObservationHandler.AllMatchingCompositeObservationHandler(
                                auditHandler, diagnosticHandler));

        Observation observation =
                Observation.createNotStarted("checkout.process", observations);

        observation.observe(() -> {
            observation.event(Observation.Event.of("payment.authorized"));
        });

        assertThat(meters.get("checkout.process").timer().count()).isEqualTo(1);
        assertThat(meters.get("checkout.process.payment.authorized")
                .counter().count()).isEqualTo(1);
        assertThat(auditStops).hasValue(1);
        assertThat(diagnosticStops).hasValue(1);
    }
}
~~~

Test này chứng minh một Observation có thể tạo Timer, Counter sự kiện và kích hoạt cả hai handler con của AllMatchingCompositeObservationHandler.

Trong test thực tế, nên giới hạn supportsContext theo loại context cần xử lý thay vì trả true cho mọi context như ví dụ rút gọn này.

## 19. Kiểm thử FirstMatchingCompositeObservationHandler

Tạo hai handler con có supportsContext cùng trả true, rồi đặt chúng theo thứ tự trong FirstMatchingCompositeObservationHandler. Khi Observation kết thúc, chỉ handler đầu tiên phù hợp được gọi.

Các trường hợp nên kiểm tra:

1. Context phù hợp handler đầu tiên: chỉ handler đầu tiên nhận callback.
2. Context không phù hợp handler đầu nhưng phù hợp handler thứ hai: handler thứ hai được gọi.
3. Không handler con nào hỗ trợ context: composite không xử lý context đó.
4. Thay đổi thứ tự handler: xác minh fallback được chọn đúng như chính sách.

Với tracing, kiểm thử sender context, receiver context và context thông thường riêng biệt để bảo đảm đúng handler được chọn. Đừng chỉ test một context chung vì DefaultTracingObservationHandler có thể là fallback phù hợp rộng hơn.

## 20. Kiểm tra error và scope callback

Ngoài trường hợp thành công, cần xác minh:

- Observation ném lỗi thì onError được gọi trước khi kết thúc.
- onStop vẫn được gọi khi operation kết thúc bằng exception.
- Scope được đóng và onScopeClosed được gọi sau khi xử lý.
- Event Counter chỉ tăng khi Observation.event được phát.
- Custom handler không ghi cùng một event hai lần do đăng ký trùng.

Khi tự quản lý lifecycle, dùng try-with-resources cho Scope và finally cho stop. Khi dùng observe, Micrometer thực hiện start, mở scope, chạy operation, báo error nếu có, đóng scope và stop Observation.

## 21. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt metrics handler trong FirstMatching cùng tracing handlers | Chỉ một handler phù hợp được chạy; metrics có thể không được ghi. | Đăng ký meter handler riêng. |
| Dùng FirstMatching khi cần mọi xử lý | Các handler sau handler phù hợp đầu tiên không được gọi. | Dùng AllMatchingCompositeObservationHandler. |
| Dùng AllMatching cho các handler thay thế nhau | Nhiều handler có thể cùng tạo span hoặc thực hiện tác vụ trùng. | Dùng FirstMatchingCompositeObservationHandler. |
| supportsContext luôn trả true | Handler xử lý context không đúng cấu trúc. | Kiểm tra loại context cụ thể. |
| Đăng ký cùng handler qua bean và customizer | Callback có thể chạy hai lần. | Chỉ có một nơi sở hữu đăng ký. |
| Handler ghi dữ liệu vào ThreadLocal nhưng không dọn | Rò rỉ context giữa các request hoặc task. | Dọn trong onScopeClosed. |
| Dùng handler để gửi HTTP đồng bộ | Tăng latency của thao tác đang được đo. | Dùng queue có giới hạn hoặc pipeline bất đồng bộ riêng. |
| Dùng event như error | Dashboard phân biệt sai lỗi kỹ thuật và mốc nghiệp vụ. | Dùng error(exception) cho lỗi, event cho sự kiện. |
| Dùng high-cardinality key-value làm metric tag | Tạo quá nhiều time series. | Chỉ dùng low-cardinality values cho meter tags. |
| Quên stop khi điều khiển lifecycle thủ công | Timer hoặc span không kết thúc. | Dùng observe hoặc stop trong finally. |

## 22. Checklist phối hợp nhiều handler

- [ ] Đã xác định mỗi handler chịu trách nhiệm về metrics, tracing hay xử lý tùy biến.
- [ ] Mỗi handler có supportsContext phù hợp với loại context.
- [ ] Đã đăng ký DefaultMeterObservationHandler riêng khi cần metrics.
- [ ] Đã dùng FirstMatchingCompositeObservationHandler cho nhóm handler thay thế nhau.
- [ ] Đã dùng AllMatchingCompositeObservationHandler khi mọi handler phù hợp đều phải chạy.
- [ ] Đã đặt thứ tự handler con đúng khi dùng FirstMatching.
- [ ] Không phụ thuộc thứ tự giữa các handler độc lập để trao đổi dữ liệu.
- [ ] Dùng Observation.Context để chia sẻ state trong vòng đời.
- [ ] onError và onEvent được dùng đúng ngữ nghĩa.
- [ ] Scope được đóng và ThreadLocal được dọn.
- [ ] Handler không thực hiện I/O đồng bộ kéo dài.
- [ ] Không đăng ký cùng handler hai lần qua Spring Boot và customizer.
- [ ] Đã kiểm thử success, error, event, scope và composite matching.
- [ ] Đã kiểm tra metric và span thực tế được tạo đúng.

Phối hợp nhiều ObservationHandler cho phép cùng một instrumentation tạo metrics, trace và hành vi tùy biến mà không làm mã nghiệp vụ phụ thuộc vào từng backend. Hãy đăng ký riêng các handler độc lập, dùng AllMatching khi tất cả handler phù hợp đều cần chạy và dùng FirstMatching khi chỉ một handler trong nhóm được chọn. Context và supportsContext là nền tảng để các handler nhận đúng dữ liệu và xử lý đúng loại Observation.

## Tài liệu tham khảo

- [Micrometer Observation - Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Observation - Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Tracing - Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [ObservationHandler source code](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-observation/src/main/java/io/micrometer/observation/ObservationHandler.java)
