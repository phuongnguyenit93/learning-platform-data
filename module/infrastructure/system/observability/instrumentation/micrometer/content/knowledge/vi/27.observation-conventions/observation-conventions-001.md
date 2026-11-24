# Tên kỹ thuật, contextualName và ý nghĩa của từng loại tên

Micrometer Observation có thể phát ra nhiều loại telemetry từ cùng một lần đo: metrics, distributed traces và các tín hiệu khác do handler đăng ký. Vì vậy, một Observation có nhiều tên hoặc nhãn mang vai trò khác nhau. Nếu dùng một tên động cho tất cả request, metrics sẽ tạo quá nhiều series. Nếu chỉ dùng một tên kỹ thuật khô cứng cho span, trace khó đọc và khó nhận ra thao tác cụ thể.

Cần phân biệt tên kỹ thuật của Observation, tên theo ngữ cảnh (contextual name), tên meter được tạo từ Observation và tên span do tracing handler tạo. Tên kỹ thuật định danh loại thao tác; contextual name giúp mô tả thao tác trong bối cảnh thực tế. Các handler quyết định cách chuyển hai giá trị này thành metrics hoặc tracing.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích Observation name (tên kỹ thuật) và contextualName.
- Phân biệt Observation name với meter name và span name.
- Chọn tên ổn định, có ý nghĩa và không làm tăng cardinality.
- Cài đặt ObservationConvention để tùy chỉnh tên và key-values.
- Hiểu thứ tự ưu tiên giữa custom convention, global convention và default convention.
- Biết khi nào contextual name được lấy từ Observation.Context.
- Dùng tên và metadata nhất quán trong metrics, tracing, predicate và dashboard.

## Bốn loại tên cần phân biệt

Trong một lần quan sát HTTP request, có thể gặp các giá trị sau:

| Loại tên | Ví dụ | Vai trò |
|---|---|---|
| Observation name (technical name) | `http.server.requests` | Định danh loại hoạt động; dùng làm tên gốc cho metric và để nhận diện Observation |
| Contextual name | `GET /orders/{orderId}` | Tên dễ hiểu hơn được suy ra từ ngữ cảnh; tracing handler thường dùng làm tên span |
| Meter name | `http.server.requests` hoặc tên đã chuẩn hóa bởi registry | Tên Timer/Counter thực sự được đăng ký trong MeterRegistry |
| Span name | `GET /orders/{orderId}` | Tên hiển thị trên trace; thường lấy contextual name khi tracing handler hỗ trợ |

Đây là các vai trò riêng biệt, dù một vài giá trị có thể giống nhau. Observation name là đầu vào ở lớp instrumentation. Meter name và span name là kết quả do các handler tạo ra; registry hoặc tracing implementation có thể áp dụng quy ước riêng.

## Observation name: tên kỹ thuật ổn định

Observation name định danh loại thao tác đang được đo. Tất cả Observation cùng một loại nên dùng chung một tên. Ví dụ:

- `http.server.requests` cho các request HTTP đi vào server.
- `http.client.requests` cho các request HTTP gửi ra ngoài.
- `business.payment.authorization` cho thao tác xác thực thanh toán.
- `database.query` cho một nhóm thao tác truy vấn database.

Tên này không nên chứa dữ liệu riêng của từng lần gọi. Không đặt tên như `GET /orders/12345`, `payment.authorization.order-987` hoặc `request-7f3a`. Các giá trị như method, route template, provider hay outcome nên được đưa vào key-value phù hợp.

Observation name có một số tác dụng:

1. Định danh loại Observation trong instrumentation và context.
2. Là tên gốc mà `DefaultMeterObservationHandler` dùng để tạo Timer khi Observation kết thúc.
3. Là tên được truyền cho `ObservationPredicate`, nhờ đó có thể quyết định có tạo Observation hay không.
4. Là tên mặc định để các handler xử lý khi contextual name không được cung cấp.

Một tên kỹ thuật tốt thường ngắn, ổn định, dùng quy ước nhất quán và không phụ thuộc vào ID hoặc nội dung request.

## Contextual name: tên có ý nghĩa trong ngữ cảnh

Contextual name mô tả Observation cụ thể hơn dựa trên context có sẵn. Với HTTP server, tên này có thể kết hợp method và route template:

- Technical name: `http.server.requests`
- Contextual name: `GET /orders/{orderId}`

Với nghiệp vụ thanh toán:

- Technical name: `business.payment.authorization`
- Contextual name: `authorize payment`

Contextual name đặc biệt hữu ích cho tracing vì người đọc trace thường muốn biết span đang đại diện cho thao tác gì. Micrometer Tracing có thể dùng contextual name làm span name; nếu không có, tracing handler có thể dùng tên kỹ thuật làm phương án mặc định.

Contextual name có thể phụ thuộc context nhưng vẫn cần ổn định và có cardinality thấp. Với HTTP, hãy dùng route template như `/orders/{orderId}` thay vì URL thật `/orders/981723`. Với RPC hoặc messaging, dùng tên operation, method hoặc destination template đã được kiểm soát.

Không đưa các giá trị sau vào contextual name:

- Request ID, trace ID hoặc span ID.
- User ID, customer ID, order ID hoặc payment ID.
- URL đầy đủ có query string hoặc path chứa ID cụ thể.
- Nội dung do người dùng nhập.
- Exception message hoặc dữ liệu payload.

Các giá trị định danh của từng lần gọi, nếu thực sự cần cho điều tra, nên được ghi thành high-cardinality key-value trong span hoặc log theo chính sách dữ liệu. Chúng không nên trở thành tên span hoặc metric dimension.

## Meter name: tên metric được tạo từ Observation name

Khi `DefaultMeterObservationHandler` được đăng ký, handler tạo meter từ Observation:

| Meter | Khi nào được tạo | Tên mặc định |
|---|---|---|
| Timer | Khi Observation được stop | `<observation-name>` |
| Counter cho event | Khi gọi `Observation.event(...)` | `<observation-name>.<event-name>` |
| LongTaskTimer | Khi Observation start, nếu bật tùy chọn | `<observation-name>.active` |

Timer ghi duration giữa start và stop. Meter này nhận các low-cardinality key-values của Observation và tag `error` theo trạng thái lỗi. Counter event được tăng khi event được phát. LongTaskTimer theo dõi những Observation đang chạy và không được bật mặc định.

Ví dụ, với Observation name `http.server.requests`, Timer có tên canonical `http.server.requests`. Nếu phát event `retry`, Counter event có thể có tên `http.server.requests.retry`. Registry có thể chuyển các tên canonical sang định dạng backend, ví dụ Prometheus dùng dấu gạch dưới và hậu tố đơn vị.

Contextual name không đổi tên Timer. Nếu contextual name là `GET /orders/{orderId}`, Timer vẫn dùng Observation name làm tên gốc; route và method nên là low-cardinality tags để truy vấn metrics.

Chỉ low-cardinality key-values được đưa vào meter tags. High-cardinality key-values không được đưa vào metrics bởi `DefaultMeterObservationHandler`, vì chúng có thể tạo cardinality explosion trong backend.

## Span name: tên hiển thị trên distributed trace

Span name mô tả một đoạn công việc trong trace. Khi Micrometer Tracing được tích hợp qua tracing ObservationHandler, contextual name là nơi phù hợp để cung cấp tên span dễ đọc.

Ví dụ:

| Observation name | Contextual name | Span name mong muốn |
|---|---|---|
| `http.server.requests` | `GET /orders/{orderId}` | `GET /orders/{orderId}` |
| `http.client.requests` | `POST inventory/items` | `POST inventory/items` |
| `business.payment.authorization` | `authorize payment` | `authorize payment` |

Tên span nên mô tả operation, không mô tả một request duy nhất. Dùng route template hoặc operation name thay vì URL có ID cụ thể. Điều này giúp trace dễ nhóm và so sánh, đồng thời tránh tạo tên span gần như duy nhất cho mỗi request.

Không phải Observation nào cũng tạo span. Span chỉ được tạo khi registry có tracing handler tương ứng và handler hỗ trợ context đó. Nếu chỉ đăng ký `DefaultMeterObservationHandler`, Observation vẫn có thể tạo metrics mà không có distributed trace.

## ObservationConvention quản lý tên và key-values

`ObservationConvention<T>` tách cấu hình metadata khỏi vòng đời instrumentation. Instrumentation tạo context và bắt đầu/dừng Observation; convention quyết định:

- `getName()`: tên kỹ thuật của Observation.
- `getContextualName(context)`: tên theo ngữ cảnh.
- `getLowCardinalityKeyValues(context)`: key-values được dùng cho metrics và tracing.
- `getHighCardinalityKeyValues(context)`: key-values có thể dùng trong span, nhưng không đưa vào meter tags.
- `supportsContext(context)`: xác định convention có áp dụng cho loại context này hay không.

Nhờ convention, người dùng có thể đổi tên hoặc cách gắn tag mà không phải sửa logic đo thời gian trong instrumentation. Convention không thay thế Observation lifecycle và không tự tạo metric hay span; handler thực hiện phần đó.

### Ví dụ context cho HTTP request

Tạo context chứa dữ liệu đã được chuẩn hóa. Route phải là route template, không phải raw URL:

~~~java
import io.micrometer.observation.Observation;

public final class HttpServerContext extends Observation.Context {

    private final String method;
    private final String routeTemplate;
    private final String requestId;

    public HttpServerContext(
        String method,
        String routeTemplate,
        String requestId
    ) {
        this.method = method;
        this.routeTemplate = routeTemplate;
        this.requestId = requestId;
    }

    public String getMethod() {
        return method;
    }

    public String getRouteTemplate() {
        return routeTemplate;
    }

    public String getRequestId() {
        return requestId;
    }
}
~~~

### Cài đặt convention

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public final class HttpServerObservationConvention
        implements ObservationConvention<HttpServerContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof HttpServerContext;
    }

    @Override
    public String getName() {
        return "http.server.requests";
    }

    @Override
    public String getContextualName(HttpServerContext context) {
        return context.getMethod() + " " + context.getRouteTemplate();
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(HttpServerContext context) {
        return KeyValues.of(
            KeyValue.of("method", context.getMethod()),
            KeyValue.of("route", context.getRouteTemplate())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(HttpServerContext context) {
        return KeyValues.of(
            KeyValue.of("request.id", context.getRequestId())
        );
    }
}
~~~

Trong ví dụ:

- `http.server.requests` là tên kỹ thuật dùng chung cho mọi request.
- `GET /orders/{orderId}` là contextual name được tạo từ context.
- `method` và `route` là low-cardinality tags, có thể dùng trong metrics.
- `request.id` là high-cardinality value, chỉ dành cho span/tracing handler hỗ trợ.

Không đưa `request.id` vào meter tag. Nếu request ID có thể chứa dữ liệu nhạy cảm hoặc không được phép xuất ra tracing backend, hãy bỏ key này hoặc dùng một định danh đã được chính sách bảo mật cho phép.

### Tạo Observation với context tường minh

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class HttpRequestInstrumentation {

    private final ObservationRegistry registry;
    private final HttpServerObservationConvention convention;

    public HttpRequestInstrumentation(ObservationRegistry registry) {
        this.registry = registry;
        this.convention = new HttpServerObservationConvention();
    }

    public void handle(
        String method,
        String routeTemplate,
        String requestId,
        Runnable handler
    ) {
        HttpServerContext context = new HttpServerContext(
            method,
            routeTemplate,
            requestId
        );

        Observation.createNotStarted(
            convention,
            () -> context,
            registry
        ).observe(handler);
    }
}
~~~

Overload này nhận convention cùng `Supplier<Context>`. Việc truyền context tường minh rất quan trọng khi convention cần tính contextual name từ dữ liệu trong context. Nếu tạo Observation chỉ bằng tên và registry mà không có context, `getContextualName(context)` không có context cụ thể để xử lý.

Trong ứng dụng Spring Boot, `ObservationRegistry` thường được cấu hình sẵn cùng các handler. Đoạn code trên giả định registry đã có metrics handler và/hoặc tracing handler phù hợp. Nếu registry không có handler, Observation vẫn chạy nhưng không tự phát ra meter hay span.

## Thứ tự ưu tiên khi chọn convention

Khi dùng overload nhận cả custom convention và default convention, Micrometer chọn convention theo thứ tự:

1. Custom convention truyền trực tiếp vào lúc tạo Observation, nếu khác `null`.
2. `GlobalObservationConvention` đã đăng ký trên `ObservationRegistry` và hỗ trợ context hiện tại.
3. Default convention do instrumentation cung cấp.

Custom convention được truyền trực tiếp có ưu tiên cao nhất. Global convention phù hợp để áp dụng quy ước chung cho một nhóm context. Default convention đảm bảo instrumentation vẫn có hành vi hợp lý khi người dùng không cấu hình gì.

Ví dụ đăng ký global convention:

~~~java
registry.observationConfig()
    .observationConvention(new GlobalHttpServerObservationConvention());
~~~

Global convention cần triển khai `GlobalObservationConvention<T>` và `supportsContext` phải chỉ nhận đúng loại context. Không đăng ký một convention tổng quát hỗ trợ mọi context nếu nó thay đổi tên hoặc tags của các instrumentation không liên quan.

Nếu cần thêm key-values chung cho mọi Observation, kể cả khi custom convention đã được chọn, hãy dùng `ObservationFilter`. Filter dùng để bổ sung hoặc sửa context sau khi convention đã cung cấp metadata; nó không phải cơ chế chọn tên thay thế cho convention.

## Tùy chỉnh contextualName trực tiếp

Nếu không cần một convention riêng, có thể đặt contextual name trực tiếp trên Observation:

~~~java
Observation.createNotStarted("business.payment.authorization", registry)
    .contextualName("authorize payment")
    .lowCardinalityKeyValue("provider", "gateway-a")
    .observe(this::authorizePayment);
~~~

Ở đây tên kỹ thuật vẫn là `business.payment.authorization`. `contextualName("authorize payment")` bổ sung tên dễ đọc cho handler có hỗ trợ. Low-cardinality key-value `provider=gateway-a` được đưa vào metrics và tracing.

Cách này phù hợp với một Observation đơn giản hoặc khi contextual name đã biết ngay tại nơi tạo Observation. Nếu naming logic cần dựa trên context, được dùng ở nhiều nơi hoặc cần cho phép người dùng thay đổi, hãy đóng gói logic vào ObservationConvention.

## Dùng @Observed với name và contextualName

Với AOP được cấu hình, `@Observed` cho phép khai báo cả tên kỹ thuật và contextual name:

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @Observed(
        name = "business.payment.authorization",
        contextualName = "authorize payment"
    )
    public PaymentResult authorize(PaymentCommand command) {
        return paymentGateway.authorize(command);
    }
}
~~~

`name` xác định loại Observation và tên gốc cho meter. `contextualName` cung cấp tên thân thiện hơn cho handler như tracing. Để annotation có hiệu lực, ứng dụng phải bật cơ chế AOP/ObservedAspect theo cấu hình framework và truyền đúng ObservationRegistry.

Không đặt `name` hoặc `contextualName` chứa ID của command. Nếu cần thêm thuộc tính theo tham số, dùng `@ObservationKeyValue` hoặc convention/resolver với cardinality được lựa chọn có chủ đích.

## ObservationDocumentation mô tả hợp đồng tên và key

`ObservationDocumentation` giúp tập trung tài liệu cho từng loại Observation. Một mục documentation có thể khai báo:

- `getName()`: tên kỹ thuật mặc định, thường là tên metric.
- `getContextualName()`: tên dễ hiểu hơn trong ngữ cảnh, thường phù hợp làm span name.
- `getDefaultConvention()`: convention mặc định cung cấp tên và key-values.
- `getLowCardinalityKeyNames()` và `getHighCardinalityKeyNames()`: danh sách key được phép theo từng mức cardinality.
- `getPrefix()`: tiền tố bắt buộc của tag key trong nhóm documentation đó.

Lưu ý `getPrefix()` là quy tắc cho tag key, không phải tiền tố được tự động nối vào Observation name. Ví dụ, documentation có thể dùng prefix `payment.` để các tag key thuộc nhóm đó có dạng `payment.provider` hoặc `payment.channel`. Tên kỹ thuật và contextual name vẫn được mô tả riêng bằng `getName()` và `getContextualName()`.

Tổ chức tên và key trong documentation giúp instrumentation có hợp đồng rõ ràng, hỗ trợ sinh tài liệu và giúp người dùng thay convention mà vẫn giữ quy ước metadata nhất quán.

## Low-cardinality và high-cardinality không phải hai loại tên

Tên kỹ thuật và contextual name là hai loại tên. Low-cardinality và high-cardinality là hai loại key-value. Không nên nhầm hai khái niệm.

| Metadata | Dùng ở đâu | Ví dụ |
|---|---|---|
| Observation name | Định danh loại thao tác; tên gốc cho meter | `http.server.requests` |
| Contextual name | Mô tả operation trong context; có thể làm span name | `GET /orders/{orderId}` |
| Low-cardinality key-value | Meter tags và span attributes | `method=GET`, `route=/orders/{orderId}` |
| High-cardinality key-value | Span attributes nếu handler hỗ trợ; không dùng làm meter tags | `request.id=req-123` |

Một route template có số lượng giá trị hữu hạn nên thường là low-cardinality. Raw URL chứa ID cụ thể có cardinality cao. Nếu đưa raw URL vào contextual name, tên span có thể tăng theo mỗi request; nếu đưa nó vào low-cardinality tag, metrics backend có thể chịu cardinality explosion.

## Predicate, filter và convention có trách nhiệm khác nhau

Ba extension point thường bị dùng nhầm:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `ObservationConvention` | Chọn tên và key-values theo context | Đặt `http.server.requests`, route, method |
| `ObservationPredicate` | Quyết định có tạo Observation hay trả về no-op | Bỏ qua một loại operation không cần đo |
| `ObservationFilter` | Sửa context trước khi Observation dừng | Thêm `cloud.zone` cho mọi Observation |

Predicate thường nhận Observation name và context, vì vậy tên kỹ thuật ổn định cũng giúp viết rule bật/tắt rõ ràng. Filter có thể thêm low/high-cardinality key-values dùng chung mà không phải thay từng convention. Không dùng filter để tạo tên động theo từng request.

## Kiểm tra tên và metadata

Có thể kiểm tra context sau khi tạo Observation bằng `TestObservationRegistry` hoặc kiểm tra meter tạo ra bằng `SimpleMeterRegistry`. Ví dụ với metrics handler:

~~~java
import org.junit.jupiter.api.Test;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HttpRequestInstrumentationTest {

    @Test
    void createsTimerWithTechnicalNameAndLowCardinalityTags() {
        SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
        ObservationRegistry observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig().observationHandler(
            new DefaultMeterObservationHandler(meterRegistry)
        );

        HttpServerObservationConvention convention =
            new HttpServerObservationConvention();

        HttpServerContext context = new HttpServerContext(
            "GET",
            "/orders/{orderId}",
            "req-123"
        );

        Observation.createNotStarted(
            convention,
            () -> context,
            observationRegistry
        ).observe(() -> {
            // Giả lập xử lý request.
        });

        Timer timer = meterRegistry.get("http.server.requests")
            .tag("method", "GET")
            .tag("route", "/orders/{orderId}")
            .timer();

        assertEquals(1.0, timer.count(), 0.0);
        meterRegistry.close();
    }
}
~~~

Ví dụ xác minh tên meter và low-cardinality tags. `request.id` không được xuất thành meter tag bởi `DefaultMeterObservationHandler`. Muốn kiểm tra contextual name, dùng `TestObservationRegistry` và assertion trên observation đã ghi nhận, hoặc kiểm tra span name trong test tracing handler.

Các điểm nên kiểm tra:

- Observation name không đổi theo request ID hoặc raw URL.
- Contextual name dùng route template hoặc operation label có cardinality hữu hạn.
- Meter name được tạo từ technical name, không bị contextual name thay thế ngoài ý muốn.
- Low-cardinality tags có tập giá trị hữu hạn.
- High-cardinality values không xuất hiện trong metrics.
- Custom convention có ưu tiên như mong đợi so với global/default convention.
- Context được truyền tường minh nếu convention cần contextual name.
- Tracing handler có mặt nếu mong đợi span được tạo.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng URL đầy đủ làm Observation name | Mỗi request có thể tạo tên meter khác nhau | Dùng tên kỹ thuật ổn định; đưa route template vào low-cardinality tag |
| Dùng request ID làm contextual name | Span name gần như duy nhất, khó nhóm | Dùng method + route template hoặc operation name |
| Nghĩ contextual name đổi tên Timer | Query metrics tìm sai tên | Timer mặc định dùng Observation name; contextual name phục vụ handler như tracing |
| Nghĩ Observation name luôn là span name | Span khó đọc hoặc không có context cụ thể | Cung cấp contextual name phù hợp |
| Convention không có context supplier | Không thể suy contextual name từ context | Dùng overload tạo Observation với Supplier<Context> |
| Global convention hỗ trợ mọi context | Làm thay đổi tên/tag của instrumentation không liên quan | Kiểm tra loại context trong supportsContext |
| Dùng ObservationFilter để thay toàn bộ naming convention | Logic tên bị phân tán và khó dự đoán | Đặt naming logic trong ObservationConvention |
| Đưa high-cardinality value vào low-cardinality key | Cardinality metrics tăng mạnh | Phân loại key-value đúng mục đích |
| Không đăng ký tracing handler | Không có span dù Observation vẫn chạy | Cấu hình Micrometer Tracing handler và exporter |
| Chỉ kiểm tra meter mà không kiểm tra span | Không phát hiện contextual name bị sai | Kiểm thử cả metrics và tracing khi dùng cả hai |

## Ghi nhớ

- Observation name là tên kỹ thuật ổn định của loại thao tác; các Observation cùng loại dùng chung tên.
- Contextual name mô tả thao tác trong ngữ cảnh và thường phù hợp làm span name.
- `DefaultMeterObservationHandler` dùng Observation name làm tên Timer; event counter và active LongTaskTimer được tạo theo tên kỹ thuật.
- Contextual name không tự đổi tên meter.
- `ObservationConvention` quản lý `getName`, `getContextualName` và low/high-cardinality key-values.
- Custom convention ưu tiên hơn global convention; global convention ưu tiên hơn default convention.
- Convention cần context tường minh nếu muốn tính contextual name từ context.
- Low-cardinality key-values trở thành meter tags; high-cardinality key-values không được đưa vào meter tags mặc định.
- Dùng route template hoặc operation name; không đưa ID, raw URL hoặc message động vào tên.
- Kiểm tra riêng meter name và span name khi xác minh instrumentation.

Khi tên kỹ thuật được giữ ổn định và contextual name mô tả đúng operation, metrics có thể tổng hợp trên một tập series nhỏ trong khi trace vẫn dễ đọc. ObservationConvention là nơi thích hợp để tập trung quy tắc đó, giúp instrumentation giữ nguyên vòng đời đo và cho phép từng ứng dụng tùy chỉnh metadata theo context.

## Tài liệu tham khảo

- [Micrometer: Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — vai trò của Observation, tên và key-values có cardinality thấp/cao.
- [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — ObservationConvention, contextual name, handler, meter mapping và ví dụ custom convention.
- [Micrometer Tracing: Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html) — cách contextual name và key-values được dùng khi tạo span.
- [ObservationConvention API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationConvention.html) — getName, getContextualName, low/high-cardinality key-values và supportsContext.
- [ObservationDocumentation API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/docs/ObservationDocumentation.html) — technical name, contextual name, default convention và quy tắc prefix cho tag keys.
- [Observation API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/Observation.html) — các overload tạo Observation, contextualName và lifecycle.

