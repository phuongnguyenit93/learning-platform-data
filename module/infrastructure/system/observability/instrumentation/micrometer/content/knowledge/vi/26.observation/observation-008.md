# Ghi nhận ngoại lệ bằng error và tín hiệu tùy ý bằng event

Micrometer Observation không chỉ đo thời gian bắt đầu và kết thúc của một operation. Trong lúc operation đang chạy, mã ứng dụng có thể báo cho Observation biết một ngoại lệ đã xảy ra bằng error hoặc một sự kiện có ý nghĩa đã xảy ra bằng event. Các tín hiệu này được chuyển đến ObservationHandler đã đăng ký trên ObservationRegistry; handler quyết định cách tạo metric, span event, log hoặc hành động quan sát khác.

Hai API phục vụ hai ý nghĩa khác nhau. error(Throwable) ghi nhận trạng thái lỗi của operation và cho handler truy cập ngoại lệ. event(Event) đánh dấu một điểm xảy ra trong vòng đời operation, chẳng hạn payment.authorized hoặc cache.miss. Một event không tự động có nghĩa operation thất bại; một operation có thể phát nhiều event rồi hoàn tất thành công hoặc thất bại.

## Vòng đời Observation và vị trí của error/event

Một Observation thường đi qua các bước:

1. Tạo Observation với tên, registry và metadata.
2. Gọi start để bắt đầu operation được quan sát.
3. Mở scope nếu cần đặt Observation hiện tại vào execution context.
4. Phát event khi có tín hiệu nghiệp vụ hoặc kỹ thuật cần ghi nhận.
5. Gọi error(exception) khi operation gặp lỗi cần được báo cáo.
6. Gọi stop khi operation kết thúc.

ObservationHandler nhận các callback tương ứng với vòng đời này:

| API | Callback handler | Ý nghĩa |
|---|---|---|
| observation.start() | onStart(context) | Operation bắt đầu |
| observation.event(event) | onEvent(event, context) | Một sự kiện xảy ra trong operation |
| observation.error(exception) | onError(context) | Operation gặp lỗi |
| observation.stop() | onStop(context) | Operation kết thúc |

~~~mermaid
sequenceDiagram
    participant App as Mã nghiệp vụ
    participant Obs as Observation
    participant Handler as ObservationHandler
    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    App->>Obs: event(payment.authorized)
    Obs->>Handler: onEvent(event, context)
    App->>Obs: error(exception) nếu có
    Obs->>Handler: onError(context)
    App->>Obs: stop()
    Obs->>Handler: onStop(context)
~~~

Không phải operation nào cũng phát event hoặc error. Với operation thành công bình thường, chuỗi tối thiểu thường là start rồi stop. Nếu có lỗi, gọi error trước stop để handler nhìn thấy lỗi khi hoàn tất Observation.

## Báo lỗi bằng Observation.error(...)

Khi một ngoại lệ đại diện cho lỗi của operation, gọi observation.error(exception). API này gắn ngoại lệ vào Observation.Context và thông báo cho các handler phù hợp. Nó không tự ném lại ngoại lệ, không thay thế xử lý lỗi nghiệp vụ và cũng không tự kết thúc Observation.

Ví dụ với thao tác gọi cổng thanh toán:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentService(
            ObservationRegistry observationRegistry,
            PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentCommand command) {
        Observation observation = Observation.createNotStarted(
                        "payment.authorize", observationRegistry)
                .lowCardinalityKeyValue(
                        "provider", normalizeProvider(command.provider()));

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            return gateway.authorize(command);
        } catch (RuntimeException | Error exception) {
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private String normalizeProvider(String provider) {
        return switch (provider) {
            case "bank-a", "bank-b", "wallet" -> provider;
            default -> "other";
        };
    }
}
~~~

Đoạn code giữ nguyên hành vi lỗi của gateway: sau khi báo error cho Observation, nó ném lại ngoại lệ để tầng gọi xử lý. Khối finally bảo đảm Observation được stop cả khi thành công lẫn khi thất bại. Scope được đóng tự động khi rời try-with-resources, trước khi finally gọi stop.

Tag provider có tập giá trị hữu hạn. Không đưa payment ID, customer ID, exception message hoặc request ID vào low-cardinality key value. Nếu cần định danh một request trong trace, chỉ cân nhắc high-cardinality key value khi chính sách dữ liệu và tracing backend cho phép; high-cardinality key value không được dùng làm metric tag bởi DefaultMeterObservationHandler.

## Dùng observe(...) để quản lý vòng đời tự động

Với operation đồng bộ, Observation.observe(...) thường gọn và ít lỗi hơn việc tự gọi start, openScope, error, đóng scope và stop. Phương thức này thực hiện vòng đời Observation, đặt scope trong lúc chạy lambda, ghi nhận ngoại lệ nếu lambda ném lỗi, rồi đóng scope và stop trước khi trả kết quả hoặc ném lại lỗi.

~~~java
public PaymentResult authorize(PaymentCommand command) {
    Observation observation = Observation.createNotStarted(
                    "payment.authorize", observationRegistry)
            .lowCardinalityKeyValue(
                    "provider", normalizeProvider(command.provider()));

    return observation.observe(() -> gateway.authorize(command));
}
~~~

Nếu cần phát event ở giữa operation, giữ biến observation để gọi event trong lambda:

~~~java
public PaymentResult authorize(PaymentCommand command) {
    Observation observation = Observation.createNotStarted(
                    "payment.authorize", observationRegistry)
            .lowCardinalityKeyValue(
                    "provider", normalizeProvider(command.provider()));

    return observation.observe(() -> {
        PaymentResult result = gateway.authorize(command);
        if (result.approved()) {
            observation.event(Observation.Event.of(
                    "payment.authorized",
                    "Payment provider accepted authorization"));
        } else {
            observation.event(Observation.Event.of(
                    "payment.declined",
                    "Payment provider declined authorization"));
        }
        return result;
    });
}
~~~

Trong ví dụ, decline là một kết quả nghiệp vụ được biểu diễn bằng event. Nó không nhất thiết là exception. Nếu quy tắc nghiệp vụ xem decline là lỗi của operation, có thể chọn cách xử lý khác, nhưng cần thống nhất định nghĩa giữa code, metric và dashboard. Không đánh dấu mọi kết quả từ chối hợp lệ thành exception chỉ để tạo tín hiệu lỗi.

observe(...) xử lý ngoại lệ mà lambda thực sự ném ra. Nếu code bắt một exception rồi chuyển thành kết quả fallback bên trong lambda, Observation không tự biết rằng exception đã từng xuất hiện. Nếu cần giữ tín hiệu đó, gọi observation.error(exception) tại điểm catch trước khi chuyển đổi kết quả.

## Phát event bằng Observation.event(...)

Event biểu diễn một tín hiệu xảy ra tại một thời điểm trong vòng đời Observation. Ví dụ:

~~~java
observation.event(Observation.Event.of("payment.authorized"));
~~~

Có thể cung cấp thêm phần mô tả cho event:

~~~java
observation.event(Observation.Event.of(
        "payment.authorized",
        "Authorization accepted by payment provider"));
~~~

Tên event nên ổn định và có cardinality thấp. Các tên như payment.authorized, payment.declined, retry.scheduled hoặc cache.miss phù hợp hơn tên được ghép từ payment ID, exception message hoặc dữ liệu đầu vào. Phần mô tả cũng không nên chứa token, thông tin cá nhân hoặc nội dung bí mật.

Một Observation có thể phát nhiều event:

~~~java
observation.event(Observation.Event.of("payment.requested"));
observation.event(Observation.Event.of("payment.authorized"));
observation.event(Observation.Event.of("receipt.created"));
~~~

Các event mô tả những mốc đã xảy ra bên trong cùng operation. Chúng không thay thế log kiểm toán hoặc event bus của nghiệp vụ: Observation event phục vụ telemetry và phụ thuộc handler, pipeline cùng chính sách lưu trữ đang cấu hình.

## error và event khác nhau ở đâu?

| Khía cạnh | error(exception) | event(event) |
|---|---|---|
| Mục đích | Báo operation gặp lỗi | Báo một tín hiệu hoặc mốc xảy ra |
| Dữ liệu đầu vào | Throwable | Observation.Event |
| Callback | onError(context) | onEvent(event, context) |
| Tác động đến trạng thái lỗi | Gắn lỗi vào context | Không tự đánh dấu operation thất bại |
| Ví dụ | Timeout, database unavailable, unexpected exception | payment.authorized, retry.scheduled, cache.miss |
| Thời điểm | Khi phát hiện lỗi | Ngay tại mốc cần ghi nhận |

Một operation có thể vừa phát event vừa gặp lỗi. Ví dụ, payment.requested và payment.gateway.called xảy ra trước khi gateway timeout. Các event vẫn mô tả tiến trình đã diễn ra; error báo kết quả cuối cùng thất bại. Khi đó Observation được stop với context có lỗi.

Không dùng event thay cho error chỉ vì muốn tránh gắn trạng thái lỗi. Ngược lại, không gọi error cho mọi event nghiệp vụ như payment.declined nếu đó là kết quả hợp lệ theo hợp đồng nghiệp vụ.

## DefaultMeterObservationHandler biến error và event thành metric

Micrometer cung cấp DefaultMeterObservationHandler để chuyển Observation lifecycle thành meter. Khi handler này được đăng ký trên ObservationRegistry, nó tạo các metric sau:

| Tín hiệu | Meter được tạo | Thời điểm |
|---|---|---|
| Observation hoàn tất | Timer có tên bằng observation name | Khi stop |
| Observation có error | Timer vẫn được ghi nhận, thêm tag error mang tên class của exception | Khi stop |
| Observation phát event | Counter có tên theo dạng observation-name.event-name | Mỗi lần event xảy ra |
| Observation đang chạy | LongTaskTimer có hậu tố .active nếu cấu hình opt-in | Khi start và stop |

Timer mặc định nhận các low-cardinality key value của Observation và tag error. Nếu không có lỗi, giá trị error thường là none. Event counter nhận các low-cardinality key value đã có tại thời điểm event được phát. High-cardinality key value không được đưa vào metric tag để tránh cardinality tăng không kiểm soát.

Ví dụ Observation tên payment.authorize phát event payment.authorized có thể tạo counter:

~~~text
payment.authorize.payment.authorized
~~~

Nếu Observation tên payment.authorize kết thúc với IllegalStateException, Timer payment.authorize có thể có tag:

~~~text
error="java.lang.IllegalStateException"
~~~

Tên metric cuối cùng có thể được registry chuẩn hóa theo backend. Với Prometheus, dấu chấm có thể trở thành dấu gạch dưới. Hãy kiểm tra endpoint exposition trước khi viết truy vấn.

Event counter chỉ xuất hiện nếu ObservationRegistry có handler chuyển event thành meter, chẳng hạn DefaultMeterObservationHandler. Gọi event(...) trên một registry không có handler phù hợp không tự tạo một Counter trong MeterRegistry.

## Cấu hình handler trong ứng dụng độc lập

Với ứng dụng không dùng Spring Boot, có thể đăng ký DefaultMeterObservationHandler trực tiếp:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationConfiguration {
    public static ObservationRegistry createRegistry(MeterRegistry meterRegistry) {
        ObservationRegistry observationRegistry = ObservationRegistry.create();
        observationRegistry.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meterRegistry).build());
        return observationRegistry;
    }
}
~~~

Khi handler được đăng ký, Observation do registry này quản lý có thể tạo Timer và event Counter trong MeterRegistry được truyền vào. Nếu cần tracing, đăng ký tracing handler phù hợp cùng registry; không phải event nào cũng cần tạo metric riêng.

## Cấu hình handler tùy chỉnh trong Spring Boot

Spring Boot dùng Micrometer Observation cho metrics và tracing. Khi có Actuator cùng registry/tracing implementation phù hợp, Boot cấu hình các handler tiêu chuẩn cho ObservationRegistry. Các bean kiểu ObservationHandler trong ApplicationContext được tự động đăng ký lên registry do Boot quản lý.

Có thể thêm handler riêng bằng bean hoặc component:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.springframework.stereotype.Component;

@Component
public class ObservationSignalHandler
        implements ObservationHandler<Observation.Context> {

    private static final System.Logger LOG =
            System.getLogger(ObservationSignalHandler.class.getName());

    @Override
    public void onError(Observation.Context context) {
        Throwable error = context.getError();
        if (error != null) {
            LOG.log(System.Logger.Level.WARNING,
                    "Observation failed with {0}",
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onEvent(
            Observation.Event event,
            Observation.Context context) {
        LOG.log(System.Logger.Level.DEBUG,
                "Observation event: {0}", event);
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
~~~

Handler này minh họa cách nhận tín hiệu để ghi log. Nó không thay thế DefaultMeterObservationHandler. Nếu đăng ký handler toàn cục như ví dụ, nó có thể nhận error và event từ nhiều loại Observation trong ứng dụng. Trong hệ thống lớn, hãy giới hạn handler theo context type hoặc cấu trúc registry nếu chỉ muốn xử lý một nhóm operation.

Không ghi toàn bộ exception message hoặc object nghiệp vụ vào log một cách mặc định. Message có thể chứa SQL, URL, token hoặc dữ liệu người dùng. Dùng exception class và mã lỗi đã chuẩn hóa để log an toàn; chi tiết cần thiết nên được xử lý theo chính sách bảo mật và redaction.

## Thứ tự thêm key value và thời điểm phát event

Event counter dùng các low-cardinality key value có sẵn tại thời điểm event xảy ra. Vì vậy, hãy thêm các chiều phân loại cần thiết trước khi phát event:

~~~java
Observation observation = Observation.createNotStarted(
                "payment.authorize", observationRegistry)
        .lowCardinalityKeyValue("provider", "bank-a")
        .lowCardinalityKeyValue("payment.method", "card");

observation.start();
observation.event(Observation.Event.of("payment.authorized"));
observation.stop();
~~~

Nếu một low-cardinality key value chỉ được thêm sau event, counter được tạo từ event trước đó không thể tự nhận lại tag đã thiếu. Timer được tạo khi stop có thể thấy các low-cardinality key value đã bổ sung trước thời điểm stop. Để metric nhất quán, xác định metadata trước start hoặc ít nhất trước event cần dùng nó.

High-cardinality key value như payment.id có thể hữu ích trong trace nhưng không nên được dùng làm metric dimension. Với metric, chọn các chiều hữu hạn như provider, payment.method, region hoặc outcome.

## Event không phải là một Counter API thay thế

Nếu cần đếm một mốc xảy ra trong Observation, event có thể tạo Counter thông qua DefaultMeterObservationHandler. Nếu cần một Counter độc lập không gắn với Observation lifecycle, dùng Counter API trực tiếp. Hai cách có mục đích khác nhau:

| Nhu cầu | Cách phù hợp |
|---|---|
| Đếm payment.authorized xảy ra bên trong payment.authorize Observation | observation.event(...) với meter handler |
| Đếm tổng số file được import ở một nơi không có Observation | Counter.increment() |
| Ghi nhận thời điểm retry scheduled bên trong workflow | observation.event(...) |
| Đo riêng thời lượng mỗi retry attempt | Timer hoặc Observation riêng cho từng attempt |
| Đếm kết quả nghiệp vụ sau khi transaction commit | Counter tại điểm commit hoặc event nghiệp vụ phù hợp |

Không vừa phát event vừa increment một Counter có cùng tên và cùng ý nghĩa cho cùng một lần xảy ra, nếu dashboard sau đó coi chúng là hai nguồn độc lập. Chọn một nguồn sở hữu cho mỗi chỉ số.

## Kiểm thử error và event bằng SimpleMeterRegistry

Có thể kiểm tra hành vi của DefaultMeterObservationHandler mà không cần backend bên ngoài:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationSignalTest {
    @Test
    void eventCreatesCounterAndErrorIsAttachedToTimer() {
        MeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build());

        Observation successful = Observation.createNotStarted(
                        "payment.authorize", observations)
                .lowCardinalityKeyValue("provider", "bank-a");
        successful.start();
        successful.event(Observation.Event.of(
                "payment.authorized", "Authorization accepted"));
        successful.stop();

        Observation failed = Observation.createNotStarted(
                        "payment.capture", observations)
                .lowCardinalityKeyValue("provider", "bank-a");
        failed.start();
        failed.error(new IllegalStateException("capture failed"));
        failed.stop();

        Counter eventCounter = meters.get(
                        "payment.authorize.payment.authorized")
                .tag("provider", "bank-a")
                .counter();
        assertThat(eventCounter.count()).isEqualTo(1.0);

        Timer failedTimer = meters.get("payment.capture")
                .tag("provider", "bank-a")
                .tag("error", IllegalStateException.class.getName())
                .timer();
        assertThat(failedTimer.count()).isEqualTo(1);

        Timer successfulTimer = meters.get("payment.authorize")
                .tag("provider", "bank-a")
                .tag("error", "none")
                .timer();
        assertThat(successfulTimer.count()).isEqualTo(1);

        meters.close();
    }
}
~~~

Test kiểm tra ba kết quả riêng: event tạo Counter; Observation thất bại tạo Timer có tag error; Observation thành công tạo Timer có error=none. Tên metric trong SimpleMeterRegistry giữ theo quy tắc Micrometer; registry xuất Prometheus có thể chuẩn hóa tên khi exposition.

Nếu muốn kiểm tra custom handler, tạo một handler test ghi lại số lần onError và onEvent vào AtomicInteger hoặc danh sách thread-safe, đăng ký handler vào ObservationRegistry rồi xác nhận callback được gọi. Không cần kiểm tra log console để xác nhận lifecycle.

## Phân biệt lỗi thực tế với kết quả nghiệp vụ

Không phải mọi kết quả không như mong đợi đều là exception. Ví dụ:

- Thanh toán bị từ chối theo quy tắc ngân hàng có thể là kết quả nghiệp vụ hợp lệ: phát event payment.declined.
- Gateway không phản hồi đúng timeout có thể là lỗi kỹ thuật: gọi error(timeoutException).
- Người dùng gửi dữ liệu không hợp lệ có thể được biểu diễn bằng kết quả validation rejected hoặc error tùy hợp đồng API và cách phân loại lỗi của hệ thống.
- Retry được lên lịch là event retry.scheduled; nếu retry cuối cùng thất bại, operation có thể kết thúc với error.

Định nghĩa rõ semantics giúp error rate không bị phóng đại bởi các kết quả nghiệp vụ bình thường. Dashboard cần phân biệt số lần bị từ chối hợp lệ với số lỗi kỹ thuật, thay vì gom tất cả vào một tag error.

## Cardinality và bảo vệ dữ liệu

Event name và low-cardinality key value được dùng để tạo metric dimension. Nếu ghép ID hoặc chuỗi tùy ý vào tên event, mỗi giá trị có thể tạo một Counter mới:

~~~java
// Không nên: mỗi payment ID có thể tạo một event name khác nhau.
observation.event(Observation.Event.of(
        "payment." + command.paymentId()));
~~~

Hãy dùng tên event cố định:

~~~java
observation.event(Observation.Event.of("payment.authorized"));
~~~

Đưa định danh cần điều tra vào trace hoặc log theo chính sách dữ liệu. High-cardinality key value chỉ nên dùng khi backend tracing và chính sách retention cho phép. Không đưa password, access token, card number, email hoặc nội dung request vào Observation metadata.

Số lượng event cũng cần có ý nghĩa. Không phát một event cho mỗi bước lặp nội bộ có tần suất rất cao nếu không có nhu cầu quan sát rõ ràng; metric counter và trace event đều có chi phí lưu trữ, truyền tải và truy vấn.

## Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy Timer có tag error | Không gọi error(exception), handler không được đăng ký hoặc Observation không được stop | Kiểm tra error call, registry handler và stop |
| Gọi error nhưng exception không được trả về caller | error(...) chỉ báo tín hiệu cho handler, không ném lại exception | Ném lại hoặc xử lý exception theo hợp đồng nghiệp vụ |
| Event không tạo Counter | Không có DefaultMeterObservationHandler hoặc handler không hỗ trợ context | Kiểm tra ObservationRegistry và handler |
| Counter event thiếu tag | Low-cardinality key value được thêm sau khi event xảy ra | Thêm metadata trước event |
| Mọi decline đều làm error rate tăng | Kết quả nghiệp vụ hợp lệ bị báo như exception | Dùng event riêng nếu decline không phải lỗi kỹ thuật |
| Cardinality tăng nhanh | Event name hoặc tag chứa ID, URL, exception message | Dùng event name và tag có tập giá trị hữu hạn |
| Handler không được gọi trong Spring Boot | Bean không nằm trong ApplicationContext hoặc registry tùy chỉnh không phải registry Boot quản lý | Kiểm tra bean discovery và registry thực tế |
| Handler log quá nhiều dữ liệu | Ghi toàn bộ exception hoặc event context | Giới hạn nội dung, dùng log level và redaction phù hợp |
| Timer không được tạo | Observation chưa stop hoặc không có meter handler phù hợp | Xác nhận lifecycle và DefaultMeterObservationHandler |

## Checklist triển khai

- [ ] Xác định ngoại lệ nào thực sự đại diện cho lỗi của operation.
- [ ] Gọi error(exception) trước stop khi operation gặp lỗi cần báo cáo.
- [ ] Vẫn xử lý hoặc ném lại exception theo hợp đồng nghiệp vụ; không dựa vào error(...) để thay thế xử lý lỗi.
- [ ] Gọi stop trong mọi đường kết thúc, kể cả khi có exception.
- [ ] Dùng event cho mốc xảy ra, không dùng event để giả lập trạng thái lỗi.
- [ ] Event name ổn định và có cardinality thấp.
- [ ] Thêm low-cardinality key value trước khi phát event.
- [ ] Không đưa ID, token, PII hoặc exception message vào metric tag.
- [ ] Xác nhận DefaultMeterObservationHandler hoặc handler tùy chỉnh đã được đăng ký.
- [ ] Kiểm tra Timer error tag và Counter event trong registry thử nghiệm.
- [ ] Không phát cùng một event rồi tăng thêm Counter thủ công cho cùng chỉ số.
- [ ] Kiểm thử cả operation thành công, lỗi và event được phát giữa operation.

## Tài liệu tham khảo

- [Micrometer Observation - Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation - Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

error và event bổ sung thông tin cho vòng đời Observation. error ghi nhận ngoại lệ để handler xử lý trạng thái thất bại; event đánh dấu một tín hiệu xảy ra trong operation. Khi DefaultMeterObservationHandler được cấu hình, stop tạo Timer có tag error và mỗi event có thể tạo Counter riêng. Giữ tên event và low-cardinality key value ổn định, đồng thời xử lý ngoại lệ và kết thúc Observation đúng cách, giúp metric và trace phản ánh chính xác điều đã xảy ra.
