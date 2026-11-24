# Xử lý event, error và dữ liệu metric được hỗ trợ theo phiên bản

Micrometer Observation mô tả một thao tác bằng vòng đời thống nhất: bắt đầu, mở scope, phát event, ghi nhận lỗi và kết thúc. Các thành phần như metrics, tracing và logging đăng ký ObservationHandler để phản ứng với vòng đời đó. Nhờ vậy, mã nghiệp vụ có thể instrument một lần, còn mỗi handler quyết định tạo Timer, Counter, span hoặc log như thế nào.

Điểm cần chú ý là Observation event/error không tự động đồng nghĩa với một metric cụ thể. Observation.error() đánh dấu lỗi trên context và thông báo cho handler; Observation.event() phát một sự kiện trong lúc Observation đang chạy. Việc chuyển chúng thành meter phụ thuộc handler được đăng ký, loại meter mà handler hỗ trợ và phiên bản Micrometer đang dùng.

Bài này thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, tập trung vào cách xử lý event, error, low/high-cardinality key-value, DefaultMeterObservationHandler, ObservationConvention, ObservationFilter và các khác biệt đáng chú ý giữa những phiên bản Micrometer.

## 1. Observation có một vòng đời, nhiều handler

Một Observation được tạo trong ObservationRegistry cùng một Observation.Context. Khi code gọi các phương thức vòng đời, những handler hỗ trợ loại context đó sẽ được gọi tương ứng.

| Thao tác | Thời điểm | Handler thường nhận |
|---|---|---|
| start() | Observation bắt đầu | onStart(context) |
| openScope() | Đặt Observation hiện hành trên thread | onScopeOpened(context) nếu handler cần |
| event(event) | Một sự kiện nghiệp vụ hoặc kỹ thuật xảy ra | onEvent(event, context) |
| error(exception) | Công việc gặp lỗi | onError(context) |
| Scope.close() | Rời scope hiện hành | onScopeClosed(context) nếu handler cần |
| stop() | Observation kết thúc | Filter chạy trước, sau đó onStop(context) |

Observation.Context là vùng dữ liệu dùng chung giữa instrumentation và các handler. Nó có thể giữ thông tin tùy chỉnh như loại thanh toán, tên queue hoặc dữ liệu phục vụ xử lý ở onStop(). Context không tự tạo meter; handler quyết định đọc dữ liệu nào và chuyển nó thành tín hiệu nào.

Một ObservationHandler có thể chỉ hỗ trợ một loại context thông qua supportsContext(). Ví dụ, handler cho client HTTP có thể chỉ xử lý ClientRequestObservationContext; handler cho context thanh toán riêng có thể chỉ xử lý PaymentContext. Điều này giúp một registry chứa nhiều handler mà mỗi handler chỉ xử lý loại dữ liệu phù hợp.

## 2. Phân biệt event, error và stop

Ba thao tác này trả lời ba câu hỏi khác nhau:

- **Event**: điều gì vừa xảy ra trong lúc thao tác đang diễn ra?
- **Error**: thao tác này gặp lỗi nào?
- **Stop**: toàn bộ thao tác đã kết thúc lúc nào?

Ví dụ một lần thanh toán có thể phát event authorization.retry khi phải thử lại, ghi error nếu gateway cuối cùng thất bại và stop khi luồng xử lý kết thúc. Event không kết thúc Observation; error cũng không tự động stop Observation.

~~~text
Observation bắt đầu
       |
       +---- event: authorization.retry
       |
       +---- error(exception), nếu có
       |
       +---- các xử lý tiếp theo
       |
Observation.stop()
       |
       +---- ObservationFilter
       |
       +---- ObservationHandler.onStop()
~~~

Observation.observe(() -> ...) là cách dùng tiện lợi cho thao tác đồng bộ: Micrometer start Observation, mở scope, chạy lambda, đánh dấu lỗi nếu lambda ném exception, đóng scope và stop Observation. Nếu cần điều khiển event hoặc scope tường minh, có thể dùng start(), event(), error() và stop() riêng.

## 3. Ghi nhận event trong lúc Observation đang chạy

Observation.event() phát một event tới các handler đã đăng ký. Một event có tên ổn định và có thể kèm mô tả ngắn:

~~~java
observation.event(Observation.Event.of("authorization.retry"));
observation.event(
        Observation.Event.of("authorization.declined", "gateway returned decline")
);
~~~

Một số tracing handler có thể chuyển event thành annotation/event trên span. Handler tùy chỉnh có thể ghi log hoặc cập nhật hệ thống khác. DefaultMeterObservationHandler trong các phiên bản được tài liệu hóa hỗ trợ event sẽ tăng Counter cho mỗi event.

Event phù hợp với các mốc có ý nghĩa vận hành:

- cache.hit hoặc cache.miss.
- message.retry.
- payment.authorized.
- fallback.used.
- validation.rejected.

Không tạo tên event từ dữ liệu thay đổi theo từng request, chẳng hạn order.12345.failed hoặc nội dung exception. Tên event sẽ tham gia cấu trúc meter name trong default meter handler; tên không giới hạn có thể tạo quá nhiều meter và làm dashboard khó quản lý.

Nếu cần mang thông tin riêng của một lần xảy ra, dùng context/event metadata cho tracing hoặc handler phù hợp. Đừng nhét user ID, order ID, token hay exception message vào tên event hoặc metric tag.

## 4. Đánh dấu lỗi bằng error()

Khi một thao tác thất bại, gọi observation.error(exception) để lưu lỗi vào context và thông báo cho handler:

~~~java
Observation observation = Observation.start("checkout.authorize", registry);

try (Observation.Scope scope = observation.openScope()) {
    gateway.authorize(payment);
}
catch (RuntimeException exception) {
    observation.error(exception);
    throw exception;
}
finally {
    observation.stop();
}
~~~

error() không thay thế xử lý exception trong nghiệp vụ. Nếu exception cần được truyền cho caller, vẫn phải throw hoặc trả kết quả lỗi theo contract của ứng dụng. Nếu ứng dụng chủ động xử lý và không ném exception tiếp, vẫn có thể gọi error() để observability ghi nhận thất bại.

error() cũng không tự kết thúc Observation. Gọi stop() trong finally hoặc dùng observe() để bảo đảm lifecycle được đóng ngay cả khi có lỗi.

Không đánh dấu mọi kết quả nghiệp vụ không thành công thành exception. Ví dụ, một lần kiểm tra tồn kho trả về "không đủ hàng" có thể là kết quả hợp lệ theo nghiệp vụ. Hãy quyết định có gọi error() dựa trên ý nghĩa của thao tác và quy ước instrumentation.

## 5. Error được chuyển thành metric như thế nào?

Khi DefaultMeterObservationHandler được đăng ký, handler tạo Timer khi Observation dừng. Timer dùng các low-cardinality key-value và một tag error:

- Nếu Observation có error, giá trị error là tên lớp exception.
- Nếu không có error, giá trị error là none.

Ví dụ:

~~~text
checkout.authorize{payment.method="card", error="none"}
checkout.authorize{payment.method="card", error="java.net.SocketTimeoutException"}
~~~

Đây là hai chuỗi thời gian khác nhau vì giá trị tag error khác nhau. Có thể dùng truy vấn backend để xem số lần authorize thành công và lỗi, hoặc tính tỷ lệ lỗi trên tổng số lần gọi.

Điều quan trọng: DefaultMeterObservationHandler không tự tạo một error Counter riêng chỉ vì observation.error(exception) được gọi. Timer vẫn ghi một lần khi Observation stop; tag error cho biết kết quả. Nếu cần đếm riêng một loại lỗi nghiệp vụ, có thể phát event có tên ổn định hoặc tạo Counter chuyên biệt với tag hữu hạn.

Không đưa exception message, stack trace hoặc nội dung request vào metric tag. Chúng có thể chứa dữ liệu nhạy cảm và tạo cardinality không giới hạn. Nếu cần chẩn đoán sâu, dùng trace/log có kiểm soát và chính sách che dữ liệu phù hợp.

## 6. Event được chuyển thành Counter như thế nào?

Trong các phiên bản Micrometer có mapping event được tài liệu hóa, DefaultMeterObservationHandler tạo Counter theo quy tắc:

~~~text
<observation-name>.<event-name>
~~~

Ví dụ Observation checkout.authorize phát event authorization.retry thì Counter có tên logic:

~~~text
checkout.authorize.authorization.retry
~~~

Counter nhận các low-cardinality key-value có sẵn tại thời điểm event được phát. Mỗi lần cùng event được phát, Counter tương ứng được tăng thêm một.

Event counter hữu ích để đo số lần một mốc xảy ra trong Observation, chẳng hạn số lần retry hoặc số lần fallback. Nếu cần số lần event trên từng đơn vị thời gian, backend có thể tính rate từ Counter theo quy tắc của registry.

Không dùng event để thay thế Timer. Counter cho biết số lần event xảy ra; Timer cho biết số lượng và thời lượng của toàn bộ Observation. Một Observation có thể phát nhiều event nhưng vẫn chỉ có một Timer được ghi khi stop.

## 7. Low-cardinality và high-cardinality key-value

Observation chia metadata thành hai nhóm:

| Loại | Ví dụ | Mục đích |
|---|---|---|
| Low cardinality | payment.method=card, outcome=approved, region=ap-southeast-1 | Dùng làm tag của metrics và metadata của tracing |
| High cardinality | order.id=ORD-..., user.id=..., trace.id=... | Dữ liệu chi tiết cho tracing/logging hoặc handler hỗ trợ |

Low cardinality phải có tập giá trị hữu hạn và có thể kiểm soát. High cardinality có thể có rất nhiều giá trị khác nhau, thường là ID hoặc định danh duy nhất.

Ví dụ:

~~~java
Observation observation = Observation.createNotStarted(
        "checkout.authorize", registry
)
.lowCardinalityKeyValue("payment.method", "card")
.lowCardinalityKeyValue("outcome", "approved")
.highCardinalityKeyValue("order.id", orderId)
.highCardinalityKeyValue("customer.id", customerId);
~~~

DefaultMeterObservationHandler chỉ sử dụng low-cardinality key-value làm meter tags. High-cardinality key-value không được đưa vào metrics vì chúng có thể làm tăng số time series rất lớn. Tracing handler hoặc custom handler vẫn có thể dùng chúng theo khả năng của backend.

Một số quy tắc thiết kế:

- Dùng HTTP route template như /orders/{id} thay vì URL chứa ID thật.
- Dùng status class hoặc outcome hữu hạn thay vì message tự do.
- Dùng tên service, region hoặc loại nghiệp vụ đã chuẩn hóa.
- Không đưa request ID, user ID, order ID hoặc trace ID thành metric tag.
- Không đưa exception message vào event name.

## 8. Dữ liệu được chốt ở những thời điểm khác nhau

Một chi tiết quan trọng là các meter được tạo ở những thời điểm khác nhau:

| Meter | Thời điểm tạo/ghi | Low-cardinality key-value được lấy khi nào? |
|---|---|---|
| Timer của Observation | Khi stop() | Sau filter, tại thời điểm stop |
| Counter của event | Khi event() được phát | Tại thời điểm event |
| LongTaskTimer active | Khi start() nếu handler được cấu hình tạo meter này | Tại thời điểm start |

Hệ quả:

- Key-value thêm sau start() không xuất hiện trên LongTaskTimer đã tạo trước đó.
- Key-value thêm sau một event không thể thay đổi tag của Counter event đã được tăng.
- ObservationFilter chạy trước onStop(), nên có thể bổ sung key-value cho Timer cuối cùng; nó chạy quá muộn để thay đổi tag của event counter hoặc LongTaskTimer đã tạo.

Nếu cần tag trên LongTaskTimer, thêm low-cardinality key-value trước khi gọi start(). Nếu muốn event counter có tag nào, thêm key-value trước khi phát event. Nếu tag chỉ cần cho Timer cuối cùng, filter trước stop có thể là nơi phù hợp.

## 9. DefaultMeterObservationHandler tạo những meter nào?

DefaultMeterObservationHandler chuyển Observation thành các meter phổ biến:

| Meter | Ý nghĩa | Tag |
|---|---|---|
| Timer <observation-name> | Số lần hoàn tất và tổng thời lượng của Observation | Low-cardinality key-value và error |
| Counter <observation-name>.<event-name> | Số lần event được phát | Low-cardinality key-value tại thời điểm event |
| LongTaskTimer <observation-name>.active | Theo dõi Observation đang chạy | Low-cardinality key-value có tại thời điểm start |

LongTaskTimer hữu ích khi muốn biết có bao nhiêu Observation đang chạy và chúng đã chạy bao lâu. Nó đặc biệt hữu ích với công việc dài như batch job hoặc request xử lý lâu. Tuy nhiên, nó tạo thêm meter và có thể tăng chi phí theo số lượng Observation và tổ hợp tag.

LongTaskTimer không thay thế Timer. LongTaskTimer phản ánh công việc còn đang chạy; Timer ghi kết quả khi Observation hoàn tất. Chọn loại meter theo nhu cầu dashboard và khả năng của backend.

## 10. Khác biệt đáng chú ý giữa các phiên bản Micrometer

Không nên suy luận hành vi từ ví dụ của một phiên bản rồi áp dụng cho mọi dự án. Tài liệu chính thức của các nhánh ổn định thể hiện một thay đổi quan trọng ở LongTaskTimer:

| Phiên bản tài liệu | Timer khi stop | Event Counter | LongTaskTimer active |
|---|---|---|---|
| 1.13.x–1.14.x | Observation API và handler đã có; cần kiểm tra mapping của release cụ thể | Có DefaultMeterObservationHandler trong ví dụ, nhưng trang tài liệu chưa mô tả đầy đủ mapping như các bản sau | Không nên giả định theo tài liệu phiên bản mới |
| 1.15.x–1.17.x | Có, kèm tag error | Có, tên <observation>.<event> | Tài liệu mô tả được tạo khi start theo mặc định; có thể tắt bằng API IgnoredMeters ở các bản hỗ trợ |
| 1.18.x | Có, kèm tag error | Có, tên <observation>.<event> | Chuyển thành opt-in; builder mặc định không tạo LongTaskTimer |

Với Micrometer 1.15–1.17, tài liệu minh họa cách đăng ký handler bằng constructor:

~~~java
registry.observationConfig()
        .observationHandler(
                new DefaultMeterObservationHandler(meterRegistry)
        );
~~~

Trong các phiên bản này, nếu không muốn tạo LongTaskTimer, tài liệu 1.16–1.17 cung cấp IgnoredMeters.LONG_TASK_TIMER:

~~~java
registry.observationConfig()
        .observationHandler(
                new DefaultMeterObservationHandler(
                        meterRegistry,
                        DefaultMeterObservationHandler.IgnoredMeters.LONG_TASK_TIMER
                )
        );
~~~

Với Micrometer 1.18, cách cấu hình được tài liệu hướng dẫn dùng builder:

~~~java
registry.observationConfig()
        .observationHandler(
                DefaultMeterObservationHandler.builder(meterRegistry).build()
        );
~~~

Trong 1.18, cấu hình mặc định không tạo LongTaskTimer. Nếu cần theo dõi Observation đang chạy, bật rõ ràng:

~~~java
registry.observationConfig()
        .observationHandler(
                DefaultMeterObservationHandler.builder(meterRegistry)
                        .includeActiveObservationLongTaskTimer(true)
                        .build()
        );
~~~

Micrometer Observation và ObservationHandler được giới thiệu từ 1.10. Tài liệu 1.13–1.14 đã có Observation API, event/error và ví dụ dùng DefaultMeterObservationHandler; phần mapping meter được mô tả rõ hơn trong tài liệu 1.15 trở đi. Khi dự án dùng bản cũ hoặc patch release khác, hãy kiểm tra API trong Javadoc/source đúng phiên bản và viết test xác nhận meter thực tế.

Không dùng constructor, IgnoredMeters hoặc builder của một phiên bản khác nếu dependency hiện tại không có API đó. Spring Boot cũng quản lý phiên bản Micrometer thông qua dependency management; kiểm tra phiên bản Micrometer thực tế được resolve thay vì chỉ nhìn version khai báo trong một dependency riêng lẻ.

## 11. Đăng ký DefaultMeterObservationHandler

Một ObservationRegistry trống không tự xuất metrics chỉ vì code tạo Observation. Cần có handler chuyển Observation sang MeterRegistry, hoặc dùng cấu hình auto-configuration của framework.

Ví dụ với API builder hiện hành:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationMetricsConfiguration {

    public ObservationRegistry createRegistry(MeterRegistry meterRegistry) {
        ObservationRegistry observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig()
                .observationHandler(
                        DefaultMeterObservationHandler.builder(meterRegistry).build()
                );

        return observationRegistry;
    }
}
~~~

Trong Spring Boot, các handler có thể đã được cấu hình tự động khi Actuator và MeterRegistry phù hợp hiện diện. Trước khi tự đăng ký thêm, kiểm tra ObservationRegistry đang được dùng có handler nào rồi để tránh tạo meter trùng hoặc xử lý cùng event hai lần.

Metrics backend chỉ nhận meter do handler tạo và registry xuất. Tracing backend có thể nhận span và event qua tracing handler riêng. Một Observation có thể tạo nhiều tín hiệu, nhưng từng tín hiệu cần handler tương ứng.

## 12. Ví dụ đầy đủ: event, error và metric

Ví dụ sau tạo Observation thanh toán, phát event retry, ghi nhận lỗi nếu gateway thất bại và kết thúc Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class CheckoutService {

    private final ObservationRegistry registry;
    private final PaymentGateway gateway;

    public CheckoutService(
            ObservationRegistry registry,
            PaymentGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public AuthorizationResult authorize(Payment payment) {
        Observation observation = Observation.createNotStarted(
                "checkout.authorize", registry
        )
        .lowCardinalityKeyValue("payment.method", payment.method())
        .lowCardinalityKeyValue("payment.provider", "primary")
        .highCardinalityKeyValue("order.id", payment.orderId());

        observation.start();

        try (Observation.Scope scope = observation.openScope()) {
            observation.event(
                    Observation.Event.of("authorization.retry")
            );

            return gateway.authorize(payment);
        }
        catch (RuntimeException exception) {
            observation.error(exception);
            throw exception;
        }
        finally {
            observation.stop();
        }
    }
}
~~~

Nếu gateway thành công, Timer được ghi với error=none. Nếu gateway ném exception, Timer được ghi với tag error chứa tên lớp exception. Event retry làm tăng Counter event tương ứng khi handler hỗ trợ mapping này.

Ví dụ này phát event retry để minh họa. Trong code thực tế, chỉ phát event khi thực sự có lần retry; không phát event retry cho mọi request. Nếu có nhiều attempt, có thể phát cùng tên event nhiều lần để Counter phản ánh tổng số lần retry.

## 13. ObservationFilter bổ sung hoặc chuẩn hóa dữ liệu trước stop

ObservationFilter nhận context và trả về context đã được chỉnh sửa. Filter chạy trước khi handler nhận onStop(). Dùng nó khi cần bổ sung metadata chung hoặc chuẩn hóa dữ liệu cho Timer cuối cùng.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

public class EnvironmentObservationFilter implements ObservationFilter {

    @Override
    public Observation.Context map(Observation.Context context) {
        return context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.environment", "production")
        );
    }
}
~~~

Đăng ký filter:

~~~java
observationRegistry.observationConfig()
        .observationFilter(new EnvironmentObservationFilter());
~~~

Filter có thể áp dụng cho nhiều Observation trong registry. Hãy giữ giá trị thêm vào low-cardinality ở mức hữu hạn. Nếu filter truy vấn cloud metadata hoặc cấu hình ngoài, tránh thực hiện I/O chậm trên mỗi lần stop; nên lấy snapshot cấu hình trước và dùng giá trị đã có.

Filter chạy ở stop, nên tag do filter thêm không xuất hiện trên event Counter đã được tạo trước đó. Nó cũng không xuất hiện trên LongTaskTimer nếu LongTaskTimer được tạo ở start.

## 14. ObservationConvention chuẩn hóa tên và key-value

ObservationConvention tách quy tắc đặt tên và metadata khỏi code thực thi. Instrumentation tạo Observation với context phù hợp; convention quyết định tên, contextual name và low/high-cardinality key-value.

Ví dụ context riêng cho thao tác tính thuế:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

class TaxContext extends Observation.Context {
    private final String taxType;
    private final String customerId;

    TaxContext(String taxType, String customerId) {
        this.taxType = taxType;
        this.customerId = customerId;
    }

    String taxType() {
        return taxType;
    }

    String customerId() {
        return customerId;
    }
}

class TaxObservationConvention
        implements ObservationConvention<TaxContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof TaxContext;
    }

    @Override
    public String getName() {
        return "tax.calculate";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(TaxContext context) {
        return KeyValues.of(
                KeyValue.of("tax.type", context.taxType())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(TaxContext context) {
        return KeyValues.of(
                KeyValue.of("customer.id", context.customerId())
        );
    }
}
~~~

Trong ví dụ, loại thuế có tập giá trị hữu hạn nên là low cardinality. Customer ID là định danh riêng nên là high cardinality. Default meter handler chỉ dùng phần low-cardinality cho metric tags.

Nếu instrumentation cho phép truyền convention riêng, convention do caller truyền có ưu tiên cao hơn global convention phù hợp; nếu không có convention riêng, global convention phù hợp được chọn; cuối cùng mới dùng default convention. Nếu cần thêm metadata bất kể convention nào được chọn, dùng ObservationFilter.

## 15. ObservationPredicate quyết định có tạo Observation hay không

ObservationPredicate được gọi khi tạo Observation và quyết định Observation có được thực thi hay trở thành no-op. Nó phù hợp để bỏ qua những Observation không cần thiết theo điều kiện đã biết trước.

~~~java
observationRegistry.observationConfig()
        .observationPredicate((name, context) ->
                !"internal.noise".equals(name)
        );
~~~

Nếu predicate trả false, Observation được tạo thành no-op và các handler không ghi nhận lifecycle như một Observation bình thường. Predicate không phải nơi để bổ sung tag hoặc thay đổi context; dùng convention hoặc filter cho việc đó.

Không dùng predicate để loại bỏ mọi lỗi hoặc mọi request chậm. Làm vậy có thể che khuất tín hiệu cần điều tra. Nếu muốn bỏ qua một loại hoạt động, cần có lý do rõ ràng và kiểm tra ảnh hưởng đến cả metrics lẫn tracing.

## 16. Viết handler tùy chỉnh cho event và error

Khi cần xử lý riêng một loại event/error, có thể viết ObservationHandler. Handler chỉ nhận context mà nó hỗ trợ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public class PaymentAuditHandler
        implements ObservationHandler<PaymentContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentContext;
    }

    @Override
    public void onError(PaymentContext context) {
        auditLogger.recordFailure(
                context.getError(),
                context.taxType()
        );
    }

    @Override
    public void onEvent(
            Observation.Event event,
            PaymentContext context) {
        auditLogger.recordEvent(event, context.taxType());
    }
}
~~~

Đăng ký handler với registry:

~~~java
observationRegistry.observationConfig()
        .observationHandler(new PaymentAuditHandler());
~~~

Đây là ví dụ minh họa; PaymentContext và auditLogger là các thành phần của ứng dụng. Handler tùy chỉnh không nên làm công việc mạng đồng bộ kéo dài trong callback vòng đời Observation. Nếu cần gửi log/audit ra ngoài, cân nhắc queue hoặc cơ chế ghi nhận không chặn phù hợp.

Nếu handler ghi metrics thủ công, phải giữ tên meter và tag hữu hạn. Tránh tạo Counter mới theo từng exception class/message hoặc event name động. Có thể dùng DefaultMeterObservationHandler cho Timer và event counter tiêu chuẩn, rồi thêm custom handler cho nghiệp vụ riêng.

## 17. Kiểm thử mapping event/error thành metrics

Dùng SimpleMeterRegistry để kiểm tra meter được tạo từ Observation. Ví dụ sau dùng API builder của Micrometer 1.18:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationMetricsTest {

    @Test
    void mapsEventAndErrorToMeters() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build()
        );

        Observation observation = Observation.createNotStarted(
                "checkout.authorize", observations
        )
        .lowCardinalityKeyValue("payment.method", "card")
        .highCardinalityKeyValue("order.id", "ORD-123");

        observation.start();
        observation.event(Observation.Event.of("authorization.retry"));
        observation.error(new IllegalStateException("gateway failed"));
        observation.stop();

        assertThat(meters.get("checkout.authorize")
                .tag("payment.method", "card")
                .tag("error", IllegalStateException.class.getName())
                .timer()
                .count()).isEqualTo(1);

        assertThat(meters.get("checkout.authorize.authorization.retry")
                .tag("payment.method", "card")
                .counter()
                .count()).isEqualTo(1);
    }
}
~~~

Bài test xác nhận:

- Timer được ghi khi Observation stop.
- Error tag chứa tên exception class.
- Event tạo Counter với tên theo Observation và event.
- Low-cardinality tag có mặt trên meter.
- High-cardinality order.id không trở thành meter tag.

Nếu kiểm tra LongTaskTimer, test cần khác theo version: ở Micrometer 1.15–1.17 tài liệu mô tả meter active được tạo mặc định; ở 1.18 phải bật includeActiveObservationLongTaskTimer(true) mới mong đợi meter đó. Không viết một assertion chung cho tất cả version.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Observation có nhưng không thấy Timer | Không có meter handler hoặc Observation chưa stop | Kiểm tra registry/handler và lifecycle |
| Có Timer nhưng thiếu tag error | Không gọi observation.error(exception) trước stop | Ghi nhận lỗi ở catch hoặc dùng observe() |
| Có error tag nhưng không có error Counter | Default handler biểu diễn error trên Timer; không tạo error Counter riêng | Dùng event hoặc Counter nghiệp vụ nếu cần |
| Phát event nhưng không có Counter | Handler/version/registry không hỗ trợ mapping event hoặc event không được phát | Kiểm tra DefaultMeterObservationHandler và version |
| Event Counter thiếu một tag | Key-value được thêm sau lúc event xảy ra | Thêm low-cardinality key-value trước event |
| LongTaskTimer thiếu tag | Key-value được thêm sau start | Thêm tag trước start và kiểm tra version |
| High-cardinality key không thấy trong metrics | Handler loại high-cardinality khỏi meter tags theo thiết kế | Tìm metadata đó trong trace/log nếu handler hỗ trợ |
| Meter tăng bất thường | Event phát nhiều lần, handler đăng ký trùng hoặc tên event động | Kiểm tra số lần phát event và cấu hình registry |
| Observation bị bỏ qua | ObservationPredicate trả false | Kiểm tra điều kiện predicate |

## 19. Quy trình kiểm tra theo phiên bản dự án

Khi nâng cấp Micrometer hoặc Spring Boot, kiểm tra lần lượt:

1. Xác định phiên bản Micrometer thực tế được resolve trong dependency tree.
2. Kiểm tra API DefaultMeterObservationHandler có constructor hay builder ở phiên bản đó.
3. Kiểm tra mapping Timer, event Counter và LongTaskTimer trong tài liệu/Javadoc của đúng version.
4. Xác nhận LongTaskTimer là mặc định hay opt-in.
5. Kiểm tra ObservationHandler và custom handler có được đăng ký đúng ObservationRegistry không.
6. Kiểm tra ObservationFilter chạy trước onStop và các tag được thêm đúng thời điểm.
7. Chạy test với SimpleMeterRegistry để xác nhận tên meter, tag và số lần ghi.
8. Kiểm tra endpoint export thực tế vì registry có thể chuẩn hóa tên meter theo backend.

Không lấy một ví dụ code từ nhánh tài liệu mới rồi dùng nguyên trạng trong dự án có dependency cũ. Hãy kiểm tra version, compile và test mapping thay vì giả định các API builder/constructor giống nhau.

## 20. Checklist vận hành

Trước khi dùng event và error để tạo metrics, xác nhận:

- Observation có handler tương ứng được đăng ký.
- Mọi Observation được stop đúng một lần.
- Lỗi được đánh dấu bằng error() trước khi stop.
- Exception vẫn được xử lý theo contract nghiệp vụ.
- Event name ổn định và có tập giá trị hữu hạn.
- Event được phát đúng lúc và không bị phát lặp ngoài ý muốn.
- Low-cardinality key-value được thêm trước thời điểm meter cần đọc.
- High-cardinality key-value không bị đưa vào metric tags.
- Đã xác định DefaultMeterObservationHandler mapping theo version.
- Đã xác định LongTaskTimer mặc định hay opt-in.
- Không đăng ký handler trùng với auto-configuration của Spring Boot.
- Test xác nhận Timer, event Counter, error tag và tag cardinality.
- Đã kiểm tra meter name và tag trên endpoint export thực tế.

Observation cung cấp một vòng đời thống nhất để các handler phản ứng với event, error và stop. DefaultMeterObservationHandler biến thời lượng thành Timer, event thành Counter và có thể theo dõi Observation đang chạy bằng LongTaskTimer tùy phiên bản/cấu hình. Hiểu thời điểm từng meter lấy key-value, phân biệt low/high cardinality và kiểm tra API của đúng phiên bản sẽ giúp metrics phản ánh đúng hoạt động mà không tạo thêm time series không cần thiết.

## Tài liệu tham khảo

- [Micrometer 1.18 - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer 1.17 - Observation Components](https://docs.micrometer.io/micrometer/reference/1.17/observation/components.html)
- [Micrometer 1.16 - Observation Components](https://docs.micrometer.io/micrometer/reference/1.16/observation/components.html)
- [Micrometer 1.15 - Observation Components](https://docs.micrometer.io/micrometer/reference/1.15/observation/components.html)
- [Micrometer 1.14 - Observation Components](https://docs.micrometer.io/micrometer/reference/1.14/observation/components.html)
- [Micrometer 1.13 - Observation Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html)
- [Micrometer - High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
